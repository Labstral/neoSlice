from __future__ import annotations
import os
import time
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QScrollArea,
    QFrame, QApplication, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QPoint, QUrl, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QIcon, QDesktopServices, QPixmap

from loguru import logger

from core.geometry.stl_loader import load_stl, mesh_info, STLLoadError
from core.geometry.analysis_report import AnalysisReport
from core.geometry.overhang_detector import analyze_overhangs, overhang_face_colors
from core.geometry.support_detector import support_face_colors
from core.geometry.layer_slicer import analyze_by_layers
from core.geometry.stability_analyzer import analyze_stability
from core.geometry.fragility_detector import detect_fragility
from core.parameters.parameter_engine import ParameterEngine
from core.export.tmf_builder import ThreeMFBuilder
from core.export.bambu_profile_installer import BambuProfileInstaller

from ui.components.drop_zone import DropZone
from ui.components.intent_selector import IntentSelector, SelectionResult
from ui.components.analysis_panel import AnalysisPanel
from ui.components.viewer_3d import Viewer3D
from ui.components.params_preview import ParamsPreview
from ui.components.filament_printer_selector import FilamentPrinterSelector
from ui.components.welcome_dialog import WelcomeDialog, should_show_welcome, is_update
from ui.components.tutorial_overlay import TutorialOverlay, should_show_tutorial
from ui.components.settings_dialog import SettingsDialog

from ui.styles.theme import (
    BG_VOID, BG_PANEL, BG_SURFACE, BG_ELEVATED, BG_INPUT,
    ACCENT, ACCENT_BRIGHT, TELE_GREEN, AMBER, ERROR_RED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, INACTIVE,
    FONT_MONO, MANAGER as _THEME, apply_title_bar_theme,
    FONT_MAIN,)
from core.i18n import _
from core.prefs import PREFS


# ── Alertes matériau × géométrie ─────────────────────────────────────────

def _compute_material_warnings(
    filament: str,
    printer: str,
    analysis: "AnalysisReport",
) -> list[str]:
    """Génère des alertes contextuelles filament + géométrie."""
    from data.filaments import FILAMENTS, base_materiau
    from data.printers import PRINTERS

    warns: list[str] = []
    fil = FILAMENTS.get(filament, {})
    prt = PRINTERS.get(printer, {})

    if not fil:
        return warns
    # produit de marque : les valeurs viennent de SA fiche (fil), les tests
    # par nom ci-dessous jugent son matériau de BASE (Sunlu Easy PA -> Nylon)
    filament = base_materiau(filament)

    # Enceinte requise mais imprimante ouverte
    if fil.get("enceinte_requise") and not prt.get("enceinte"):
        warns.append(
            f"{filament} nécessite une enceinte fermée — {printer or 'cette imprimante'} est ouverte."
            " Risque de décollement ou warping."
        )

    # TPU/TPE + AMS → incompatible
    if filament in ("TPU", "TPE") and prt.get("ams"):
        warns.append(
            f"{filament} est incompatible avec l'AMS — chargement direct requis."
        )

    # Matériau flexible + pièce fragile → risque impression
    if filament in ("TPU", "TPE") and analysis.has_fragile_zones:
        warns.append(
            f"Parois fines ({analysis.min_wall_thickness_mm:.1f} mm) + {filament} flexible :"
            " la pièce peut être difficile à imprimer — envisager 4+ parois."
        )

    # Haute température + pièce très large → warping fort
    if filament in ("ABS", "ASA", "PC") and analysis.is_large_flat_part:
        warns.append(
            f"{filament} sur grande pièce plate : risque élevé de warping."
            " Brim large (10+ mm) et plateau chauffé recommandés."
        )

    # PC / PA-CF → séchage obligatoire
    if filament in ("PC", "PA-CF", "Nylon"):
        for w in fil.get("warnings", []):
            if "séchage" in w.lower() or "sechage" in w.lower():
                warns.append(w)
                break

    return warns


# ── Worker threads ─────────────────────────────────────────────────────────

class STLLoadWorker(QObject):
    """Charge load_stl() hors du thread principal — évite le freeze UI sur gros fichiers."""
    mesh_loaded = Signal(object)   # trimesh.Trimesh
    error       = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def run(self):
        try:
            from core.geometry.stl_loader import load_stl, STLLoadError
            mesh = load_stl(self._path)
            self.mesh_loaded.emit(mesh)
        except Exception as exc:
            self.error.emit(str(exc))


class AnalysisWorker(QObject):
    progress = Signal(int, str)
    analysis_complete = Signal(object)
    error = Signal(str)

    def __init__(self, mesh, nozzle_diameter_mm: float = 0.4, is_color_assembly: bool = False,
                 force_full: bool = False):
        super().__init__()
        self._mesh = mesh
        self._nozzle_mm = float(nozzle_diameter_mm)
        # Assemblage multicolore imbriqué (badge) : pièce solide qui s'imprime à
        # plat → sur le maillage non-manifold (parts qui se chevauchent) l'analyse
        # voit de faux surplombs/régions flottantes. Neutralisés en fin de run.
        self._is_color_assembly = bool(is_color_assembly)
        # « Forcer l'analyse complète » (bouton du panneau) : ignore la décision
        # Auto/Économique pour CETTE pièce.
        self._force_full = bool(force_full)

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor
            from core.perf import decision as _perf_decision

            t0 = time.perf_counter()
            report = AnalysisReport()
            report.nozzle_diameter_mm = self._nozzle_mm
            self._support_mask = None
            self._ov_result    = None

            # ── Verrou mesh ultra-haute-poly (> 500k faces) ───────────────────
            # analyze_overhangs + analyze_by_layers sont O(faces) et prennent
            # plusieurs minutes sur 5M+ faces. On bascule vers les fallbacks rapides.
            _FACE_LIMIT = 500_000
            _face_count_raw = len(self._mesh.faces)
            # Décision de performance PAR PIÈCE (mode Auto) : quelles analyses
            # tournent pour CE mesh sur CETTE machine (voir core/perf.py).
            _dec = _perf_decision(_face_count_raw, force_full=self._force_full)

            if _face_count_raw > _FACE_LIMIT:
                logger.warning(
                    f"Mesh ultra-haute-poly ({_face_count_raw:,} faces > {_FACE_LIMIT:,}) — "
                    "analyses lourdes remplacées par fallbacks rapides."
                )
                self.progress.emit(15, "Mesh complexe — surplombs rapides…")

                # ── Surplombs rapides : normales de face (numpy, O(n), < 3s) ──
                ov = None
                floating = False
                try:
                    from core.geometry.overhang_detector import OverhangResult as _OR
                    _fn   = self._mesh.face_normals          # calcul cross-product numpy
                    _cz   = _fn[:, 2]                        # composante Z de chaque normale
                    # Exclure les faces de la base (posées sur le plateau) :
                    # on calcule le Z du premier vertex de chaque face (rapide, O(n))
                    _fz   = self._mesh.vertices[self._mesh.faces[:, 0], 2]
                    _zmin = float(self._mesh.vertices[:, 2].min())
                    _zmax = float(self._mesh.vertices[:, 2].max())
                    _base_tol = max(1.0, (_zmax - _zmin) * 0.025)  # 2.5% hauteur ou 1 mm
                    _omsk = (_cz < -0.707) & (_fz > _zmin + _base_tol)
                    _sev  = float(_omsk.mean())
                    _rat  = float(_omsk.mean())
                    if _omsk.any():
                        _sang = np.degrees(np.arcsin(np.clip(-_cz[_omsk], 0.0, 1.0)))
                        _max  = float(_sang.max())
                    else:
                        _max  = 0.0
                    ov = _OR(
                        severity           = _sev,
                        overhang_ratio     = _rat,
                        projected_ratio    = _rat * 0.5,
                        max_angle_deg      = _max,
                        critical_face_mask = _omsk,
                        has_floating_regions = False,
                        display_mask       = _omsk,
                    )
                    logger.info(
                        f"Fast overhangs: {_omsk.sum():,}/{_face_count_raw:,} faces "
                        f"({_rat*100:.1f}%)"
                    )
                except Exception:
                    logger.exception("Fast overhang analysis échouée")

                self.progress.emit(35, "Mesh complexe — stabilité rapide…")
                class _FastResult:
                    stability_score = 0.5; center_of_mass = [0, 0, 0]
                    brim_recommendation_mm = 0.0; min_wall_thickness_mm = 99.0
                    fragility_severity = 0.0; has_fragile_zones = False
                    overhang_severity = 0.0; overhang_ratio = 0.0
                    projected_overhang_ratio = 0.0; support_volume_ratio = 0.0
                    support_needed = False; has_floating_regions = False
                    fallback_used = True
                _fr = _FastResult()
                try:
                    from core.geometry.stability_analyzer import analyze_stability as _as
                    _st = _as(self._mesh)
                    _fr.stability_score        = _st.score
                    _fr.center_of_mass         = _st.center_of_mass.tolist()
                    _fr.brim_recommendation_mm = _st.brim_recommendation_mm
                except Exception:
                    pass
                try:
                    from core.geometry.fragility_detector import detect_fragility as _df
                    _fd = _df(self._mesh, nozzle_diameter_mm=self._nozzle_mm)
                    _fr.has_fragile_zones      = _fd.has_fragile_zones
                    _fr.min_wall_thickness_mm  = _fd.min_thickness_mm
                    _fr.fragility_severity     = _fd.severity
                except Exception:
                    pass
                lr = _fr
            else:
                # ── Tâches d'analyse encapsulées pour exécution parallèle ─────
                # ThreadPoolExecutor : NumPy/SciPy/Trimesh libèrent le GIL →
                # vraie parallélisation CPU sur tous les PC (pas de CUDA requis).

                def _task_overhangs():
                    """Surplombs + régions flottantes — lecture seule du mesh."""
                    try:
                        ov = analyze_overhangs(self._mesh, smooth=False, check_floating=False)
                        floating = False
                        try:
                            from scipy.sparse import csr_matrix
                            from scipy.sparse.csgraph import connected_components as _cc
                            _adj = self._mesh.face_adjacency
                            _n   = len(self._mesh.faces)
                            _r   = np.concatenate([_adj[:, 0], _adj[:, 1]])
                            _c   = np.concatenate([_adj[:, 1], _adj[:, 0]])
                            _g   = csr_matrix((np.ones(len(_r), np.uint8), (_r, _c)), shape=(_n, _n))
                            _n_comp, _lbl = _cc(_g, directed=False)
                            if _n_comp > 1:
                                _z_min_g = float(self._mesh.bounds[0][2])
                                _tol     = max(0.5, float(self._mesh.extents[2]) * 0.02)
                                _ctrs    = self._mesh.triangles_center
                                for _ci in range(_n_comp):
                                    if float(_ctrs[_lbl == _ci, 2].min()) > _z_min_g + _tol:
                                        floating = True
                                        break
                        except Exception:
                            pass
                        return ov, floating
                    except Exception:
                        logger.exception("Analyse surplombs échouée")
                        return None, False

                def _task_stability():
                    """Stabilité + fragilité par couches Shapely — timeout 18s."""
                    import threading as _th
                    _holder = [None]; _ev = _th.Event()
                    def _run_layers():
                        try:
                            _holder[0] = analyze_by_layers(self._mesh, nozzle_diameter_mm=self._nozzle_mm)
                        except Exception:
                            pass
                        finally:
                            _ev.set()
                    _th.Thread(target=_run_layers, daemon=True).start()
                    _ev.wait(timeout=18.0)
                    if _holder[0] is not None:
                        return _holder[0]
                    logger.warning("analyze_by_layers timeout (>18s) — fallback stabilité rapide")
                    try:
                        raise TimeoutError
                    except Exception:
                        logger.exception("Analyse par couches échouée — fallback stabilité")
                        class _Fallback:
                            stability_score = 0.5; center_of_mass = [0, 0, 0]
                            brim_recommendation_mm = 0.0; min_wall_thickness_mm = 99.0
                            fragility_severity = 0.0; has_fragile_zones = False
                            overhang_severity = 0.0; overhang_ratio = 0.0
                            projected_overhang_ratio = 0.0; support_volume_ratio = 0.0
                            support_needed = False; has_floating_regions = False
                            fallback_used = True
                        fb = _Fallback()
                        try:
                            from core.geometry.stability_analyzer import analyze_stability as _as
                            st = _as(self._mesh)
                            fb.stability_score        = st.score
                            fb.center_of_mass         = st.center_of_mass.tolist()
                            fb.brim_recommendation_mm = st.brim_recommendation_mm
                        except Exception:
                            pass
                        try:
                            from core.geometry.fragility_detector import detect_fragility as _df
                            fr = _df(self._mesh, nozzle_diameter_mm=self._nozzle_mm)
                            fb.has_fragile_zones     = fr.has_fragile_zones
                            fb.min_wall_thickness_mm = fr.min_thickness_mm
                            fb.fragility_severity    = fr.severity
                        except Exception:
                            pass
                        return fb

                # ── Dispatch parallèle selon la décision par pièce ────────────
                n_workers = _dec["n_workers"]
                self.progress.emit(12, "Analyses en cours…")

                # Ticker de progression : les tâches (surplombs + stabilité)
                # tournent en parallèle sans jalons intermédiaires. Un thread léger
                # fait avancer la barre régulièrement (12 → 66) pendant l'attente,
                # pour un pourcentage réaliste plutôt qu'un saut 10 → 100.
                import threading as _thp
                import random as _rnd
                _stop_tick = _thp.Event()

                def _tick():
                    # Progression NATURELLE (pas un défilement mécanique) : intervalles
                    # variables, pauses aléatoires (le % se fige un instant), et sauts
                    # de tailles différentes — comme un vrai calcul qui accélère et
                    # ralentit. Plafonné à 66 (la suite = fusion/finalisation).
                    p = 12
                    _labels = ("Analyses en cours…", "Analyse des surplombs…",
                               "Calcul de stabilité…", "Détection de fragilité…",
                               "Analyse par couches…")
                    while not _stop_tick.wait(_rnd.uniform(0.12, 0.55)):
                        r = _rnd.random()
                        if r < 0.22:
                            continue                      # pause : le % se fige
                        elif r < 0.80:
                            step = _rnd.choice((1, 1, 2, 2, 3))   # petit pas courant
                        else:
                            step = _rnd.choice((4, 5, 7))         # saut occasionnel
                        p = min(66, p + step)
                        try:
                            self.progress.emit(p, _rnd.choice(_labels))
                        except Exception:
                            break
                _thp.Thread(target=_tick, daemon=True).start()
                try:
                    with ThreadPoolExecutor(max_workers=n_workers) as pool:
                        fut_ov   = pool.submit(_task_overhangs) if _dec["overhangs"] else None
                        fut_stab = pool.submit(_task_stability)

                        ov, floating = fut_ov.result() if fut_ov else (None, False)
                        lr           = fut_stab.result()
                finally:
                    _stop_tick.set()
                if not _dec["overhangs"]:
                    report.overhangs_skipped_reason = _dec["skip_reason"]

            self.progress.emit(72, "Fusion des résultats…")

            # ── Application résultats surplombs ───────────────────────────────
            if ov is not None:
                logger.info(
                    f"Overhangs OK: display={ov.display_mask.sum() if ov.display_mask is not None else 0} "
                    f"faces, sévérité={ov.severity:.4f}"
                )
                report.overhang_severity        = ov.severity
                report.overhang_ratio           = ov.overhang_ratio
                report.projected_overhang_ratio = ov.projected_ratio
                report.max_overhang_angle       = ov.max_angle_deg
                # Ratio support basé sur display_mask (cohérent avec jauge et couleurs)
                _dm_ratio = (float(ov.display_mask.sum()) / len(ov.display_mask)
                             if ov.display_mask is not None and len(ov.display_mask) > 0
                             else ov.overhang_ratio)
                # Règle voulue : dès qu'il y a des surplombs rouges (même petits), on
                # active les supports. Le slicer gère ensuite la quantité et le placement.
                # On mesure l'AIRE réelle en surplomb (mm2) plutôt qu'un pourcentage
                # relatif : sur une grande pièce plate, un petit surplomb réel doit
                # quand même déclencher les supports. Petit plancher (10 mm2, environ
                # 3x3 mm) pour ignorer 1-2 faces de bruit (micro-artefacts de bord).
                _oh_area_mm2 = 0.0
                try:
                    if (ov.display_mask is not None and ov.display_mask.any()
                            and self._mesh is not None
                            and len(ov.display_mask) == len(self._mesh.area_faces)):
                        _oh_area_mm2 = float(self._mesh.area_faces[ov.display_mask].sum())
                except Exception:
                    _oh_area_mm2 = 0.0
                report.support_needed           = (
                    _oh_area_mm2 > 10.0 or _dm_ratio > 0.002 or ov.has_floating_regions
                )
                report.estimated_support_ratio  = (
                    min(0.60, max(_dm_ratio * 2.0, 0.04)) if report.support_needed else 0.0
                )
                viz_mask = ov.display_mask if ov.display_mask is not None else ov.critical_face_mask
                self._support_mask = viz_mask
                self._ov_result    = ov
            report.has_floating_regions = floating
            if floating:
                report.support_needed = True

            # ── Application résultats stabilité ───────────────────────────────
            report.stability_score        = lr.stability_score
            report.center_of_mass         = lr.center_of_mass
            report.brim_recommendation_mm = lr.brim_recommendation_mm
            report.min_wall_thickness_mm  = lr.min_wall_thickness_mm
            report.fragility_severity     = lr.fragility_severity
            report.has_fragile_zones      = lr.has_fragile_zones
            if lr.overhang_severity > report.overhang_severity:
                report.overhang_severity        = lr.overhang_severity
                report.overhang_ratio           = max(report.overhang_ratio, lr.overhang_ratio)
                report.projected_overhang_ratio = max(report.projected_overhang_ratio, lr.projected_overhang_ratio)
                report.estimated_support_ratio  = max(report.estimated_support_ratio, lr.support_volume_ratio)
            report.support_needed = (
                report.support_needed or lr.support_needed
                or lr.overhang_severity > 0.005 or lr.has_floating_regions
            )
            report.has_floating_regions = report.has_floating_regions or lr.has_floating_regions
            if getattr(lr, "fallback_used", False) and _face_count_raw <= _FACE_LIMIT:
                report.warnings.append(
                    "Analyse par couches indisponible (shapely manquant) — stabilité heuristique"
                )

            # ── Infos géométriques ────────────────────────────────────────────
            self.progress.emit(95, "Finalisation...")
            info = mesh_info(self._mesh)
            report.bounding_box_mm  = info["bounding_box_mm"]
            report.volume_cm3       = info["volume_cm3"]
            report.surface_area_cm2 = info["surface_area_cm2"]
            report.face_count       = info["faces"]

            bb = report.bounding_box_mm
            max_dim = max(bb)
            report.is_large_flat_part = (max_dim > 100 and bb[2] < max_dim * 0.15)

            # Assemblage multicolore imbriqué (badge) : pièce solide qui s'imprime à
            # plat. Le maillage combiné (parts qui se chevauchent) n'est pas manifold
            # → l'analyse y voit de FAUX surplombs internes (dessous des couches,
            # creux gravés remplis) et de fausses régions flottantes.
            if self._is_color_assembly:
                report.has_floating_regions = False
                report.support_needed = False
                report.estimated_support_ratio = 0.0
                # Si la pièce est PLATE (badge/coaster/plaque : hauteur << largeur),
                # il n'y a aucun vrai surplomb → on neutralise les métriques de
                # surplomb (faussées par les faces internes). Un assemblage couleur
                # EN RELIEF (rare) garde sa détection ; les pièces non-couleur aussi.
                _ext = self._mesh.bounds[1] - self._mesh.bounds[0]
                _flat = float(_ext[2]) < 0.25 * max(float(_ext[0]), float(_ext[1]), 1.0)
                if _flat:
                    report.overhang_severity = 0.0
                    report.overhang_ratio = 0.0
                    report.projected_overhang_ratio = 0.0
                    report.max_overhang_angle = 0.0
                    # Le bandeau SURPLOMBS calcule son % depuis les MASQUES de
                    # l'OverhangResult (display_mask), pas depuis les champs ci-dessus.
                    # On vide donc aussi les masques, sinon la jauge afficherait
                    # encore les faces internes (23%).
                    if self._ov_result is not None:
                        try:
                            if getattr(self._ov_result, "display_mask", None) is not None:
                                self._ov_result.display_mask = np.zeros_like(self._ov_result.display_mask)
                            if getattr(self._ov_result, "critical_face_mask", None) is not None:
                                self._ov_result.critical_face_mask = np.zeros_like(self._ov_result.critical_face_mask)
                        except Exception:
                            pass

            # ── Avertissements ────────────────────────────────────────────────
            if not info["is_watertight"]:
                report.warnings.append("Mesh non-fermé — résultats approximatifs")
            if report.stability_score < 0.35:
                report.warnings.append("Pièce instable — brim recommandé")
            if report.has_fragile_zones:
                rec = self._nozzle_mm * 3.0
                report.warnings.append(
                    f"Parois fines (min {report.min_wall_thickness_mm:.1f} mm"
                    f" — recommandé >= {rec:.1f} mm pour buse {self._nozzle_mm:.1f} mm)"
                )
            if report.has_floating_regions:
                report.warnings.append(
                    "Régions flottantes — supports générés automatiquement"
                )
            elif report.support_needed:
                report.warnings.append(
                    "Supports requis — activer dans Bambu Studio : "
                    "onglet Process > Support > Enable support"
                )

            report.analysis_time_ms = (time.perf_counter() - t0) * 1000
            if self._support_mask is not None:
                report.support_face_mask = self._support_mask
            if self._ov_result is not None:
                report.overhang_result = self._ov_result
            self.progress.emit(100, "Analyse terminée")
            self.analysis_complete.emit(report)

        except Exception as exc:
            logger.exception("Erreur pendant l'analyse")
            self.error.emit(str(exc))


