from __future__ import annotations

import math
import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox, QPushButton
from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QEvent, Signal, QThread, QObject
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient
from loguru import logger
from ui.styles.theme import MANAGER as _T, FONT_MAIN
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
    # Gradient Bambu-style : gris neutre → jaune → orange → rouge
    _OVERHANG_CMAP_DARK  = _LSC.from_list("neoslice_oh_dk", ["#8A9BAD", "#FFE000", "#FF6600", "#CC2010"])
    _OVERHANG_CMAP_LIGHT = _LSC.from_list("neoslice_oh_lt", ["#C8D4DC", "#FFE000", "#FF6600", "#CC2010"])
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
        font = QFont(FONT_MAIN, 9, QFont.Bold)
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


# _MeshPrepWorker supprimé — compute_normals VTK dans un QThread cause
# wglMakeCurrent conflicts (error 170). Phase 2 tourne maintenant sur le
# main thread via QTimer.singleShot avec compteur de génération.


# ── Viewer 3D ──────────────────────────────────────────────────────────────

class Viewer3D(QWidget):
    """Visualisation 3D interactive du mesh STL.

    Utilise PyVista via pyvistaqt si disponible, sinon affiche un placeholder.
    Supporte la colorisation par zones (overhangs, fragilité).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mesh = None
        self._pv_mesh_cache = None   # cache pyvista mesh — évite de recalculer les normales
        self._face_colors: np.ndarray | None = None
        self._auto_rotate = False
        self._user_interacting = False
        self._setup_ui()
        self._overlay = _LoadingOverlay(self)
        self._setup_rotation()

    def _apply_rot_checkbox_style(self):
        pal = _T.palette()
        is_dk = _T.is_dark()
        if is_dk:
            bg = 'rgba(6,14,26,160)'; col = '#2A5F8A'; hov = '#4A7A9B'
            ind_bg = '#060E1A'; ind_br = '#1A3550'
        else:
            bg = 'rgba(240,242,245,200)'; col = '#555555'; hov = '#333333'
            ind_bg = '#ffffff'; ind_br = '#c0c0c0'
        acc = pal['TELE_GREEN']
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
        acc = pal['TELE_GREEN']
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
                    self._plotter.actors[name].visibility = visible
            self._plotter.render()
        except Exception:
            pass

    def refresh_theme(self):
        if hasattr(self, '_rot_checkbox'):
            self._apply_rot_checkbox_style()
        if hasattr(self, '_plate_checkbox'):
            self._apply_plate_checkbox_style()
        pal = _T.palette()
        self.setStyleSheet(f"background: {pal['VIEWER_BG']};")
        if self._plotter is None:
            return
        # Fond VTK — toujours mis à jour (indépendant du mesh)
        try:
            self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
        except Exception:
            pass
        # Mesh — mise à jour du matériau/plateau si une pièce est chargée
        if self._mesh is not None:
            try:
                _saved_cam = self._plotter.camera_position
                self._plotter.remove_actor("build_plate_surface", render=False)
                self._plotter.remove_actor("build_plate_grid", render=False)
                self._add_build_plate(self._mesh)
                if getattr(self, "_view_mode", "normal") == "normal":
                    _mesh_color = "#e8e4de"
                    rq = self._render_quality()
                    self._plotter.remove_actor("main_mesh", render=False)
                    # Réutilise le mesh pyvista en cache — évite de recalculer les normales
                    if self._pv_mesh_cache is not None:
                        pv_mesh = self._pv_mesh_cache
                    else:
                        pv_mesh = self._place_on_plate(self._smooth_normals(self._trimesh_to_pyvista(self._mesh), rq["feature_angle"]))
                        self._pv_mesh_cache = pv_mesh
                    self._plotter.add_mesh(
                        pv_mesh,
                        color=_mesh_color,
                        show_edges=False,
                        smooth_shading=True,
                        pbr=True,
                        metallic=rq["metallic"],
                        roughness=rq["roughness"],
                        ambient=rq["ambient"],
                        diffuse=rq["diffuse"],
                        specular=rq["specular"],
                        name="main_mesh",
                        reset_camera=False,
                    )
                elif getattr(self, "_view_mode", "normal") == "analysis" \
                        and self._face_colors is not None:
                    self.colorize_overhangs(self._mesh, self._face_colors, _keep_camera=True)
                self._plotter.camera_position = _saved_cam
            except Exception:
                pass
        # Render final — toujours exécuté
        try:
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

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plotter = None
        self._init_cover = None
        if HAS_PYVISTA:
            try:
                pal = _T.palette()
                self.setStyleSheet(f"background: {pal['VIEWER_BG']};")
                self._plotter = QtInteractor(self)
                self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
                self._plotter.hide_axes()
                layout.addWidget(self._plotter)
                # Forcer le premier rendu (fond) puis les effets OpenGL après affichage
                QTimer.singleShot(300, self._init_background)
                QTimer.singleShot(900, self._init_opengl_effects)
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

    def _init_background(self):
        """Force le rendu du fond dès que VTK est prêt."""
        if self._plotter is None:
            return
        try:
            pal = _T.palette()
            self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
            self._plotter.render()
        except Exception:
            pass

    def _init_opengl_effects(self):
        """Initialise les effets OpenGL ultra qualité après affichage de la fenêtre."""
        if self._plotter is None:
            return
        # Lissage rasterisation — réduit le crénelage sur les contours et arêtes
        try:
            self._plotter.ren_win.SetPolygonSmoothing(True)
            self._plotter.ren_win.SetLineSmoothing(True)
            self._plotter.ren_win.SetPointSmoothing(True)
        except Exception:
            pass
        # MSAA — le SetMultiSamples entre en conflit avec SSAO (FBO), on désactive
        # pour laisser FXAA + polygon smoothing gérer l'AA
        try:
            self._plotter.ren_win.SetMultiSamples(0)
        except Exception:
            pass
        # FXAA — post-process haute qualité, compatible SSAO
        try:
            self._plotter.enable_anti_aliasing('fxaa')
        except Exception:
            pass
        # SSAO — qualité selon le mode de performance
        ssao = self._render_quality()["ssao"]
        if ssao is not None:
            try:
                self._plotter.enable_ssao(**ssao)
            except Exception:
                try:
                    self._plotter.enable_ssao(radius=0.8, bias=0.01, kernel_size=32, blur=True)
                except Exception:
                    pass
        # Depth peeling — transparence correcte pour les couches qui se croisent
        try:
            self._plotter.enable_depth_peeling(number_of_peels=4, occlusion_ratio=0.0)
        except Exception:
            pass
        # Tone mapping VTK — mappage HDR → évite les blancs brûlés, rendu cinématique
        try:
            rw = self._plotter.ren_win
            rw.SetToneMappingType(3)     # GenericFilmic (similaire Unreal)
            rw.SetExposure(1.0)
        except Exception:
            try:
                rw = self._plotter.ren_win
                rw.SetToneMappingType(1)  # Reinhard (fallback)
            except Exception:
                pass
        # Re-render après les effets pour s'assurer que le fond est toujours correct
        try:
            pal = _T.palette()
            self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
            self._plotter.render()
        except Exception:
            pass
        self._setup_cam_observer()

    def _setup_cam_observer(self):
        """Rend le plateau transparent quand la caméra passe en dessous (vue Bambu Studio)."""
        if self._plotter is None:
            return
        try:
            def _cam_cb(caller, event):
                try:
                    pos = self._plotter.camera.position
                    actor = self._plotter.actors.get("build_plate_surface")
                    if actor:
                        actor.prop.opacity = 0.0 if pos[2] < 0 else self._PLATE_OPACITY
                except Exception:
                    pass
            self._plotter.renderer.GetActiveCamera().AddObserver("ModifiedEvent", _cam_cb)
        except Exception:
            pass

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
        self._rot_checkbox.setFont(QFont(FONT_MAIN, 9))
        self._apply_rot_checkbox_style()
        self._rot_checkbox.hide()
        self._rot_checkbox.stateChanged.connect(self._on_rot_toggle)

        self._plate_checkbox = QCheckBox(_("viewer.show_plate"), self)
        self._plate_checkbox.setChecked(True)
        self._plate_checkbox.setFont(QFont(FONT_MAIN, 9))
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
            # Pivot fixe = centre de la pièce, indépendant du pan caméra
            pivot = getattr(self, '_rotation_pivot',
                            np.array(self._plotter.camera.focal_point))

            pos   = np.array(self._plotter.camera.position)
            focal = np.array(self._plotter.camera.focal_point)

            angle = math.radians(0.8)
            cos_a, sin_a = math.cos(angle), math.sin(angle)

            def _rot_xy(p):
                d = p - pivot
                return pivot + np.array([
                    d[0] * cos_a - d[1] * sin_a,
                    d[0] * sin_a + d[1] * cos_a,
                    d[2],
                ])

            self._plotter.camera.position    = tuple(_rot_xy(pos))
            self._plotter.camera.focal_point = tuple(_rot_xy(focal))
            self._plotter.camera.up = (0.0, 0.0, 1.0)
            self._plotter.renderer.ResetCameraClippingRange()
            self._plotter.render()
            # repaint() synchrone évite le flash async de update()
            if hasattr(self, "_rot_checkbox") and self._rot_checkbox.isVisible():
                self._rot_checkbox.raise_()
                self._rot_checkbox.repaint()
            if hasattr(self, "_plate_checkbox") and self._plate_checkbox.isVisible():
                self._plate_checkbox.raise_()
                self._plate_checkbox.repaint()
        except Exception as _e:
            logger.warning(f"Erreur rotation auto : {_e}")

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
        """Éclairage studio 8 points — qualité cinématique (type Unreal Engine)."""
        self._plotter.remove_all_lights()
        # Key principale — haut-droite-devant, blanc chaud soleil
        self._plotter.add_light(pv.Light(
            position=(6, 4, 14), focal_point=(0, 0, 0),
            intensity=1.50, color=[1.0, 0.97, 0.90],
        ))
        # Key large — haut-gauche, softbox secondaire
        self._plotter.add_light(pv.Light(
            position=(-4, 6, 11), focal_point=(0, 0, 0),
            intensity=0.65, color=[1.0, 0.98, 0.96],
        ))
        # Fill — gauche-bas, bleu ciel froid pour contrebalancer
        self._plotter.add_light(pv.Light(
            position=(-10, -2, 2), focal_point=(0, 0, 0),
            intensity=0.28, color=[0.72, 0.86, 1.0],
        ))
        # Rim fort — contre-jour arrière (separation light), éclat maximal
        self._plotter.add_light(pv.Light(
            position=(-1, -12, 6), focal_point=(0, 0, 0),
            intensity=0.80, color=[0.80, 0.90, 1.0],
        ))
        # Rim droit — contre-jour droit, sépare la pièce du fond
        self._plotter.add_light(pv.Light(
            position=(10, -6, 4), focal_point=(0, 0, 0),
            intensity=0.40, color=[0.88, 0.94, 1.0],
        ))
        # Top — zénithale, illumine les surfaces horizontales
        self._plotter.add_light(pv.Light(
            position=(0, 0, 18), focal_point=(0, 0, 0),
            intensity=0.28, color=[0.93, 0.96, 1.0],
        ))
        # Bounce — réflexion montante depuis le plateau (GI simulé)
        self._plotter.add_light(pv.Light(
            position=(0, 0, -10), focal_point=(0, 0, 0),
            intensity=0.10, color=[1.0, 0.97, 0.90],
        ))
        # Accent latéral — souligne les détails fins sur la droite
        self._plotter.add_light(pv.Light(
            position=(12, 2, 0), focal_point=(0, 0, 0),
            intensity=0.20, color=[1.0, 0.98, 0.88],
        ))

    _PLATE_SIZE    = 256.0  # mm — plateau par défaut sans mesh
    _PLATE_GRID    = 10.0   # mm — espacement de la grille
    _PLATE_OPACITY = 0.90   # opacité plateau vue de dessus (0 depuis dessous)

    def _add_build_plate(self, mesh=None) -> None:
        """Ajoute un plateau dont la taille s'adapte à la pièce chargée."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        try:
            if mesh is not None:
                # Empreinte XY uniquement — ne pas utiliser Z (hauteur) qui rendrait
                # le plateau minuscule pour les pièces très hautes (arbres, tours, etc.)
                ext = mesh.bounding_box.extents
                footprint = float(max(ext[0], ext[1]))
                plate_size = max(footprint * 2.5, 30.0)
                raw = plate_size / 10.0
                magnitude = 10.0 ** int(np.floor(np.log10(max(raw, 1e-9))))
                spacing = max(round(raw / magnitude) * magnitude, 0.01)
            else:
                plate_size = self._PLATE_SIZE
                spacing = self._PLATE_GRID
            self._current_plate_size = plate_size
            half = plate_size / 2.0

            # Plateau style Bambu Studio — couleurs identiques quel que soit le thème
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
                color="#2a2b2e",
                opacity=self._PLATE_OPACITY,
                show_edges=False,
                name="build_plate_surface",
                pickable=False,
            )

            # Grille carrée : forcer spacing à diviser plate_size exactement
            n_cells = max(2, round(plate_size / spacing))
            spacing = plate_size / n_cells
            lines = np.linspace(-half, half, n_cells + 1)

            # Z=-0.1 : offset suffisant vs plateau à Z=-0.5 pour éviter le Z-fighting VTK
            _gz = -0.1
            pts, segs, idx = [], [], 0
            for x in lines:
                pts += [[x, -half, _gz], [x, half, _gz]]
                segs += [2, idx, idx + 1]
                idx += 2
            for y in lines:
                pts += [[-half, y, _gz], [half, y, _gz]]
                segs += [2, idx, idx + 1]
                idx += 2

            grid = pv.PolyData()
            grid.points = np.array(pts, dtype=np.float32)
            grid.lines = np.array(segs, dtype=np.int_)
            _grid_color   = "#454749" if _T.is_dark() else "#6a6e72"
            _grid_opacity = 1.0
            _grid_width   = 1.2      if _T.is_dark() else 1.4
            self._plotter.add_mesh(
                grid,
                color=_grid_color,
                opacity=_grid_opacity,
                line_width=_grid_width,
                name="build_plate_grid",
                pickable=False,
            )
        except Exception:
            pass

    def _cancel_mesh_prep(self) -> None:
        """Annule la Phase 2 en cours en incrémentant le compteur de génération."""
        self._load_gen = getattr(self, '_load_gen', 0) + 1

    # Couleurs de prévisualisation par slot AMS (neutres, distinctes)
    _SLOT_COLORS = {
        1: "#DCDCD4", 2: "#7EC4E8", 3: "#E89C6C", 4: "#7CD4A0",
        5: "#C07CE0", 6: "#E0E07C", 7: "#E07C7C", 8: "#7CE0E0",
    }

    def _load_multipart_mesh(self, threemf_data) -> None:
        """Affiche un 3MF multi-objets — chaque objet = acteur séparé coloré par slot."""
        from core.geometry.threemf_data import ThreeMFData

        combined = threemf_data.combined_mesh
        self._mesh = combined
        self._pv_mesh_cache = None
        self._face_colors = None
        self._view_mode = "normal"
        self._plotter.clear()
        self._setup_lights()
        self._add_build_plate(combined)

        _bb = combined.bounding_box.extents
        self._rotation_pivot = np.array([0.0, 0.0, float(_bb[2]) * 0.5])

        # Calcul de l'offset global : centrer XY, poser à Z=0
        # combined.bounds = [[xmin,ymin,zmin], [xmax,ymax,zmax]]
        b = combined.bounds
        ox = -(float(b[0][0]) + float(b[1][0])) / 2
        oy = -(float(b[0][1]) + float(b[1][1])) / 2
        oz = -float(b[0][2])

        _total_faces = sum(len(o.mesh.faces) for o in threemf_data.objects)
        _smooth = _total_faces < 150_000

        for obj in threemf_data.objects:
            try:
                m = obj.mesh.copy()
                if not np.allclose(obj.transform, np.eye(4)):
                    m.apply_transform(obj.transform)
                m.apply_translation([ox, oy, oz])
                pv_obj = self._trimesh_to_pyvista(m)
                color = self._SLOT_COLORS.get(obj.extruder, "#AABBCC")
                actor_name = f"obj_{obj.object_id}"
                self._plotter.add_mesh(
                    pv_obj, color=color, show_edges=False,
                    smooth_shading=_smooth,
                    pbr=False, ambient=0.15, diffuse=0.85,
                    name=actor_name,
                )
            except Exception as _e:
                logger.warning(f"Objet {obj.name} non affiché : {_e}")

        # Caméra basée sur le mesh combiné
        try:
            _elev = math.radians(25)
            _far  = 1e6
            self._plotter.camera.position = (0.0, -math.cos(_elev) * _far,
                                              math.sin(_elev) * _far)
            self._plotter.camera.focal_point = (0.0, 0.0, 0.0)
            self._plotter.camera.up = (0.0, 0.0, 1.0)
            _pad = float(combined.bounding_box.extents.max()) * 0.5
            # Bounds approximatifs du mesh centré
            _hw = float(combined.bounding_box.extents[0]) / 2 + _pad
            _hd = float(combined.bounding_box.extents[1]) / 2 + _pad
            _ht = float(combined.bounding_box.extents[2]) + _pad
            _pv_b = [-_hw, _hw, -_hd, _hd, -_pad * 0.2, _ht]
            try:
                self._plotter.reset_camera(bounds=_pv_b)
            except TypeError:
                self._plotter.reset_camera()
            self._plotter.renderer.ResetCameraClippingRange()
        except Exception as _ce:
            logger.warning(f"Camera setup multipart échoué : {_ce}")
            self._plotter.reset_camera()

        self._plotter.render()
        logger.info(f"3MF multipart affiché : {threemf_data.object_count} objets · {threemf_data.slot_count} slot(s)")

    def load_mesh(self, mesh) -> None:
        """Affiche un trimesh.Trimesh ou ThreeMFData."""
        if not HAS_PYVISTA or self._plotter is None:
            return

        # Route vers le renderer multi-acteurs pour les 3MF multicolores
        try:
            from core.geometry.threemf_data import ThreeMFData as _TMF
            if isinstance(mesh, _TMF):
                self._cancel_mesh_prep()
                self._load_multipart_mesh(mesh)
                return
        except ImportError:
            pass

        # Arrêter Phase 2 précédente AVANT plotter.clear() — évite wglMakeCurrent conflict
        self._cancel_mesh_prep()

        self._mesh = mesh
        self._pv_mesh_cache = None
        self._face_colors = None
        self._view_mode = "normal"
        self._plotter.clear()
        self._setup_lights()
        self._add_build_plate(mesh)

        # Centre de rotation fixe = centre XY de la pièce posée sur le plateau
        # Stocké maintenant pour que _tick_rotate orbite toujours autour de lui,
        # même si l'utilisateur a pané la caméra entre-temps.
        _bb = mesh.bounding_box.extents
        self._rotation_pivot = np.array([0.0, 0.0, float(_bb[2]) * 0.5])

        # ── Phase 1 : affichage immédiat
        # smooth_shading=False pour les grands meshes : évite le calcul VTK de normales
        # (30-60s sur 6M faces). Pour les petits meshes (< 100k faces), smooth=True est rapide.
        _n_faces = len(mesh.faces)
        _ultra_poly_display = _n_faces > 500_000
        _phase1_smooth = _n_faces < 100_000
        raw_pv = self._place_on_plate(self._trimesh_to_pyvista(mesh))
        try:
            self._plotter.add_mesh(
                raw_pv, color="#e8e4de", show_edges=False,
                smooth_shading=_phase1_smooth, name="main_mesh",
            )
        except Exception as _e:
            logger.warning(f"Phase 1 add_mesh échoué : {_e}")

        # Caméra — positionnée dès la phase 1
        try:
            _elev = math.radians(25)
            _far  = 1e6
            self._plotter.camera.position = (0.0, -math.cos(_elev) * _far,
                                              math.sin(_elev) * _far)
            self._plotter.camera.focal_point = (0.0, 0.0, 0.0)
            self._plotter.camera.up = (0.0, 0.0, 1.0)
            _pad = float(mesh.bounding_box.extents.max()) * 0.5
            _pb  = raw_pv.bounds
            _pv_b = [_pb[0]-_pad, _pb[1]+_pad, _pb[2]-_pad, _pb[3]+_pad,
                     _pb[4]-_pad*0.2, _pb[5]+_pad*0.5]
            try:
                self._plotter.reset_camera(bounds=_pv_b)
            except TypeError:
                self._plotter.reset_camera()
                self._plotter.camera.zoom(2.0)
            self._plotter.renderer.ResetCameraClippingRange()
        except Exception as _ce:
            logger.warning(f"Camera setup échoué : {_ce}")
            self._plotter.reset_camera()

        self._plotter.render()   # ← mesh visible immédiatement

        # ── Phase 2 : normales PBR sur main thread via QTimer (évite wglMakeCurrent) ──
        if _ultra_poly_display:
            logger.info(f"Phase 2 PBR skippée ({_n_faces:,} faces > 500k)")
            return
        rq = self._render_quality()
        self._load_gen = getattr(self, '_load_gen', 0) + 1
        _gen      = self._load_gen
        _raw_copy = raw_pv  # pas de .copy() — on réutilise direct (déjà local)

        def _phase2():
            if getattr(self, '_load_gen', 0) != _gen:
                return   # un nouveau mesh a été chargé entre-temps
            try:
                pv_mesh = _raw_copy.compute_normals(
                    cell_normals=False,
                    point_normals=True,
                    feature_angle=rq["feature_angle"],
                )
                self._apply_pbr_mesh(pv_mesh, rq)
            except Exception as exc:
                logger.warning(f"Phase 2 normals échouée : {exc}")

        QTimer.singleShot(300, _phase2)

    def _apply_pbr_mesh(self, pv_mesh, rq: dict) -> None:
        """Reçu sur le main thread — remplace le mesh brut par la version PBR."""
        if pv_mesh is None or self._mesh is None or self._plotter is None:
            return
        if self._view_mode != "normal":
            return   # l'utilisateur est déjà passé en mode analyse
        self._pv_mesh_cache = pv_mesh
        try:
            self._plotter.add_mesh(
                pv_mesh,
                color="#e8e4de",
                show_edges=False,
                smooth_shading=True,
                pbr=True,
                metallic=rq["metallic"],
                roughness=rq["roughness"],
                ambient=rq["ambient"],
                diffuse=rq["diffuse"],
                specular=rq["specular"],
                name="main_mesh",
                reset_camera=False,
            )
            self._plotter.render()
        except Exception as _me:
            logger.warning(f"PBR upgrade échoué : {_me}")

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
        pv_mesh = self._place_on_plate(self._trimesh_to_pyvista(mesh))

        # Sévérité par face [0, 1] — canal R = sévérité encodée, G=128 = face sûre
        face_sev = face_colors[:, 0].astype(np.float32) / 255.0

        # Face → vertex : chaque vertex = moyenne des faces adjacentes.
        # np.bincount est O(F), bien plus rapide que np.add.at sur gros meshes.
        n_v = len(mesh.vertices)
        f = mesh.faces                          # (F, 3)
        flat = f.ravel()                        # (F*3,)
        rep  = np.repeat(face_sev, 3)           # sévérité répétée 3× par face
        v_sev = np.bincount(flat, weights=rep,  minlength=n_v)
        v_cnt = np.bincount(flat,               minlength=n_v)
        v_sev /= np.maximum(v_cnt, 1)

        # Passe de diffusion légère — adoucit les contours sans diluer les zones sévères.
        # Le max() préserve la valeur haute si un voisin est moins sévère.
        v0, v1, v2 = f[:, 0], f[:, 1], f[:, 2]
        nbr = (
            np.bincount(v0, weights=v_sev[v1] + v_sev[v2], minlength=n_v)
          + np.bincount(v1, weights=v_sev[v0] + v_sev[v2], minlength=n_v)
          + np.bincount(v2, weights=v_sev[v0] + v_sev[v1], minlength=n_v)
        )
        v_sev_diffused = v_sev * 0.80 + (nbr / np.maximum(v_cnt * 2, 1)) * 0.20
        # Conserver le maximum pour ne pas dégrader les pics de sévérité élevée
        v_sev = np.maximum(v_sev, v_sev_diffused)

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
            try:
                _elev = math.radians(25)
                _far = 1e6
                self._plotter.camera.position = (0.0, -math.cos(_elev) * _far,
                                                  math.sin(_elev) * _far)
                self._plotter.camera.focal_point = (0.0, 0.0, 0.0)
                self._plotter.camera.up = (0.0, 0.0, 1.0)
                _pad = float(mesh.bounding_box.extents.max()) * 0.5
                _pb = pv_mesh.bounds
                _pv_b = [_pb[0]-_pad, _pb[1]+_pad, _pb[2]-_pad, _pb[3]+_pad,
                         _pb[4]-_pad*0.2, _pb[5]+_pad*0.5]
                try:
                    self._plotter.reset_camera(bounds=_pv_b)
                except TypeError:
                    self._plotter.reset_camera()
                    self._plotter.camera.zoom(2.0)
                self._plotter.renderer.ResetCameraClippingRange()
            except Exception:
                self._plotter.reset_camera()
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
    def _place_on_plate(pv_mesh: "pv.PolyData") -> "pv.PolyData":
        """Translate mesh to sit on plate: centered on XY, Z_min=0."""
        b = pv_mesh.bounds  # xmin, xmax, ymin, ymax, zmin, zmax
        pv_mesh.translate([-(b[0]+b[1])/2, -(b[2]+b[3])/2, -b[4]], inplace=True)
        return pv_mesh

    @staticmethod
    def _trimesh_to_pyvista(mesh) -> "pv.PolyData":
        """Convertit un trimesh.Trimesh en pyvista.PolyData."""
        faces = np.column_stack([
            np.full(len(mesh.faces), 3, dtype=np.int_),
            mesh.faces,
        ]).ravel()
        return pv.PolyData(mesh.vertices.astype(np.float32), faces)

    @staticmethod
    def _render_quality() -> dict:
        """Paramètres de rendu selon le mode de performance (PREFS)."""
        from core.prefs import PREFS
        mode = PREFS.get("perf_mode", "full")
        _Q = {
            "full": {
                # PBR ultra qualité — lisse comme du PLA brillant, éclairage cinématique
                "metallic": 0.08, "roughness": 0.06, "specular": 0.92,
                "ambient": 0.01,  "diffuse":  0.98,
                "feature_angle": 8.0,
                "ssao": dict(radius=1.8, bias=0.003, kernel_size=256, blur=True),
            },
            "balanced": {
                "metallic": 0.10, "roughness": 0.28, "specular": 0.35,
                "ambient": 0.06,  "diffuse":  0.90,
                "feature_angle": 25.0,
                "ssao": dict(radius=0.9, bias=0.010, kernel_size=64,  blur=True),
            },
            "lite": {
                "metallic": 0.00, "roughness": 0.55, "specular": 0.00,
                "ambient": 0.15,  "diffuse":  0.85,
                "feature_angle": 45.0,
                "ssao": None,
            },
        }
        return _Q.get(mode, _Q["full"])

    @staticmethod
    def _smooth_normals(pv_mesh: "pv.PolyData", feature_angle: float = 20.0) -> "pv.PolyData":
        """Calcule des normales lissées par vertex — élimine les facettes et artefacts triangulaires."""
        try:
            return pv_mesh.compute_normals(
                cell_normals=False,
                point_normals=True,
                feature_angle=feature_angle,
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
