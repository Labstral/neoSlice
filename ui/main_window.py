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
from core.geometry.support_detector import detect_support_by_raycast, support_face_colors
from core.geometry.orientation_optimizer import optimize_orientation
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
)
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


# ── Worker thread ──────────────────────────────────────────────────────────

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
            from core.prefs import PREFS
            perf_mode = PREFS.get("perf_mode", "full")

            t0 = time.perf_counter()
            report = AnalysisReport()
            report.nozzle_diameter_mm = self._nozzle_mm

            # ── 1. Surplombs — ray-casting vertical depuis le plateau ────────────
            # Pour chaque colonne XY, un rayon monte du plateau et détecte chaque
            # face orientée vers le bas. S'il n'y a pas de matière solide en dessous
            # (gap > seuil), la face nécessite un support. Même approche que Bambu.
            self._support_mask = None
            self.progress.emit(10, "Ray-casting surplombs...")
            if perf_mode == "lite":
                # Lite mode: skip expensive ray-cast — set neutral defaults
                report.overhang_severity        = 0.0
                report.overhang_ratio           = 0.0
                report.projected_overhang_ratio = 0.0
                report.estimated_support_ratio  = 0.0
                report.support_needed           = False
                report.has_floating_regions     = False
            else:
                try:
                    rc_mask, rc_ratio, rc_severity = detect_support_by_raycast(self._mesh)
                    logger.info(f"Ray-cast OK: {rc_mask.sum()} faces, sévérité={rc_severity:.4f}")
                    report.overhang_severity        = rc_severity
                    report.overhang_ratio           = rc_ratio
                    report.projected_overhang_ratio = rc_ratio
                    report.estimated_support_ratio  = min(0.60, rc_ratio * 2.5)
                    # Seuil relatif bas + seuil absolu : pour les meshes haute-résolution
                    # (1.5M faces), même 1% de sévérité = centaines de mm² réels.
                    n_overhang_faces = int(rc_mask.sum())
                    report.support_needed = rc_severity > 0.01 or n_overhang_faces > 100
                    self._support_mask              = rc_mask   # gardé pour la visu
                    # Régions flottantes via normales (rapide, pas de ray-cast)
                    try:
                        from core.geometry.overhang_detector import analyze_overhangs as _ao
                        ov = _ao(self._mesh, smooth=False, check_floating=True)
                        report.has_floating_regions = ov.has_floating_regions
                        if ov.has_floating_regions:
                            report.support_needed = True
                    except Exception:
                        pass
                except Exception:
                    logger.exception("Ray-casting surplombs échoué — fallback normales")
                    try:
                        from core.geometry.overhang_detector import analyze_overhangs as _ao
                        ov = _ao(self._mesh)
                        report.overhang_severity        = ov.severity
                        report.overhang_ratio           = ov.overhang_ratio
                        report.projected_overhang_ratio = ov.projected_ratio
                        report.has_floating_regions     = ov.has_floating_regions
                        report.estimated_support_ratio  = min(0.60, ov.projected_ratio * 2.0)
                        report.support_needed           = ov.severity > 0.15 or ov.has_floating_regions
                    except Exception:
                        pass

            # ── 2. Stabilité + fragilité — analyse par couches Shapely ──────────
            # Le layer_slicer est meilleur pour la stabilité (empreinte réelle,
            # centre de masse, ratio hauteur/largeur) et la fragilité (épaisseur).
            self.progress.emit(35, "Analyse stabilité et fragilité...")
            try:
                lr = analyze_by_layers(self._mesh, nozzle_diameter_mm=self._nozzle_mm)
                report.stability_score          = lr.stability_score
                report.center_of_mass           = lr.center_of_mass
                report.brim_recommendation_mm   = lr.brim_recommendation_mm
                report.min_wall_thickness_mm    = lr.min_wall_thickness_mm
                report.fragility_severity       = lr.fragility_severity
                report.has_fragile_zones        = lr.has_fragile_zones
                # Surplombs : layer_slicer (méthode FDM réelle couche/couche) est
                # meilleur que le ray-cast pour les overhangs latéraux sur pièces
                # connectées (ex: mâchoire de bishop qui dépasse du corps).
                # On prend le MAX des deux méthodes.
                if lr.overhang_severity > report.overhang_severity:
                    report.overhang_severity        = lr.overhang_severity
                    report.overhang_ratio           = max(report.overhang_ratio, lr.overhang_ratio)
                    report.projected_overhang_ratio = max(report.projected_overhang_ratio, lr.projected_overhang_ratio)
                    report.estimated_support_ratio  = max(report.estimated_support_ratio, lr.support_volume_ratio)
                report.support_needed = (
                    report.support_needed
                    or lr.support_needed
                    or lr.overhang_severity > 0.005
                    or lr.has_floating_regions
                )
                # Régions flottantes : prendre le OR des deux méthodes
                report.has_floating_regions     = report.has_floating_regions or lr.has_floating_regions
                if lr.fallback_used:
                    report.warnings.append(
                        "Analyse par couches indisponible (shapely manquant) — stabilité heuristique"
                    )
            except Exception:
                logger.exception("Analyse par couches échouée — fallback stabilité")
                try:
                    from core.geometry.stability_analyzer import analyze_stability as _as
                    st = _as(self._mesh)
                    report.stability_score        = st.score
                    report.center_of_mass         = st.center_of_mass.tolist()
                    report.brim_recommendation_mm = st.brim_recommendation_mm
                except Exception:
                    pass
                try:
                    from core.geometry.fragility_detector import detect_fragility as _df
                    fr = _df(self._mesh, nozzle_diameter_mm=self._nozzle_mm)
                    report.has_fragile_zones     = fr.has_fragile_zones
                    report.min_wall_thickness_mm = fr.min_thickness_mm
                    report.fragility_severity    = fr.severity
                except Exception:
                    pass

            # ── Orientation optimale ──────────────────────────────────────────
            self.progress.emit(70, "Recherche de l'orientation optimale...")
            if perf_mode == "full":
                try:
                    orientation = optimize_orientation(self._mesh, n_fibonacci=24)
                    if orientation is None:
                        raise ValueError("optimize_orientation a retourné None")
                    report.optimal_rotation            = orientation.rotation_matrix.flatten().tolist()
                    report.orientation_score           = orientation.total_score
                    report.orientation_label           = orientation.direction_label
                    report.orientation_improvement_pct = orientation.improvement_pct
                except Exception:
                    logger.warning("Optimisation orientation ignorée (géométrie dégénérée)")
                    report.optimal_rotation  = np.eye(4).flatten().tolist()
                    report.orientation_score = 0.5
                    report.orientation_label = ""
            else:
                # balanced / lite: skip orientation optimizer
                report.optimal_rotation  = np.eye(4).flatten().tolist()
                report.orientation_score = 0.5
                report.orientation_label = ""

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
            if max_dim < 15.0:
                report.warnings.append(
                    f"Pièce très petite ({max_dim:.1f} mm) — "
                    "l'analyse des surplombs n'est pas fiable à cette échelle. "
                    "Vérifier les supports directement dans Bambu Studio."
                )
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
                    "Régions flottantes détectées — supports obligatoires "
                    "(onglet Process > Support > Enable support)"
                )
            elif report.support_needed:
                report.warnings.append(
                    "Supports requis — activer dans Bambu Studio : "
                    "onglet Process > Support > Enable support"
                )

            report.analysis_time_ms = (time.perf_counter() - t0) * 1000
            if self._support_mask is not None:
                report.support_face_mask = self._support_mask
            self.progress.emit(100, "Analyse terminée")
            self.analysis_complete.emit(report)

        except Exception as exc:
            logger.exception("Erreur pendant l'analyse")
            self.error.emit(str(exc))


