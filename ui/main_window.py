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
from ui.components.welcome_dialog import WelcomeDialog, should_show_welcome
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
    from data.filaments import FILAMENTS
    from data.printers import PRINTERS

    warns: list[str] = []
    fil = FILAMENTS.get(filament, {})
    prt = PRINTERS.get(printer, {})

    if not fil:
        return warns

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

    def __init__(self, mesh, nozzle_diameter_mm: float = 0.4):
        super().__init__()
        self._mesh = mesh
        self._nozzle_mm = float(nozzle_diameter_mm)

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor
            from core.prefs import PREFS
            perf_mode = PREFS.get("perf_mode", "full")

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

                # ── Dispatch parallèle selon le mode ──────────────────────────
                n_workers = {"full": 3, "balanced": 2, "lite": 1}[perf_mode]
                self.progress.emit(10, "Analyses en cours…")

                with ThreadPoolExecutor(max_workers=n_workers) as pool:
                    fut_ov   = pool.submit(_task_overhangs) if perf_mode != "lite" else None
                    fut_stab = pool.submit(_task_stability)

                    ov, floating = fut_ov.result() if fut_ov else (None, False)
                    lr           = fut_stab.result()

            self.progress.emit(70, "Fusion des résultats…")

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
                report.estimated_support_ratio  = min(0.60, ov.projected_ratio * 2.0)
                report.support_needed           = ov.severity > 0.0 or ov.overhang_ratio > 0.0
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

