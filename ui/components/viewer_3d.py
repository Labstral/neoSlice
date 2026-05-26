from __future__ import annotations

import math
import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox, QPushButton
from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QEvent, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient
from loguru import logger

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    HAS_PYVISTA = True
except Exception as e:
    logger.warning(f"pyvistaqt non disponible (import) : {e}")
    HAS_PYVISTA = False

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
        self._text = "ANALYSE EN COURS..."
        self._pulse = 0.0
        self._pulse_dir = 1

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def show_loading(self, text: str = "ANALYSE EN COURS..."):
        self._text = text
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

        # Fond semi-transparent dégradé radial
        painter.fillRect(self.rect(), QColor(3, 9, 18, 200))

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
        painter.drawText(QRect(cx - 160, text_y + 24, 320, 18), Qt.AlignCenter, "CALCUL EN COURS — VEUILLEZ PATIENTER")

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_overlay"):
            self._overlay.resize(self.size())
        if hasattr(self, "_rot_checkbox"):
            cw = self._rot_checkbox.sizeHint().width() + 16
            self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 26, cw, 22)
        if hasattr(self, "_orient_btn_viewer"):
            bw = self._orient_btn_viewer.sizeHint().width() + 20
            self._orient_btn_viewer.setGeometry(10, 10, bw, 28)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plotter = None
        if HAS_PYVISTA:
            try:
                self._plotter = QtInteractor(self)
                self._plotter.set_background("#030912", top="#0B1A2E")
                self._plotter.hide_axes()
                layout.addWidget(self._plotter)
                # Différer anti-aliasing et SSAO après que le widget est affiché
                # pour éviter l'erreur "framebuffer not initialized" de VTK
                QTimer.singleShot(800, self._init_opengl_effects)
                return
            except Exception as e:
                logger.warning(f"pyvistaqt non disponible (init) : {e}")
                self._plotter = None

        placeholder = QLabel(
            "Visualisation 3D\n\n"
            "Installez pyvistaqt pour activer le viewer :\n"
            "pip install pyvistaqt"
        )
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(
            "color: #4A4A6A; font-size: 13px; "
            "background-color: #070710; border-radius: 10px;"
        )
        layout.addWidget(placeholder)

    def _init_opengl_effects(self):
        """Initialise anti-aliasing et SSAO après que la fenêtre est visible."""
        if self._plotter is None:
            return
        try:
            self._plotter.enable_anti_aliasing()
        except Exception:
            pass
        try:
            self._plotter.enable_ssao(radius=0.8, bias=0.025, kernel_size=32, blur=True)
        except Exception:
            pass

    def _setup_orient_btn(self):
        """Bouton flottant en haut à gauche du viewer — appliquer l'orientation optimale."""
        self._orient_btn_viewer = QPushButton("↻  Appliquer l'orientation optimale", self)
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

        self._rot_checkbox = QCheckBox("⟳  Rotation auto", self)
        self._rot_checkbox.setChecked(False)
        self._rot_checkbox.setFont(QFont("Segoe UI", 7))
        self._rot_checkbox.setStyleSheet("""
            QCheckBox {
                color: #2A5F8A;
                background: rgba(6,14,26,160);
                spacing: 5px;
                padding: 2px 6px;
                border-radius: 3px;
            }
            QCheckBox:hover { color: #4A7A9B; }
            QCheckBox::indicator {
                width: 11px; height: 11px;
                border: 1px solid #1A3550;
                border-radius: 2px;
                background: #060E1A;
            }
            QCheckBox::indicator:checked {
                background: #1E90FF;
                border-color: #1E90FF;
            }
        """)
        self._rot_checkbox.hide()
        self._rot_checkbox.stateChanged.connect(self._on_rot_toggle)

    def _on_rot_toggle(self, state: int):
        if state:  # 2 = Qt.Checked, 0 = Qt.Unchecked
            self._auto_rotate = True
            if self._plotter:
                self._rot_timer.start()
                self._rot_checkbox.raise_()
        else:
            self._auto_rotate = False
            self._rot_timer.stop()

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
        except Exception:
            pass

    def show_orient_btn(self, label: str = "", clickable: bool = True) -> None:
        """Affiche le bouton d'orientation. clickable=False → info non-cliquable qui disparaît."""
        if clickable:
            text = f"↻  {label}" if label else "↻  Appliquer l'orientation optimale"
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
            text = label or "✓  Orientation actuelle : optimale"
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

    def start_auto_rotate(self):
        """Démarre la rotation automatique après analyse (case cochée par défaut)."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        self._auto_rotate = True
        self._rot_checkbox.blockSignals(True)
        self._rot_checkbox.setChecked(True)
        self._rot_checkbox.blockSignals(False)
        # Positionne et affiche le checkbox au-dessus du renderer OpenGL
        cw = self._rot_checkbox.sizeHint().width() + 16
        self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
        self._rot_checkbox.show()
        self._rot_checkbox.raise_()
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
        if self._plotter:
            self._plotter.removeEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._plotter:
            t = event.type()
            if t in (QEvent.MouseButtonPress, QEvent.Wheel):
                self._user_interacting = True
            elif t == QEvent.MouseButtonRelease:
                self._user_interacting = False
        return False

    def _setup_lights(self):
        """Éclairage 3-points équilibré : ratio key/fill ~3:1 pour des ombres douces mais lisibles."""
        self._plotter.remove_all_lights()
        self._plotter.add_light(pv.Light(
            position=(4, 3, 6), focal_point=(0, 0, 0), intensity=0.90,
        ))
        self._plotter.add_light(pv.Light(
            position=(-4, -2, 3), focal_point=(0, 0, 0), intensity=0.32,
        ))
        self._plotter.add_light(pv.Light(
            position=(0, -5, 0), focal_point=(0, 0, 0), intensity=0.18,
        ))

    def load_mesh(self, mesh) -> None:
        """Affiche un trimesh.Trimesh dans le viewer."""
        if not HAS_PYVISTA or self._plotter is None:
            return

        self._mesh = mesh
        self._face_colors = None
        self._plotter.clear()
        self._setup_lights()

        pv_mesh = self._trimesh_to_pyvista(mesh)

        self._plotter.add_mesh(
            pv_mesh,
            color="#5A7AAA",
            show_edges=False,
            smooth_shading=True,
            pbr=True,
            metallic=0.05,
            roughness=0.45,
            name="main_mesh",
        )

        self._plotter.reset_camera()
        self._plotter.camera.elevation = 20
        self._plotter.render()

    def colorize_overhangs(self, mesh, face_colors: np.ndarray) -> None:
        """Recolorie le mesh selon les zones de surplomb.

        face_colors : ndarray (N, 4) RGBA uint8 par face.
        """
        if not HAS_PYVISTA or self._plotter is None:
            return

        self._plotter.clear()
        self._setup_lights()
        pv_mesh = self._trimesh_to_pyvista(mesh)

        severity = face_colors[:, 0].astype(float) / 255.0
        pv_mesh.cell_data["overhang"] = severity

        # Auto-scale : si le max réel est < 0.4 on compresse à 0.5 pour que
        # même les petits surplombs passent en jaune/rouge et restent lisibles.
        clim_max = max(0.5, float(severity.max()))

        self._plotter.add_mesh(
            pv_mesh,
            scalars="overhang",
            cmap="RdYlGn_r",
            clim=[0, clim_max],
            show_scalar_bar=False,
            smooth_shading=True,
            name="main_mesh",
        )
        self._plotter.render()

    def set_loading(self, loading: bool, text: str = "OPTIMISATION DE L'ORIENTATION..."):
        """Affiche ou masque l'overlay de chargement sur le viewer."""
        if loading:
            self._overlay.show_loading(text)
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

    def closeEvent(self, event):
        if self._plotter is not None:
            self._plotter.close()
        super().closeEvent(event)