class OrientationWorker(QObject):
    done = Signal(object, object)  # (rotated_mesh, overhang_colors | None)
    error = Signal(str)

    def __init__(self, mesh, rotation_matrix):
        super().__init__()
        self._mesh = mesh
        self._rot = rotation_matrix

    def run(self):
        try:
            rotated = self._mesh.copy()
            rotated.apply_transform(self._rot)
            rotated.apply_translation(-rotated.bounds[0])  # Z=0
            cx = (rotated.bounds[1][0]) / 2.0
            cy = (rotated.bounds[1][1]) / 2.0
            rotated.apply_translation([-cx, -cy, 0])  # centrer XY
            try:
                ov = analyze_overhangs(rotated)
                colors = overhang_face_colors(rotated, ov)
            except Exception:
                colors = None
            self.done.emit(rotated, colors)
        except Exception as exc:
            logger.exception("Erreur application orientation")
            self.error.emit(str(exc))


# ── TopBar ─────────────────────────────────────────────────────────────────

class _TopBar(QWidget):
    """Barre haute 48px — logo + scan-line animée + sélecteur de thème."""

    coffee_clicked    = Signal()
    tutorial_clicked  = Signal()
    new_piece_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
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

        self._logo = QLabel("◈")
        self._logo.setFont(QFont("Segoe UI", 16))
        layout.addWidget(self._logo)

        self._title_lbl = QLabel(_("app.title"))
        self._title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        layout.addWidget(self._title_lbl)

        self._beta = QLabel("BÊTA")
        self._beta.setFont(QFont("Segoe UI", 7, QFont.Bold))
        layout.addWidget(self._beta)

        self._sub = QLabel(_("app.subtitle"))
        self._sub.setFont(QFont("Segoe UI", 7))
        layout.addWidget(self._sub)

        layout.addStretch()

        self._new_btn = QPushButton(_("app.btn_new_piece"))
        self._new_btn.setFont(QFont("Segoe UI", 7, QFont.Bold))
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
        help_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
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
        coffee_btn.setFont(QFont("Segoe UI", 10))
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

        feedback_btn = QPushButton("")
        feedback_btn.setFont(QFont("Segoe MDL2 Assets", 11))
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
            QUrl("https://docs.google.com/forms/d/e/1FAIpQLSfCH4GGn26aHaabNBG40FSlPgx_4pljh1z3WDfyWACkmTCeFw/viewform?usp=publish-editor")
        ))

        self.icon_group = QWidget()
        self.icon_group.setStyleSheet("background: transparent;")
        icon_lay = QHBoxLayout(self.icon_group)
        icon_lay.setContentsMargins(0, 0, 0, 0)
        icon_lay.setSpacing(2)
        icon_lay.addWidget(feedback_btn)
        icon_lay.addWidget(help_btn)
        icon_lay.addWidget(coffee_btn)
        layout.addWidget(self.icon_group)

        from version import __version__
        version = QLabel(f"v{__version__}")
        version.setFont(QFont(FONT_MONO, 8))
        version.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        layout.addWidget(version)

    def set_has_stl(self, active: bool):
        self._new_btn.setEnabled(active)

    def refresh_theme(self) -> None:
        pal = _THEME.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        self._sep.setStyleSheet(f"color: {pal['INACTIVE']};")
        self._logo.setStyleSheet(f"color: {pal['ACCENT']}; background: transparent;")
        self._title_lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; font-size: 13px; font-weight: bold;")
        self._beta.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        self._sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
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
        self._msg.setFont(QFont(FONT_MONO, 9))
        self._msg.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self._msg.setWordWrap(False)
        layout.addWidget(self._msg, 1)

        self._export_btn = QPushButton(_("export.btn"))
        self._export_btn.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._export_btn.setFixedHeight(28)
        self._export_btn.setMinimumWidth(260)
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

    def set_message(self, text: str, dot_color: str = TELE_GREEN):
        # Aplatir les messages multi-lignes (ex: exceptions VTK/qhull) et limiter la longueur
        text = " — ".join(line.strip() for line in text.splitlines() if line.strip())
        if len(text) > 130:
            text = text[:127] + "…"
        self._msg.setText(text.upper())
        self._dot.setStyleSheet(f"color: {dot_color}; background: transparent;")

    def _pulse_tick(self):
        self._pulse_phase = (self._pulse_phase + 1) % 80
        t = abs(self._pulse_phase - 40) / 40.0  # 0.0 → 1.0 → 0.0
        blue = int(160 + 95 * (1.0 - t))        # 160 → 255 → 160
        self._export_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #020408;
                border: 1px solid rgb(30, 100, {blue});
                border-radius: 3px;
                padding: 0 16px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {ACCENT_BRIGHT};
                border-color: white;
            }}
        """)

    def set_export_enabled(self, enabled: bool):
        self._export_btn.setEnabled(enabled)
        if enabled:
            self._pulse_phase = 0
            self._pulse_timer.start(20)
        else:
            self._pulse_timer.stop()
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

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(ACCENT), 1))
        painter.drawLine(0, 0, self.width(), 0)


# ── Section divider avec étape numérotée ──────────────────────────────────

class _StepHeader(QWidget):
    """En-tête de section avec numéro d'étape et indicateur d'état."""

    def __init__(self, number: str, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
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
        self._lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._lbl.setStyleSheet("letter-spacing: 2px;")
        layout.addWidget(self._lbl)

        layout.addStretch()
        self._set_colors(INACTIVE, TEXT_LABEL)

    def _set_colors(self, accent_color: str, text_color: str):
        self._bar.setStyleSheet(f"background: {accent_color}; border-radius: 1px;")
        self._num.setStyleSheet(f"color: {accent_color}; background: transparent;")
        self._lbl.setStyleSheet(
            f"color: {text_color}; letter-spacing: 2px; background: transparent;"
        )

    def set_pending(self):
        self._set_colors(INACTIVE, TEXT_LABEL)

    def set_active(self):
        self._set_colors(ACCENT, TEXT_PRIMARY)

    def set_done(self):
        self._set_colors(TELE_GREEN, TELE_GREEN)


# ── Centre : fond grille ───────────────────────────────────────────────────

class _GridWidget(QWidget):
    """Widget central avec fond en grille légère façon HUD."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(30, 144, 255, 8), 1))
        step = 40
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)