# ── TopBar ─────────────────────────────────────────────────────────────────

from ui.components.pro_badge import PRO_CYAN, PRO_VIOLET

# Couleur intermédiaire (cyan ↔ violet à 50 %) — pour raccorder les deux moitiés.
PRO_MID = "#6594F3"

# Style du bouton CTA « neoSlice Pro » : dégradé complet cyan→violet.
# Indépendant du thème : la couleur d'identité Pro est fixe.
_PRO_GRADIENT_BTN = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
        color: #ffffff; border: none; border-radius: 3px;
        padding: 0 10px; letter-spacing: 1px; font-weight: bold;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #38DDF5, stop:1 #B86CF8);
    }}
"""

# NEOGEN + DIAGNOSTIC + ESPACE PRO : TROIS boutons séparés, mais UN dégradé
# cyan→violet continu qui s'étend sur les trois (tiers interpolés linéairement
# entre PRO_CYAN #22D3EE et PRO_VIOLET #A855F7 ; PRO_MID reste le milieu exact).
PRO_TIER1 = "#4FA9F1"   # couleur à 1/3 du dégradé
PRO_TIER2 = "#7B7FF4"   # couleur à 2/3 du dégradé
_PRO_BTN_LEFT = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {PRO_CYAN}, stop:1 {PRO_TIER1});
        color: #ffffff; border: none; border-radius: 3px;
        padding: 0 10px; font-weight: bold;
    }}
"""
_PRO_BTN_MID = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {PRO_TIER1}, stop:1 {PRO_TIER2});
        color: #ffffff; border: none; border-radius: 3px;
        padding: 0 10px; font-weight: bold;
    }}
"""
_PRO_BTN_RIGHT = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {PRO_TIER2}, stop:1 {PRO_VIOLET});
        color: #ffffff; border: none; border-radius: 3px;
        padding: 0 10px; font-weight: bold;
    }}
"""

# Variante à QUATRE boutons (NEOGEN | CARTE | DIAGNOSTIC | ESPACE PRO) — même
# dégradé cyan→violet continu, découpé en 4 segments (bornes à 0, ¼, ½, ¾, 1).
_G4A, _G4B, _G4C = "#44B4F0", "#6594F2", "#8775F5"


def _seg4(c1, c2):
    return (f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 {c1}, stop:1 {c2}); color: #ffffff; border: none;"
            f" border-radius: 3px; padding: 0 10px; font-weight: bold; }}")


_PRO_BTN_Q1 = _seg4(PRO_CYAN, _G4A)
_PRO_BTN_Q2 = _seg4(_G4A, _G4B)
_PRO_BTN_Q3 = _seg4(_G4B, _G4C)
_PRO_BTN_Q4 = _seg4(_G4C, PRO_VIOLET)


class _TopBar(QWidget):
    """Barre haute 48px — logo + scan-line animée + sélecteur de thème."""

    coffee_clicked    = Signal()
    tutorial_clicked  = Signal()
    new_piece_clicked = Signal()
    settings_clicked  = Signal()
    diag_clicked      = Signal()
    cost_clicked      = Signal()
    neogen_clicked    = Signal()      # bouton neoGen (bibliothèque d'objets à personnaliser)
    pro_clicked       = Signal()      # bouton « neoSlice Pro » (ouvre le paywall)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self._scanline_y = 0
        # Animation de la scan-line activable/désactivable (réglages). Désactivée =
        # scan-line FIGÉE juste sous le sous-titre (soulignement), grille en pause.
        self._anim_enabled = bool(PREFS.get("scanbar_anim", False))
        self._radar_last = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.destroyed.connect(self._timer.stop)
        self._setup_ui()
        self.refresh_theme()
        if self._anim_enabled:
            self._timer.start(16)   # ~60 fps → glissement fluide
        else:
            self._scanline_y = self._frozen_y()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 16, 1)
        layout.setSpacing(12)

        # Petite barre grise verticale, alignée (x=12) sur la barre verte des
        # sections du panneau de gauche en dessous.
        self._title_bar = QFrame()
        self._title_bar.setFixedWidth(3)
        self._title_bar.setFixedHeight(28)
        layout.addWidget(self._title_bar, 0, Qt.AlignVCenter)

        self._title_lbl = QLabel(_("app.title"))
        self._title_lbl.setFont(QFont(FONT_MAIN, 26, QFont.Bold))
        layout.addWidget(self._title_lbl, 0, Qt.AlignVCenter)

        # Badge « Pro » (dégradé cyan→violet) — visible seulement si licence active
        from ui.components.pro_badge import ProBadge
        self._pro_badge = ProBadge("Pro", point_size=17, letter_spacing=1.5)
        layout.addWidget(self._pro_badge, 0, Qt.AlignVCenter)

        self._sub = QLabel(_("app.subtitle"))
        self._sub.setFont(QFont(FONT_MAIN, 8))
        layout.addWidget(self._sub)

        layout.addStretch()

        # Bouton NEOGEN (bibliothèque d'objets 3D à personnaliser, prêts à imprimer) — Pro
        self._neogen_btn = QPushButton(_("app.btn_neogen"))
        self._neogen_btn.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        self._neogen_btn.setFixedHeight(26)
        self._neogen_btn.setCursor(Qt.PointingHandCursor)
        self._neogen_btn.setToolTip(_("neogen.tooltip"))
        self._neogen_btn.clicked.connect(self.neogen_clicked)

        self._diag_btn = QPushButton(_("app.btn_diag"))
        self._diag_btn.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        self._diag_btn.setFixedHeight(26)
        self._diag_btn.setCursor(Qt.PointingHandCursor)
        self._diag_btn.setToolTip("Diagnostiquer un défaut d'impression — par photo ou en le choisissant")
        self._diag_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 3px;
                padding: 0 10px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
        """)
        self._diag_btn.clicked.connect(self.diag_clicked)

        # Bouton ESPACE PRO (hub de gestion : bobines, devis, clients…) — remplace DEVIS
        self._cost_btn = QPushButton(_("pro.space_btn"))
        self._cost_btn.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        self._cost_btn.setFixedHeight(26)
        self._cost_btn.setCursor(Qt.PointingHandCursor)
        self._cost_btn.setToolTip(_("pro.space_tooltip"))
        self._cost_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_SECONDARY};
                border: 1px solid {INACTIVE}; border-radius: 3px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(30,144,255,0.10);
                color: {ACCENT}; border-color: {ACCENT};
            }}
        """)
        self._cost_btn.clicked.connect(self.cost_clicked)

        # Bouton CTA « neoSlice Pro » (dégradé cyan→violet) — affiché à la place
        # de DIAGNOSTIC/DEVIS quand la version Pro n'est pas active.
        self._pro_cta_btn = QPushButton("neoSlice Pro")
        self._pro_cta_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._pro_cta_btn.setFixedHeight(26)
        self._pro_cta_btn.setCursor(Qt.PointingHandCursor)
        self._pro_cta_btn.setToolTip("Diagnostic IA — essais gratuits puis neoSlice Pro (diagnostic + devis)")
        self._pro_cta_btn.setStyleSheet(_PRO_GRADIENT_BTN)
        self._pro_cta_btn.clicked.connect(self.pro_clicked)

        self._new_btn = QPushButton(_("app.btn_new_piece"))
        self._new_btn.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        self._new_btn.setFixedHeight(26)
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.setEnabled(False)
        self._new_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #0D2540;
                border: 1px solid #0D2540;
                border-radius: 3px;
                padding: 0 10px;
                letter-spacing: 1px;
            }}
            QPushButton:enabled {{
                color: {TEXT_SECONDARY};
                border-color: {INACTIVE};
            }}
            QPushButton:enabled:hover {{
                background: rgba(30,144,255,0.10);
                color: {ACCENT};
                border-color: {ACCENT};
            }}
        """)
        self._new_btn.clicked.connect(self.new_piece_clicked)
        layout.addWidget(self._new_btn)
        # NEOGEN + DIAGNOSTIC + ESPACE PRO : trois boutons séparés, mais UN seul
        # dégradé cyan→violet continu qui s'étend sur les trois.
        layout.addWidget(self._neogen_btn)
        layout.addWidget(self._diag_btn)
        layout.addWidget(self._cost_btn)
        layout.addWidget(self._pro_cta_btn)
        self.refresh_pro()   # état initial des boutons Pro (après leur création)

        import sys as _sys
        _mac = _sys.platform == "darwin"
        help_btn = QPushButton("?")
        # macOS : glyphe texte plus petit dans son cadre que la police d'icônes
        # Windows (Segoe MDL2) → on agrandit pour une taille visuelle comparable.
        help_btn.setFont(QFont(FONT_MAIN, 15 if _mac else 11, QFont.Bold))
        help_btn.setFixedSize(28, 28)
        help_btn.setToolTip("Guide d'utilisation")
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {INACTIVE};
                border: none; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(30,144,255,0.15); color: {ACCENT_BRIGHT};
            }}
        """)
        help_btn.clicked.connect(self.tutorial_clicked)
        coffee_btn = QPushButton()
        _ci = _coffee_icon()
        if _ci is not None:
            coffee_btn.setIcon(_ci)
            coffee_btn.setIconSize(QSize(18, 18))
        else:
            coffee_btn.setText("☕")
        coffee_btn.setFont(QFont(FONT_MAIN, 10))
        coffee_btn.setFixedSize(28, 28)
        coffee_btn.setToolTip("À propos / Soutenir le développement")
        coffee_btn.setCursor(Qt.PointingHandCursor)
        coffee_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {INACTIVE};
                border: none; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(255,221,0,0.15); color: #FFDD00;
            }}
        """)
        coffee_btn.clicked.connect(self.coffee_clicked)

        import sys as _sys
        _ICON_FEEDBACK = "" if _sys.platform == "win32" else "✉"
        _ICON_SETTINGS = "" if _sys.platform == "win32" else "⚙"
        # macOS : les symboles unicode ⚙/✉ se dessinent petits dans leur cadre → 17pt
        # pour remplir la case 28×28 comme la police d'icônes Windows (Segoe MDL2).
        _FONT_ICON     = QFont("Segoe MDL2 Assets", 11) if _sys.platform == "win32" else QFont(FONT_MAIN, 17)

        feedback_btn = QPushButton(_ICON_FEEDBACK)
        feedback_btn.setFont(_FONT_ICON)
        feedback_btn.setFixedSize(28, 28)
        feedback_btn.setToolTip("Envoyer un retour / signaler un bug")
        feedback_btn.setCursor(Qt.PointingHandCursor)
        feedback_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {INACTIVE};
                border: none; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(30,144,255,0.15); color: {ACCENT_BRIGHT};
            }}
        """)
        feedback_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://neoslice-ai.com/retour")
        ))

        self._settings_btn = QPushButton(_ICON_SETTINGS)
        self._settings_btn.setFont(_FONT_ICON)
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setToolTip(_("app.tip_settings"))
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.clicked.connect(self.settings_clicked)

        self._help_btn    = help_btn
        self._coffee_btn  = coffee_btn
        self._feedback_btn = feedback_btn

        self.icon_group = QWidget()
        self.icon_group.setStyleSheet("background: transparent;")
        icon_lay = QHBoxLayout(self.icon_group)
        icon_lay.setContentsMargins(0, 0, 0, 0)
        icon_lay.setSpacing(2)
        icon_lay.addWidget(self._settings_btn)
        icon_lay.addWidget(self._feedback_btn)
        icon_lay.addWidget(self._help_btn)
        icon_lay.addWidget(self._coffee_btn)
        layout.addWidget(self.icon_group)

        from version import __version__
        self._version_lbl = QLabel(f"v{__version__}")
        self._version_lbl.setFont(QFont(FONT_MONO, 8))
        layout.addWidget(self._version_lbl)

    def set_has_stl(self, active: bool):
        self._new_btn.setEnabled(active)

    def set_new_enabled(self, enabled: bool):
        """Active « NOUVELLE PIÈCE » indépendamment du chargement d'un STL :
        dans neoGen / l'éditeur de carte, on veut pouvoir réinitialiser la
        scène de PARTOUT, même sans pièce déjà chargée."""
        self._new_btn.setEnabled(enabled)

    def refresh_pro(self) -> None:
        """Bascule l'UI Pro selon l'état de la licence.

        - Pro actif   : badge visible, boutons DIAGNOSTIC IA + DEVIS visibles et
                        colorés en dégradé cyan→violet, CTA masqué.
        - Pro inactif : badge + boutons Pro masqués, bouton CTA « neoSlice Pro »
                        (dégradé) visible à la place."""
        from core import licensing
        is_pro = licensing.est_pro()
        from core import licensing as _lic
        coming = getattr(_lic, "PRO_COMING_SOON", False)
        self._pro_badge.setVisible(is_pro)
        self._neogen_btn.setVisible(is_pro)
        self._diag_btn.setVisible(is_pro)
        self._cost_btn.setVisible(is_pro)
        self._pro_cta_btn.setVisible(not is_pro)
        if is_pro:
            # Trois boutons distincts ; UN dégradé cyan→violet continu sur les trois
            self._neogen_btn.setStyleSheet(_PRO_BTN_LEFT)
            self._diag_btn.setStyleSheet(_PRO_BTN_MID)
            self._cost_btn.setStyleSheet(_PRO_BTN_RIGHT)
        else:
            self._pro_cta_btn.setText("neoSlice Pro")
            self._pro_cta_btn.setToolTip(
                "neoSlice Pro arrive bientôt"
                if coming else
                "Diagnostic IA — essais gratuits puis neoSlice Pro (diagnostic + devis)"
            )

    def refresh_theme(self) -> None:
        pal = _THEME.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        self._title_bar.setStyleSheet(f"background: {pal['INACTIVE']}; border-radius: 1px;")
        self._title_lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; font-size: 26px; font-weight: bold; letter-spacing: 0px;")
        # Animation coupée → sous-titre en couleur claire (bien lisible) ; animée →
        # base ternie, l'effet radar gère la mise en surbrillance au passage.
        _sub_col = pal['TEXT_PRIMARY'] if not getattr(self, '_anim_enabled', True) else pal['TEXT_LABEL']
        self._sub.setStyleSheet(f"color: {_sub_col}; background: transparent;")
        if hasattr(self, '_version_lbl'):
            self._version_lbl.setStyleSheet(
                f"color: {pal['ACCENT_BRIGHT']}; background: {pal['BG_SURFACE']}; "
                f"border: 1px solid {pal['ACCENT']}; border-radius: 2px; padding: 1px 5px;"
            )
        self._diag_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']};
                color: #ffffff;
                border: none;
                border-radius: 3px;
                padding: 0 10px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
        """)
        self._new_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {pal['INACTIVE']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 3px;
                padding: 0 10px;
                letter-spacing: 1px;
            }}
            QPushButton:enabled {{
                color: {pal['TEXT_SECONDARY']};
                border-color: {pal['INACTIVE']};
            }}
            QPushButton:enabled:hover {{
                background: rgba(30,144,255,0.10);
                color: {pal['ACCENT']};
                border-color: {pal['ACCENT']};
            }}
        """)
        _icon_style = f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: none; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{
                background: {pal['BG_ELEVATED']}; color: {pal['ACCENT_BRIGHT']};
            }}
        """
        for btn in (self._settings_btn, self._feedback_btn, self._help_btn, self._coffee_btn):
            btn.setStyleSheet(_icon_style)
        # Recolorer l'icône café selon le thème (silhouette claire en sombre)
        _ci = _coffee_icon()
        if _ci is not None:
            self._coffee_btn.setIcon(_ci)
        # Ré-applique l'état Pro APRÈS le style de thème : sinon le style vert
        # ci-dessus du bouton diagnostic écrase le dégradé cyan→violet du mode Pro.
        self.refresh_pro()
        self.update()

    def _frozen_y(self) -> float:
        """Position FIGÉE de la scan-line quand l'animation est coupée : juste sous
        le TEXTE du sous-titre « AI-POWERED 3D PRINT OPTIMIZER » (soulignement).
        ⚠️ Le QLabel occupe toute la hauteur de la barre (texte centré dedans), donc
        on vise le bas du TEXTE = centre du label + demi-hauteur de police, pas
        `geometry().bottom()` (= bas de la barre)."""
        try:
            fm = self._sub.fontMetrics()
            cy = self._sub.geometry().center().y()      # = centre vertical du texte
            return float(cy + fm.height() / 2.0 + 2.0)  # 2px sous le texte
        except Exception:
            return float(max(1, int(self.height() * 0.62)))

    def set_scanbar_animation(self, enabled: bool):
        """Active/désactive l'animation. Désactivée → scan-line figée sous le
        sous-titre, grille en pause autour, sous-titre bien lisible."""
        self._anim_enabled = bool(enabled)
        self._radar_last = None
        if self._anim_enabled:
            if not self._timer.isActive():
                self._timer.start(16)
        else:
            self._timer.stop()
            self._scanline_y = self._frozen_y()
        self.refresh_theme()   # recolore le sous-titre selon l'état
        self.update()

    def _tick(self):
        # Déplacement fractionnaire à ~60 fps → mouvement fluide.
        # 0.55 px/frame ≈ 33 px/s (rythme posé et lent).
        self._scanline_y = (self._scanline_y + 0.55) % max(self.height(), 1)
        self._update_radar_glow()
        self.update()

    def _update_radar_glow(self):
        """Effet radar : le sous-titre s'éclaircit quand la scan-line le traverse,
        puis se ternit (sans jamais disparaître)."""
        if not hasattr(self, "_sub"):
            return
        pal = _THEME.palette()
        cy = self._sub.geometry().center().y()
        reveal = max(0.0, 1.0 - abs(self._scanline_y - cy) / 16.0)  # 0 loin → 1 dessus
        base = QColor(pal["TEXT_LABEL"])     # état terne (toujours lisible)
        hi   = QColor(pal["TEXT_PRIMARY"])   # état mis en surbrillance
        col = QColor(
            int(base.red()   + (hi.red()   - base.red())   * reveal),
            int(base.green() + (hi.green() - base.green()) * reveal),
            int(base.blue()  + (hi.blue()  - base.blue())  * reveal),
        )
        key = col.rgb()
        if key == getattr(self, "_radar_last", None):
            return   # couleur inchangée → on évite un restyle inutile à 60 fps
        self._radar_last = key
        self._sub.setStyleSheet(f"color: {col.name()}; background: transparent;")

    def paintEvent(self, event):
        super().paintEvent(event)
        pal = _THEME.palette()
        if not self._anim_enabled:           # scan-line FIGÉE sous le sous-titre
            self._scanline_y = self._frozen_y()
        painter = QPainter(self)
        painter.setPen(QPen(QColor(pal["ACCENT"]), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        # Scan-line en dégradé cyan→violet (couleurs « PRO »), avec FONDU vertical :
        # invisible en haut (apparition), pleine opacité au milieu, se refond en bas.
        from PySide6.QtGui import QLinearGradient, QBrush
        _h = max(self.height(), 1)
        _t = self._scanline_y / _h
        # Puissance 3 → fondu bien plus marqué aux deux extrémités, pleine
        # visibilité concentrée au centre.
        _fade = (4.0 * _t * (1.0 - _t)) ** 3   # 0 aux bords → 1 au centre
        # Figée → soulignement net (pleine visibilité) ; animée → fondu vertical.
        _a = 230 if not self._anim_enabled else max(0, min(255, int(255 * _fade)))
        _c1 = QColor(PRO_CYAN);   _c1.setAlpha(_a)
        _cm = QColor(PRO_MID);    _cm.setAlpha(_a)
        _c2 = QColor(PRO_VIOLET); _c2.setAlpha(_a)
        # Bornes horizontales : la scan-line passe DERRIÈRE le sous-titre
        # (AI-POWERED) puis traverse l'espace vide jusqu'avant « Nouvelle pièce ».
        # Le bord gauche démarre au sous-titre.
        _x1, _x2 = 0, self.width()
        try:
            _x1 = self._sub.geometry().left()           # démarre au sous-titre (passe derrière)
            _x2 = self._new_btn.geometry().left() - 16
            if _x2 <= _x1:               # garde-fou si le layout n'est pas prêt
                _x1, _x2 = 0, self.width()
        except Exception:
            pass

        # Grille « radar » de fond : à peine visible partout, elle se RÉVÈLE
        # (contraste) dans une bande autour de la scan-line. Couleur PRO_MID,
        # alpha plancher très bas, pic au niveau de la ligne.
        _step = 18
        _cy = self._scanline_y
        _band = 20.0
        _A_MIN, _A_MAX = 9, 64
        # Lignes horizontales : alpha selon la proximité verticale de la scan-line.
        _gy = _step
        while _gy < _h:
            _p = max(0.0, 1.0 - abs(_gy - _cy) / _band)
            _gc = QColor(PRO_MID); _gc.setAlpha(int(_A_MIN + (_A_MAX - _A_MIN) * _p))
            painter.setPen(QPen(_gc, 1))
            painter.drawLine(_x1, _gy, _x2, _gy)
            _gy += _step
        # Lignes verticales : pen à dégradé vertical (pic d'alpha à la scan-line).
        def _vstop(g, ypx, a):
            c = QColor(PRO_MID); c.setAlpha(a)
            g.setColorAt(min(0.9999, max(0.0, ypx / _h)), c)
        _gx = _x1
        while _gx <= _x2:
            _vg = QLinearGradient(0, 0, 0, _h)
            _vstop(_vg, 0, _A_MIN)
            _vstop(_vg, _cy - _band, _A_MIN)
            _vstop(_vg, _cy, _A_MAX)
            _vstop(_vg, _cy + _band, _A_MIN)
            _vstop(_vg, _h, _A_MIN)
            painter.setPen(QPen(QBrush(_vg), 1))
            painter.drawLine(_gx, 0, _gx, _h)
            _gx += _step

        _grad = QLinearGradient(_x1, 0, _x2, 0)
        _grad.setColorAt(0.0, _c1)
        _grad.setColorAt(0.5, _cm)
        _grad.setColorAt(1.0, _c2)
        painter.setPen(QPen(QBrush(_grad), 1))
        _sy = int(self._scanline_y)
        painter.drawLine(_x1, _sy, _x2, _sy)


# ── StatusBar ──────────────────────────────────────────────────────────────

class _StatusBar(QWidget):
    """Barre basse 40px — statut + bouton export."""

    export_clicked    = Signal()
    diag_apply_clicked = Signal(object)   # DiagnosticResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self._pulse_phase = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self.destroyed.connect(self._pulse_timer.stop)
        self._diag_result = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setFont(QFont(FONT_MONO, 10))
        self._dot.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
        layout.addWidget(self._dot)

        self._msg = QLabel(_("status.initial"))
        self._msg.setFont(QFont(FONT_MONO, 10))
        self._msg.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._msg.setWordWrap(False)
        layout.addWidget(self._msg, 1)

        # Bouton corrections diagnostic — à gauche de l'export, masqué par défaut
        self._diag_btn = QPushButton()
        self._diag_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._diag_btn.setFixedHeight(30)
        self._diag_btn.setCursor(Qt.PointingHandCursor)
        self._diag_btn.clicked.connect(self._on_diag_apply)
        self._diag_btn.hide()
        self._apply_diag_btn_style()
        layout.addWidget(self._diag_btn)

        self._export_btn = QPushButton(_("export.btn", slicer=_slicer_name()))
        self._export_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._export_btn.setFixedHeight(30)
        self._export_btn.setEnabled(False)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #020408;
                border: none;
                border-radius: 3px;
                padding: 0 16px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {ACCENT_BRIGHT};
            }}
            QPushButton:disabled {{
                background: {INACTIVE};
                color: {TEXT_LABEL};
            }}
        """)
        self._export_btn.clicked.connect(self.export_clicked)
        layout.addWidget(self._export_btn)

    # ── Bouton corrections diagnostic ──────────────────────────────────────
    def _apply_diag_btn_style(self):
        pal = _THEME.palette()
        self._diag_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['AMBER']}; color: #ffffff;
                border: none; border-radius: 3px; padding: 0 16px; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: #FFC933; }}
            QPushButton:disabled {{ background: {pal['TELE_GREEN']}; color: #ffffff; }}
        """)

    def set_diagnostic_result(self, result):
        from core.defect_detection.defect_classes import DefectClass, defect_label
        self._diag_result = result
        has_corr = (
            result is not None
            and result.defect != DefectClass.GOOD
            and any(not k.startswith("_") for k in result.remediation)
        )
        if has_corr:
            label = defect_label(result.defect)
            # Clé à molette en présentation texte (U+FE0E) → monochrome, suit
            # la couleur du texte (blanc), compatible Windows/macOS.
            wrench = "\U0001F527︎"
            self._diag_btn.setText(f"{wrench}  APPLIQUER CORRECTIONS — {label.upper()}")
            self._diag_btn.setEnabled(True)
            self._apply_diag_btn_style()
            self._diag_btn.show()
        else:
            self._diag_btn.hide()

    def clear_diagnostic_result(self):
        self._diag_result = None
        self._diag_btn.hide()

    def _on_diag_apply(self):
        if self._diag_result is not None:
            self.diag_apply_clicked.emit(self._diag_result)
            self._diag_btn.setText("✓  CORRECTIONS APPLIQUÉES")
            self._diag_btn.setEnabled(False)

    def refresh_theme(self):
        pal = _THEME.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        self._dot.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        self._msg.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        if self._diag_btn.isEnabled():
            self._apply_diag_btn_style()
        if not self._export_btn.isEnabled():
            self._export_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                    border: none; border-radius: 3px; padding: 0 16px; letter-spacing: 1px;
                }}
                QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
                QPushButton:disabled {{
                    background: {pal['INACTIVE']}; color: {pal['TEXT_LABEL']};
                }}
            """)
        self.update()

    def set_message(self, text: str, dot_color: str = TELE_GREEN):
        # Aplatir les messages multi-lignes (ex: exceptions VTK/qhull) et limiter la longueur
        text = " — ".join(line.strip() for line in text.splitlines() if line.strip())
        if len(text) > 130:
            text = text[:127] + "…"
        self._msg.setText(text.upper())
        self._dot.setStyleSheet(f"color: {dot_color}; background: transparent;")

    def _pulse_tick(self):
        pal = _THEME.palette()
        _bg = pal['ACCENT'] if _THEME.is_dark() else pal['TELE_GREEN']
        self._pulse_phase = (self._pulse_phase + 1) % 80
        t = abs(self._pulse_phase - 40) / 40.0
        alpha = int(80 + 120 * (1.0 - t))
        self._export_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_bg};
                color: {pal['EXPORT_FG']};
                border: 1px solid rgba(255,255,255,{alpha});
                border-radius: 3px;
                padding: 0 16px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {pal['ACCENT_BRIGHT']};
                border-color: white;
            }}
        """)

    def set_export_enabled(self, enabled: bool):
        pal = _THEME.palette()
        _bg = pal['ACCENT'] if _THEME.is_dark() else pal['TELE_GREEN']
        self._export_btn.setEnabled(enabled)
        if enabled:
            self._pulse_phase = 0
            self._pulse_timer.start(20)
        else:
            self._pulse_timer.stop()
            self._export_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_bg};
                    color: {pal['EXPORT_FG']};
                    border: none;
                    border-radius: 3px;
                    padding: 0 16px;
                    letter-spacing: 1px;
                }}
                QPushButton:hover {{
                    background: {pal['ACCENT_BRIGHT']};
                }}
                QPushButton:disabled {{
                    background: {pal['INACTIVE']};
                    color: {pal['TEXT_LABEL']};
                }}
            """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(_THEME.palette()["ACCENT"]), 1))
        painter.drawLine(0, 0, self.width(), 0)