class _TopBar(QWidget):
    """Barre haute 48px — logo + scan-line animée + sélecteur de thème."""

    coffee_clicked    = Signal()
    tutorial_clicked  = Signal()
    new_piece_clicked = Signal()
    settings_clicked  = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self._scanline_y = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)
        self.destroyed.connect(self._timer.stop)
        self._setup_ui()
        self.refresh_theme()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 1)
        layout.setSpacing(12)

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.VLine)
        self._sep.setFixedHeight(24)
        layout.addWidget(self._sep)

        self._logo = QLabel()
        _meipass = getattr(__import__("sys"), "_MEIPASS", None)
        _logo_path = (Path(_meipass) if _meipass else Path(__file__).parent.parent) / "assets" / "neoSlice.png"
        if _logo_path.exists():
            # Hauteur 46px, largeur proportionnelle (logo 3:2 → ~69px)
            _px_full = QPixmap(str(_logo_path))
            _logo_h  = 46
            _logo_w  = int(_logo_h * _px_full.width() / _px_full.height()) if _px_full.height() else _logo_h
            _px = _px_full.scaled(_logo_w, _logo_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._logo.setPixmap(_px)
            self._logo.setFixedSize(_logo_w, _logo_h)
        else:
            self._logo.setText("◈")
            self._logo.setFont(QFont(FONT_MAIN, 22))

        # Logo centré entre le séparateur et le titre — widgets séparés,
        # le layout spacing=12 donne un espace égal des deux côtés.
        layout.addWidget(self._logo, 0, Qt.AlignVCenter)

        self._title_lbl = QLabel(_("app.title"))
        self._title_lbl.setFont(QFont(FONT_MAIN, 26, QFont.Bold))
        layout.addWidget(self._title_lbl, 0, Qt.AlignVCenter)

        self._beta = QLabel("BÊTA")
        self._beta.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        layout.addWidget(self._beta)

        self._sub = QLabel(_("app.subtitle"))
        self._sub.setFont(QFont(FONT_MAIN, 8))
        layout.addWidget(self._sub)

        layout.addStretch()

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

        help_btn = QPushButton("?")
        help_btn.setFont(QFont(FONT_MAIN, 11, QFont.Bold))
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
        coffee_btn = QPushButton("☕")
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
        _FONT_ICON     = QFont("Segoe MDL2 Assets", 11) if _sys.platform == "win32" else QFont(FONT_MAIN, 13)

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

    def refresh_theme(self) -> None:
        pal = _THEME.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        self._sep.setStyleSheet(f"color: {pal['INACTIVE']};")
        self._logo.setStyleSheet("background: transparent;")
        self._title_lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; font-size: 26px; font-weight: bold; letter-spacing: 3px;")
        self._beta.setStyleSheet(
            f"color: {pal['AMBER']}; border: 1px solid {pal['AMBER']}; "
            f"border-radius: 2px; padding: 1px 4px; background: rgba(255,184,0,0.10);"
        )
        self._sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        if hasattr(self, '_version_lbl'):
            self._version_lbl.setStyleSheet(
                f"color: {pal['ACCENT_BRIGHT']}; background: {pal['BG_SURFACE']}; "
                f"border: 1px solid {pal['ACCENT']}; border-radius: 2px; padding: 1px 5px;"
            )
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
        self.update()

    def _tick(self):
        self._scanline_y = (self._scanline_y + 3) % max(self.height(), 1)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        pal = _THEME.palette()
        painter = QPainter(self)
        painter.setPen(QPen(QColor(pal["ACCENT"]), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.setPen(QPen(QColor(pal["SCAN_R"], pal["SCAN_G"], pal["SCAN_B"], pal["SCAN_A"]), 1))
        painter.drawLine(0, self._scanline_y, self.width(), self._scanline_y)


# ── StatusBar ──────────────────────────────────────────────────────────────

class _StatusBar(QWidget):
    """Barre basse 40px — statut + bouton export."""

    export_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self._pulse_phase = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self.destroyed.connect(self._pulse_timer.stop)
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

        self._export_btn = QPushButton(_("export.btn"))
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

    def refresh_theme(self):
        pal = _THEME.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        self._dot.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        self._msg.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
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

        self._num = QLabel(number)
        self._num.setFont(QFont(FONT_MONO, 11, QFont.Bold))
        layout.addWidget(self._num)

        self._lbl = QLabel(title.upper())
        self._lbl.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        layout.addWidget(self._lbl)

        layout.addStretch()
        self.set_pending()

    def _set_colors(self, bar_color: str, num_color: str):
        pal = _THEME.palette()
        self._bar.setStyleSheet(f"background: {bar_color}; border-radius: 1px;")
        self._num.setStyleSheet(f"color: {num_color}; background: transparent;")
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


# ── Fenêtre principale ─────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    # Signal thread-safe pour la popup de mise à jour (émis depuis thread background)
    _update_ready = Signal(str, str, str)  # version, url, notes

    def __init__(self):
        super().__init__()
        self._mesh = None
        self._original_mesh = None
        self._threemf_data = None          # ThreeMFData si 3MF multicolore
        self._analysis: AnalysisReport | None = None
        self._stl_load_thread: QThread | None = None
        self._stl_load_worker: STLLoadWorker | None = None
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._current_config = None
        self._current_selection = None
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

    def closeEvent(self, event):
        event.accept()
        import os
        os._exit(0)

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
        self.setStyleSheet(f"QMainWindow {{ background: {_THEME.palette()['BG_VOID']}; }}")

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
        self._step_config = _StepHeader("①", "Configuration")
        self._step_config.set_active()
        layout.addWidget(self._step_config)

        self._filament_selector = FilamentPrinterSelector()
        _default_printer = PREFS.get("printer_default", "")
        if _default_printer:
            self._filament_selector.set_printer(_default_printer)
        self._filament_selector.selection_changed.connect(self._on_filament_printer_changed)
        self._filament_selector.printer_confirmed.connect(self._on_printer_confirmed)
        self._filament_selector.filament_confirmed.connect(self._on_filament_confirmed)
        layout.addWidget(self._filament_selector)

        sep0 = QFrame()
        sep0.setFixedHeight(1)
        sep0.setStyleSheet(f"background: {INACTIVE}; margin: 4px 0;")
        layout.addWidget(sep0)

        # ── Étape ② — Import STL ──
        self._step_stl = _StepHeader("②", "Import STL / 3MF")
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
        self._step_intent = _StepHeader("③", "Instruction Mission")
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
        dlg = WelcomeDialog(self, assets_path=assets)
        apply_title_bar_theme(dlg)
        dlg.exec()

    def _apply_theme(self):
        pal = _THEME.palette()
        self.setStyleSheet(f"QMainWindow {{ background: {pal['BG_VOID']}; }}")
        if hasattr(self, '_workspace'):
            self._workspace.setStyleSheet(f"background: {pal['BG_VOID']};")
        if hasattr(self, '_left_scroll'):
            self._left_scroll.setStyleSheet(f"""
                QScrollArea {{ background: {pal['BG_PANEL']}; border: none; border-right: 1px solid {pal['INACTIVE']}; }}
                QScrollBar:vertical {{ background: {pal['BG_PANEL']}; width: 6px; border: none; }}
                QScrollBar::handle:vertical {{ background: {pal['TEXT_LABEL']}; border-radius: 3px; min-height: 20px; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; background: transparent; }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            """)
            self._left_scroll.viewport().setStyleSheet(f"background: {pal['BG_PANEL']}; border: none;")
            if self._left_scroll.widget():
                self._left_scroll.widget().setStyleSheet(f"background: {pal['BG_PANEL']};")
        if hasattr(self, '_right_scroll'):
            self._right_scroll.setStyleSheet(f"""
                QScrollArea {{ background: {pal['BG_PANEL']}; border: none; border-left: 1px solid {pal['INACTIVE']}; }}
                QScrollBar:vertical {{ background: {pal['BG_PANEL']}; width: 4px; border: none; }}
                QScrollBar::handle:vertical {{ background: {pal['TEXT_LABEL']}; border-radius: 2px; min-height: 20px; }}
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
        apply_title_bar_theme(self)

    def _open_settings(self):
        from PySide6.QtCore import QPoint
        from core.prefs import PREFS as _PREFS
        dlg = SettingsDialog(self)
        apply_title_bar_theme(dlg)
        dlg.update_request.connect(self._on_settings_update_request)
        btn = self._topbar._settings_btn
        btn_br = btn.mapToGlobal(QPoint(btn.width(), btn.height()))
        dlg.move(btn_br.x() - 400, btn_br.y() + 4)
        dlg.exec()
        # Sync printer default → FilamentPrinterSelector
        new_printer = _PREFS.get("printer_default", "")
        if new_printer and hasattr(self, '_filament_selector'):
            self._filament_selector.set_printer(new_printer)

    def _on_settings_update_request(self, version: str, url: str, notes: str):
        self._pending_update = (version, url, notes)
        self._show_update_dialog()

    def _show_welcome_first_launch(self):
        """Premier lancement : welcome → tutorial si pas encore vu."""
        self._show_welcome()
        if should_show_tutorial():
            QTimer.singleShot(300, self._show_tutorial)

    # ── Tutorial ───────────────────────────────────────────────────────────

    def _show_tutorial(self):
        if self._tutorial is not None:
            try:
                self._tutorial.hide()
                self._tutorial.deleteLater()
            except RuntimeError:
                pass
            self._tutorial = None

        targets = {
            "config":    self._filament_selector,
            "drop":      self._drop_zone,
            "intent":    self._intent_selector,
            "statusbar": self._statusbar._export_btn,
            "topbar":    self._topbar.icon_group,
        }
        self._tutorial = TutorialOverlay(self, targets)
        self._tutorial.finished.connect(self._on_tutorial_finished)
        self._tutorial.show()
        self._tutorial.raise_()
        self._tutorial.activateWindow()

    def _on_tutorial_finished(self):
        self._tutorial = None

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

    def _show_update_dialog(self):
        info = getattr(self, "_pending_update", None)
        if not info:
            return
        new_version, download_url, notes = info

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
            try:
                req = _urlreq.Request(
                    download_url,
                    headers={"User-Agent": f"neoSlice/{new_version}"}
                )
                with _urlreq.urlopen(req, timeout=60) as resp:
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
                # Vérifier que c'est un vrai exécutable Windows (magic bytes MZ)
                with open(tmp, "rb") as _chk:
                    magic = _chk.read(2)
                if magic != b"MZ":
                    import os as _os
                    try: _os.remove(tmp)
                    except: pass
                    _q.put(("error", "Fichier téléchargé invalide (accès refusé ou repo privé). Rendez le repo public ou téléchargez manuellement."))
                    return
                _q.put(("done", tmp))
            except Exception as exc:
                _q.put(("error", str(exc)))

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
                        # Windows : lancer l'installeur et quitter
                        status_lbl.setText(_("update.installing"))
                        QTimer.singleShot(600, lambda: (
                            subprocess.Popen([val]),
                            QApplication.quit()
                        ))
                elif kind == "error":
                    _poll_timer.stop()
                    progress_bar.setRange(0, 100)
                    progress_bar.setValue(0)
                    status_lbl.setText(_("update.failed"))
                    status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']};")
                    install_btn.setText(_("update.btn_retry"))
                    install_btn.setEnabled(True)
                    install_btn.show()
            except _queue.Empty:
                pass

        def _start_download():
            install_btn.setEnabled(False)
            install_btn.hide()
            later_btn.setEnabled(False)
            progress_bar.show()
            status_lbl.setText(_("update.downloading", pct=0))
            status_lbl.show()
            dlg.adjustSize()
            _poll_timer.timeout.connect(_on_poll)
            _poll_timer.start(80)
            _threading.Thread(target=_download, daemon=True).start()

        install_btn.clicked.connect(_start_download)

        apply_title_bar_theme(dlg)
        dlg.exec()

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

        self._viewer.stop_auto_rotate()
        self._viewer.reset()
        self._analysis_panel.reset()
        self._drop_zone.reset()
        self._intent_selector.set_locked(True)
        self._intent_selector.reset_selection()
        self._params_preview.reset()

        self._step_stl.set_pending()
        self._step_intent.set_pending()
        self._topbar.set_has_stl(False)
        self._statusbar.set_export_enabled(False)
        self._statusbar.set_message(_("status.ready"), TELE_GREEN)

    def _on_stl_dropped(self, path: Path):
        """Démarre le chargement STL en thread — feedback immédiat, zéro freeze UI."""
        logger.info(f"STL reçu : {path}")
        self._stl_path = path

        # ── Feedback instantané (< 1 ms) ────────────────────────────────────
        self._step_stl.set_active()
        self._viewer.stop_auto_rotate()
        self._viewer.set_loading(True, f"CHARGEMENT — {path.name}")
        self._statusbar.set_message(f"Chargement — {path.name}", AMBER)
        self._original_mesh = None

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

        # 3MF multi-objets → extraire le mesh combiné, stocker les données multicolores
        if isinstance(mesh, ThreeMFData):
            self._threemf_data = mesh          # sauvegardé pour l'export passthrough
            mesh = mesh.combined_mesh          # le reste du code utilise le mesh fusionné
            logger.info(f"3MF multicolore : {self._threemf_data.summary()}")
        else:
            self._threemf_data = None          # mono-objet classique

        self._mesh = mesh
        self._original_mesh = mesh.copy()

        # Charger le mesh pendant que l'overlay est encore affiché — évite le flash plateau vide.
        # set_loading(False) sera appelé par _on_analysis_complete à la fin de l'analyse.
        self._viewer.load_mesh(self._mesh)
        self._topbar.set_has_stl(True)

        try:
            from ui.components.welcome_dialog import _load_prefs, _save_prefs
            _p = _load_prefs(); _p["last_stl"] = str(path); _save_prefs(_p)
        except Exception:
            pass
        self._drop_zone.set_recent_file(path)
        self._statusbar.set_message(_("status.loading", name=path.name), AMBER)
        self._start_analysis()

    def _on_stl_load_error(self, msg: str):
        """Appelé si load_stl() lève une exception."""
        self._viewer.set_loading(False)
        self._statusbar.set_message(f"Erreur chargement : {msg}", ERROR_RED)
        logger.error(f"STL load error : {msg}")

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
        self._analysis_worker = AnalysisWorker(
            self._mesh,
            nozzle_diameter_mm=self._current_nozzle_mm,
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

        if report.overhang_severity > 0.0 or report.support_needed:
            try:
                ov = report.overhang_result
                if ov is not None:
                    # Utiliser display_mask pour la visu (masque brut, sans filtre pont)
                    # critical_face_mask filtre trop agressivement sur les maillages organiques
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
                    # Fallback : recalcul rapide (smooth=False pour la vitesse)
                    ov = analyze_overhangs(self._mesh, smooth=False, check_floating=False)
                    colors = overhang_face_colors(self._mesh, ov)
                self._viewer.colorize_overhangs(self._mesh, colors)
            except Exception:
                logger.exception("colorize_overhangs échoué")

        self._viewer.start_auto_rotate()

        oh_pct = report.overhang_severity * 100
        oh_tag = _("status.oh_tag", pct=oh_pct) if oh_pct > 0.1 else ""
        self._statusbar.set_message(
            _("status.analysis_ok", ms=report.analysis_time_ms, oh_tag=oh_tag),
            TELE_GREEN,
        )

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

            config.neoslice_intent_text = result.human_summary

            self._current_config = config
            self._current_selection = result

            self._params_preview.update_from_config(config, analysis)
            self._analysis_panel.set_generation_active()
            self._analysis_panel.show_material_warnings(
                _compute_material_warnings(filament, printer, analysis)
            )
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
            path = self._tmf_builder.build(
                mesh=self._mesh,
                config=config,
                output_path=Path(output_path),
                printer_ui_name=self._current_printer,
                filament_ui_name=self._current_filament,
                nozzle_diameter_mm=nozzle_mm,
                threemf_data=getattr(self, "_threemf_data", None),
            )
            logger.info(f"3MF exporté : {path}")

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

        fil_layout.addWidget(_kv("Filament sélectionné", filament_name))
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
                background: {_ep['BG_ELEVATED']}; color: {_ep['ERROR_RED']};
                border: 1px solid {_ep['ERROR_RED']}; border-radius: 4px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ep['ERROR_RED']}; color: {_ep['EXPORT_FG']}; }}
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


        btn_bambu = QPushButton("  Ouvrir dans Bambu Studio")
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
                import sys as _sys, subprocess as _sp
                try:
                    if _sys.platform == "win32":
                        import os as _os
                        _os.startfile(str(tmf_path))
                    elif _sys.platform == "darwin":
                        _sp.run(["open", str(tmf_path)], check=False)
                    else:
                        _sp.run(["xdg-open", str(tmf_path)], check=False)
                except Exception:
                    pass

        btn_bambu.clicked.connect(_open_in_bambu)

        btn_pdf.clicked.connect(_generate_pdf)
        btn_close.clicked.connect(dlg.accept)

        btn_hl.addWidget(btn_pdf, 1)
        btn_hl.addWidget(btn_bambu, 0)
        btn_hl.addWidget(btn_close, 0)
        layout.addWidget(btn_row)

        apply_title_bar_theme(dlg)
        dlg.exec()