# ── Fenêtre principale ─────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._mesh = None
        self._original_mesh = None
        self._analysis: AnalysisReport | None = None
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._orient_thread: QThread | None = None
        self._orient_worker: OrientationWorker | None = None
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

        if should_show_welcome():
            QTimer.singleShot(200, self._show_welcome_first_launch)
        elif should_show_tutorial():
            QTimer.singleShot(400, self._show_tutorial)

    def closeEvent(self, event):
        event.accept()
        import os
        os._exit(0)

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
        self.setStyleSheet(f"QMainWindow {{ background: {BG_VOID}; }}")

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
        self._topbar.new_piece_clicked.connect(self._on_new_piece)
        root.addWidget(self._topbar)

        # ── Workspace 3 colonnes ──
        workspace = QWidget()
        workspace.setStyleSheet(f"background: {BG_VOID};")
        ws_layout = QHBoxLayout(workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(0)

        ws_layout.addWidget(self._build_panel_left())
        ws_layout.addWidget(self._build_panel_center(), stretch=1)
        ws_layout.addWidget(self._build_panel_right())

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
        self._filament_selector.selection_changed.connect(self._on_filament_printer_changed)
        self._filament_selector.printer_confirmed.connect(self._on_printer_confirmed)
        self._filament_selector.filament_confirmed.connect(self._on_filament_confirmed)
        layout.addWidget(self._filament_selector)

        sep0 = QFrame()
        sep0.setFixedHeight(1)
        sep0.setStyleSheet(f"background: {INACTIVE}; margin: 4px 0;")
        layout.addWidget(sep0)

        # ── Étape ② — Import STL ──
        self._step_stl = _StepHeader("②", "Import STL")
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
        layout.addWidget(self._intent_selector)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ── Panneau centre ─────────────────────────────────────────────────────

    def _build_panel_center(self) -> QWidget:
        container = _GridWidget()
        container.setStyleSheet(f"background: {BG_VOID};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Analyse géométrique ──
        self._analysis_panel = AnalysisPanel()
        self._analysis_panel.apply_orientation.connect(self._on_apply_orientation)
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
        self._viewer.apply_orientation.connect(self._on_apply_orientation)
        self._viewer.reset_orientation.connect(self._on_reset_orientation)
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
        assets = Path(__file__).parent.parent / "assets"
        dlg = WelcomeDialog(self, assets_path=assets)
        apply_title_bar_theme(dlg)
        dlg.exec()

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

    def _on_tutorial_finished(self):
        self._tutorial = None

    # ── Handlers ───────────────────────────────────────────────────────────

    def _check_for_updates(self):
        from core.updater import check_for_update

        def _on_result(version: str | None, url: str, notes: str):
            if version:
                self._pending_update = (version, url, notes)
                QTimer.singleShot(0, self._show_update_dialog)

        self._pending_update: tuple | None = None
        check_for_update(_on_result)

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
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']};")
        lay.addWidget(title_lbl)

        # Corps
        body_lbl = QLabel(_("update.body", new=new_version, cur=cur_version))
        body_lbl.setFont(QFont("Segoe UI", 10))
        body_lbl.setTextFormat(Qt.RichText)
        body_lbl.setWordWrap(True)
        lay.addWidget(body_lbl)

        # Notes de version (optionnel)
        if notes:
            notes_title = QLabel(_("update.notes_label"))
            notes_title.setFont(QFont("Segoe UI", 8, QFont.Bold))
            notes_title.setStyleSheet(f"color: {pal['TEXT_LABEL']};")
            lay.addWidget(notes_title)
            notes_lbl = QLabel(notes)
            notes_lbl.setFont(QFont("Segoe UI", 9))
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
        status_lbl.setFont(QFont("Segoe UI", 9))
        status_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.hide()
        lay.addWidget(status_lbl)

        lay.addSpacing(2)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        later_btn = QPushButton(_("update.btn_later"))
        later_btn.setFont(QFont("Segoe UI", 9))
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
        install_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
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
                    tmp = tempfile.mktemp(suffix=".exe", prefix="neoSlice_update_")
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

    def _on_apply_orientation(self):
        """Applique la rotation optimale au mesh — calcul sur thread séparé."""
        if self._analysis is None or not self._analysis.optimal_rotation:
            return
        if self._orient_thread and self._orient_thread.isRunning():
            return

        rot = np.array(self._analysis.optimal_rotation).reshape(4, 4)
        self._viewer.stop_auto_rotate()
        self._viewer.hide_orient_btn()
        self._statusbar.set_message(_("status.orient_applying"), AMBER)

        self._orient_thread = QThread()
        self._orient_worker = OrientationWorker(self._mesh, rot)
        self._orient_worker.moveToThread(self._orient_thread)
        self._orient_thread.started.connect(self._orient_worker.run)
        self._orient_worker.done.connect(self._on_orientation_done)
        self._orient_worker.error.connect(self._on_orientation_error)
        self._orient_worker.done.connect(self._orient_thread.quit)
        self._orient_worker.error.connect(self._orient_thread.quit)
        self._orient_thread.start()

    def _on_orientation_done(self, rotated, colors):
        self._mesh = rotated
        self._viewer.load_mesh(self._mesh)
        if colors is not None:
            self._viewer.colorize_overhangs(self._mesh, colors)
        self._viewer.start_auto_rotate()
        self._analysis_panel.mark_orientation_applied()
        self._viewer.show_reset_btn()
        self._statusbar.set_message(_("status.orient_done"), AMBER)
        # Ré-analyser avec la nouvelle orientation pour montrer les vraies métriques
        self._start_analysis()

    def _on_orientation_error(self, msg):
        self._statusbar.set_message(_("status.orient_err", msg=msg), ERROR_RED)
        self._viewer.start_auto_rotate()

    def _on_reset_orientation(self):
        if self._original_mesh is None:
            return
        self._mesh = self._original_mesh
        self._viewer.stop_auto_rotate()
        self._viewer.load_mesh(self._mesh)
        self._viewer.hide_reset_btn()
        self._viewer.start_auto_rotate()
        self._statusbar.set_message(_("status.orient_reset"), AMBER)
        # Ré-analyser sur le mesh original pour restaurer les métriques d'origine
        self._start_analysis()

    def _on_new_piece(self):
        self._analysis_timeout.stop()
        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.quit()
            self._analysis_thread.wait(2000)
        if self._orient_thread and self._orient_thread.isRunning():
            self._orient_thread.quit()
            self._orient_thread.wait(2000)

        self._mesh = None
        self._original_mesh = None
        self._analysis = None
        self._current_config = None
        self._current_selection = None

        self._viewer.stop_auto_rotate()
        self._viewer.hide_orient_btn()
        self._viewer.hide_reset_btn()
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
        logger.info(f"STL reçu : {path}")
        self._stl_path = path
        self._statusbar.set_message(f"Chargement — {path.name}", AMBER)
        self._step_stl.set_active()

        self._viewer.hide_reset_btn()
        self._original_mesh = None
        try:
            self._mesh = load_stl(path)
            self._original_mesh = self._mesh.copy()
        except STLLoadError as e:
            self._statusbar.set_message(f"Erreur chargement : {e}", ERROR_RED)
            return
        except Exception as e:
            logger.exception("Erreur inattendue chargement fichier")
            self._statusbar.set_message(f"Erreur chargement : {e}", ERROR_RED)
            return
        except Exception as e:
            logger.exception("Erreur inattendue chargement fichier")
            self._statusbar.set_message(f"Erreur chargement : {e}", ERROR_RED)
            return

        self._viewer.stop_auto_rotate()
        self._viewer.load_mesh(self._mesh)
        self._topbar.set_has_stl(True)
        # Persistance du dernier fichier
        try:
            from ui.components.welcome_dialog import _load_prefs, _save_prefs
            _p = _load_prefs(); _p["last_stl"] = str(path); _save_prefs(_p)
        except Exception:
            pass
        self._drop_zone.set_recent_file(path)
        self._statusbar.set_message(_("status.loading", name=path.name), AMBER)
        self._start_analysis()

    def _start_analysis(self):
        self._analysis_timeout.stop()
        if self._analysis_thread and self._analysis_thread.isRunning():
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

        if report.overhang_severity > 0.05:
            try:
                mask = report.support_face_mask
                if mask is not None:
                    colors = support_face_colors(self._mesh, mask)
                else:
                    ov = analyze_overhangs(self._mesh)
                    colors = overhang_face_colors(self._mesh, ov)
                self._viewer.colorize_overhangs(self._mesh, colors)
            except Exception:
                logger.exception("colorize_overhangs échoué")

        self._viewer.start_auto_rotate()
        self._viewer.hide_orient_btn()

        if not PREFS.get("auto_rotate", True):
            self._analysis_panel.hide_orient_btn()

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

        dlg = QDialog(self)
        dlg.setWindowTitle("Fichier .3MF généré")
        dlg.setMinimumWidth(480)
        dlg.setStyleSheet(f"QDialog {{ background: {BG_PANEL}; }}")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        def _sep():
            s = QFrame()
            s.setFixedHeight(1)
            s.setStyleSheet(f"background: {INACTIVE};")
            return s

        def _section_lbl(text):
            l = QLabel(text)
            l.setFont(QFont("Segoe UI", 7, QFont.Bold))
            l.setStyleSheet(f"color: {TEXT_LABEL}; letter-spacing: 2px;")
            return l

        # ── Titre succès ──
        title = QLabel("✓   Fichier 3MF généré avec succès")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet(f"color: {TELE_GREEN};")
        layout.addWidget(title)

        layout.addWidget(_sep())

        # ── Action requise ──
        action_lbl = QLabel("⚠   ACTION REQUISE DANS BAMBU STUDIO")
        action_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        action_lbl.setStyleSheet(f"color: {AMBER};")
        layout.addWidget(action_lbl)

        info = QLabel(
            "Les paramètres d'impression (qualité, vitesse, supports…) sont intégrés dans le 3MF.<br>"
            "Les paramètres du <b>filament</b> (températures, ventilation, débit) doivent être "
            "configurés manuellement dans Bambu Studio."
        )
        info.setFont(QFont("Segoe UI", 9))
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(f"color: {TEXT_SECONDARY};")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Filament / Imprimante ──
        fil_box = QWidget()
        fil_box.setStyleSheet(f"background: {BG_SURFACE}; border-radius: 4px;")
        fil_layout = QVBoxLayout(fil_box)
        fil_layout.setContentsMargins(12, 8, 12, 8)
        fil_layout.setSpacing(4)

        def _kv(k, v, color=TELE_GREEN):
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            lbl_k = QLabel(k)
            lbl_k.setFont(QFont(FONT_MONO, 8))
            lbl_k.setStyleSheet(f"color: {TEXT_SECONDARY};")
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
                wlbl.setFont(QFont("Segoe UI", 8))
                wlbl.setStyleSheet(f"color: {ERROR_RED};")
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
        btn_pdf.setFont(QFont("Segoe UI", 9, QFont.Bold))
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
        btn_close.setFont(QFont("Segoe UI", 9, QFont.Bold))
        btn_close.setFixedHeight(34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {_ep['ACCENT']}; color: {_ep['EXPORT_FG']};
                border: none; border-radius: 4px; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {_ep['ACCENT_BRIGHT']}; }}
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
                if analysis and hasattr(self, "_current_config"):
                    ok = generate_full_report_pdf(
                        filament_name, printer_name,
                        self._current_config, analysis,
                        Path(save_path),
                        plate_type=_plate_type,
                    )
                else:
                    ok = generate_filament_pdf(
                        filament_name, printer_name, Path(save_path),
                        plate_type=_plate_type,
                    )
            except Exception as _pdf_err:
                logger.exception("Erreur génération PDF")
                QMessageBox.critical(dlg, "Erreur PDF", str(_pdf_err))
                return
            if ok:
                try:
                    subprocess.Popen(f'explorer /select,"{save_path}"')
                except Exception:
                    pass
                self._statusbar.set_message(f"PDF → {save_path}", TELE_GREEN)
            else:
                QMessageBox.critical(dlg, "Erreur PDF", "Génération échouée — reportlab installé ?")


        btn_bambu = QPushButton("  Ouvrir dans Bambu Studio")
        btn_bambu.setIcon(_make_printer_icon())
        btn_bambu.setIconSize(QSize(18, 18))
        btn_bambu.setFont(QFont("Segoe UI", 9, QFont.Bold))
        btn_bambu.setFixedHeight(34)
        btn_bambu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bambu.setStyleSheet(f"""
            QPushButton {{
                background: {_ep['BG_ELEVATED']}; color: {_ep['TELE_GREEN']};
                border: 1px solid {_ep['TELE_GREEN']}; border-radius: 4px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ep['TELE_GREEN']}; color: {_ep['EXPORT_FG']}; }}
        """)
        btn_bambu.setVisible(tmf_path is not None and tmf_path.exists())

        def _open_in_bambu():
            if tmf_path and tmf_path.exists():
                import os as _os
                try:
                    _os.startfile(str(tmf_path))
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