# ── Section divider avec étape numérotée ──────────────────────────────────

class _NumBadge(QWidget):
    """Badge rond numéroté dessiné à la main (cercle + chiffre centré).

    On n'utilise PAS les glyphes Unicode précomposés (①②③) : leur espacement
    chiffre/anneau varie d'un chiffre à l'autre (le « 2 » touchait le cercle).
    En dessinant nous-mêmes, tous les chiffres ont un rendu strictement
    identique et bien lisible."""

    _D = 20  # diamètre du cercle (px)

    def __init__(self, digit: str, parent=None):
        super().__init__(parent)
        self._digit = digit
        self._color = "#1E90FF"
        self.setFixedSize(self._D + 4, self._D + 4)

    def set_color(self, color: str):
        self._color = color
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QPen, QFontMetrics
        from PySide6.QtCore import QPointF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        d = self._D
        x = (self.width() - d) / 2.0
        y = (self.height() - d) / 2.0
        pen = QPen(QColor(self._color))
        pen.setWidthF(1.8)
        p.setPen(pen)
        p.drawEllipse(QPointF(x + d / 2.0, y + d / 2.0), d / 2.0, d / 2.0)
        f = QFont(FONT_MAIN, 10, QFont.Bold)
        p.setFont(f)
        # HORIZONTAL : centrer sur l'AVANCE du chiffre (chasse), pas sur l'encre —
        # les chiffres sont dessinés centrés dans leur chasse par le typographe, ce
        # qui garantit un alignement en colonne identique pour 1, 2, 3…
        # VERTICAL : centrer sur l'ENCRE (les chiffres n'ont pas de jambage → un
        # simple AlignVCenter les ferait paraître remontés).
        fm = QFontMetrics(f)
        br = fm.tightBoundingRect(self._digit)
        bx = (self.width() - fm.horizontalAdvance(self._digit)) / 2.0
        by = self.height() / 2.0 - br.height() / 2.0 - br.y()
        p.drawText(QPointF(bx, by), self._digit)
        p.end()


class _StepHeader(QWidget):
    """En-tête de section avec numéro d'étape et indicateur d'état."""

    def __init__(self, number: str, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self._state = "pending"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._bar = QFrame()
        self._bar.setFixedWidth(3)
        self._bar.setFixedHeight(14)
        layout.addWidget(self._bar)

        # Badge rond dessiné (espacement identique pour tous les chiffres).
        self._num = _NumBadge(number)
        layout.addWidget(self._num)

        self._lbl = QLabel(title.upper())
        self._lbl.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        layout.addWidget(self._lbl)

        layout.addStretch()
        self.set_pending()

    def _set_colors(self, bar_color: str, num_color: str):
        pal = _THEME.palette()
        self._bar.setStyleSheet(f"background: {bar_color}; border-radius: 1px;")
        self._num.set_color(num_color)
        self._lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; letter-spacing: 2px; background: transparent;"
        )

    def set_pending(self):
        self._state = "pending"
        pal = _THEME.palette()
        self._set_colors(pal["INACTIVE"], pal["ACCENT"])

    def set_active(self):
        self._state = "active"
        pal = _THEME.palette()
        self._set_colors(pal["ACCENT"], pal["ACCENT"])

    def set_done(self):
        self._state = "done"
        pal = _THEME.palette()
        self._set_colors(pal["TELE_GREEN"], pal["ACCENT"])

    def refresh_theme(self):
        getattr(self, f"set_{self._state}", self.set_pending)()


# ── Centre : fond uni ──────────────────────────────────────────────────────

class _GridWidget(QWidget):
    """Widget central — fond uni sans quadrillage."""


# Exécutables des slicers par plateforme (pour ouvrir le 3MF dans le bon logiciel)
# CrealityPrint ET UltiMaker Cura s'installent dans un dossier VERSIONNÉ
# (« Creality Print 6.3 », « UltiMaker Cura 5.6.0 ») → glob, robuste aux MAJ.
_CREALITY_EXES = [
    str(p)
    for base in (r"C:\Program Files\Creality", r"C:\Program Files (x86)\Creality")
    for p in sorted(Path(base).glob("Creality Print*/CrealityPrint.exe"))
]
_CURA_EXES = [
    str(p)
    for base in (r"C:\Program Files", r"C:\Program Files (x86)")
    for p in sorted(Path(base).glob("UltiMaker Cura*/UltiMaker-Cura.exe"))
]

