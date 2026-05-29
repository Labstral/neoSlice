from __future__ import annotations

import math
import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox, QPushButton
from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QEvent, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient
from loguru import logger
from ui.styles.theme import MANAGER as _T
from core.i18n import _

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    HAS_PYVISTA = True
except Exception as e:
    logger.warning(f"pyvistaqt non disponible (import) : {e}")
    HAS_PYVISTA = False

try:
    from matplotlib.colors import LinearSegmentedColormap as _LSC
    _OVERHANG_CMAP_DARK  = _LSC.from_list("neoslice_oh_dk", ["#8A9BAD", "#D4A820", "#CC2010"])
    _OVERHANG_CMAP_LIGHT = _LSC.from_list("neoslice_oh_lt", ["#d8dde2", "#D4A820", "#CC2010"])
except Exception:
    _OVERHANG_CMAP_DARK  = "RdYlGn_r"
    _OVERHANG_CMAP_LIGHT = "RdYlGn_r"

try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False


# ── Overlay de chargement ──────────────────────────────────────────────────

class _LoadingOverlay(QWidget):
    """Overlay semi-transparent avec spinner NASA affiché au-dessus du viewer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._angle = 0
        self._text = _("viewer.loading_default")
        self._pulse = 0.0
        self._pulse_dir = 1

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def show_loading(self, text: str = ""):
        self._text = text or _("viewer.loading_default")
        self._angle = 0
        self._pulse = 0.0
        if self.parent():
            self.resize(self.parent().size())
        self._timer.start(16)
        self.show()
        self.raise_()

    def hide_loading(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._angle = (self._angle + 3) % 360
        self._pulse = self._pulse + 0.04 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse = 1.0
            self._pulse_dir = -1
        elif self._pulse <= 0.0:
            self._pulse = 0.0
            self._pulse_dir = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond semi-transparent adapté au thème
        _ov_pal = _T.palette()
        if _T.is_dark():
            painter.fillRect(self.rect(), QColor(3, 9, 18, 200))
        else:
            painter.fillRect(self.rect(), QColor(240, 242, 245, 200))

        cx = self.width() // 2
        cy = self.height() // 2 - 12

        R = 40  # rayon spinner

        # ── Cercle de fond (rail) ──
        pen_rail = QPen(QColor(30, 60, 100, 80), 5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_rail)
        painter.drawEllipse(cx - R, cy - R, R * 2, R * 2)

        # ── Arc spinner (trail dégradé en plusieurs passes) ──
        trail_steps = 6
        for i in range(trail_steps):
            alpha = int(255 * (i + 1) / trail_steps)
            blue = int(200 + 55 * (i / trail_steps))
            pen_arc = QPen(QColor(0, 170, blue, alpha), 5, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen_arc)
            # Chaque pas couvre 20° de l'arc total de 120°
            start = (90 - self._angle - i * 20) * 16
            span = -20 * 16
            painter.drawArc(cx - R, cy - R, R * 2, R * 2, start, span)

        # ── Tête de l'arc (point lumineux) ──
        head_alpha = int(180 + 75 * self._pulse)
        pen_head = QPen(QColor(80, 220, 255, head_alpha), 6, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_head)
        head_angle_rad = math.radians(self._angle)
        hx = cx + R * math.cos(head_angle_rad)
        hy = cy - R * math.sin(head_angle_rad)
        painter.drawPoint(int(hx), int(hy))

        # ── Texte principal ──
        text_y = cy + R + 22
        painter.setPen(QColor(180, 210, 240, 230))
        font = QFont("Segoe UI", 9, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        painter.setFont(font)
        painter.drawText(QRect(cx - 160, text_y, 320, 26), Qt.AlignCenter, self._text)

        # ── Sous-titre pulsant ──
        sub_alpha = int(100 + 80 * self._pulse)
        painter.setPen(QColor(80, 130, 170, sub_alpha))
        sub_font = QFont("Courier New", 7)
        sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        painter.setFont(sub_font)
        painter.drawText(QRect(cx - 160, text_y + 24, 320, 18), Qt.AlignCenter, _("viewer.loading_sub"))

        # ── Lignes HUD dans les coins ──
        size_hud = 16
        hud_col = QColor(0, 180, 255, int(80 + 40 * self._pulse))
        pen_hud = QPen(hud_col, 1)
        painter.setPen(pen_hud)
        margin = 14
        corners = [
            (margin, margin),
            (self.width() - margin, margin),
            (margin, self.height() - margin),
            (self.width() - margin, self.height() - margin),
        ]
        dirs = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
        for (ox, oy), (dx, dy) in zip(corners, dirs):
            painter.drawLine(ox, oy, ox + dx * size_hud, oy)
            painter.drawLine(ox, oy, ox, oy + dy * size_hud)


# ── Viewer 3D ──────────────────────────────────────────────────────────────

class Viewer3D(QWidget):
    """Visualisation 3D interactive du mesh STL.

    Utilise PyVista via pyvistaqt si disponible, sinon affiche un placeholder.
    Supporte la colorisation par zones (overhangs, fragilité).
    """

    apply_orientation = Signal()
    reset_orientation = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mesh = None
        self._face_colors: np.ndarray | None = None
        self._auto_rotate = False
        self._user_interacting = False
        self._setup_ui()
        self._overlay = _LoadingOverlay(self)
        self._setup_rotation()
        self._setup_orient_btn()
        self._setup_reset_btn()

    def _apply_rot_checkbox_style(self):
        pal = _T.palette()
        is_dk = _T.is_dark()
        if is_dk:
            bg = 'rgba(6,14,26,160)'; col = '#2A5F8A'; hov = '#4A7A9B'
            ind_bg = '#060E1A'; ind_br = '#1A3550'
        else:
            bg = 'rgba(240,242,245,200)'; col = '#555555'; hov = '#333333'
            ind_bg = '#ffffff'; ind_br = '#c0c0c0'
        acc = pal['ACCENT']
        self._rot_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {col}; background: {bg};
                spacing: 5px; padding: 2px 6px; border-radius: 3px;
            }}
            QCheckBox:hover {{ color: {hov}; }}
            QCheckBox::indicator {{
                width: 11px; height: 11px;
                border: 1px solid {ind_br}; border-radius: 2px;
                background: {ind_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {acc}; border-color: {acc};
            }}
        """)

    def _apply_plate_checkbox_style(self):
        pal = _T.palette()
        is_dk = _T.is_dark()
        if is_dk:
            bg = 'rgba(6,14,26,160)'; col = '#2A5F8A'; hov = '#4A7A9B'
            ind_bg = '#060E1A'; ind_br = '#1A3550'
        else:
            bg = 'rgba(240,242,245,200)'; col = '#555555'; hov = '#333333'
            ind_bg = '#ffffff'; ind_br = '#c0c0c0'
        acc = pal['ACCENT']
        self._plate_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {col}; background: {bg};
                spacing: 5px; padding: 2px 6px; border-radius: 3px;
            }}
            QCheckBox:hover {{ color: {hov}; }}
            QCheckBox::indicator {{
                width: 11px; height: 11px;
                border: 1px solid {ind_br}; border-radius: 2px;
                background: {ind_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {acc}; border-color: {acc};
            }}
        """)

    def _on_plate_toggle(self, state: int):
        if self._plotter is None:
            return
        try:
            visible = bool(state)
            for name in ("build_plate_surface", "build_plate_grid"):
                if name in self._plotter.actors:
                    if visible:
                        self._plotter.actors[name].VisibilityOn()
                    else:
                        self._plotter.actors[name].VisibilityOff()
            self._plotter.render()
        except Exception:
            pass

    def refresh_theme(self):
        if hasattr(self, '_rot_checkbox'):
            self._apply_rot_checkbox_style()
        if hasattr(self, '_plate_checkbox'):
            self._apply_plate_checkbox_style()
        if self._plotter is not None:
            pal = _T.palette()
            try:
                _saved_cam = self._plotter.camera_position
                self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
                if self._mesh is not None:
                    self._plotter.remove_actor("build_plate_surface", render=False)
                    self._plotter.remove_actor("build_plate_grid", render=False)
                    self._add_build_plate()
                    if getattr(self, "_view_mode", "normal") == "normal":
                        _mesh_color = "#5A7AAA" if _T.is_dark() else "#f8f8f8"
                        self._plotter.remove_actor("main_mesh", render=False)
                        pv_mesh = self._smooth_normals(self._trimesh_to_pyvista(self._mesh))
                        self._plotter.add_mesh(
                            pv_mesh,
                            color=_mesh_color,
                            show_edges=False,
                            smooth_shading=True,
                            pbr=True,
                            metallic=0.0,
                            roughness=0.38,
                            ambient=0.15,
                            name="main_mesh",
                            reset_camera=False,
                        )
                    elif getattr(self, "_view_mode", "normal") == "analysis" \
                            and self._face_colors is not None:
                        self.colorize_overhangs(self._mesh, self._face_colors, _keep_camera=True)
                    self._plotter.camera_position = _saved_cam
                self._plotter.render()
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_overlay"):
            self._overlay.resize(self.size())
        if hasattr(self, "_rot_checkbox") and hasattr(self, "_plate_checkbox"):
            cw = max(
                self._rot_checkbox.sizeHint().width() + 16,
                self._plate_checkbox.sizeHint().width() + 16,
            )
            self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
            self._plate_checkbox.setGeometry(self.width() - cw - 8, self.height() - 56, cw, 22)
        elif hasattr(self, "_rot_checkbox"):
            cw = self._rot_checkbox.sizeHint().width() + 16
            self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
        if hasattr(self, "_orient_btn_viewer"):
            bw = self._orient_btn_viewer.sizeHint().width() + 20
            self._orient_btn_viewer.setGeometry(10, 10, bw, 28)
        if hasattr(self, "_reset_btn_viewer") and self._reset_btn_viewer.isVisible():
            bw = self._reset_btn_viewer.sizeHint().width() + 20
            self._reset_btn_viewer.setGeometry(10, 10, bw, 28)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plotter = None
        if HAS_PYVISTA:
            try:
                self._plotter = QtInteractor(self)
                pal = _T.palette()
                self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
                self._plotter.hide_axes()
                layout.addWidget(self._plotter)
                # Différer anti-aliasing et SSAO après que le widget est affiché
                # pour éviter l'erreur "framebuffer not initialized" de VTK
                QTimer.singleShot(800, self._init_opengl_effects)
                return
            except Exception as e:
                logger.warning(f"pyvistaqt non disponible (init) : {e}")
                self._plotter = None

        placeholder = QLabel(_("viewer.no_pyvista"))
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(
            "color: #4A4A6A; font-size: 13px; "
            "background-color: #070710; border-radius: 10px;"
        )
        layout.addWidget(placeholder)

    def _init_opengl_effects(self):
        """Initialise les effets OpenGL haute qualité après affichage de la fenêtre."""
        if self._plotter is None:
            return
        # MSAA 8× — anti-aliasing multi-échantillon, élimine le crénelage des arêtes
        try:
            self._plotter.ren_win.SetMultiSamples(8)
        except Exception:
            pass
        # FXAA — passe supplémentaire de lissage des arêtes
        try:
            self._plotter.renderer.SetUseFXAA(True)
        except Exception:
            pass
        # SSAO très léger — occlusion ambiante subtile sans artefacts
        # radius en unités monde (mm) : 0.4 mm → effet doux aux jonctions de surfaces
        # NE PAS activer depth peeling avec SSAO (conflit FBO dans VTK)
        try:
            self._plotter.enable_ssao(radius=0.4, bias=0.02, kernel_size=48, blur=True)
        except Exception:
            pass

    def _setup_orient_btn(self):
        """Bouton flottant en haut à gauche du viewer — appliquer l'orientation optimale."""
        self._orient_btn_viewer = QPushButton(_("viewer.orient_btn"), self)
        self._orient_btn_viewer.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._orient_btn_viewer.setFixedHeight(28)
        self._orient_btn_viewer.setCursor(Qt.PointingHandCursor)
        self._orient_btn_viewer.setStyleSheet("""
            QPushButton {
                background: rgba(6,14,26,200);
                color: #1E90FF;
                border: 1px solid #1E90FF;
                border-radius: 4px;
                padding: 0 12px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #1E90FF;
                color: #020408;
            }
        """)
        self._orient_btn_viewer.hide()
        self._orient_btn_viewer.clicked.connect(self.apply_orientation)

    def _setup_rotation(self):
        """Timer de rotation automatique (~30fps, 0.3°/frame ≈ 1 tour en 20s)."""
        self._rot_timer = QTimer(self)
        self._rot_timer.setInterval(33)
        self._rot_timer.timeout.connect(self._tick_rotate)

        self._resume_timer = QTimer(self)
        self._resume_timer.setSingleShot(True)
        self._resume_timer.timeout.connect(self._on_resume_rotate)

        self._rot_checkbox = QCheckBox(_("viewer.auto_rotate"), self)
        self._rot_checkbox.setChecked(False)
        self._rot_checkbox.setFont(QFont("Segoe UI", 9))
        self._apply_rot_checkbox_style()
        self._rot_checkbox.hide()
        self._rot_checkbox.stateChanged.connect(self._on_rot_toggle)

        self._plate_checkbox = QCheckBox(_("viewer.show_plate"), self)
        self._plate_checkbox.setChecked(True)
        self._plate_checkbox.setFont(QFont("Segoe UI", 9))
        self._apply_plate_checkbox_style()
        self._plate_checkbox.hide()
        self._plate_checkbox.stateChanged.connect(self._on_plate_toggle)

    def _on_rot_toggle(self, state: int):
        if state:  # 2 = Qt.Checked, 0 = Qt.Unchecked
            self._auto_rotate = True
            if self._plotter:
                self._rot_timer.start()
                self._rot_checkbox.raise_()
        else:
            self._auto_rotate = False
            self._rot_timer.stop()

    def _on_resume_rotate(self):
        self._user_interacting = False

    def _tick_rotate(self):
        if not self._auto_rotate or self._user_interacting or self._plotter is None:
            return
        try:
            focal = np.array(self._plotter.camera.focal_point)
            pos   = np.array(self._plotter.camera.position)
            d     = pos - focal
            # Orbite autour de l'axe Z monde (plateau à plat)
            angle = math.radians(0.8)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            new_pos = focal + np.array([
                d[0] * cos_a - d[1] * sin_a,
                d[0] * sin_a + d[1] * cos_a,
                d[2],
            ])
            self._plotter.camera.position = tuple(new_pos)
            self._plotter.camera.up = (0.0, 0.0, 1.0)
            self._plotter.renderer.ResetCameraClippingRange()
            self._plotter.render()
            # Force repaint des widgets Qt superposés (checkbox, boutons) après render VTK
            if hasattr(self, "_rot_checkbox"):
                self._rot_checkbox.update()
            if hasattr(self, "_plate_checkbox") and self._plate_checkbox.isVisible():
                self._plate_checkbox.update()
            if hasattr(self, "_orient_btn_viewer") and self._orient_btn_viewer.isVisible():
                self._orient_btn_viewer.update()
            if hasattr(self, "_reset_btn_viewer") and self._reset_btn_viewer.isVisible():
                self._reset_btn_viewer.update()
        except Exception as _e:
            logger.warning(f"Erreur rotation auto : {_e}")

    def show_orient_btn(self, label: str = "", clickable: bool = True) -> None:
        """Affiche le bouton d'orientation. clickable=False → info non-cliquable qui disparaît."""
        if clickable:
            text = _("viewer.orient_apply_lbl", label=label) if label else _("viewer.orient_btn")
            self._orient_btn_viewer.setEnabled(True)
            self._orient_btn_viewer.setCursor(Qt.PointingHandCursor)
            self._orient_btn_viewer.setStyleSheet("""
                QPushButton {
                    background: rgba(6,14,26,200);
                    color: #1E90FF;
                    border: 1px solid #1E90FF;
                    border-radius: 4px;
                    padding: 0 12px;
                    letter-spacing: 1px;
                }
                QPushButton:hover { background: #1E90FF; color: #020408; }
            """)
        else:
            text = label or _("viewer.orient_optimal")
            self._orient_btn_viewer.setEnabled(False)
            self._orient_btn_viewer.setCursor(Qt.ArrowCursor)
            self._orient_btn_viewer.setStyleSheet("""
                QPushButton {
                    background: rgba(6,14,26,180);
                    color: #2ECC71;
                    border: 1px solid #2ECC71;
                    border-radius: 4px;
                    padding: 0 12px;
                    letter-spacing: 1px;
                }
                QPushButton:disabled { color: #2ECC71; border-color: #2ECC71; }
            """)
            QTimer.singleShot(4000, self.hide_orient_btn)

        self._orient_btn_viewer.setText(text)
        bw = self._orient_btn_viewer.sizeHint().width() + 20
        self._orient_btn_viewer.setGeometry(10, 10, bw, 28)
        self._orient_btn_viewer.show()
        self._orient_btn_viewer.raise_()

    def hide_orient_btn(self) -> None:
        """Masque le bouton d'orientation."""
        self._orient_btn_viewer.hide()

    def _setup_reset_btn(self):
        """Bouton flottant — réinitialiser l'orientation d'origine."""
        self._reset_btn_viewer = QPushButton(_("viewer.orient_reset"), self)
        self._reset_btn_viewer.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._reset_btn_viewer.setFixedHeight(28)
        self._reset_btn_viewer.setCursor(Qt.PointingHandCursor)
        self._reset_btn_viewer.setStyleSheet("""
            QPushButton {
                background: rgba(6,14,26,200);
                color: #F0A500;
                border: 1px solid #F0A500;
                border-radius: 4px;
                padding: 0 12px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #F0A500;
                color: #020408;
            }
        """)
        self._reset_btn_viewer.hide()
        self._reset_btn_viewer.clicked.connect(self.reset_orientation)

    def show_reset_btn(self) -> None:
        """Affiche le bouton de réinitialisation de l'orientation."""
        bw = self._reset_btn_viewer.sizeHint().width() + 20
        self._reset_btn_viewer.setGeometry(10, 10, bw, 28)
        self._reset_btn_viewer.show()
        self._reset_btn_viewer.raise_()

    def hide_reset_btn(self) -> None:
        """Masque le bouton de réinitialisation."""
        self._reset_btn_viewer.hide()

    def start_auto_rotate(self):
        """Démarre la rotation automatique après analyse (case cochée par défaut)."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        from core.prefs import PREFS
        _lite = PREFS.get("perf_mode", "full") == "lite"

        # Plateau checkbox — toujours visible après analyse, quel que soit le mode
        cw_plt = self._plate_checkbox.sizeHint().width() + 16
        if _lite:
            self._plate_checkbox.setGeometry(self.width() - cw_plt - 8, self.height() - 30, cw_plt, 22)
            self._plate_checkbox.show()
            self._plate_checkbox.raise_()
            return

        self._auto_rotate = True
        self._rot_checkbox.blockSignals(True)
        self._rot_checkbox.setChecked(True)
        self._rot_checkbox.blockSignals(False)
        # Positionne et affiche les checkboxes en bas à droite
        cw_rot = self._rot_checkbox.sizeHint().width() + 16
        cw = max(cw_rot, cw_plt)
        self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
        self._rot_checkbox.show()
        self._rot_checkbox.raise_()
        self._plate_checkbox.setGeometry(self.width() - cw - 8, self.height() - 56, cw, 22)
        self._plate_checkbox.show()
        self._plate_checkbox.raise_()
        self._rot_timer.start()
        self._plotter.installEventFilter(self)

    def stop_auto_rotate(self):
        """Arrête et masque la rotation (reset / nouvelle pièce)."""
        self._auto_rotate = False
        self._rot_timer.stop()
        self._rot_checkbox.blockSignals(True)
        self._rot_checkbox.setChecked(False)
        self._rot_checkbox.blockSignals(False)
        self._rot_checkbox.hide()
        self._plate_checkbox.hide()
        if self._plotter:
            self._plotter.removeEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._plotter:
            t = event.type()
            if t == QEvent.MouseButtonPress:
                self._user_interacting = True
                self._resume_timer.stop()
            elif t == QEvent.MouseButtonRelease:
                self._resume_timer.start(800)
            elif t == QEvent.Wheel:
                # Zoom molette : pause courte sans couper la rotation
                self._resume_timer.start(600)
        return False

    def _setup_lights(self):
        """Éclairage 4 points cinématographique : key chaud / fill froid / rim / bounce plateau."""
        self._plotter.remove_all_lights()
        # Key — lumière principale, blanc chaud, haut-droite-devant
        self._plotter.add_light(pv.Light(
            position=(6, 4, 10), focal_point=(0, 0, 0),
            intensity=0.88, color=[1.0, 0.97, 0.92],
        ))
        # Fill — côté gauche, bleu doux, adoucit les ombres du key
        self._plotter.add_light(pv.Light(
            position=(-5, -2, 4), focal_point=(0, 0, 0),
            intensity=0.26, color=[0.82, 0.90, 1.0],
        ))
        # Rim — contre-jour arrière-droit, révèle les contours
        self._plotter.add_light(pv.Light(
            position=(2, -7, 2), focal_point=(0, 0, 0),
            intensity=0.16, color=[0.88, 0.94, 1.0],
        ))
        # Bounce — réflexion montante depuis le plateau, très subtile
        self._plotter.add_light(pv.Light(
            position=(0, 0, -6), focal_point=(0, 0, 0),
            intensity=0.05, color=[1.0, 0.96, 0.88],
        ))

    _PLATE_SIZE = 256.0   # mm — plateau carré fixe (256 × 256)
    _PLATE_GRID = 10.0    # mm — espacement de la grille

    def _add_build_plate(self, mesh=None) -> None:
        """Ajoute un plateau dont la taille s'adapte à la pièce chargée."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        try:
            if mesh is not None:
                max_dim = float(mesh.bounding_box.extents.max())
                plate_size = min(max_dim * 3.0, self._PLATE_SIZE)
                plate_size = max(plate_size, 15.0)
                raw = plate_size / 10.0
                magnitude = 10.0 ** int(np.floor(np.log10(max(raw, 1e-9))))
                spacing = max(round(raw / magnitude) * magnitude, 0.01)
            else:
                plate_size = self._PLATE_SIZE
                spacing = self._PLATE_GRID
            self._current_plate_size = plate_size
            half = plate_size / 2.0

            # Surface — couleur selon thème
            _bp_dark = _T.is_dark()
            plate = pv.Plane(
                center=(0.0, 0.0, -0.5),
                direction=(0, 0, 1),
                i_size=plate_size,
                j_size=plate_size,
                i_resolution=1,
                j_resolution=1,
            )
            self._plotter.add_mesh(
                plate,
                color="#070E18" if _bp_dark else "#8e9296",
                opacity=0.15 if _bp_dark else 0.70,
                show_edges=False,
                ambient=0.65,
                name="build_plate_surface",
                pickable=False,
            )

            # Grille 10 mm (de -128 à +128)
            pts, segs, idx = [], [], 0
            for x in np.arange(-half, half + 1e-6, spacing):
                pts += [[x, -half, 0.0], [x, half, 0.0]]
                segs += [2, idx, idx + 1]
                idx += 2
            for y in np.arange(-half, half + 1e-6, spacing):
                pts += [[-half, y, 0.0], [half, y, 0.0]]
                segs += [2, idx, idx + 1]
                idx += 2

            grid = pv.PolyData()
            grid.points = np.array(pts, dtype=np.float32)
            grid.lines = np.array(segs, dtype=np.int_)
            self._plotter.add_mesh(
                grid,
                color="#163548" if _bp_dark else "#808488",
                opacity=0.55,
                line_width=0.8,
                name="build_plate_grid",
                pickable=False,
            )
        except Exception:
            pass

    def load_mesh(self, mesh) -> None:
        """Affiche un trimesh.Trimesh dans le viewer."""
        if not HAS_PYVISTA or self._plotter is None:
            return

        self._mesh = mesh
        self._face_colors = None
        self._view_mode = "normal"
        self._plotter.clear()
        self._setup_lights()
        self._add_build_plate(mesh)

        pv_mesh = self._smooth_normals(self._trimesh_to_pyvista(mesh))
        _mesh_color = "#5A7AAA" if _T.is_dark() else "#f8f8f8"

        self._plotter.add_mesh(
            pv_mesh,
            color=_mesh_color,
            show_edges=False,
            smooth_shading=True,
            pbr=True,
            metallic=0.0,
            roughness=0.38,
            ambient=0.15,
            name="main_mesh",
        )

        half = getattr(self, "_current_plate_size", self._PLATE_SIZE) / 2.0
        mesh_h = float(mesh.bounding_box.extents[2])
        self._plotter.renderer.ResetCamera(-half, half, -half, half, -0.5, mesh_h + 1.0)
        self._plotter.camera.elevation = 20
        self._plotter.camera.zoom(0.72)
        self._plotter.renderer.ResetCameraClippingRange()
        self._plotter.render()

    def colorize_overhangs(self, mesh, face_colors: np.ndarray, _keep_camera: bool = False) -> None:
        """Recolorie le mesh selon les zones de surplomb — rendu smooth par vertex."""
        if not HAS_PYVISTA or self._plotter is None:
            return

        self._view_mode = "analysis"
        self._face_colors = face_colors
        self._plotter.clear()
        self._setup_lights()
        self._add_build_plate(mesh)
        # NE PAS appeler _smooth_normals : split_vertices=True change le n_points
        # et casserait la correspondance face→vertex de nos scalaires.
        # Pas de problème visuel : ambient=1.0 / diffuse=0.0, les normales n'ont aucun effet.
        pv_mesh = self._trimesh_to_pyvista(mesh)

        # Sévérité par face [0, 1]
        b_ch = face_colors[:, 2].astype(np.int32)
        g_ch = face_colors[:, 1].astype(np.int32)
        face_sev = np.zeros(len(face_colors), dtype=np.float32)
        oh = b_ch < 100
        face_sev[oh & (g_ch > 140)] = 0.55
        face_sev[oh & (g_ch > 60) & (g_ch <= 140)] = 0.80
        face_sev[oh & (g_ch <= 60)] = 1.0

        # Face → vertex : chaque vertex = moyenne des faces adjacentes.
        # np.bincount est O(F), bien plus rapide que np.add.at sur gros meshes.
        n_v = len(mesh.vertices)
        f = mesh.faces                          # (F, 3)
        flat = f.ravel()                        # (F*3,)
        rep  = np.repeat(face_sev, 3)           # sévérité répétée 3× par face
        v_sev = np.bincount(flat, weights=rep,  minlength=n_v)
        v_cnt = np.bincount(flat,               minlength=n_v)
        v_sev /= np.maximum(v_cnt, 1)

        # Passe de diffusion : blend 65% valeur propre + 35% moyenne voisins directs.
        # Adoucit les transitions entre zones — donne des contours ronds sans artefacts.
        v0, v1, v2 = f[:, 0], f[:, 1], f[:, 2]
        nbr = (
            np.bincount(v0, weights=v_sev[v1] + v_sev[v2], minlength=n_v)
          + np.bincount(v1, weights=v_sev[v0] + v_sev[v2], minlength=n_v)
          + np.bincount(v2, weights=v_sev[v0] + v_sev[v1], minlength=n_v)
        )
        v_sev = v_sev * 0.65 + (nbr / np.maximum(v_cnt * 2, 1)) * 0.35

        pv_mesh.point_data["overhang"] = v_sev.astype(np.float32)
        self._plotter.add_mesh(
            pv_mesh,
            scalars="overhang",
            cmap=_OVERHANG_CMAP_DARK if _T.is_dark() else _OVERHANG_CMAP_LIGHT,
            clim=[0.0, 1.0],
            show_scalar_bar=False,
            smooth_shading=True,
            ambient=1.0,
            diffuse=0.0,
            specular=0.0,
            name="main_mesh",
        )

        if not _keep_camera:
            self._plotter.reset_camera()
            self._plotter.camera.elevation = -25
            self._plotter.camera.azimuth = 30
        self._plotter.render()

    def set_loading(self, loading: bool, text: str = ""):
        """Affiche ou masque l'overlay de chargement sur le viewer."""
        if loading:
            self._overlay.show_loading(text or _("viewer.loading_orient"))
        else:
            self._overlay.hide_loading()

    def reset(self):
        """Efface la scène — appelé lors d'une nouvelle pièce."""
        if self._plotter:
            self._plotter.clear()
            self._mesh = None
            self._plotter.render()

    def reset_view(self):
        if self._plotter:
            self._plotter.reset_camera()
            self._plotter.render()

    @staticmethod
    def _trimesh_to_pyvista(mesh) -> "pv.PolyData":
        """Convertit un trimesh.Trimesh en pyvista.PolyData."""
        faces = np.column_stack([
            np.full(len(mesh.faces), 3, dtype=np.int_),
            mesh.faces,
        ]).ravel()
        return pv.PolyData(mesh.vertices.astype(np.float32), faces)

    @staticmethod
    def _smooth_normals(pv_mesh: "pv.PolyData") -> "pv.PolyData":
        """Calcule des normales lissées par vertex — élimine les facettes et artefacts triangulaires.

        feature_angle=25° : les surfaces < 25° entre faces sont lissées ;
        les vraies arêtes vives (> 25°) restent nettes.
        """
        try:
            return pv_mesh.compute_normals(
                cell_normals=False,
                point_normals=True,
                feature_angle=25.0,
                split_vertices=True,
                flip_normals=False,
                consistent_normals=True,
                non_manifold_traversal=True,
                progress_bar=False,
            )
        except Exception:
            return pv_mesh

    def closeEvent(self, event):
        if self._plotter is not None:
            self._plotter.close()
        super().closeEvent(event)