_SLICER_EXES = {
    "win32": {
        "bambu": [r"C:\Program Files\Bambu Studio\bambu-studio.exe"],
        "orca":  [r"C:\Program Files\OrcaSlicer\orca-slicer.exe",
                  r"C:\Program Files\OrcaSlicer\OrcaSlicer.exe"],
        "prusa": [r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe"],
        "creality": _CREALITY_EXES,
        "elegoo": [r"C:\Program Files\ElegooSlicer\elegoo-slicer.exe"],
        "anycubic": [r"C:\Program Files\AnycubicSlicerNext\AnycubicSlicerNext.exe"],
        "snapmaker": [r"C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe"],
        "cura": _CURA_EXES,
    },
    "darwin": {  # ouverts via `open -a <AppName>`
        "bambu": ["BambuStudio"],
        "orca":  ["OrcaSlicer"],
        "prusa": ["PrusaSlicer"],
        "creality": ["Creality Print"],
        "elegoo": ["ElegooSlicer"],
        "anycubic": ["AnycubicSlicerNext"],
        "snapmaker": ["Snapmaker Orca"],
        "cura": ["UltiMaker Cura"],
    },
}


def _open_3mf_in_slicer(path: str, slicer: str) -> None:
    """Ouvre le 3MF dans le slicer choisi (bambu/orca/prusa). Lance l'exécutable
    précis si trouvé, sinon retombe sur l'association de fichier par défaut."""
    import sys as _sys, subprocess as _sp, os as _os
    try:
        if _sys.platform == "win32":
            for exe in _SLICER_EXES["win32"].get(slicer, []):
                if _os.path.exists(exe):
                    _sp.Popen([exe, path])
                    return
            _os.startfile(path)            # repli : appli associée au .3mf
        elif _sys.platform == "darwin":
            apps = _SLICER_EXES["darwin"].get(slicer, [])
            if apps:
                _sp.run(["open", "-a", apps[0], path], check=False)
            else:
                _sp.run(["open", path], check=False)
        else:
            _sp.run(["xdg-open", path], check=False)
    except Exception:
        try:
            if _sys.platform == "win32":
                _os.startfile(path)
            else:
                _sp.run(["open" if _sys.platform == "darwin" else "xdg-open", path], check=False)
        except Exception:
            pass


def _slicer_name() -> str:
    """Nom affiché du slicer de sortie choisi (Bambu Studio / OrcaSlicer / PrusaSlicer)."""
    from core.prefs import PREFS as _P
    sl = _P.get("slicer_output", "bambu")
    return _({"orca": "settings.slicer_orca",
              "prusa": "settings.slicer_prusa",
              "creality": "settings.slicer_creality",
              "elegoo": "settings.slicer_elegoo",
              "anycubic": "settings.slicer_anycubic",
              "snapmaker": "settings.slicer_snapmaker",
              "cura": "settings.slicer_cura"}.get(sl, "settings.slicer_bambu"))


def _coffee_icon():
    """QIcon du café personnalisé (assets/coffee.png) si présent, sinon None.

    Thème clair : image d'origine (tasse grise, bien visible sur fond clair).
    Thème sombre : la tasse grise se fondrait dans le fond → on la recolore en
    silhouette claire (via le canal alpha) pour qu'elle ressorte nettement."""
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage
    assets = Path(__file__).parent.parent / "assets"
    p = assets / "coffee.png"
    if not p.exists():
        return None
    pix = QPixmap(str(p))
    if pix.isNull():
        return None

    # L'image source est portrait avec beaucoup de marge vide → on recadre sur le
    # contenu (pixels non transparents) puis on centre sur un CARRÉ : l'icône reste
    # proportionnée et alignée avec les glyphes voisins (plus d'effet « écrasé »).
    try:
        import numpy as _np
        img = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        arr = _np.frombuffer(ptr, _np.uint8).reshape(h, w, 4)
        ys, xs = _np.where(arr[:, :, 3] > 12)
        if len(xs) and len(ys):
            x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
            pix = pix.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        side = max(pix.width(), pix.height())
        sq = QPixmap(side, side); sq.fill(Qt.transparent)
        pn = QPainter(sq)
        pn.drawPixmap((side - pix.width()) // 2, (side - pix.height()) // 2, pix)
        pn.end()
        pix = sq
    except Exception:
        pass

    if _THEME.is_dark():
        tinted = QPixmap(pix.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(_THEME.palette()["TEXT_SECONDARY"]))
        painter.end()
        return QIcon(tinted)
    return QIcon(pix)


# ── Fenêtre principale ─────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    # Signal thread-safe pour la popup de mise à jour (émis depuis thread background)
    _update_ready = Signal(str, str, str)  # version, url, notes
    # Signal thread-safe : une MAJ de la base de connaissances d'Oen est disponible
    _kb_update_ready = Signal(str)         # kb_version
    _brands_update_ready = Signal(str)     # version bibliothèque filaments

    def __init__(self):
        super().__init__()
        self._mesh = None
        self._original_mesh = None
        self._threemf_data = None
        self._analysis: AnalysisReport | None = None
        self._stl_load_thread: QThread | None = None
        self._stl_load_worker: STLLoadWorker | None = None
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._current_config = None
        self._current_selection = None
        self._pending_diag_result = None   # DiagnosticResult accepté, en attente d'application
        self._diag_dialog = None           # dialog diagnostic persistant (singleton)
        self._parameter_engine = ParameterEngine()
        self._tmf_builder = ThreeMFBuilder()
        self._profile_installer = BambuProfileInstaller()
        self._analysis_timeout = QTimer(self)
        self._analysis_timeout.setSingleShot(True)
        self._analysis_timeout.timeout.connect(self._on_analysis_timeout)

        self._current_printer: str = "X1 Carbon"
        self._current_filament: str = "PLA"
        self._current_nozzle_mm: float = 0.4
        self._tutorial: TutorialOverlay | None = None

        self._setup_window()
        self._setup_ui()
        _THEME.register(self._apply_theme)
        self._apply_theme()

        if should_show_welcome():
            QTimer.singleShot(200, self._show_welcome_first_launch)
        elif should_show_tutorial():
            QTimer.singleShot(400, self._show_tutorial)

        self._update_ready.connect(self._show_update_dialog_signal)
        QTimer.singleShot(3000, self._check_for_updates)
        # Verifie discretement si la base de connaissances d'Oen a une MAJ (Pro +
        # Oen installe seulement). Non bloquant, hors-ligne-safe.
        self._kb_update_ready.connect(self._on_kb_update_available)
        QTimer.singleShot(6000, self._check_kb_update)
        self._brands_update_ready.connect(self._on_brands_updated)
        QTimer.singleShot(9000, self._check_brands_update)

        # L'assistant IA lit l'etat courant de l'appli (params + analyse viewer)
        try:
            from core.assistant import context as _assist_ctx
            _assist_ctx.register_app_state(self._assistant_snapshot)
        except Exception:
            pass

    def _assistant_snapshot(self) -> dict:
        """Instantane de l'etat courant pour l'assistant IA : imprimante, filament,
        buse, config de generation et analyse geometrique de l'objet charge."""
        stl_path = getattr(self, "_stl_path", None)
        name = None
        if stl_path:
            try:
                from pathlib import Path as _P
                name = _P(str(stl_path)).name
            except Exception:
                name = str(stl_path)
        return {
            "filename": name,
            "has_mesh": getattr(self, "_mesh", None) is not None,
            "printer": getattr(self, "_current_printer", "") or "",
            "filament": getattr(self, "_current_filament", "") or "",
            "nozzle_mm": getattr(self, "_current_nozzle_mm", None),
            "config": getattr(self, "_current_config", None),
            "analysis": getattr(self, "_analysis", None),
        }

    def _hard_quit(self, code: int = 0):
        """Sortie GARANTIE et immédiate de neoSlice.

        1) tue le serveur Ollama enfant (lancé par Oen via subprocess) : os._exit
           ne tue pas les enfants → sinon ollama.exe reste orphelin (process
           fantôme visible dans le gestionnaire des tâches) ;
        2) os._exit : n'attend AUCUN thread non-daemon. Sans ça, un worker ou le
           lecteur de flux Ollama maintient neoSlice.exe en vie après la
           fermeture → l'installateur de mise à jour croit neoSlice ouvert et
           refuse de s'installer (« fermez neoSlice » alors qu'il est fermé)."""
        try:
            import sys as _sys, subprocess as _sp
            if _sys.platform == "win32":
                _sp.run(["taskkill", "/F", "/IM", "ollama.exe"],
                        capture_output=True, creationflags=0x08000000)
        except Exception:
            pass
        import os
        os._exit(code)

    def closeEvent(self, event):
        event.accept()
        self._hard_quit(0)

    # ── Fenêtre ────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("neoSlice")
        self.setMinimumSize(1200, 720)
        self.resize(1400, 860)
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - 1400) // 2,
            (screen.height() - 860) // 2,
        )
        _p = _THEME.palette()
        self.setStyleSheet(
            f"QMainWindow {{ background: {_p['BG_VOID']}; }}"
            f"QToolTip {{ background-color: {_p['BG_ELEVATED']}; "
            f"color: {_p['TEXT_PRIMARY']}; border: 1px solid {_p['ACCENT']}; "
            f"padding: 4px 8px; border-radius: 3px; }}"
        )

        assets = Path(__file__).parent.parent / "assets"
        if not assets.exists():
            assets = Path(os.path.dirname(os.path.abspath(__file__))).parent / "assets"
        # .ico en priorité sur Windows (meilleur rendu natif), .png en fallback
        icon_path = assets / "neoSlice.ico"
        if not icon_path.exists():
            icon_path = assets / "neoSlice.png"
        if icon_path.exists():
            app_icon = QIcon(str(icon_path))
            self.setWindowIcon(app_icon)
            QApplication.instance().setWindowIcon(app_icon)

    # ── Layout principal ───────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── TopBar ──
        self._topbar = _TopBar()
        self._topbar.coffee_clicked.connect(self._show_welcome)
        self._topbar.tutorial_clicked.connect(self._show_tutorial)
        self._topbar.settings_clicked.connect(self._open_settings)
        self._topbar.new_piece_clicked.connect(self._on_new_piece)
        self._topbar.diag_clicked.connect(self._open_diagnostic)
        self._topbar.cost_clicked.connect(self._open_pro_hub)
        self._topbar.neogen_clicked.connect(self._open_neogen)
        # Bouton CTA « neoSlice Pro » : « bientôt disponible » en pré-lancement,
        # sinon ouvre le diagnostic (essais gratuits → paywall).
        self._topbar.pro_clicked.connect(self._on_pro_cta)
        root.addWidget(self._topbar)

        # ── Workspace 3 colonnes ──
        workspace = QWidget()
        self._workspace = workspace
        workspace.setStyleSheet(f"background: {_THEME.palette()['BG_VOID']};")
        ws_layout = QHBoxLayout(workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(0)

        self._left_scroll = self._build_panel_left()
        self._center_container = self._build_panel_center()
        self._right_scroll = self._build_panel_right()
        ws_layout.addWidget(self._left_scroll)
        ws_layout.addWidget(self._center_container, stretch=1)
        ws_layout.addWidget(self._right_scroll)

        root.addWidget(workspace, stretch=1)

        # ── StatusBar ──
        self._statusbar = _StatusBar()
        self._statusbar.export_clicked.connect(self._on_export_requested)
        self._statusbar.diag_apply_clicked.connect(self._do_apply_diagnostic)
        root.addWidget(self._statusbar)

    # ── Panneau gauche ─────────────────────────────────────────────────────

    def _build_panel_left(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setFixedWidth(360)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG_PANEL}; border: none; border-right: 1px solid {INACTIVE}; }}
            QScrollBar:vertical {{ background: {BG_PANEL}; width: 6px; border: none; }}
            QScrollBar::handle:vertical {{ background: {INACTIVE}; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: transparent; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        scroll.viewport().setStyleSheet(f"background: {BG_PANEL}; border: none;")

        content = QWidget()
        content.setStyleSheet(f"background: {BG_PANEL};")
        layout = QVBoxLayout(content)
        # Marge droite = 20px pour que la bordure pointillée soit toujours visible
        # même si la scrollbar s'affiche (6px) par-dessus le contenu.
        layout.setContentsMargins(12, 12, 20, 12)
        layout.setSpacing(6)

        # ── Étape ① — Configuration ──
        self._step_config = _StepHeader("1", "Configuration")
        self._step_config.set_active()
        layout.addWidget(self._step_config)

        self._filament_selector = FilamentPrinterSelector()
        _default_printer = PREFS.get("printer_default", "")
        if _default_printer:
            self._filament_selector.set_printer(_default_printer)
            # set_printer ne lève pas selection_changed → lire la valeur directement
            _p = self._filament_selector.current_printer()
            _f = self._filament_selector.current_filament()
            if _p:
                self._current_printer = _p
            if _f:
                self._current_filament = _f
        self._filament_selector.selection_changed.connect(self._on_filament_printer_changed)
        self._filament_selector.printer_confirmed.connect(self._on_printer_confirmed)
        self._filament_selector.filament_confirmed.connect(self._on_filament_confirmed)
        # Étape ① validée -> déverrouille « Générer configuration » (les pièces
        # neoGen chargent sans passer par le glisser-déposer qui imposait ça)
        self._filament_selector.printer_confirmed.connect(self._maj_prerequis_generation)
        self._filament_selector.filament_confirmed.connect(self._maj_prerequis_generation)
        layout.addWidget(self._filament_selector)

        sep0 = QFrame()
        sep0.setFixedHeight(1)
        sep0.setStyleSheet(f"background: {INACTIVE}; margin: 4px 0;")
        layout.addWidget(sep0)

        # ── Étape ② — Import STL / OBJ / 3MF ──
        self._step_stl = _StepHeader("2", "Import STL / OBJ / 3MF")
        layout.addWidget(self._step_stl)

        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._on_stl_dropped)
        layout.addWidget(self._drop_zone)

        # Dernier fichier STL ouvert
        from ui.components.welcome_dialog import _load_prefs
        _prefs = _load_prefs()
        _last = _prefs.get("last_stl")
        if _last:
            from pathlib import Path as _P
            _lp = _P(_last)
            if _lp.exists():
                self._drop_zone.set_recent_file(_lp)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {INACTIVE}; margin: 4px 0;")
        layout.addWidget(sep)

        # ── Étape ③ — Instructions ──
        self._step_intent = _StepHeader("3", "Instruction Mission")
        layout.addWidget(self._step_intent)

        self._intent_selector = IntentSelector()
        self._intent_selector.intent_submitted.connect(self._on_intent_submitted)
        self._filament_selector.nozzle_changed.connect(self._intent_selector.update_nozzle)
        self._filament_selector.nozzle_changed.connect(
            lambda d: setattr(self, "_current_nozzle_mm", d)
        )
        layout.addWidget(self._intent_selector)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ── Panneau centre ─────────────────────────────────────────────────────

    def _build_panel_center(self) -> QWidget:
        container = _GridWidget()
        container.setStyleSheet(f"background: {_THEME.palette()['BG_VOID']};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Analyse géométrique ──
        self._analysis_panel = AnalysisPanel()
        self._analysis_panel.force_full_requested.connect(self._on_force_full_analysis)
        layout.addWidget(self._analysis_panel)

        # ── Barre de progression ──
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: {BG_PANEL}; border: none; }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {ACCENT}, stop:1 {TELE_GREEN});
            }}
        """)
        layout.addWidget(self._progress_bar)

        # ── Viewer 3D ──
        self._viewer = Viewer3D()
        layout.addWidget(self._viewer, stretch=1)

        return container

    # ── Panneau droit ──────────────────────────────────────────────────────

    def _build_panel_right(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setFixedWidth(320)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG_PANEL}; border: none; border-left: 1px solid {INACTIVE}; }}
            QScrollBar:vertical {{ background: {BG_PANEL}; width: 4px; border: none; }}
            QScrollBar::handle:vertical {{ background: {INACTIVE}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: transparent; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        scroll.viewport().setStyleSheet(f"background: {BG_PANEL}; border: none;")

        self._params_preview = ParamsPreview()
        scroll.setWidget(self._params_preview)
        return scroll

    # ── Welcome dialog ─────────────────────────────────────────────────────

    def _show_welcome(self):
        import sys as _sys
        _meipass = getattr(_sys, "_MEIPASS", None)
        if _meipass:
            assets = Path(_meipass) / "assets"
        else:
            assets = Path(__file__).parent.parent / "assets"
        dlg = WelcomeDialog(self, assets_path=assets, show_whats_new=is_update())
        apply_title_bar_theme(dlg)
        dlg.exec()

    def _apply_theme(self):
        pal = _THEME.palette()
        # La règle QToolTip est posée ICI (sur le QMainWindow) car elle cascade
        # sur TOUS les widgets enfants — c'est le seul moyen fiable de forcer une
        # infobulle claire en thème clair (le stylesheet app global est ignoré
        # par les widgets qui ont leur propre stylesheet, ex. icônes topbar).
        self.setStyleSheet(
            f"QMainWindow {{ background: {pal['BG_VOID']}; }}"
            f"QToolTip {{ background-color: {pal['BG_ELEVATED']}; "
            f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['ACCENT']}; "
            f"padding: 4px 8px; border-radius: 3px; }}"
        )
        if hasattr(self, '_workspace'):
            self._workspace.setStyleSheet(f"background: {pal['BG_VOID']};")
        if hasattr(self, '_left_scroll'):
            self._left_scroll.setStyleSheet(f"""
                QScrollArea {{ background: {pal['BG_PANEL']}; border: none; border-right: 1px solid {pal['INACTIVE']}; }}
                QScrollBar:vertical {{ background: {pal['BG_PANEL']}; width: 6px; border: none; }}
                QScrollBar::handle:vertical {{ background: {pal['TEXT_SECONDARY']}; border-radius: 3px; min-height: 24px; }}
                QScrollBar::handle:vertical:hover {{ background: {pal['ACCENT']}; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: transparent; }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            """)
            self._left_scroll.viewport().setStyleSheet(f"background: {pal['BG_PANEL']}; border: none;")
            if self._left_scroll.widget():
                self._left_scroll.widget().setStyleSheet(f"background: {pal['BG_PANEL']};")
        # Panneau neoGen : sa palette est capturée à la construction -> on le
        # RECONSTRUIT avec le nouveau thème en préservant son état (pièce en
        # cours de modification, conversation, onglet).
        _panel = getattr(self, "_neogen_panel", None)
        if _panel is not None:
            from ui.components.neogen_dialog import NeoGenPanel
            etat = _panel.exporter_etat()
            actif = (hasattr(self, "_right_scroll")
                     and self._right_scroll.widget() is _panel)
            neuf = NeoGenPanel()
            neuf.importer_etat(etat)
            neuf.piece_ready.connect(self._on_stl_dropped)
            neuf.close_requested.connect(self._show_params_panel)
            if actif:
                self._right_scroll.takeWidget()
                self._right_scroll.setWidget(neuf)
            _panel.deleteLater()
            self._neogen_panel = neuf
        if hasattr(self, '_right_scroll'):
            self._right_scroll.setStyleSheet(f"""
                QScrollArea {{ background: {pal['BG_PANEL']}; border: none; border-left: 1px solid {pal['INACTIVE']}; }}
                QScrollBar:vertical {{ background: {pal['BG_PANEL']}; width: 6px; border: none; }}
                QScrollBar::handle:vertical {{ background: {pal['TEXT_SECONDARY']}; border-radius: 3px; min-height: 24px; }}
                QScrollBar::handle:vertical:hover {{ background: {pal['ACCENT']}; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: transparent; }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            """)
            self._right_scroll.viewport().setStyleSheet(f"background: {pal['BG_PANEL']}; border: none;")
        if hasattr(self, '_center_container'):
            self._center_container.setStyleSheet(f"background: {pal['BG_VOID']};")
            self._center_container.update()
        if hasattr(self, '_progress_bar'):
            self._progress_bar.setStyleSheet(f"""
                QProgressBar {{ background: {pal['BG_PANEL']}; border: none; }}
                QProgressBar::chunk {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {pal['ACCENT']}, stop:1 {pal['TELE_GREEN']});
                }}
            """)
        for attr in ('_step_config', '_step_stl', '_step_intent', '_step_analysis'):
            step = getattr(self, attr, None)
            if step:
                step.refresh_theme()
        self._topbar.refresh_theme()
        self._statusbar.refresh_theme()
        if hasattr(self, '_viewer'):
            self._viewer.refresh_theme()
        if hasattr(self, '_analysis_panel'):
            self._analysis_panel.refresh_theme()
        if hasattr(self, '_filament_selector'):
            self._filament_selector.refresh_theme()
        if hasattr(self, '_intent_selector'):
            self._intent_selector.refresh_theme()
        if hasattr(self, '_params_preview'):
            self._params_preview.refresh_theme()
        if hasattr(self, '_drop_zone'):
            self._drop_zone.refresh_theme()
        if getattr(self, '_carte_panel', None) is not None:
            self._carte_panel.refresh_theme()
        _ng = getattr(self, '_neogen_panel', None)
        if _ng is not None and hasattr(_ng, 'refresh_theme'):
            _ng.refresh_theme()
        apply_title_bar_theme(self)

    def _open_settings(self):
        from PySide6.QtCore import QPoint
        from core.prefs import PREFS as _PREFS
        _slicer_before = _PREFS.get("slicer_output", "bambu")
        dlg = SettingsDialog(self)
        apply_title_bar_theme(dlg)
        dlg.update_request.connect(self._on_settings_update_request)
        dlg.pro_activated.connect(self._topbar.refresh_pro)
        dlg.scanbar_anim_changed.connect(self._topbar.set_scanbar_animation)
        btn = self._topbar._settings_btn
        btn_br = btn.mapToGlobal(QPoint(btn.width(), btn.height()))
        # Position sous la roue crantee, mais bornee pour rester dans l'ecran
        # (la fenetre peut etre haute : elle defile et ne doit pas sortir en bas).
        from PySide6.QtGui import QGuiApplication
        dlg.adjustSize()
        avail = QGuiApplication.primaryScreen().availableGeometry()
        x = btn_br.x() - 400
        y = btn_br.y() + 4
        if y + dlg.height() > avail.bottom():
            y = max(avail.top() + 8, avail.bottom() - dlg.height() - 8)
        dlg.move(x, y)
        dlg.exec()
        # Changement de slicer de sortie → rebasculer le catalogue d'imprimantes
        # (chaque slicer a son propre catalogue : Bambu 11 marques, Orca 58, Prusa 32)
        _slicer_after = _PREFS.get("slicer_output", "bambu")
        if _slicer_after != _slicer_before and hasattr(self, '_filament_selector'):
            self._filament_selector.refresh_printers()
            # Le bouton d'export est sur la barre de statut → mettre à jour le slicer
            if hasattr(self, "_statusbar") and hasattr(self._statusbar, "_export_btn"):
                self._statusbar._export_btn.setText(_("export.btn", slicer=_slicer_name()))
        # Sync printer default → FilamentPrinterSelector
        new_printer = _PREFS.get("printer_default", "")
        if new_printer and hasattr(self, '_filament_selector'):
            self._filament_selector.set_printer(new_printer)
        # Pro peut avoir été activé dans les réglages → tuto Pro (une fois)
        self._maybe_launch_pro_tutorial()

    def _open_neogen(self):
        """Bascule la COLONNE DE DROITE entre les paramètres générés et le
        panneau neoGen : le viewer reste visible en entier pendant qu'on crée
        et qu'on itère sur une pièce. Instance réutilisée -> le contexte de
        modification (pièce en cours) survit aux allers-retours."""
        from ui.components.neogen_dialog import NeoGenPanel
        panel = getattr(self, "_neogen_panel", None)
        if panel is None:
            panel = NeoGenPanel()
            panel.piece_ready.connect(self._on_stl_dropped)
            panel.close_requested.connect(self._show_params_panel)
            panel.ouvrir_carte.connect(self._open_carte)   # depuis Personnalisation
            self._neogen_panel = panel
        if self._right_scroll.widget() is panel:
            self._show_params_panel()          # 2e clic sur NEOGEN = referme
            return
        self._right_scroll.takeWidget()        # détache SANS détruire
        self._right_scroll.setWidget(panel)
        self._right_scroll.setFixedWidth(400)  # un peu plus large pour le confort
        self._topbar.set_new_enabled(True)     # « Nouvelle pièce » actif dans neoGen
        if hasattr(panel, "refresh_theme"):
            panel.refresh_theme()              # thème courant (titres/onglets)

    def _open_carte(self):
        """Bascule la colonne de droite vers le personnalisateur de carte de
        visite + met le viewer en VUE DE DESSUS sur la carte (à plat)."""
        from ui.components.carte_visite_panel import CartePanel
        panel = getattr(self, "_carte_panel", None)
        if panel is None:
            panel = CartePanel()
            panel.apercu_pret.connect(self._viewer.afficher_carte)
            panel.exporter_demande.connect(self._exporter_carte)
            panel.convertir_litho_demande.connect(self._ouvrir_carte_en_litho)
            # déplacement d'un élément à la souris (viewer) -> maj dx/dy panneau
            self._viewer.element_deplace.connect(panel.deplacer_element)
            # clic sur un élément (viewer) -> encadre sa section dans la colonne
            self._viewer.element_selectionne.connect(panel.surligner_element)
            # touche Suppr sur un élément sélectionné -> le supprimer
            self._viewer.element_suppr_demande.connect(panel.supprimer_element)
            # fermeture (✕) : revenir au panneau neoGen (la carte vient de
            # Personnalisation), pas aux paramètres
            panel.close_requested.connect(self._open_neogen_depuis_carte)
            self._carte_panel = panel
        # « Ouvrir l'éditeur » doit TOUJOURS afficher l'éditeur (jamais rester
        # sans effet). Si déjà affiché, on se contente de rafraîchir l'aperçu.
        if self._right_scroll.widget() is not panel:
            self._right_scroll.takeWidget()
            self._right_scroll.setWidget(panel)
            self._right_scroll.setFixedWidth(400)
        self._topbar.set_new_enabled(True)     # « Nouvelle pièce » actif sur la carte
        panel.refresh_theme()                  # thème courant (évite labels invisibles)
        # Ré-initialisation PROPRE du viewer en mode carte : sans ça, si le
        # « _view_mode » était resté à « carte » (ou l'inverse), afficher_carte
        # sautait la 1re initialisation et la carte ne réapparaissait pas au
        # ré-affichage → « rien ne se passe » au 2e « Ouvrir l'éditeur ».
        try:
            self._viewer.quitter_mode_carte()
        except Exception:
            pass
        panel._planifier_apercu()              # (re)génère l'aperçu courant

    def _open_neogen_depuis_carte(self):
        """✕ de la carte -> revient au panneau neoGen (d'où on l'a ouverte)."""
        try:
            self._viewer.quitter_mode_carte()
        except Exception:
            pass
        panel = getattr(self, "_neogen_panel", None)
        if panel is not None:
            self._right_scroll.takeWidget()
            self._right_scroll.setWidget(panel)
            self._right_scroll.setFixedWidth(400)
            self._topbar.set_new_enabled(True)
        else:
            self._show_params_panel()

    def _ouvrir_carte_en_litho(self, spec, image_path):
        """« Convertir en lithophanie » : ouvre le MENU STANDARD de lithophanie
        (objet « Photo en relief / lithophanie ») pré-rempli avec l'image du design
        de la carte → l'utilisateur a accès à TOUS les réglages litho (ep_min,
        ep_max, cadre, debout, mode) et génère une vraie lithophanie image."""
        try:
            self._viewer.quitter_mode_carte()
        except Exception:
            pass
        self._open_neogen()
        panel = getattr(self, "_neogen_panel", None)
        if panel is not None and hasattr(panel, "_ouvrir_dans_biblio"):
            try:
                panel._ouvrir_dans_biblio(
                    "photo_relief",
                    {"image": str(image_path), "largeur": float(spec.largeur)})
            except Exception:
                logger.exception("Ouverture menu lithophanie échouée")

    def _exporter_carte(self, spec, couleurs=None, litho: bool = False):
        """« Exporter la carte » : au lieu d'un export direct (qui produisait un
        3MF illisible), on INJECTE la carte dans la scène comme si on avait glissé
        un fichier. L'utilisateur choisit ensuite imprimante/filament/paramètres
        puis « Générer le 3MF » → export correct par le pipeline habituel
        (multicouleur préservé via les corps du 3MF, ou lithophanie)."""
        self._charger_carte_dans_scene(spec, litho=litho)

    def _charger_carte_dans_scene(self, spec, litho: bool = False, litho_params=None):
        panel = getattr(self, "_carte_panel", None)
        carte_spec = None
        try:
            from core.neogen.carte_visite import generer_fichier_carte
            # APERÇU : carte FUSIONNÉE unique (une seule pièce visible dans le
            # viewer). Le vrai 3MF multicouleur n'est construit qu'à l'export
            # (« Générer le 3MF ») pour ne pas afficher un corps par couleur.
            chemin = generer_fichier_carte(spec, litho=litho, litho_params=litho_params)
            if not litho:
                import copy
                carte_spec = copy.deepcopy(spec)
        except Exception as exc:
            logger.exception("Préparation carte échouée")
            if panel:
                panel.set_statut("⚠ " + _("carte.export_err", msg=str(exc)[:80]))
            return
        # Quitter l'éditeur de carte + rendre la colonne aux paramètres, puis
        # charger la pièce dans le pipeline normal (analyse, intention, export).
        try:
            self._viewer.quitter_mode_carte()
        except Exception:
            pass
        self._show_params_panel()
        self._on_stl_dropped(Path(chemin))
        # APRÈS _on_stl_dropped (qui remet _carte_export_spec à None) : mémorise la
        # spec colorée pour que l'export final reconstruise le multicouleur.
        self._carte_export_spec = carte_spec
        if panel:
            panel.set_statut("✓ " + _("carte.dans_scene"))

    def _show_params_panel(self):
        """Rend la colonne de droite aux paramètres générés (état normal)."""
        if not hasattr(self, "_right_scroll"):
            return
        # De retour aux paramètres : « Nouvelle pièce » ne reste actif que si une
        # pièce est réellement chargée (sinon rien à réinitialiser).
        self._topbar.set_new_enabled(getattr(self, "_mesh", None) is not None)
        if self._right_scroll.widget() is self._params_preview:
            return
        self._right_scroll.takeWidget()
        self._right_scroll.setWidget(self._params_preview)
        self._right_scroll.setFixedWidth(320)

    def _open_diagnostic(self):
        from ui.components.defect_diagnostic import DefectDiagnosticDialog
        from PySide6.QtCore import QPoint

        # NB : le consentement au partage de photos n'est PLUS demandé ici. Il
        # ne concerne que l'envoi d'une vraie photo → il est demandé dans
        # DefectDiagnosticDialog._start_analysis, au moment d'analyser. Le mode
        # manuel (choix du défaut) n'envoie rien et n'en a donc pas besoin.

        # Dialog persistant : créé une seule fois, réutilisé → l'image et le
        # résultat d'analyse survivent à la fermeture/réouverture.
        if getattr(self, "_diag_dialog", None) is None:
            self._diag_dialog = DefectDiagnosticDialog(self)
            apply_title_bar_theme(self._diag_dialog)
            self._diag_dialog.corrections_ready.connect(self._apply_defect_corrections)
            self._diag_dialog.pro_state_changed.connect(self._topbar.refresh_pro)

        dlg = self._diag_dialog
        dlg.refresh_trial_label()   # compteur d'essais à jour à chaque ouverture
        # Largeur réelle (le dialog réutilisé peut avoir une width() périmée)
        dlg.adjustSize()
        w = dlg.sizeHint().width() or 460
        # S'ancrer sur le bouton réellement VISIBLE : hors Pro, _diag_btn est
        # masqué (c'est le CTA « neoSlice Pro » qui est affiché). Un widget caché
        # renvoie une géométrie (0,0) → la fenêtre se collait en haut à gauche.
        btn = self._topbar._diag_btn
        if not btn.isVisible():
            btn = self._topbar._pro_cta_btn
        btn_br = btn.mapToGlobal(QPoint(btn.width(), btn.height()))
        # Aligne le bord droit du dialog sous le bouton, puis borne à la fenêtre
        x = btn_br.x() - w
        win = self.frameGeometry()
        x = max(win.left() + 8, min(x, win.right() - w - 8))
        # Place le dialog (encore masqué) en laissant assez de hauteur pour qu'il
        # tienne à l'écran une fois agrandi (le diagnostic peut être haut). On NE
        # le déplace plus après affichage → pas de décalage de zone cliquable.
        y = btn_br.y() + 4
        scr = dlg.screen() or self.screen()
        if scr is not None:
            geo = scr.availableGeometry()
            reserve = int(geo.height() * 0.85)
            y = max(geo.top() + 8, min(y, geo.bottom() - 8 - reserve))
        dlg.move(x, y)
        dlg.exec()
        # Activation possible via le diagnostic (essais → paywall) → tuto Pro (une fois)
        self._maybe_launch_pro_tutorial()

    def _on_pro_cta(self):
        """Clic sur « neoSlice Pro » → ouvre DIRECTEMENT la fenêtre d'activation Pro.
        (Plus de diagnostic ni d'essais gratuits : le Diagnostic IA est réservé au Pro.)
        En pré-lancement : message « bientôt »."""
        from core import licensing
        if getattr(licensing, "PRO_COMING_SOON", False):
            self._show_coming_soon()
            return
        if licensing.est_pro():
            return
        from ui.components.paywall_dialog import PaywallDialog
        wall = PaywallDialog(self)
        wall.exec()
        if licensing.est_pro():
            self._topbar.refresh_pro()
        self._maybe_launch_pro_tutorial()

    def _show_coming_soon(self):
        """Annonce que neoSlice Pro arrive bientôt (aucun accès pour l'instant)."""
        from PySide6.QtWidgets import QMessageBox
        pal = _THEME.palette()
        box = QMessageBox(self)
        box.setWindowTitle("neoSlice Pro")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(_("pro.coming_soon_text"))
        box.setInformativeText(_("pro.coming_soon_info"))
        # Couleurs adaptées au thème (le bouton OK natif est illisible sinon)
        box.setStyleSheet(f"""
            QMessageBox {{ background: {pal['BG_PANEL']}; }}
            QMessageBox QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }}
            QPushButton {{
                background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                border: none; border-radius: 3px; padding: 5px 22px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
        """)
        apply_title_bar_theme(box)
        box.exec()

    def _open_pro_hub(self, initial_tab: str | None = None):
        """Ouvre l'Espace Pro (bobines, devis, clients…). Pro pur → paywall si non débloqué.
        `initial_tab` : clé d'onglet à ouvrir directement (ex. "spools")."""
        from core import licensing
        # Masquer la sphère Oen (fenêtre OpenGL au premier plan) pendant TOUT le
        # temps où un modal est ouvert : la laisser flotter au-dessus fait
        # planter Windows sous charge (crash « Espace Pro pendant l'install »).
        self._viewer.masquer_sphere_pour_modal(True)
        try:
            if not licensing.est_pro():
                from ui.components.paywall_dialog import PaywallDialog
                wall = PaywallDialog(self)
                wall.exec()
                if not licensing.est_pro():
                    return
                self._topbar.refresh_pro()

            from ui.components.pro_hub import ProHubDialog
            hub = ProHubDialog(self, devis_context=self._devis_context(),
                               initial_tab=initial_tab)
            apply_title_bar_theme(hub)
            # Le centrage sur l'écran est géré par ProHubDialog.showEvent (fiable).
            hub.exec()
        finally:
            self._viewer.masquer_sphere_pour_modal(False)
        self._maybe_launch_pro_tutorial()   # 1re activation → tuto Pro (une fois)

    def _devis_context(self) -> dict:
        """Contexte transmis au devis intégré (poids/durée/imprimante/pièce).
        Mêmes estimations que le panneau « EN RÉSUMÉ » → cohérence garantie."""
        from pathlib import Path
        est_weight_g = None
        est_time_h = None
        cfg = getattr(self, "_current_config", None)
        a = getattr(self, "_analysis", None)
        if cfg is not None and a is not None and getattr(a, "volume_cm3", 0) > 0:
            try:
                est_weight_g = cfg.estimated_filament_g(a.volume_cm3, getattr(a, "surface_area_cm2", 0.0))
                bb = getattr(a, "bounding_box_mm", None)
                height_mm = bb[2] if (bb and len(bb) > 2) else 20.0
                sup_ratio = (getattr(a, "estimated_support_ratio", 0.0)
                             if getattr(a, "support_needed", False) else 0.0)
                est_min = cfg.estimated_time_minutes(a.volume_cm3, height_mm,
                                                     support_ratio=sup_ratio)
                est_time_h = est_min / 60.0
            except Exception:
                est_weight_g = est_time_h = None

        printer = ""
        try:
            printer = self._filament_selector.current_printer() or ""
        except Exception:
            pass

        part = ""
        p = getattr(self, "_stl_path", None)
        if p:
            try:
                part = Path(p).stem
            except Exception:
                part = ""

        return {"est_weight_g": est_weight_g, "est_time_h": est_time_h,
                "printer_model": printer, "part_name": part}

    def _offer_spool_deduction(self, config):
        """Après export, propose de décompter le filament estimé d'une bobine du stock
        (Espace Pro). Sans effet si non-Pro ou aucune bobine du bon matériau."""
        try:
            from core import licensing
            if not licensing.est_pro():
                return
            from core.business import store
            a = getattr(self, "_analysis", None)
            if a is None or getattr(a, "volume_cm3", 0) <= 0:
                return
            grams = config.estimated_filament_g(a.volume_cm3, getattr(a, "surface_area_cm2", 0.0))
            if not grams or grams <= 0:
                return
            material = (self._filament_selector.current_filament() or "").strip()
            spools = store.spools_for_material(material)
            if not spools:
                return

            from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                           QComboBox, QPushButton)
            dlg = QDialog(self)
            dlg.setWindowTitle(_("spool.deduct_title"))
            apply_title_bar_theme(dlg)
            pal = _THEME.palette()
            dlg.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 16, 20, 16)
            lay.setSpacing(12)
            msg = QLabel(_("spool.deduct_prompt", g=f"{grams:.0f}"))
            msg.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
            msg.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            msg.setWordWrap(True)
            lay.addWidget(msg)

            combo = QComboBox()
            for s in spools:
                label = (f"{s.get('materiau','')} · {s.get('marque','')} "
                         f"{s.get('couleur_nom','')} — {float(s.get('poids_restant_g') or 0):.0f} g")
                combo.addItem(label.strip(), s["id"])
            combo.setStyleSheet(
                f"QComboBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
                f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 4px 8px; }}")
            lay.addWidget(combo)

            row = QHBoxLayout()
            row.addStretch()
            skip = QPushButton(_("spool.deduct_none"))
            skip.setCursor(Qt.PointingHandCursor)
            skip.clicked.connect(dlg.reject)
            ok = QPushButton(_("spool.save"))
            ok.setCursor(Qt.PointingHandCursor)
            ok.clicked.connect(dlg.accept)
            skip.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
                f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}")
            ok.setStyleSheet(
                f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
                f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}")
            row.addWidget(skip)
            row.addWidget(ok)
            lay.addLayout(row)

            if dlg.exec() == QDialog.Accepted:
                sid = combo.currentData()
                if sid:
                    store.consume(sid, grams)
                    s = store.get_spool(sid)
                    nm = f"{s.get('marque','')} {s.get('couleur_nom','')}".strip() if s else ""
                    self._statusbar.set_message(
                        _("spool.deduct_ok", g=f"{grams:.0f}", name=nm), TELE_GREEN)
        except Exception as exc:
            logger.warning(f"Décompte bobine ignoré : {exc}")

    def _build_color_section(self, layout, config, tmf_path, sep_fn, section_lbl_fn):
        """Ajoute (si Pro) la section de répartition des couleurs + décompte du stock
        DANS la fenêtre de succès d'export. Estime le grammage par couleur selon les
        slots détectés, prévisualise les couleurs dans le viewer, et décompte le
        stock au clic sur Valider (une seule fenêtre)."""
        try:
            from core import licensing
            if not licensing.est_pro():
                return False
            a = getattr(self, "_analysis", None)
            if a is None or getattr(a, "volume_cm3", 0) <= 0:
                return False
            from core.export.color_breakdown import compute as _compute_breakdown
            _carte_spec = getattr(self, "_carte_export_spec", None)
            if _carte_spec is not None:
                # Carte : un slot par couleur choisie (l'aperçu est fusionné, donc
                # _threemf_data ne porte pas les slots).
                from core.export.color_breakdown import from_carte as _bd_carte
                breakdown = _bd_carte(_carte_spec, config)
            else:
                breakdown = _compute_breakdown(self._threemf_data, self._mesh, a, config)
            if breakdown.total_g <= 0:
                return False
            material = (self._filament_selector.current_filament() or "").strip()

            def _spool_provider():
                from core.business import store
                return store.spools_for_material(material)

            def _register_cb():
                self._open_pro_hub(initial_tab="spools")

            def _on_confirm(rows, purge):
                from core.business import store
                deducted = 0
                total_g = 0.0
                extra = purge if len(rows) > 1 else 0.0
                for r in rows:
                    if r.spool_id and r.grams > 0:
                        g = r.grams + extra
                        store.consume(r.spool_id, g)
                        deducted += 1
                        total_g += g
                # Écrire les couleurs choisies dans le 3MF (best-effort).
                try:
                    from core.export.color_patch import patch_filament_colours
                    colors = [x.hex for x in sorted(rows, key=lambda x: x.slot)]
                    if len(colors) > 1 and tmf_path:
                        patch_filament_colours(tmf_path, colors)
                except Exception:
                    pass
                if deducted:
                    self._statusbar.set_message(
                        _("color_export.deduct_ok", n=deducted, g=f"{total_g:.0f}"), TELE_GREEN)
                return deducted

            # S'assurer que le viewer est en mode multi-objets (acteurs par objet
            # presents) pour que la previsualisation des couleurs par slot marche,
            # meme si une analyse (surplombs) avait bascule l'affichage.
            try:
                if breakdown.kind == "multiobject" and self._threemf_data is not None:
                    self._viewer._load_multipart_mesh(self._threemf_data)
            except Exception:
                pass

            layout.addWidget(sep_fn())
            layout.addWidget(section_lbl_fn(_("color_export.section")))
            from ui.components.color_export_dialog import ColorBreakdownWidget
            widget = ColorBreakdownWidget(
                self, breakdown, material, viewer=self._viewer,
                spool_provider=_spool_provider, register_cb=_register_cb,
                on_confirm=_on_confirm)
            layout.addWidget(widget)
            return True
        except Exception as exc:
            logger.warning(f"Section couleur ignorée : {exc}")
            return False

    def _apply_defect_corrections(self, result):
        """L'utilisateur a cliqué « Utiliser ces corrections » dans le dialog.
        On mémorise le résultat ; le bouton n'apparaît dans la barre de statut
        que si une config a déjà été générée (les deux conditions doivent être
        réunies). Sinon il apparaîtra dès la génération de la config."""
        self._pending_diag_result = result
        self._refresh_diag_button()

    def _refresh_diag_button(self):
        """Affiche le bouton corrections seulement si :
          1. une config a été générée (_current_config non nul), ET
          2. un diagnostic avec corrections a été accepté dans le dialog."""
        result = self._pending_diag_result
        has_config = getattr(self, "_current_config", None) is not None
        if has_config and result is not None:
            self._statusbar.set_diagnostic_result(result)
        else:
            self._statusbar.clear_diagnostic_result()

    def _do_apply_diagnostic(self, result):
        """Applique réellement les corrections du diagnostic au PrintConfig
        courant (déclenché par le bouton de la barre de statut)."""
        if getattr(self, "_current_config", None) is None:
            return
        from core.defect_detection.detector import DefectDetector
        DefectDetector().apply_remediation(self._current_config, result)
        if hasattr(self, "_params_preview") and self._analysis is not None:
            # Re-render des sections sans réinitialiser l'état du bouton diagnostic
            self._params_preview._render_sections(self._current_config, self._analysis)

    def _on_settings_update_request(self, version: str, url: str, notes: str):
        self._pending_update = (version, url, notes)
        self._show_update_dialog()

    def _show_welcome_first_launch(self):
        """Premier lancement : welcome → tutorial si pas encore vu."""
        self._show_welcome()
        if should_show_tutorial():
            QTimer.singleShot(300, self._show_tutorial)

    # ── Tutorial ───────────────────────────────────────────────────────────

    def _show_tutorial(self, mode: str = "full"):
        if self._tutorial is not None:
            try:
                self._tutorial.hide()
                self._tutorial.deleteLater()
            except RuntimeError:
                pass
            self._tutorial = None

        # Cible = [titre de section + contenu] pour que l'encadré du tutoriel
        # englobe aussi le titre (① Configuration, ② Import STL, ③ Mission…).
        # Cibles Pro : si la version Pro n'est pas active, les boutons DIAGNOSTIC IA
        # et ESPACE PRO sont masqués → on surligne le bouton « neoSlice Pro » visible
        # (le tutoriel explique alors le contenu Pro et invite à le débloquer).
        from core import licensing as _lic
        try:
            _is_pro = _lic.est_pro()
        except Exception:
            _is_pro = False
        _diag_anchor = self._topbar._diag_btn if _is_pro else self._topbar._pro_cta_btn
        _pro_anchor  = self._topbar._cost_btn if _is_pro else self._topbar._pro_cta_btn
        # Oen : cible = la sphere de l'assistant (bas gauche du viewer, fenetre
        # top-level) quand Pro ; sinon on pointe le bouton « neoSlice Pro » (upsell).
        # La sphere peut ne pas exister encore (creee au showEvent du viewer) -> None
        # -> l'etape s'affiche en encart centre (repli propre).
        _oen_anchor = (getattr(self._viewer, "_strands", None) if _is_pro
                       else self._topbar._pro_cta_btn)
        # Export multicouleur : pas d'element d'UI permanent -> encart centre quand Pro
        # (target None), et bouton Pro en surbrillance quand non-Pro (upsell).
        _color_anchor = None if _is_pro else self._topbar._pro_cta_btn
        targets = {
            "settings":  self._topbar._settings_btn,
            "config":    [self._step_config, self._filament_selector],
            "drop":      [self._step_stl, self._drop_zone],
            "intent":    [self._step_intent, self._intent_selector],
            "statusbar": self._statusbar._export_btn,
            "diag":      _diag_anchor,
            "pro":       _pro_anchor,
            "oen":       _oen_anchor,
            "color":     _color_anchor,
            # Les 4 boutons d'icones (pas le conteneur icon_group, qui est etire a
            # toute la hauteur de la barre -> cadre de surbrillance trop haut). L'union
            # de leurs rects = la hauteur reelle des icones (28 px), comme les autres.
            "topbar":    [self._topbar._settings_btn, self._topbar._feedback_btn,
                          self._topbar._help_btn, self._topbar._coffee_btn],
        }
        self._tutorial = TutorialOverlay(self, targets, mode=mode)
        self._tutorial.finished.connect(self._on_tutorial_finished)
        self._tutorial.show()
        self._tutorial.raise_()
        self._tutorial.activateWindow()

    def _on_tutorial_finished(self):
        self._tutorial = None

    def _maybe_launch_pro_tutorial(self):
        """Après activation de neoSlice Pro (fermeture de la fenêtre de remerciement),
        lance UNE SEULE FOIS le tuto post-activation : Diagnostic IA, Espace Pro, Oen
        et export multicouleur. Idempotent (pref `pro_tutorial_done`) → sans danger si
        appelé depuis plusieurs points de sortie Pro."""
        # L'état Pro a pu changer → montre/masque la sphère Oen (gating Pro).
        try:
            self._viewer.refresh_assistant_visibility()
        except Exception:
            pass
        try:
            from core import licensing
            if not licensing.est_pro():
                return
            from ui.components.welcome_dialog import _load_prefs, _save_prefs
            prefs = _load_prefs()
            if prefs.get("pro_tutorial_done"):
                return
            prefs["pro_tutorial_done"] = True
            _save_prefs(prefs)
        except Exception:
            return
        # Différé : laisse le(s) dialogue(s) Pro se fermer complètement avant l'overlay.
        QTimer.singleShot(350, lambda: self._show_tutorial(mode="pro"))

    # ── Handlers ───────────────────────────────────────────────────────────

    def _check_for_updates(self):
        from core.updater import check_for_update

        def _on_result(version: str | None, url: str, notes: str):
            if version:
                # Emit thread-safe signal — s'exécute toujours sur le main thread
                self._update_ready.emit(version, url or "", notes or "")

        check_for_update(_on_result)

    def _show_update_dialog_signal(self, version: str, url: str, notes: str):
        """Slot connecté à _update_ready — appelé sur le main thread."""
        self._pending_update = (version, url, notes)
        self._show_update_dialog()

    def _check_kb_update(self):
        """Vérifie en arrière-plan si une nouvelle base de connaissances d'Oen existe.
        Ne fait rien si Oen n'est pas installé ou hors Pro. 100% hors-ligne-safe :
        aucune popup si offline, aucune exception ne remonte."""
        try:
            from core import licensing
            from core.assistant.engine import AssistantEngine
            from core.assistant.installer import is_installed
            if not licensing.est_pro():
                return
            if not (is_installed() or AssistantEngine.available()):
                return
        except Exception:
            return
        import threading

        def _work():
            try:
                from core.assistant.kb_update import available_update
                info = available_update()
                if info and info.get("kb_version") and not info.get("incompatible_app"):
                    # Signal thread-safe -> repasse sur le main thread pour l'UI.
                    self._kb_update_ready.emit(str(info.get("kb_version")))
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _check_brands_update(self):
        """Bibliothèque de filaments par marque : vérifie et APPLIQUE en
        arrière-plan (contrairement à la KB d'Oen, pas de confirmation — la
        base est petite, bornée au chargement, et sans effet sur une config
        déjà générée). 100 % hors-ligne-safe."""
        import threading

        def _work():
            try:
                from core.filaments_maj import verifier_et_appliquer
                version = verifier_et_appliquer()
                if version:
                    self._brands_update_ready.emit(version)
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _on_brands_updated(self, version: str):
        """Nouvelle bibliothèque installée : rafraîchit la liste de filaments
        si l'utilisateur n'a pas encore validé son choix (sinon elle sera à
        jour au prochain passage — on ne change pas une sélection en cours)."""
        try:
            if not getattr(self._filament_selector, "_filament_done", True):
                self._filament_selector._populate_filaments()
            self._statusbar.set_message(
                f"Bibliothèque de filaments mise à jour ({version})", TELE_GREEN)
        except Exception:
            pass

    def _on_kb_update_available(self, version: str):
        """MAJ de la base d'Oen dispo : toast discret, clic -> gestionnaire de
        Modules (où vit désormais le bouton de mise à jour de la base)."""
        try:
            from ui.components.toast import show_toast
            show_toast(self, _("oen.kb_update_toast"), on_click=self._open_modules_mgr)
        except Exception:
            pass

    def _open_modules_mgr(self):
        from ui.components.modules_dialog import ModulesDialog
        ModulesDialog(self).exec()

    def _show_update_dialog(self):
        info = getattr(self, "_pending_update", None)
        if not info:
            return
        new_version, download_url, notes = info

        # Évite d'empiler plusieurs popups (ex: revérification depuis Paramètres)
        old = getattr(self, "_update_dlg", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
            self._update_dlg = None

        import queue as _queue
        import threading as _threading
        import tempfile
        import subprocess
        import urllib.request as _urlreq
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
        )
        from version import __version__ as cur_version

        pal = _THEME.palette()
        dlg = QDialog(self)
        dlg.setWindowTitle(_("update.title"))
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {pal['BG_PANEL']}; }}
            QLabel  {{ background: transparent; color: {pal['TEXT_PRIMARY']}; }}
            QProgressBar {{
                background: {pal['BG_SURFACE']}; border: 1px solid {pal['INACTIVE']};
                border-radius: 4px; height: 8px; text-align: center;
            }}
            QProgressBar::chunk {{ background: {pal['ACCENT']}; border-radius: 3px; }}
        """)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)

        # Titre
        title_lbl = QLabel(_("update.title"))
        title_lbl.setFont(QFont(FONT_MAIN, 13, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']};")
        lay.addWidget(title_lbl)

        # Corps
        body_lbl = QLabel(_("update.body", new=new_version, cur=cur_version))
        body_lbl.setFont(QFont(FONT_MAIN, 10))
        body_lbl.setTextFormat(Qt.RichText)
        body_lbl.setWordWrap(True)
        lay.addWidget(body_lbl)

        # Notes de version (optionnel)
        if notes:
            notes_title = QLabel(_("update.notes_label"))
            notes_title.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            notes_title.setStyleSheet(f"color: {pal['TEXT_LABEL']};")
            lay.addWidget(notes_title)
            notes_lbl = QLabel(notes)
            notes_lbl.setFont(QFont(FONT_MAIN, 9))
            notes_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
            notes_lbl.setWordWrap(True)
            lay.addWidget(notes_lbl)

        lay.addSpacing(4)

        # Zone progression (cachée au départ)
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFixedHeight(8)
        progress_bar.setTextVisible(False)
        progress_bar.hide()
        lay.addWidget(progress_bar)

        status_lbl = QLabel("")
        status_lbl.setFont(QFont(FONT_MAIN, 9))
        status_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.hide()
        lay.addWidget(status_lbl)

        lay.addSpacing(2)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        later_btn = QPushButton(_("update.btn_later"))
        later_btn.setFont(QFont(FONT_MAIN, 9))
        later_btn.setFixedHeight(32)
        later_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 0 14px;
            }}
            QPushButton:hover {{ color: {pal['TEXT_PRIMARY']}; border-color: {pal['TEXT_SECONDARY']}; }}
        """)
        later_btn.clicked.connect(dlg.reject)

        install_btn = QPushButton(_("update.btn_install"))
        install_btn.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        install_btn.setFixedHeight(32)
        install_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                border: none; border-radius: 4px; padding: 0 18px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['TEXT_LABEL']}; }}
        """)

        btn_row.addWidget(later_btn)
        btn_row.addStretch()
        btn_row.addWidget(install_btn)
        lay.addLayout(btn_row)

        # ── Logique de téléchargement ──────────────────────────────────────
        _q: _queue.Queue = _queue.Queue()
        _poll_timer = QTimer(dlg)

        def _download():
            import os as _os
            try:
                req = _urlreq.Request(
                    download_url,
                    headers={"User-Agent": f"neoSlice/{new_version}"}
                )
                # timeout 120s par opération socket — marge pour connexions lentes
                with _urlreq.urlopen(req, timeout=120) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    import sys as _sys
                    _upd_suffix = ".exe" if _sys.platform == "win32" else ".zip" if _sys.platform == "darwin" else ""
                    tmp = tempfile.mktemp(suffix=_upd_suffix, prefix="neoSlice_update_")
                    downloaded = 0
                    with open(tmp, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            pct = int(downloaded / total * 100) if total > 0 else -1
                            _q.put(("progress", pct))

                # ── Vérification CRITIQUE : téléchargement complet ? ──────────
                # Empêche de lancer un installateur tronqué (cause de l'erreur
                # "Application 16 bits non prise en charge" sur fichier incomplet).
                if total > 0 and downloaded != total:
                    try: _os.remove(tmp)
                    except Exception: pass
                    _mo_got, _mo_tot = downloaded // 1048576, total // 1048576
                    _q.put(("error",
                        f"Téléchargement incomplet ({_mo_got} Mo sur {_mo_tot} Mo). "
                        "Votre connexion a été interrompue — cliquez sur Réessayer."))
                    return

                # Sécurité supplémentaire : en-tête plateforme
                import sys as _sys2
                if _sys2.platform == "win32":
                    with open(tmp, "rb") as _chk:
                        magic = _chk.read(2)
                    if magic != b"MZ":
                        try: _os.remove(tmp)
                        except Exception: pass
                        _q.put(("error", "Fichier téléchargé invalide. Téléchargez manuellement depuis neoslice-ai.com."))
                        return
                else:
                    if _os.path.getsize(tmp) < 1_000_000:
                        try: _os.remove(tmp)
                        except Exception: pass
                        _q.put(("error", "Fichier téléchargé trop petit — téléchargement incomplet. Réessayez."))
                        return
                _q.put(("done", tmp))
            except Exception as exc:
                # Connexion coupée en cours de route → message clair (pas de stacktrace)
                _q.put(("error",
                    "Le téléchargement a échoué (connexion interrompue). "
                    "Vérifiez votre connexion et cliquez sur Réessayer."))

        def _on_poll():
            try:
                kind, val = _q.get_nowait()
                if kind == "progress":
                    if val >= 0:
                        progress_bar.setRange(0, 100)
                        progress_bar.setValue(val)
                        status_lbl.setText(_("update.downloading", pct=val))
                    else:
                        progress_bar.setRange(0, 0)
                        status_lbl.setText(_("update.downloading", pct="…"))
                elif kind == "done":
                    _poll_timer.stop()
                    progress_bar.setRange(0, 100)
                    progress_bar.setValue(100)
                    import sys as _sys
                    if _sys.platform == "darwin":
                        # macOS : ouvrir le .zip dans le Finder, guider l'utilisateur
                        import subprocess as _sp
                        try:
                            _sp.Popen(["open", "-R", val])
                        except Exception:
                            pass
                        status_lbl.setText(
                            "Décompresse le .zip → glisse neoSlice.app dans Applications"
                        )
                        status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']};")
                        install_btn.setText("Fermer")
                        install_btn.setEnabled(True)
                        install_btn.show()
                        later_btn.setEnabled(True)
                    else:
                        # Windows : lancer l'installeur puis MOURIR POUR DE BON.
                        # QApplication.quit() ne suffisait pas (ne tue pas le
                        # process si un thread non-daemon tourne → l'installateur
                        # voyait neoSlice.exe encore ouvert). os._exit garantit que
                        # neoSlice.exe a disparu avant la vérif « app ouverte ? »
                        # de l'installateur (+ CloseApplications=force côté .iss).
                        status_lbl.setText(_("update.installing"))
                        QTimer.singleShot(600, lambda: (
                            subprocess.Popen([val]),
                            self._hard_quit(0)
                        ))
                elif kind == "error":
                    _poll_timer.stop()
                    progress_bar.setRange(0, 100)
                    progress_bar.setValue(0)
                    progress_bar.hide()
                    # Message clair + rappel qu'on peut continuer sans mettre à jour
                    status_lbl.setWordWrap(True)
                    base_msg = str(val) if val else _("update.failed")
                    status_lbl.setText(
                        base_msg + "\n\nVous pouvez continuer à utiliser le logiciel : "
                        "cliquez sur « Plus tard »."
                    )
                    status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']};")
                    install_btn.setText(_("update.btn_retry"))
                    install_btn.setEnabled(True)
                    install_btn.show()
                    later_btn.setEnabled(True)
                    later_btn.setText("Plus tard")
                    dlg.adjustSize()
            except _queue.Empty:
                pass

        def _start_download():
            install_btn.setEnabled(False)
            install_btn.hide()
            # "Plus tard" reste cliquable : l'utilisateur n'est jamais piégé,
            # même pendant un téléchargement qui traîne ou échoue.
            later_btn.setEnabled(True)
            later_btn.setText(_("update.btn_later"))
            progress_bar.show()
            status_lbl.setText(_("update.downloading", pct=0))
            status_lbl.show()
            dlg.adjustSize()
            _poll_timer.timeout.connect(_on_poll)
            _poll_timer.start(80)
            _threading.Thread(target=_download, daemon=True).start()

        install_btn.clicked.connect(_start_download)

        # Non-modal : la fenêtre principale reste TOUJOURS utilisable, même si
        # la mise à jour échoue/bloque → l'utilisateur n'est jamais coincé au
        # lancement. À la fermeture, on coupe le timer (évite d'accéder à des
        # widgets détruits si un téléchargement tourne encore en fond).
        def _on_dlg_finished(*_):
            try:
                _poll_timer.stop()
            except Exception:
                pass
        dlg.finished.connect(_on_dlg_finished)

        apply_title_bar_theme(dlg)
        self._update_dlg = dlg          # garde une référence (sinon GC en non-modal)
        dlg.setModal(False)
        dlg.show()

    def _on_new_piece(self):
        self._analysis_timeout.stop()
        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.quit()
            self._analysis_thread.wait(2000)
        self._mesh = None
        self._original_mesh = None
        self._analysis = None
        self._current_config = None
        self._current_selection = None
        self._pending_diag_result = None   # nouvelle pièce → diagnostic obsolète

        self._viewer.stop_auto_rotate()
        # Quitter un éventuel mode carte/neoGen : coupe le drag d'éléments et
        # réarme l'affichage normal avant d'effacer la scène.
        try:
            self._viewer.quitter_mode_carte()
        except Exception:
            pass
        self._viewer.reset()
        self._analysis_panel.reset()
        self._drop_zone.reset()
        self._intent_selector.set_locked(True)
        self._intent_selector.reset_selection()
        self._params_preview.reset()
        # Revenir à la colonne des paramètres (referme neoGen / l'éditeur de carte
        # s'ils étaient ouverts) → scène réinitialisée de PARTOUT.
        self._show_params_panel()

        self._step_stl.set_pending()
        self._step_intent.set_pending()
        self._topbar.set_has_stl(False)
        self._statusbar.set_export_enabled(False)
        self._statusbar.clear_diagnostic_result()
        self._statusbar.set_message(_("status.ready"), TELE_GREEN)

    def _maj_prerequis_generation(self):
        """« Générer configuration » n'est actif que si l'étape ① (imprimante,
        filament, plateau) est validée — voir set_prerequis."""
        try:
            self._intent_selector.set_prerequis(self._filament_selector.est_valide())
        except Exception:
            pass

    def _on_stl_dropped(self, path: Path):
        """Démarre le chargement STL en thread — feedback immédiat, zéro freeze UI."""
        logger.info(f"STL reçu : {path}")
        self._stl_path = path
        # Lithophanie neoGen : reconnue au NOM du fichier -> son profil
        # d'impression sera appliqué automatiquement à la génération. L'UI le
        # MONTRE : choix « Lithophanie » sélectionné + groupe Résistance grisé
        # (volontaire) + bannière récap au-dessus du viewer. Tout revient à la
        # normale au chargement d'un autre fichier.
        self._est_lithophanie = path.stem.lower().startswith("lithophanie")
        try:
            self._intent_selector.set_lithophanie(self._est_lithophanie)
            self._analysis_panel.show_litho_banner(self._est_lithophanie)
            self._maj_prerequis_generation()
        except Exception:
            pass

        # ── Feedback instantané (< 1 ms) ────────────────────────────────────
        self._step_stl.set_active()
        self._viewer.stop_auto_rotate()
        # L'overlay du viewer élide lui-même le texte à la largeur du cadre.
        self._viewer.set_loading(True, f"CHARGEMENT — {path.name}")
        self._statusbar.set_message(f"Chargement — {path.name}", AMBER)
        self._original_mesh = None

        # Nouveau fichier : purger immédiatement l'état du précédent, sinon la
        # colonne de droite (paramètres) et l'analyse gardent les anciennes valeurs
        # jusqu'à la fin de la nouvelle analyse.
        self._threemf_data = None
        self._analysis = None
        self._current_config = None
        self._current_selection = None
        self._carte_export_spec = None   # tout nouveau fichier annule le mode carte multicouleur
        try:
            self._params_preview.reset()
            self._analysis_panel.reset()
        except Exception:
            pass

        # ── Annuler un chargement précédent si encore actif ─────────────────
        if self._stl_load_worker:
            try:
                self._stl_load_worker.mesh_loaded.disconnect()
                self._stl_load_worker.error.disconnect()
            except Exception:
                pass
        if self._stl_load_thread:
            if self._stl_load_thread.isRunning():
                self._stl_load_thread.quit()
                # Ne pas wait() — le thread Python continue jusqu'à la fin de load_stl().
                # On garde la référence dans _zombie_load_threads pour éviter que Python
                # GC le QThread pendant qu'il tourne (→ crash VTK/Qt).
                if not hasattr(self, '_zombie_load_threads'):
                    self._zombie_load_threads = []
                self._zombie_load_threads.append(self._stl_load_thread)
            # Nettoyer les zombies déjà terminés
            if hasattr(self, '_zombie_load_threads'):
                self._zombie_load_threads = [
                    t for t in self._zombie_load_threads if t.isRunning()
                ]

        # ── Lancer load_stl() dans un thread dédié ──────────────────────────
        self._stl_load_thread = QThread()
        self._stl_load_worker = STLLoadWorker(path)
        self._stl_load_worker.moveToThread(self._stl_load_thread)

        self._stl_load_thread.started.connect(self._stl_load_worker.run)
        self._stl_load_worker.mesh_loaded.connect(self._on_stl_load_done)
        self._stl_load_worker.error.connect(self._on_stl_load_error)
        self._stl_load_worker.mesh_loaded.connect(self._stl_load_thread.quit)
        self._stl_load_worker.error.connect(self._stl_load_thread.quit)

        self._stl_load_thread.start()

    def _on_stl_load_done(self, mesh):
        """Appelé dans le thread principal quand load_stl() est terminé."""
        from core.geometry.threemf_data import ThreeMFData
        path = self._stl_path

        if isinstance(mesh, ThreeMFData):
            self._threemf_data = mesh
            self._mesh = mesh.combined_mesh
            logger.info(f"3MF multicolore : {mesh.summary()}")
        else:
            self._threemf_data = None
            self._mesh = mesh

        self._original_mesh = self._mesh.copy()

        # Passer ThreeMFData au viewer pour affichage multi-acteurs colorés,
        # ou le mesh simple pour affichage normal.
        self._viewer.load_mesh(mesh)

        # Pour les 3MF multi-objets : le viewer a arrangé les pièces en une grille compacte
        # et mis à jour viewer._mesh avec ce mesh normalisé (~200mm vs 2371mm original).
        # Mettre à jour self._mesh pour que colorize_overhangs et l'export utilisent
        # le mesh de la bonne taille (face count identique = même meshes, positions différentes).
        if isinstance(mesh, ThreeMFData):
            _vm = getattr(self._viewer, '_mesh', None)
            if _vm is not None and len(_vm.faces) == len(self._mesh.faces):
                self._mesh = _vm
                logger.debug(f"main_window._mesh mis à jour avec viewer._mesh arrangé ({len(_vm.faces)} faces)")

        self._topbar.set_has_stl(True)

        try:
            from ui.components.welcome_dialog import _load_prefs, _save_prefs
            _p = _load_prefs(); _p["last_stl"] = str(path); _save_prefs(_p)
        except Exception:
            pass
        self._drop_zone.set_recent_file(path)
        # Miniature d'aperçu dans la zone d'import (différée : le rendu hors-écran
        # ne doit pas bloquer la fin du chargement).
        QTimer.singleShot(120, lambda p=path: self._update_drop_thumbnail(p))
        self._statusbar.set_message(_("status.loading", name=path.name), AMBER)
        self._start_analysis()

    def _update_drop_thumbnail(self, path):
        """Génère et affiche la miniature du modèle dans la zone d'import."""
        try:
            from core.geometry.thumbnail import make_thumbnail_png
            png = make_thumbnail_png(path, mesh=self._mesh, dark=_THEME.is_dark())
            if png:
                self._drop_zone.set_thumbnail(png)
        except Exception as e:
            logger.debug(f"Miniature non générée : {e}")

    def _on_stl_load_error(self, msg: str):
        """Appelé si load_stl() lève une exception."""
        self._viewer.set_loading(False)
        self._statusbar.set_message(f"Erreur chargement : {msg}", ERROR_RED)
        logger.error(f"STL load error : {msg}")

    def _on_force_full_analysis(self):
        """« Forcer l'analyse complète » (panneau) : relance l'analyse de la
        pièce courante en ignorant la décision Auto/Économique — l'utilisateur
        assume le temps de calcul."""
        if getattr(self, "_mesh", None) is None:
            return
        self._force_full_next = True
        self._start_analysis()

    def _start_analysis(self):
        self._analysis_timeout.stop()
        if self._analysis_thread and self._analysis_thread.isRunning():
            if self._analysis_worker:
                try:
                    self._analysis_worker.analysis_complete.disconnect()
                    self._analysis_worker.error.disconnect()
                    self._analysis_worker.progress.disconnect()
                except Exception:
                    pass
            self._analysis_thread.quit()
            self._analysis_thread.wait(2000)

        self._analysis_panel.set_loading()
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._statusbar.set_export_enabled(False)
        self._viewer.set_loading(True, "ANALYSE DE LA PIÈCE EN COURS...")
        self._intent_selector.set_loading(True)

        self._analysis_thread = QThread()
        _force = bool(getattr(self, "_force_full_next", False))
        self._force_full_next = False          # one-shot (posé par « Forcer l'analyse »)
        self._analysis_worker = AnalysisWorker(
            self._mesh,
            nozzle_diameter_mm=self._current_nozzle_mm,
            is_color_assembly=bool(getattr(self._threemf_data, "is_color_assembly", False)),
            force_full=_force,
        )
        self._analysis_worker.moveToThread(self._analysis_thread)

        self._analysis_thread.started.connect(self._analysis_worker.run)
        self._analysis_worker.progress.connect(self._on_analysis_progress)
        self._analysis_worker.analysis_complete.connect(self._on_analysis_complete)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_worker.analysis_complete.connect(self._analysis_thread.quit)
        self._analysis_worker.error.connect(self._analysis_thread.quit)

        self._analysis_thread.start()
        self._analysis_timeout.start(60_000)  # 60s max

    def _on_analysis_timeout(self):
        logger.error("Analyse timeout (60s) — thread forcé à quitter")
        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.quit()
            self._analysis_thread.wait(1000)
        self._on_analysis_error(_("status.analysis_timeout"))

    def _on_analysis_progress(self, percent: int, message: str):
        self._progress_bar.setValue(percent)
        self._statusbar.set_message(message, AMBER)
        self._analysis_panel.set_progress(percent, message)

    def _on_analysis_complete(self, report: AnalysisReport):
        self._analysis_timeout.stop()
        # La pièce a été réinitialisée (Nouvelle pièce) pendant que l'analyse
        # tournait → ce résultat est obsolète, on l'ignore pour ne pas re-remplir
        # le panneau qu'on vient de vider.
        if self._mesh is None:
            return
        self._analysis = report
        logger.info(f"Analyse terminée en {report.analysis_time_ms:.0f}ms")

        self._analysis_panel.update_from_report(report)
        self._progress_bar.hide()
        self._viewer.set_loading(False)
        self._intent_selector.set_loading(False)
        self._intent_selector.enable_generate(True)

        self._step_stl.set_done()
        self._step_intent.set_active()
        self._intent_selector.set_locked(False)

        # Pré-sélection automatique des presets selon l'analyse
        self._intent_selector.auto_select_from_analysis(report)

        _is_multipart = self._threemf_data is not None and self._threemf_data.object_count > 1
        # Pour les 3MF multi-objets : toujours coloriser — l'analyse du mesh combiné
        # sous-estime les surplombs (plate_tol trop grande car z_height = hauteur de la plus
        # grande pièce, excluant les surplombs des petites pièces).
        if _is_multipart or report.overhang_severity > 0.0 or report.support_needed or report.overhang_ratio > 0.0:
            try:
                if _is_multipart:
                    colors = self._build_multipart_overhang_colors()
                else:
                    ov = report.overhang_result
                    if ov is not None:
                        visu_ov = ov.__class__(
                            severity=ov.severity,
                            overhang_ratio=ov.overhang_ratio,
                            projected_ratio=ov.projected_ratio,
                            max_angle_deg=ov.max_angle_deg,
                            critical_face_mask=(
                                ov.display_mask if ov.display_mask is not None
                                else ov.critical_face_mask
                            ),
                            has_floating_regions=ov.has_floating_regions,
                            display_mask=ov.display_mask,
                        )
                        colors = overhang_face_colors(self._mesh, visu_ov)
                    else:
                        ov = analyze_overhangs(self._mesh, smooth=False, check_floating=False)
                        colors = overhang_face_colors(self._mesh, ov)
                self._viewer.colorize_overhangs(self._mesh, colors)
            except Exception:
                logger.exception("colorize_overhangs échoué")

        self._viewer.start_auto_rotate()

        # Barres de fragilité flottantes pour les 3MF multi-groupes
        if self._threemf_data is not None and self._threemf_data.plate_count > 1:
            try:
                self._show_fragility_bars_multipart()
            except Exception:
                logger.exception("Barres fragilité multipart échouées")

        oh_pct = report.overhang_severity * 100
        oh_tag = _("status.oh_tag", pct=oh_pct) if oh_pct > 0.1 else ""
        self._statusbar.set_message(
            _("status.analysis_ok", ms=report.analysis_time_ms, oh_tag=oh_tag),
            TELE_GREEN,
        )

    def _build_multipart_overhang_colors(self) -> np.ndarray:
        """Analyse les surplombs par objet séparément — symétrie garantie.

        Chaque objet est analysé indépendamment dans son propre repère (Z_min→0).
        Pour les objets de taille similaire (copies du même modèle), on utilise
        l'analyse qui détecte le MOINS de surplombs et on l'applique à toutes
        les copies similaires — élimine les asymétries dues aux différences mineures
        de maillage entre copies sauvegardées différemment.
        """
        from core.geometry.overhang_detector import analyze_overhangs, overhang_face_colors

        td = self._threemf_data
        per_obj: list[tuple] = []  # (mesh, colors, overhang_ratio, viewer_n_faces)

        # Face count corrigé du viewer (même logique que _load_multipart_mesh)
        _raw_fc  = [len(o.mesh.faces) for o in td.objects]
        _min_fc  = min(_raw_fc) if _raw_fc else 0

        for obj in td.objects:
            orig_fc = len(obj.mesh.faces)
            dev = abs(orig_fc - _min_fc) / max(_min_fc, 1) if _min_fc > 0 else 0
            viewer_fc = _min_fc if (dev > 0 and dev < 0.05) else orig_fc

            m = obj.mesh.copy()
            if not np.allclose(obj.transform, np.eye(4)):
                m.apply_transform(obj.transform)
            m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])

            try:
                ov = analyze_overhangs(m, smooth=True, check_floating=False)
                mask = ov.display_mask if ov.display_mask is not None else ov.critical_face_mask
                visu_ov = ov.__class__(
                    severity=ov.severity, overhang_ratio=ov.overhang_ratio,
                    projected_ratio=ov.projected_ratio, max_angle_deg=ov.max_angle_deg,
                    critical_face_mask=mask, has_floating_regions=False,
                    display_mask=ov.display_mask,
                )
                colors = overhang_face_colors(m, visu_ov)
                # Adapter au face count du viewer si correction appliquée
                if len(colors) != viewer_fc:
                    if len(colors) > viewer_fc:
                        colors = colors[:viewer_fc]
                    else:
                        extra = viewer_fc - len(colors)
                        pad = np.zeros((extra, 4), dtype=np.uint8)
                        pad[:, 1] = 128; pad[:, 3] = 255
                        colors = np.vstack([colors, pad])
                per_obj.append((m, colors, float(ov.overhang_ratio), viewer_fc))
            except Exception:
                safe = np.zeros((viewer_fc, 4), dtype=np.uint8)
                safe[:, 1] = 128; safe[:, 3] = 255
                per_obj.append((m, safe, 0.0, viewer_fc))

        if not per_obj:
            return np.zeros((len(self._mesh.faces), 4), dtype=np.uint8)

        # Note: le masquage spatial par negative_part est retiré car il supprimait
        # aussi les overhangs des bras (le bbox du modifier couvre tout le Groot).
        # Le filtre internal_flat dans analyze_overhangs (nz < -0.92 à mi-hauteur)
        # + l'utilisation du mesh propre (min faces) suffisent pour éliminer le cylindre.

        all_colors = []
        for i, (m, colors, ratio, nf) in enumerate(per_obj):
            all_colors.append(colors)

        return np.vstack(all_colors) if all_colors else np.zeros((len(self._mesh.faces), 4), dtype=np.uint8)

    def _show_fragility_bars_multipart(self) -> None:
        """Calcule la fragilité par groupe de pièces et affiche les barres flottantes."""
        import math, numpy as np
        from core.geometry.fragility_detector import detect_fragility
        import trimesh as _trimesh

        td  = self._threemf_data
        objs = td.objects

        # ── Grouper les objets par grille spatiale (même algo que _add_multipart_plates) ──
        orig_pos = [[float(o.transform[0, 3]), float(o.transform[1, 3])] for o in objs]

        groups: dict[tuple, list[int]] = {}
        for grid in (256, 300, 350, 400, 500):
            groups = {}
            for i, (x, y) in enumerate(orig_pos):
                key = (math.floor(x / grid), math.floor(y / grid))
                groups.setdefault(key, []).append(i)
            if len(groups) == td.plate_count:
                break

        if len(groups) < 2:
            return  # pas assez de groupes pour les barres

        # Transforms Bambu appliqués — pour le calcul de fragilité (espace absolu)
        transformed = []
        for o in objs:
            m = o.mesh.copy()
            if not np.allclose(o.transform, np.eye(4)):
                m.apply_transform(o.transform)
            transformed.append(m)

        # Centres viewer-space précalculés par le viewer lors du rendu (post-arrange + centrage)
        _viewer_obj_bounds = getattr(self._viewer, "_object_viewer_bounds", [])

        bars = []
        for pid, (tile, idxs) in enumerate(groups.items()):
            # Mesh du groupe (transforms Bambu appliqués, positions absolues)
            group_meshes = [transformed[i] for i in idxs]
            group_combined = _trimesh.util.concatenate(group_meshes)

            # Fragilité — normaliser Z_min → 0
            try:
                nozzle_d = float(getattr(self, "_current_nozzle_diameter", 0.4))
                group_combined.apply_translation(
                    [0.0, 0.0, -float(group_combined.bounds[0][2])]
                )
                fr = detect_fragility(group_combined, nozzle_diameter_mm=nozzle_d)
                score = float(fr.severity)
            except Exception:
                score = 0.0

            # Position viewer-space : centroïde des bounds des objets du groupe.
            # _object_viewer_bounds est stocké par le viewer après arrange + centrage global,
            # ce qui garantit l'alignement parfait avec les acteurs affichés.
            try:
                valid = [_viewer_obj_bounds[i] for i in idxs if i < len(_viewer_obj_bounds)]
                if not valid:
                    raise ValueError("no viewer bounds for group")
                # Barycentre de l'union des bounds — correct même si le groupe
                # mélange objets de tailles très différentes (ex: boîte + sphère)
                cx = (min(v["xmin"] for v in valid) + max(v["xmax"] for v in valid)) / 2
                cy = (min(v["ymin"] for v in valid) + max(v["ymax"] for v in valid)) / 2
                cz = max(v["cz"] for v in valid)
            except Exception:
                b = group_combined.bounds
                cx = (float(b[0][0]) + float(b[1][0])) / 2
                cy = (float(b[0][1]) + float(b[1][1])) / 2
                cz = float(b[1][2])

            bars.append({
                "cx": cx, "cy": cy, "cz": cz,
                "score": score,
                "label": "Fragilité",
            })

        self._viewer.show_fragility_bars(bars)

        # Mettre à jour la jauge principale — mode "indépendant par lot"
        max_score = max((b["score"] for b in bars), default=0.0)
        if hasattr(self, "_analysis_panel"):
            self._analysis_panel.set_fragility_independent(max_score)

    def _on_analysis_error(self, message: str):
        self._analysis_timeout.stop()
        self._progress_bar.hide()
        self._viewer.set_loading(False)
        self._intent_selector.set_loading(False)
        # Masquer les traces internes VTK/qhull — afficher un message utilisateur propre
        vtk_keywords = ("qhull", "vtk", "while executing", "options selected", "thread analysis")
        first_line = (message.splitlines()[0] if message else "erreur inconnue").strip()
        if any(kw in first_line.lower() for kw in vtk_keywords):
            first_line = "Avertissement géométrique interne (non critique) — résultats disponibles"
        self._statusbar.set_message(_("status.analysis_err", msg=first_line), ERROR_RED)

    def _on_printer_confirmed(self):
        self._statusbar.set_message(_("status.printer_confirmed"), TELE_GREEN)

    def _on_filament_printer_changed(self, printer: str, filament: str):
        self._current_printer = printer
        self._current_filament = filament
        self._current_nozzle_mm = self._filament_selector.current_nozzle_diameter_mm()

    def _on_filament_confirmed(self):
        """Étapes ①② validées → on déverrouille la drop zone."""
        self._drop_zone.set_locked(False)
        self._step_config.set_done()
        self._step_stl.set_active()
        self._statusbar.set_message(
            "Configuration validée — glissez votre fichier STL",
            TELE_GREEN,
        )

    def _on_intent_submitted(self, result: SelectionResult):
        if self._mesh is None:
            self._statusbar.set_message("Chargez d'abord un fichier STL.", AMBER)
            return

        logger.info(f"Instructions : {result.human_summary!r}")
        self._show_params_panel()   # neoGen ouvert ? -> rend la colonne aux paramètres
        self._params_preview.set_loading(True)
        self._analysis_panel.set_generation_busy()

        analysis = self._analysis or AnalysisReport()

        try:
            filament = getattr(self, "_current_filament", "")
            printer  = getattr(self, "_current_printer", "")
            config = self._parameter_engine.generate(
                result.intent_profile, analysis,
                filament_name=filament,
                printer_name=printer,
                nozzle_diameter_mm=self._current_nozzle_mm,
            )

            # Appliquer les surcharges directes du sélecteur (support, brim…)
            for attr, value in result.config_overrides.items():
                if hasattr(config, attr):
                    setattr(config, attr, value)

            # Pièce lithophanie (neoGen) : profil d'impression AUTOMATIQUE —
            # remplissage 100 %, 4 parois, couche fine, parois lentes, brim.
            # Prime sur l'intention : sans lui, le motif de remplissage se
            # voit par transparence et ruine la photo.
            if getattr(self, "_est_lithophanie", False):
                from core.parameters.parameter_engine import (
                    appliquer_profil_lithophanie)
                config = appliquer_profil_lithophanie(config)

            config.neoslice_intent_text = result.human_summary

            self._current_config = config
            self._current_selection = result

            self._params_preview.update_from_config(config, analysis)
            # Config (re)générée → réévalue l'affichage du bouton corrections.
            # Si un diagnostic est en attente, le bouton apparaît maintenant ;
            # la nouvelle config ne contient pas encore les corrections → bouton
            # actionnable à nouveau.
            self._refresh_diag_button()
            self._analysis_panel.set_generation_active()
            # (l'info lithophanie n'est PAS répétée ici : la bannière cyan
            # au-dessus du viewer récapitule déjà tout le profil)
            self._analysis_panel.show_material_warnings(
                _compute_material_warnings(filament, printer, analysis))
            self._statusbar.set_message(
                f"Configuration générée — profil : {config.neoslice_profile_name}",
                TELE_GREEN,
            )
            self._statusbar.set_export_enabled(True)
            self._step_intent.set_done()
        except Exception as e:
            logger.exception("Erreur génération paramètres")
            self._statusbar.set_message(_("status.gen_err", msg=e), ERROR_RED)

    def _on_export_requested(self):
        if not hasattr(self, "_current_config") or self._mesh is None:
            return

        # Lire l'imprimante/filament ACTUELLEMENT sélectionnés (source de vérité) :
        # l'utilisateur a pu changer d'imprimante sans re-valider → `self._current_*`
        # (mis à jour par signal) pouvait être périmé (ex. Ender-3 V2 au lieu de K2 Pro).
        try:
            _sel = self._filament_selector
            _cp = _sel.current_printer()
            if _cp:
                self._current_printer = _cp
            _cf = _sel.current_filament()
            if _cf:
                self._current_filament = _cf
            self._current_nozzle_mm = _sel.current_nozzle_diameter_mm()
        except Exception:
            pass

        config = self._current_config
        profile_name = f"neoSlice - {config.neoslice_profile_name.replace('_', ' ').title()}"

        ok, result_msg, _profile_path = self._profile_installer.install_profile(
            config, profile_label=profile_name, printer_ui_name=self._current_printer
        )

        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QStandardPaths
        stl_stem = getattr(self, "_stl_path", None)
        stl_stem = stl_stem.stem if stl_stem else "model"
        _exp_folder = PREFS.get("export_folder", "")
        if _exp_folder and Path(_exp_folder).is_dir():
            downloads = Path(_exp_folder)
        else:
            _dl_str = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DownloadLocation)
            downloads = Path(_dl_str) if _dl_str else Path.home()
        default_name = str(downloads / f"{stl_stem}_neoslice_output.3mf")
        import sys as _sys
        if _sys.platform == "darwin":
            # macOS : le dialog natif ignore le dossier suggéré (utilise le dernier visité)
            # On force le dossier via QFileDialog objet
            _dlg = QFileDialog(self, "Enregistrer le fichier .3MF",
                               default_name, "Fichiers 3MF (*.3mf)")
            _dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            _dlg.setDirectory(str(downloads))
            _dlg.selectFile(f"{stl_stem}_neoslice_output.3mf")
            output_path = _dlg.selectedFiles()[0] if _dlg.exec() else ""
        else:
            output_path, _filter = QFileDialog.getSaveFileName(
                self, "Enregistrer le fichier .3MF",
                default_name, "Fichiers 3MF (*.3mf)",
            )
        if not output_path:
            return

        try:
            nozzle_mm = self._filament_selector.current_nozzle_diameter_mm()

            # CARTE MULTICOULEUR : reconstruire un vrai 3MF avec un slot par couleur,
            # au format du slicer de sortie choisi (la spec colorée a été mémorisée).
            _carte_spec = getattr(self, "_carte_export_spec", None)
            if _carte_spec is not None:
                from core.export.carte_multicouleur import build_carte_multicouleur
                path = build_carte_multicouleur(
                    _carte_spec, config, Path(output_path),
                    self._current_printer, self._current_filament, nozzle_mm)
                logger.info(f"3MF carte multicouleur exporté : {path}")
                selection = getattr(self, "_current_selection", None)
                self._show_success_dialog(config, selection, path)
                if ok:
                    self._statusbar.set_message(_("status.export_ok"), TELE_GREEN)
                else:
                    self._statusbar.set_message(_("status.export_ok_warn", msg=result_msg), AMBER)
                return

            # Pour les 3MF en entrée : injecter les paramètres dans le fichier original.
            # NE PAS reconstruire le 3MF depuis zéro — ça perd la structure (modifier_part,
            # components, metadata) et les Generic-Cubes deviennent des solides dans BS.
            _src_3mf = getattr(self, "_stl_path", None)
            _is_3mf_input = bool(_src_3mf and str(_src_3mf).lower().endswith(".3mf")
                                  and self._threemf_data is not None)
            logger.info(f"[EXPORT] src={_src_3mf} is_3mf={_is_3mf_input} threemf={self._threemf_data is not None}")

            from core.prefs import PREFS as _PREFS
            from data.printers import is_catalogue_model as _is_cat_model
            if _PREFS.get("slicer_output", "bambu") == "prusa":
                # Sortie PrusaSlicer : format 3MF différent → toujours reconstruire depuis le mesh
                from core.export.prusa_3mf_builder import PrusaThreeMFBuilder
                path = PrusaThreeMFBuilder().build(
                    mesh=self._mesh,
                    config=config,
                    output_path=Path(output_path),
                    printer_ui_name=self._current_printer,
                    filament_ui_name=self._current_filament,
                    nozzle_diameter_mm=nozzle_mm,
                )
            elif _PREFS.get("slicer_output", "bambu") == "cura":
                # Sortie Cura : format 3MF (pile de conteneurs) totalement différent
                # de Bambu/Prusa → toujours reconstruire depuis le mesh.
                from core.export.cura_3mf_builder import CuraThreeMFBuilder
                path = CuraThreeMFBuilder().build(
                    mesh=self._mesh,
                    config=config,
                    output_path=Path(output_path),
                    printer_ui_name=self._current_printer,
                    filament_ui_name=self._current_filament,
                    nozzle_diameter_mm=nozzle_mm,
                )
            elif _is_3mf_input and not _is_cat_model(self._current_printer):
                # Injecter dans le 3MF source UNIQUEMENT pour une Bambu Lab : le 3MF
                # source est alors cohérent. Pour une imprimante du CATALOGUE
                # (Creality, Elegoo…), le 3MF source est souvent un projet Bambu/autre
                # imprimante → ses métadonnées non patchées font apparaître la MAUVAISE
                # imprimante (X1C, Ender-3 V2…) dans CrealityPrint/Elegoo. On reconstruit
                # alors proprement depuis le mesh (chemin natif ci-dessous).
                path = self._tmf_builder.inject_settings_into_3mf(
                    source_path=_src_3mf,
                    config=config,
                    output_path=Path(output_path),
                    printer_ui_name=self._current_printer,
                    filament_ui_name=self._current_filament,
                    nozzle_diameter_mm=nozzle_mm,
                )
            else:
                path = self._tmf_builder.build(
                    mesh=self._mesh,
                    config=config,
                    output_path=Path(output_path),
                    printer_ui_name=self._current_printer,
                    filament_ui_name=self._current_filament,
                    nozzle_diameter_mm=nozzle_mm,
                )
            logger.info(f"3MF exporté : {path}")

            # Espace Pro : la répartition des couleurs + décompte du stock est
            # intégrée DANS la fenêtre de succès (une seule fenêtre).
            selection = getattr(self, "_current_selection", None)
            self._show_success_dialog(config, selection, path)

            if ok:
                self._statusbar.set_message(_("status.export_ok"), TELE_GREEN)
            else:
                self._statusbar.set_message(_("status.export_ok_warn", msg=result_msg), AMBER)

        except Exception as e:
            logger.exception("Erreur export")
            self._statusbar.set_message(_("status.export_err", msg=e), ERROR_RED)

    def _show_success_dialog(self, config, selection: "SelectionResult | None", tmf_path: "Path | None" = None):
        from PySide6.QtWidgets import QDialog, QFileDialog
        from data.filaments import FILAMENTS

        filament_name = self._current_filament
        printer_name  = self._current_printer
        filament_data = FILAMENTS.get(filament_name, {})
        warnings      = filament_data.get("warnings", [])

        _dp = _THEME.palette()

        dlg = QDialog(self)
        dlg.setWindowTitle("Fichier .3MF généré")
        dlg.setMinimumWidth(480)
        dlg.setStyleSheet(f"QDialog {{ background: {_dp['BG_PANEL']}; }}")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        def _sep():
            s = QFrame()
            s.setFixedHeight(1)
            s.setStyleSheet(f"background: {_dp['INACTIVE']};")
            return s

        def _section_lbl(text):
            l = QLabel(text)
            l.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
            l.setStyleSheet(f"color: {_dp['TEXT_LABEL']}; letter-spacing: 2px;")
            return l

        # ── Titre succès ──
        title = QLabel("✓   Fichier 3MF généré avec succès")
        title.setFont(QFont(FONT_MAIN, 12, QFont.Bold))
        title.setStyleSheet(f"color: {_dp['TELE_GREEN']};")
        layout.addWidget(title)

        layout.addWidget(_sep())

        # ── Action requise ──
        action_lbl = QLabel("⚠   ACTION REQUISE DANS BAMBU STUDIO")
        action_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        action_lbl.setStyleSheet(f"color: {_dp['AMBER']};")
        layout.addWidget(action_lbl)

        info = QLabel(
            "Les paramètres d'impression (qualité, vitesse, supports…) sont intégrés dans le 3MF.<br>"
            "Les paramètres du <b>filament</b> (températures, ventilation, débit) doivent être "
            "configurés manuellement dans Bambu Studio."
        )
        info.setFont(QFont(FONT_MAIN, 9))
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(f"color: {_dp['TEXT_SECONDARY']};")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Filament / Imprimante ──
        fil_box = QWidget()
        fil_box.setStyleSheet(f"background: {_dp['BG_SURFACE']}; border-radius: 4px;")
        fil_layout = QVBoxLayout(fil_box)
        fil_layout.setContentsMargins(12, 8, 12, 8)
        fil_layout.setSpacing(4)

        def _kv(k, v, color=_dp['TELE_GREEN']):
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            lbl_k = QLabel(k)
            lbl_k.setFont(QFont(FONT_MONO, 8))
            lbl_k.setStyleSheet(f"color: {_dp['TEXT_SECONDARY']};")
            lbl_v = QLabel(v)
            lbl_v.setFont(QFont(FONT_MONO, 8))
            lbl_v.setStyleSheet(f"color: {color};")
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(lbl_k, 1)
            hl.addWidget(lbl_v, 0)
            return row

        fil_layout.addWidget(_kv("Filament sélectionné",
                                 filament_data.get("label", filament_name)))
        fil_layout.addWidget(_kv("Imprimante", printer_name))
        layout.addWidget(fil_box)

        # ── Warnings filament ──
        if warnings:
            for w in warnings:
                wlbl = QLabel(f"⚠  {w}")
                wlbl.setFont(QFont(FONT_MAIN, 8))
                wlbl.setStyleSheet(f"color: {_dp['ERROR_RED']};")
                wlbl.setWordWrap(True)
                layout.addWidget(wlbl)

        layout.addWidget(_sep())

        # ── Boutons ──
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        btn_hl = QHBoxLayout(btn_row)
        btn_hl.setContentsMargins(0, 0, 0, 0)
        btn_hl.setSpacing(10)

        def _make_pdf_icon() -> QIcon:
            sz = 22
            px = QPixmap(sz, sz)
            px.fill(QColor(0, 0, 0, 0))
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor(ERROR_RED))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, sz, sz, 4, 4)
            p.setFont(QFont("Helvetica", 7, QFont.Weight.Bold))
            p.setPen(QColor("white"))
            p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "PDF")
            p.end()
            return QIcon(px)

        def _make_printer_icon() -> QIcon:
            sz = 22
            px = QPixmap(sz, sz)
            px.fill(QColor(0, 0, 0, 0))
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            col = QColor(TELE_GREEN)
            p.setPen(Qt.PenStyle.NoPen)
            # Printer body
            p.setBrush(col)
            p.drawRoundedRect(0, 6, sz, 10, 2, 2)
            # Paper input tray (top, darker)
            p.setBrush(col.darker(150))
            p.drawRect(4, 1, 14, 6)
            # Paper output sheet (bottom, light)
            p.setBrush(QColor("#C8DCF0"))
            p.drawRect(4, 15, 14, 6)
            # Lines on paper
            p.setPen(QPen(QColor(TELE_GREEN).darker(120), 1))
            p.drawLine(6, 17, 16, 17)
            p.drawLine(6, 19, 13, 19)
            p.end()
            return QIcon(px)

        btn_pdf = QPushButton("  Télécharger la fiche PDF des réglages")
        btn_pdf.setIcon(_make_pdf_icon())
        btn_pdf.setIconSize(QSize(18, 18))
        btn_pdf.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        btn_pdf.setFixedHeight(34)
        btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        _ep = _THEME.palette()
        btn_pdf.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_ep['ERROR_RED']};
                border: 1px solid {_ep['ERROR_RED']}; border-radius: 4px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ep['ERROR_RED']}; color: {_ep['EXPORT_FG']}; border: none; }}
        """)

        btn_close = QPushButton("Fermer")
        btn_close.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {_ep['TELE_GREEN']}; color: {_ep['EXPORT_FG']};
                border: none; border-radius: 4px; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {_ep['TELE_GREEN']}; opacity: 0.85; filter: brightness(1.1); }}
        """)

        def _generate_pdf():
            import re as _re
            import subprocess
            from PySide6.QtCore import QStandardPaths
            from PySide6.QtWidgets import QMessageBox
            safe_name = _re.sub(r'[<>:"/\\|?*]', '_',
                                f"neoSlice_{filament_name}_{printer_name}.pdf")
            _dl_str = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DownloadLocation)
            _dl = Path(_dl_str) if _dl_str else Path.home()
            _dl.mkdir(parents=True, exist_ok=True)
            save_path = str(_dl / safe_name)
            _plate_type = self._filament_selector.current_plate_type()
            try:
                from core.export.pdf_generator import generate_full_report_pdf, generate_filament_pdf
                analysis = self._analysis
                _dark = _THEME.is_dark()
                if analysis and hasattr(self, "_current_config"):
                    ok = generate_full_report_pdf(
                        filament_name, printer_name,
                        self._current_config, analysis,
                        Path(save_path),
                        plate_type=_plate_type,
                        dark=_dark,
                    )
                else:
                    ok = generate_filament_pdf(
                        filament_name, printer_name, Path(save_path),
                        plate_type=_plate_type,
                        dark=_dark,
                    )
            except Exception as _pdf_err:
                logger.exception("Erreur génération PDF")
                QMessageBox.critical(dlg, "Erreur PDF", str(_pdf_err))
                return
            if ok:
                import sys as _sys
                try:
                    if _sys.platform == "win32":
                        subprocess.Popen(f'explorer /select,"{save_path}"')
                    elif _sys.platform == "darwin":
                        subprocess.run(["open", "-R", save_path], check=False)
                    else:
                        subprocess.run(["xdg-open", str(Path(save_path).parent)], check=False)
                except Exception:
                    pass
                self._statusbar.set_message(f"PDF → {save_path}", TELE_GREEN)
            else:
                QMessageBox.critical(dlg, "Erreur PDF", "Génération échouée — reportlab installé ?")


        from core.prefs import PREFS as _PREFS_btn
        _slicer_sel = _PREFS_btn.get("slicer_output", "bambu")
        _btn_open_key = {"prusa": "export.btn_prusa",
                         "orca": "export.btn_orca",
                         "creality": "export.btn_creality",
                         "elegoo": "export.btn_elegoo",
                         "anycubic": "export.btn_anycubic",
                         "snapmaker": "export.btn_snapmaker",
                         "cura": "export.btn_cura"}.get(_slicer_sel, "export.btn_bambu")
        btn_bambu = QPushButton(_(_btn_open_key))
        btn_bambu.setIcon(_make_printer_icon())
        btn_bambu.setIconSize(QSize(18, 18))
        btn_bambu.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        btn_bambu.setFixedHeight(34)
        btn_bambu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bambu.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_ep['TELE_GREEN']};
                border: 1px solid {_ep['TELE_GREEN']}; border-radius: 4px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ep['TELE_GREEN']}; color: {_ep['EXPORT_FG']}; border: none; }}
        """)
        btn_bambu.setVisible(tmf_path is not None and tmf_path.exists())

        def _open_in_bambu():
            if tmf_path and tmf_path.exists():
                _open_3mf_in_slicer(str(tmf_path), _slicer_sel)

        btn_bambu.clicked.connect(_open_in_bambu)

        btn_pdf.clicked.connect(_generate_pdf)
        btn_close.clicked.connect(dlg.accept)

        btn_hl.addWidget(btn_pdf, 1)
        btn_hl.addWidget(btn_bambu, 0)
        btn_hl.addWidget(btn_close, 0)
        layout.addWidget(btn_row)

        # ── Couleurs et décompte du stock (Pro), dans la même fenêtre ──
        _has_colors = self._build_color_section(layout, config, tmf_path, _sep, _section_lbl)

        apply_title_bar_theme(dlg)
        if _has_colors:
            # Fenêtre NON-MODALE accolée au bord droit : le viewer principal reste
            # en place (contexte OpenGL intact, pas de réparentage) et visible à
            # gauche pour voir la prévisualisation des couleurs en direct.
            try:
                dlg.adjustSize()
                _g = self.frameGeometry()
                dlg.move(max(0, _g.right() - dlg.width() - 20), max(0, _g.top() + 70))
            except Exception:
                pass
            self._success_dlg = dlg   # garder une référence (sinon GC en non-modal)
            dlg.finished.connect(lambda *_: setattr(self, "_success_dlg", None))
            dlg.setModal(False)
            dlg.show()
        else:
            # Pas de section couleur : fenêtre modale centrée classique.
            try:
                from PySide6.QtWidgets import QApplication as _QApp
                dlg.adjustSize()
                _scr = self.screen() or _QApp.primaryScreen()
                if _scr is not None:
                    _g = _scr.availableGeometry()
                    dlg.move(_g.center().x() - dlg.width() // 2,
                             _g.center().y() - dlg.height() // 2)
            except Exception:
                pass
            dlg.exec()
