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
    # Gradient : blanc cassé (safe) → jaune → orange → rouge profond
    # Zones safe = blanc → pièces lisibles, surplombs = couleurs vives
    _OVERHANG_CMAP_DARK  = _LSC.from_list("neoslice_oh_dk",
        [(0.0, "#C8C4BE"), (0.22, "#FFE000"), (0.55, "#FF4400"), (0.82, "#CC0000"), (1.0, "#880000")])
    _OVERHANG_CMAP_LIGHT = _LSC.from_list("neoslice_oh_lt",
        [(0.0, "#D4D0CA"), (0.22, "#FFE000"), (0.55, "#FF4400"), (0.82, "#CC0000"), (1.0, "#880000")])
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
        pen_rail = QPen(QColor(101, 148, 243, 70), 5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_rail)
        painter.drawEllipse(cx - R, cy - R, R * 2, R * 2)

        # ── Arc spinner : traînée en dégradé PRO (cyan → violet) qui tourne ──
        _cyan = (34, 211, 238)      # PRO_CYAN (tête)
        _violet = (168, 85, 247)    # PRO_VIOLET (queue)
        trail_steps = 6
        for i in range(trail_steps):
            alpha = int(255 * (i + 1) / trail_steps)
            f = i / (trail_steps - 1)          # 0 (queue=violet) → 1 (tête=cyan)
            r = int(_violet[0] + (_cyan[0] - _violet[0]) * f)
            g = int(_violet[1] + (_cyan[1] - _violet[1]) * f)
            b = int(_violet[2] + (_cyan[2] - _violet[2]) * f)
            pen_arc = QPen(QColor(r, g, b, alpha), 5, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen_arc)
            # Chaque pas couvre 20° de l'arc total de 120°
            start = (90 - self._angle - i * 20) * 16
            span = -20 * 16
            painter.drawArc(cx - R, cy - R, R * 2, R * 2, start, span)

        # ── Texte principal (contraste adapté au thème) ──
        text_y = cy + R + 22
        if _T.is_dark():
            painter.setPen(QColor(180, 210, 240, 230))
        else:
            painter.setPen(QColor(30, 50, 80, 245))   # bleu nuit lisible sur fond clair
        font = QFont(FONT_MAIN, 9, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        painter.setFont(font)
        # Élider à la largeur du cadre (320px) : un nom de fichier long ne doit pas
        # être coupé aux deux bouts.
        _txt = painter.fontMetrics().elidedText(self._text, Qt.ElideMiddle, 306)
        painter.drawText(QRect(cx - 160, text_y, 320, 26), Qt.AlignCenter, _txt)

        # ── Sous-titre pulsant ──
        sub_alpha = int(100 + 80 * self._pulse)
        if _T.is_dark():
            painter.setPen(QColor(80, 130, 170, sub_alpha))
        else:
            painter.setPen(QColor(55, 85, 120, min(255, sub_alpha + 70)))
        sub_font = QFont(FONT_MAIN, 7)
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

    # (index élément, dx_mm, dy_mm) — élément de carte déplacé à la souris
    element_deplace = Signal(int, float, float)

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
        self._setup_strands()

    _STRANDS_SIZE = 120     # côté de la sphère décorative (px)
    _STRANDS_MARGIN_X = 0   # marge gauche (px, négatif = décale vers la gauche)
    _STRANDS_MARGIN_Y = -6  # marge basse (px, négatif = descend la sphère)

    def _setup_strands(self):
        """Prépare l'overlay sphère. La création réelle est différée à showEvent :
        à l'__init__, le viewer n'est pas encore rattaché → self.window() serait faux."""
        self._strands = None
        self._strands_win = None

    def showEvent(self, event):
        super().showEvent(event)
        if (getattr(self, "_strands", None) is None and HAS_PYVISTA
                and self._plotter is not None):
            try:
                # Mini-fenêtre top-level translucide (vraie transparence via le système,
                # au-dessus de la fenêtre native VTK). Suit neoSlice via l'eventFilter.
                from ui.components.strands_widget import StrandsOverlay
                win = self.window()
                self._strands = StrandsOverlay(win, px=self._STRANDS_SIZE, translucent=True)
                self._strands.clicked.connect(self._open_assistant)
                self._strands_win = win
                if win is not None:
                    win.installEventFilter(self)
            except Exception as e:
                logger.warning(f"Strands overlay non disponible : {e}")
                self._strands = None
        self._reposition_strands()

    def _open_assistant(self):
        """Clic sur la sphère → ouvre (ou ferme) la fenêtre glass de l'assistant."""
        try:
            from ui.components.glass_panel import GlassPanel
        except Exception as e:
            logger.warning(f"GlassPanel indisponible : {e}")
            return
        if getattr(self, "_glass", None) is None:
            self._glass = GlassPanel(self.window())
            # Pendant que l'IA rédige, la sphère s'anime plus (vagues plus vives)
            if self._strands is not None:
                self._glass.busy_changed.connect(self._strands.set_active)
        if self._glass.isVisible():
            self._glass.close_anim()
            return
        from PySide6.QtCore import QPoint
        s = self._strands
        anchor = s.mapToGlobal(QPoint(s.width() // 2, s.height() // 3)) if s else None
        self._glass.open_from(anchor)

    def _begin_settle(self):
        """Agrandir/réduire (WindowStateChange) : la fenêtre s'anime côté OS. On masque
        la sphère et on ignore les repositionnements tant que ça bouge, puis on la
        remet une fois stabilisée → plus de « saut » en avance."""
        s = getattr(self, "_strands", None)
        if s is None:
            return
        self._strands_settling = True
        s.hide()
        if not hasattr(self, "_strands_settle"):
            from PySide6.QtCore import QTimer
            self._strands_settle = QTimer(self)
            self._strands_settle.setSingleShot(True)
            self._strands_settle.timeout.connect(self._end_settle)
        self._strands_settle.start(220)

    def _end_settle(self):
        self._strands_settling = False
        self._reposition_strands()

    @staticmethod
    def _assistant_enabled() -> bool:
        """Oen est une fonctionnalité Pro : la sphère n'apparaît qu'en version Pro."""
        try:
            from core import licensing
            return bool(licensing.est_pro())
        except Exception:
            return False

    def refresh_assistant_visibility(self):
        """À appeler quand l'état Pro change (activation) → montre/masque la sphère."""
        self._reposition_strands()

    def masquer_sphere_pour_modal(self, masquer: bool) -> None:
        """Masque la sphère Oen pendant qu'un DIALOGUE MODAL est ouvert. La
        sphère est une fenêtre OpenGL top-level TOUJOURS au premier plan
        (raise_) : la laisser flotter au-dessus d'un modal fait planter Windows
        quand le système est sous charge (ex. installation d'Oen qui sature le
        GPU/compositeur) — crash « Espace Pro pendant l'install » signalé.
        Réentrant : un compteur autorise des modaux imbriqués (paywall→ProHub)."""
        self._modal_depth = getattr(self, "_modal_depth", 0) + (1 if masquer else -1)
        self._modal_depth = max(0, self._modal_depth)
        s = getattr(self, "_strands", None)
        if s is None:
            return
        if self._modal_depth > 0:
            s.hide()
        else:
            self._reposition_strands()

    def _reposition_strands(self):
        """Cale l'overlay sphère sur le coin bas-gauche du viewer (coords écran)."""
        s = getattr(self, "_strands", None)
        if s is None:
            return
        from PySide6.QtCore import QPoint
        win = self.window()
        # Gating Pro : en version non-Pro, Oen est masqué (sphère cachée).
        if not self._assistant_enabled():
            s.hide()
            return
        # Un modal est ouvert : la sphère OpenGL ne doit PAS repasser au premier
        # plan par-dessus lui (crash Windows sous charge — voir masquer_sphere).
        if getattr(self, "_modal_depth", 0) > 0:
            s.hide()
            return
        if (win is not None and win.isMinimized()) or not self.isVisible():
            s.hide()
            return
        g = self.mapToGlobal(QPoint(
            self._STRANDS_MARGIN_X,
            self.height() - self._STRANDS_SIZE - self._STRANDS_MARGIN_Y))
        s.move(g)
        if not s.isVisible():
            s.show()
        s.raise_()

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
                outline: none;
            }}
            QCheckBox:focus {{ outline: none; }}
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
                outline: none;
            }}
            QCheckBox:focus {{ outline: none; }}
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
            for name, actor in self._plotter.actors.items():
                if name.startswith("build_plate_surface") or name.startswith("build_plate_grid"):
                    actor.visibility = visible
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
        # labels du widget d'orientation : lisibles dans le nouveau thème
        self._style_orient_labels()
        # Mesh — mise à jour du matériau/plateau si une pièce est chargée
        if self._mesh is not None:
            try:
                _saved_cam = self._plotter.camera_position
                self._plotter.remove_actor("build_plate_surface", render=False)
                self._plotter.remove_actor("build_plate_grid", render=False)
                self._add_build_plate(self._mesh)
                if getattr(self, "_view_mode", "normal") == "normal":
                    _mesh_color = "#f2ede8"
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
                        pbr=False,   # mat lumineux (cohérent avec _apply_pbr_mesh)
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
        # Recréer les barres de fragilité — colorize_overhangs (mode analyse) a fait
        # plotter.clear() qui efface les vtkFollower. Sans ça, les barres
        # disparaissent au changement de thème.
        if getattr(self, "_fragility_bars_data", None):
            try:
                self.show_fragility_bars(self._fragility_bars_data)
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

        if getattr(self, "_strands", None) is not None and not getattr(self, "_strands_settling", False):
            self._reposition_strands()

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
        self._gl_failed = False   # True si l'init OpenGL échoue (≠ lib absente)
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
                logger.warning(f"init 3D (OpenGL) échouée : {e}")
                self._plotter = None
                self._gl_failed = True

        self._build_viewer_placeholder(layout)

    def _build_viewer_placeholder(self, layout):
        """Message d'indisponibilité du viewer, distinct selon la cause :
        - lib pyvista absente (cas dev),
        - OpenGL non supporté par la machine (cas le plus courant côté utilisateur)
          → propose le mode compatibilité (rendu logiciel) avec redémarrage.
        - échec même en mode compatibilité."""
        from core.prefs import PREFS
        software_on = PREFS.get("viewer_software_gl", False)
        if not HAS_PYVISTA:
            msg = _("viewer.no_pyvista")
        elif software_on:
            msg = _("viewer.software_failed")
        else:
            msg = _("viewer.no_opengl")

        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setAlignment(Qt.AlignCenter)
        hl.setSpacing(14)
        holder.setStyleSheet("background-color: #070710; border-radius: 10px;")

        label = QLabel(msg)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #6A6A8A; font-size: 13px; background: transparent;")
        hl.addWidget(label)

        # Bouton mode compatibilité : uniquement si l'OpenGL a échoué et qu'on n'est
        # pas déjà en logiciel (sinon inutile).
        if HAS_PYVISTA and self._gl_failed and not software_on:
            btn = QPushButton(_("viewer.btn_software"))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { color: #fff; background: #1E90FF; border: none; "
                "border-radius: 5px; padding: 8px 16px; font-size: 12px; }"
                "QPushButton:hover { background: #3AA0FF; }")
            btn.clicked.connect(self._enable_software_gl_and_restart)
            hl.addWidget(btn, alignment=Qt.AlignCenter)

        layout.addWidget(holder)

    def _enable_software_gl_and_restart(self):
        """Active le rendu OpenGL logiciel et redémarre neoSlice pour l'appliquer."""
        import sys as _sys
        from core.prefs import PREFS
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        PREFS.set("viewer_software_gl", True)
        args = _sys.argv[1:] if getattr(_sys, "frozen", False) else _sys.argv
        QProcess.startDetached(_sys.executable, args)
        QApplication.quit()

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
        # Re-render après les effets
        try:
            pal = _T.palette()
            self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
            self._plotter.render()
        except Exception:
            pass
        self._setup_orientation_cube()
        self._setup_cam_observer()

    def _setup_orientation_cube(self):
        """Widget d'orientation CLIQUABLE en haut à droite (axes X/Y/Z à boules) :
        clic sur un axe -> la caméra se recentre de ce côté. Couleurs pâles
        classiques (X rouge, Y vert pomme, Z bleu-violet) et labels adaptés au
        thème (lisibles en clair ET en sombre)."""
        if self._plotter is None:
            return
        try:
            w = self._plotter.add_camera_orientation_widget()
            rep = w.GetRepresentation()
            rep.SetXAxisColor(0.90, 0.46, 0.46)     # rouge pâle
            rep.SetYAxisColor(0.56, 0.83, 0.44)     # vert pomme pâle
            rep.SetZAxisColor(0.42, 0.55, 0.95)     # bleu (légère pointe de violet)
            try:
                rep.SetSize(88, 88)                 # un peu plus petit (défaut 120)
                rep.SetHandleSize(0.008)            # boules plus fines
                rep.SetTotalLength(0.9)
                rep.SetContainerVisibility(0)       # PAS de disque/sphère de fond :
                #                                     seulement les axes + bulles X/Y/Z
            except Exception:
                pass
            self._orient_widget = w
            self._orient_rep = rep
            self._style_orient_labels()
        except Exception as e:
            logger.debug(f"cube d'orientation indisponible : {e}")

    def _style_orient_labels(self):
        """Labels X/Y/Z (dans leurs bulles) lisibles selon le thème : clairs sur
        fond sombre, sombres sur fond clair. Le disque de fond (container) est
        masqué -> seuls les axes et leurs bulles restent visibles."""
        rep = getattr(self, "_orient_rep", None)
        if rep is None:
            return
        lab = (0.95, 0.95, 0.97) if _T.is_dark() else (0.12, 0.12, 0.16)
        try:
            for getp in (rep.GetXPlusLabelProperty, rep.GetXMinusLabelProperty,
                         rep.GetYPlusLabelProperty, rep.GetYMinusLabelProperty,
                         rep.GetZPlusLabelProperty, rep.GetZMinusLabelProperty):
                getp().SetColor(*lab)
            if self._plotter is not None:
                self._plotter.render()
        except Exception:
            pass

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
        self._rot_checkbox.setEnabled(True)
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
        # Suivre la fenêtre principale pour recaler l'overlay sphère (top-level)
        if getattr(self, "_strands", None) is not None and obj is getattr(self, "_strands_win", None):
            t = event.type()
            if t == QEvent.WindowStateChange:
                self._begin_settle()               # agrandir/réduire : anti-décalage
            elif t == QEvent.Hide:
                self._strands.hide()
            elif not getattr(self, "_strands_settling", False):
                # PAS de WindowActivate ici : s.raise_() churnait l'activation →
                # boucle d'événements → event loop saturé → sphère jamais peinte.
                if t in (QEvent.Move, QEvent.Resize, QEvent.Show):
                    self._reposition_strands()      # suivi immédiat (sinon)
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
        """Éclairage studio cinématique — style Unreal Engine hero shot."""
        self._plotter.remove_all_lights()
        # Key principale — haut-droite-devant, blanc chaud
        self._plotter.add_light(pv.Light(
            position=(5, 3, 12), focal_point=(0, 0, 0),
            intensity=1.60, color=[1.0, 0.97, 0.92],
        ))
        # Softbox secondaire — haut-gauche, lumière douce de remplissage
        self._plotter.add_light(pv.Light(
            position=(-5, 5, 9), focal_point=(0, 0, 0),
            intensity=0.55, color=[0.95, 0.97, 1.0],
        ))
        # Fill froid — gauche bas, bleu ciel (cold fill pour contraste chaud/froid)
        self._plotter.add_light(pv.Light(
            position=(-12, -2, 1), focal_point=(0, 0, 0),
            intensity=0.30, color=[0.65, 0.82, 1.0],
        ))
        # Rim fort arrière — contre-jour, séparation dramatique du fond
        self._plotter.add_light(pv.Light(
            position=(-2, -14, 5), focal_point=(0, 0, 0),
            intensity=1.20, color=[0.75, 0.88, 1.0],
        ))
        # Rim droit — éclat latéral pour les surfaces verticales
        self._plotter.add_light(pv.Light(
            position=(14, -5, 3), focal_point=(0, 0, 0),
            intensity=0.55, color=[0.90, 0.95, 1.0],
        ))
        # Zénithale — surfaces horizontales (dessus des pièces)
        self._plotter.add_light(pv.Light(
            position=(0, 0, 20), focal_point=(0, 0, 0),
            intensity=0.35, color=[0.95, 0.97, 1.0],
        ))
        # Bounce GI — lumière montante simulant la réflexion du plateau
        self._plotter.add_light(pv.Light(
            position=(1, 1, -8), focal_point=(0, 0, 0),
            intensity=0.18, color=[1.0, 0.96, 0.88],
        ))
        # Accent micro-détails — souligne les détails fins côté droit
        self._plotter.add_light(pv.Light(
            position=(16, 0, 2), focal_point=(0, 0, 0),
            intensity=0.28, color=[1.0, 0.98, 0.90],
        ))

    _PLATE_SIZE    = 256.0  # mm — plateau par défaut sans mesh
    _PLATE_GRID    = 10.0   # mm — espacement de la grille
    _PLATE_OPACITY = 0.90   # opacité plateau vue de dessus (0 depuis dessous)

    def _draw_single_plate(self, cx: float, cy: float, plate_size: float,
                            suffix: str = "",
                            plate_w: float | None = None,
                            plate_h: float | None = None) -> None:
        """Dessine un plateau (surface + grille) centré en (cx, cy, 0).

        plate_w / plate_h permettent un plateau rectangulaire ; sinon plate_size carré.
        """
        try:
            pw = float(plate_w) if plate_w is not None else float(plate_size)
            ph = float(plate_h) if plate_h is not None else float(plate_size)
            hw, hh = pw / 2.0, ph / 2.0

            # Espacement de grille : cases d'environ 10mm (style BS), min 5mm
            ref_size = max(pw, ph)
            raw = ref_size / 30.0   # vise ~30 cases par côté
            magnitude = 10.0 ** int(np.floor(np.log10(max(raw, 1e-9))))
            spacing = max(round(raw / magnitude) * magnitude, 5.0)

            plate = pv.Plane(
                center=(cx, cy, -1.0),
                direction=(0, 0, 1),
                i_size=pw,
                j_size=ph,
                i_resolution=1,
                j_resolution=1,
            )
            self._plotter.add_mesh(
                plate,
                color="#2a2b2e",
                opacity=self._PLATE_OPACITY,
                show_edges=False,
                name=f"build_plate_surface{suffix}",
                pickable=False,
            )

            nx = max(2, round(pw / spacing))
            ny = max(2, round(ph / spacing))
            lines_v = np.linspace(cx - hw, cx + hw, nx + 1)
            lines_h = np.linspace(cy - hh, cy + hh, ny + 1)
            # Grille nettement SOUS le dessous des pièces (à z=0) : évite que la
            # grille traverse le bas des pièces selon l'angle (Z-fighting), surtout
            # avec le polygon-offset VTK actif. 0.5 mm d'écart = séparation franche
            # sans que les pièces paraissent flotter.
            _gz = -0.5
            pts, segs, idx = [], [], 0
            for x in lines_v:
                pts += [[x, cy - hh, _gz], [x, cy + hh, _gz]]
                segs += [2, idx, idx + 1]
                idx += 2
            for y in lines_h:
                pts += [[cx - hw, y, _gz], [cx + hw, y, _gz]]
                segs += [2, idx, idx + 1]
                idx += 2
            grid = pv.PolyData()
            grid.points = np.array(pts, dtype=np.float32)
            grid.lines = np.array(segs, dtype=np.int_)
            # Grille style BS : presque noire en dark, gris moyen en clair
            _grid_color = "#1a1c1e" if _T.is_dark() else "#8a8e92"
            _grid_width  = 1.0      if _T.is_dark() else 1.2
            self._plotter.add_mesh(
                grid, color=_grid_color, opacity=1.0,
                line_width=_grid_width,
                name=f"build_plate_grid{suffix}", pickable=False,
            )
        except Exception:
            pass

    def _add_build_plate(self, mesh=None) -> None:
        """Ajoute un plateau dont la taille s'adapte à la pièce chargée."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        try:
            if mesh is not None:
                # Empreinte XY uniquement — ne pas utiliser Z (hauteur)
                ext = mesh.bounding_box.extents
                footprint = float(max(ext[0], ext[1]))
                # Marge adaptative : généreuse pour les petites pièces, serrée pour les grandes
                margin = max(footprint * 0.3, 60.0)
                plate_size = max(footprint + margin, 30.0)
            else:
                plate_size = self._PLATE_SIZE
            self._current_plate_size = plate_size
            self._draw_single_plate(0.0, 0.0, plate_size)
        except Exception:
            pass

    def _add_multipart_plates(self, final_meshes: list, orig_positions: list,
                               plate_count: int) -> None:
        """Dessine un plateau distinct par groupe de pièces.

        Utilise une grille spatiale sur les positions ORIGINALES (avant centrage)
        pour reproduire fidèlement l'assignation de plateaux de Bambu Studio.
        orig_positions : liste de [x, y] dans l'espace global 3MF (transforms XY).
        """
        if not HAS_PYVISTA or self._plotter is None:
            return
        try:
            import numpy as _np
            import math as _math

            pos_arr = _np.array(orig_positions, dtype=np.float64)

            # Trouver la taille de grille qui donne exactement plate_count groupes
            labels = None
            for grid_size in (256, 300, 350, 400, 500, 600, 800):
                tile_map: dict[tuple, list] = {}
                for i, (x, y) in enumerate(orig_positions):
                    key = (_math.floor(x / grid_size), _math.floor(y / grid_size))
                    tile_map.setdefault(key, []).append(i)
                n_tiles = len(tile_map)
                if n_tiles == plate_count:
                    # Convertir en labels
                    lbl = [0] * len(orig_positions)
                    for pid, idxs in enumerate(tile_map.values()):
                        for i in idxs:
                            lbl[i] = pid
                    labels = lbl
                    logger.debug(f"Grille {grid_size}mm → {n_tiles} tuiles ✓")
                    break

            if labels is None:
                # Fallback K-means si aucune grille ne donne le bon nombre
                from scipy.cluster.vq import kmeans2 as _km2
                k = min(plate_count, len(orig_positions))
                _, km_labels = _km2(pos_arr[:, :2].astype(np.float64), k,
                                    minit="points", seed=42)
                labels = [int(l) for l in km_labels]
                logger.warning(f"Grille spatiale échouée → K-means k={k}")

            PAD = 20.0
            unique_plates = sorted(set(labels))
            for pid in unique_plates:
                idxs = [i for i, l in enumerate(labels) if l == pid]
                if not idxs:
                    continue
                cluster_pts = _np.vstack([final_meshes[i].vertices for i in idxs])
                xmin, ymin = cluster_pts[:, 0].min(), cluster_pts[:, 1].min()
                xmax, ymax = cluster_pts[:, 0].max(), cluster_pts[:, 1].max()
                cx = (xmin + xmax) / 2
                cy = (ymin + ymax) / 2
                pw = max((xmax - xmin) + PAD * 2, 30.0)
                ph = max((ymax - ymin) + PAD * 2, 30.0)
                self._draw_single_plate(cx, cy, max(pw, ph),
                                        suffix=f"_{pid}",
                                        plate_w=pw, plate_h=ph)

        except Exception as _e:
            logger.warning(f"Multi-plate draw failed: {_e}")
            try:
                import numpy as _np
                cluster_pts = _np.vstack([m.vertices for m in final_meshes])
                xmin, xmax = cluster_pts[:, 0].min(), cluster_pts[:, 0].max()
                ymin, ymax = cluster_pts[:, 1].min(), cluster_pts[:, 1].max()
                size = max(xmax - xmin, ymax - ymin) * 1.3
                self._draw_single_plate((xmin+xmax)/2, (ymin+ymax)/2, size)
            except Exception:
                self._draw_single_plate(0.0, 0.0, self._PLATE_SIZE)

    def _cancel_mesh_prep(self) -> None:
        """Annule la Phase 2 en cours en incrémentant le compteur de génération."""
        self._load_gen = getattr(self, '_load_gen', 0) + 1

    # Couleurs filament AMS — saturées pour montrer le PBR (reflets nets sur surface brillante)
    _SLOT_COLORS = {
        1: "#F0EBE0",  # blanc ivoire PLA
        2: "#2E86C1",  # bleu vif
        3: "#E67E22",  # orange chaud
        4: "#27AE60",  # vert foncé
        5: "#8E44AD",  # violet
        6: "#F1C40F",  # jaune
        7: "#E74C3C",  # rouge
        8: "#1ABC9C",  # turquoise
    }

    def _compute_arrange(self, transformed_meshes: list) -> tuple:
        """Shelf-packing pour séparer les pièces superposées à l'origine.

        Returns (do_arrange: bool, offsets: list[(dx, dy)]).
        Si les pièces sont déjà positionnées (spread suffisant), renvoie False.
        """
        MARGIN = 15.0
        n = len(transformed_meshes)
        if n <= 1:
            return False, [(0.0, 0.0)]

        centroids_xy = []
        sizes_xy = []
        for m in transformed_meshes:
            b = m.bounds
            cx = (float(b[0][0]) + float(b[1][0])) / 2
            cy = (float(b[0][1]) + float(b[1][1])) / 2
            w = max(float(b[1][0]) - float(b[0][0]), 5.0)
            h = max(float(b[1][1]) - float(b[0][1]), 5.0)
            centroids_xy.append((cx, cy))
            sizes_xy.append((w, h))

        max_extent = max(max(s) for s in sizes_xy)
        cx_mean = sum(c[0] for c in centroids_xy) / n
        cy_mean = sum(c[1] for c in centroids_xy) / n
        spread = max(abs(c[0] - cx_mean) + abs(c[1] - cy_mean) for c in centroids_xy)

        # Bien positionné sur 1 plateau (spread < 200mm) → garder les positions.
        # Multi-plateau (spread > 200mm) → arranger pour affichage compact.
        if spread > max_extent * 0.15 and spread < 200.0:
            return False, [(0.0, 0.0)] * n  # déjà positionné

        # Shelf-packing : trier par hauteur décroissante
        order = sorted(range(n), key=lambda i: sizes_xy[i][1], reverse=True)
        avg_w = sum(s[0] for s in sizes_xy) / n
        max_row_w = max(math.sqrt(n) * avg_w * 1.2, max(s[0] for s in sizes_xy))

        shelves: list[tuple[list, float]] = []
        current_shelf: list[tuple[int, float, float, float]] = []
        current_x = 0.0
        current_h = 0.0

        for idx in order:
            w, h = sizes_xy[idx]
            if current_shelf and current_x + w > max_row_w + MARGIN:
                shelves.append((current_shelf, current_h))
                current_shelf = []
                current_x = 0.0
                current_h = 0.0
            current_shelf.append((idx, current_x, w, h))
            current_x += w + MARGIN
            current_h = max(current_h, h)
        if current_shelf:
            shelves.append((current_shelf, current_h))

        total_h = sum(s[1] for s in shelves) + MARGIN * max(len(shelves) - 1, 0)
        placed: dict[int, tuple[float, float]] = {}
        cur_y = -total_h / 2

        for shelf_items, shelf_h in shelves:
            shelf_w = sum(item[2] for item in shelf_items) + MARGIN * max(len(shelf_items) - 1, 0)
            cur_x = -shelf_w / 2
            for idx, _, w, h in shelf_items:
                orig_cx, orig_cy = centroids_xy[idx]
                target_x = cur_x + w / 2
                target_y = cur_y + shelf_h / 2
                placed[idx] = (target_x - orig_cx, target_y - orig_cy)
                cur_x += w + MARGIN
            cur_y += shelf_h + MARGIN

        offsets = [placed.get(i, (0.0, 0.0)) for i in range(n)]
        logger.info(f"Auto-arrange : {n} pièces sur {len(shelves)} rangée(s)")
        return True, offsets

    def _load_multipart_mesh(self, threemf_data) -> None:
        """Affiche un 3MF multi-objets — chaque objet = acteur séparé coloré par slot."""
        import trimesh as _trimesh

        self._mesh = threemf_data.combined_mesh
        self._pv_mesh_cache = None
        self._face_colors = None
        self._view_mode = "normal"
        # Memoire (object_id -> slot) pour la re-colorisation live par slot
        # (previsualisation des couleurs choisies a l'export).
        self._slot_object_ids = [
            (o.object_id, int(o.extruder)) for o in threemf_data.objects]
        self._plotter.clear()
        self._setup_lights()

        # NB : on n'active PAS le polygon-offset global de VTK ici. Il décalait les
        # lignes (grille du plateau) vers la caméra → la grille traversait le bas
        # des objets selon l'angle. L'empilement correct des couleurs (chaque
        # couche remplit le creux de la base, cf. offset Z global) suffit à éviter
        # le Z-fighting du multicouleur sans ce réglage global néfaste.

        # Afficher TOUS les objets de tous les plateaux.
        # L'auto-arrange gère la disposition compacte si les positions Bambu sont dispersées.
        _display_objects = threemf_data.objects
        _plate_indices = {getattr(o, "plate_index", 0) for o in _display_objects}
        _has_multiplate = len(_plate_indices) > 1

        # LOG DIAGNOSTIC — montre EXACTEMENT ce qui est rendu
        logger.info(f"[VIEWER RENDER] {len(_display_objects)} objets:")
        for _do in _display_objects:
            logger.info(f"  → {_do.object_id} | name={_do.name} | faces={len(_do.mesh.faces)} | extents={_do.mesh.bounding_box.extents.round(1)} | plate={_do.plate_index}")

        raw_meshes = []
        for obj in _display_objects:
            raw_meshes.append(obj.mesh)

        face_counts = [len(m.faces) for m in raw_meshes]
        if len(face_counts) > 1:
            min_fc = min(face_counts)
            clean_idx = face_counts.index(min_fc)
            clean_mesh = raw_meshes[clean_idx]
            # Remplacer les meshes avec trop de faces par le mesh propre
            corrected = []
            for i, (obj, fc) in enumerate(zip(_display_objects, face_counts)):
                deviation = abs(fc - min_fc) / max(min_fc, 1)
                if deviation > 0 and deviation < 0.05:
                    # Même modèle mais modifié par boolean → utiliser la version propre
                    m = clean_mesh.copy()
                else:
                    m = obj.mesh.copy()
                if not np.allclose(obj.transform, np.eye(4)):
                    m.apply_transform(obj.transform)
                corrected.append(m)
            transformed = corrected
        else:
            transformed = []
            for obj in _display_objects:
                m = obj.mesh.copy()
                if not np.allclose(obj.transform, np.eye(4)):
                    m.apply_transform(obj.transform)
                transformed.append(m)

        # 2) Auto-arrange si les pièces se superposent ET fichier mono-slot.
        # Pour les fichiers multicolores (slot_count > 1 = régions intentionnellement superposées),
        # NE PAS auto-arranger — SAUF si les positions Bambu absolues rendent le combined mesh
        # énorme (> 380mm en XY = multi-plateau ou positions absolues hors plateau normal).
        try:
            _cb = threemf_data.combined_mesh.bounding_box.extents
            _footprint_xy = float(max(_cb[0], _cb[1]))
        except Exception:
            _footprint_xy = 0.0

        # Seuil 200mm : en dessous = assemblage mono-plateau, pas d'arrange forcé.
        # Au-dessus = multi-plateau ou positions absolues Bambu → forcer compactage.
        _positions_huge = _footprint_xy > 200.0

        if threemf_data.slot_count > 1 and not _positions_huge:
            do_arrange = False
            arrange_offsets = [(0.0, 0.0)] * len(transformed)
        else:
            do_arrange, arrange_offsets = self._compute_arrange(transformed)

        # 3) Construire les meshes finaux (avec arrange + poser sur plateau)
        # Pour un assemblage MULTICOLORE (couches de couleur empilées), on abaisse
        # TOUT l'ensemble d'un SEUL offset (z_min global) afin de PRÉSERVER
        # l'empilement relatif des couches. Sinon chaque couche est collée au
        # plateau, les couches se chevauchent au même Z et leurs surfaces
        # coïncident → Z-fighting (scintillement, couleurs hachurées).
        _is_color_assembly = threemf_data.slot_count > 1
        _gzmin = min((float(t.bounds[0][2]) for t in transformed), default=0.0)
        final_meshes = []
        for m, (dx, dy) in zip(transformed, arrange_offsets):
            mc = m.copy()
            if do_arrange:
                # Arrange XY + poser chaque pièce indépendamment sur le plateau (Z_min→0)
                mc.apply_translation([dx, dy, -float(m.bounds[0][2])])
            else:
                b = threemf_data.combined_mesh.bounds
                _zoff = -_gzmin if _is_color_assembly else -float(m.bounds[0][2])
                mc.apply_translation([
                    -(float(b[0][0]) + float(b[1][0])) / 2,
                    -(float(b[0][1]) + float(b[1][1])) / 2,
                    _zoff,
                ])
            final_meshes.append(mc)

        # 4) Centrer l'ensemble sur XY
        ref = _trimesh.util.concatenate(final_meshes) if final_meshes else self._mesh
        rb = ref.bounds
        gx = -(float(rb[0][0]) + float(rb[1][0])) / 2
        gy = -(float(rb[0][1]) + float(rb[1][1])) / 2

        # CRITIQUE : mettre à jour self._mesh avec le mesh arrangé/normalisé.
        # Sans ça, quand colorize_overhangs appelle _add_build_plate(self._mesh),
        # il utilise le combined_mesh original (ex: 2371mm) → plateau gigantesque
        # → les objets correctement arrangés apparaissent minuscules au centre.
        if gx != 0.0 or gy != 0.0:
            _ref_centered = ref.copy()
            _ref_centered.apply_translation([gx, gy, 0.0])
            self._mesh = _ref_centered
        else:
            self._mesh = ref

        # Stocker les centres viewer-space de chaque objet (après centrage global).
        # Utilisé par les barres de fragilité pour se positionner exactement au-dessus
        # de chaque groupe, sans dépendre d'un calcul de face-offsets fragile.
        self._object_viewer_bounds: list[dict] = []
        for _mf in final_meshes:
            _b = _mf.bounds
            self._object_viewer_bounds.append({
                "xmin": float(_b[0][0]) + gx,
                "xmax": float(_b[1][0]) + gx,
                "ymin": float(_b[0][1]) + gy,
                "ymax": float(_b[1][1]) + gy,
                "cz":   float(_b[1][2]),
            })

        self._add_build_plate(self._mesh)

        _bb = ref.bounding_box.extents
        self._rotation_pivot = np.array([0.0, 0.0, float(_bb[2]) * 0.5])

        rq = self._render_quality()
        _total_faces = sum(len(m.faces) for m in final_meshes)
        # compute_normals (rendu lisse haute qualité, = rendu de base) sur le main
        # thread. Seuil relevé 600k→3M : sans lui, un modèle multi-couleurs lourd
        # (ex. Darth Vader 959k faces) restait FACETTÉ à l'export couleur alors que la
        # vue de base est impeccable. 3M reste une soupape pour les meshes extrêmes.
        _use_pbr = _total_faces < 3_000_000

        for m_final, obj in zip(final_meshes, _display_objects):
            try:
                mc = m_final.copy()
                mc.apply_translation([gx, gy, 0.0])
                pv_obj = self._trimesh_to_pyvista(mc)
                color = self._SLOT_COLORS.get(obj.extruder, "#AABBCC")

                if _use_pbr:
                    # Normales PBR : feature_angle 25° → arêtes vives nettes,
                    # surfaces courbes lisses. split_vertices = hard-edge shading.
                    try:
                        pv_obj = pv_obj.compute_normals(
                            cell_normals=False,
                            point_normals=True,
                            feature_angle=rq["feature_angle"],
                            split_vertices=True,
                            flip_normals=False,
                            consistent_normals=True,
                            progress_bar=False,
                        )
                    except Exception:
                        pass
                    self._plotter.add_mesh(
                        pv_obj, color=color, show_edges=False,
                        smooth_shading=True,
                        pbr=False,   # mat lumineux, cohérent partout
                        specular=rq["specular"],
                        ambient=rq["ambient"],
                        diffuse=rq["diffuse"],
                        name=f"obj_{obj.object_id}",
                    )
                else:
                    # Mesh lourd (>600k faces) : on SAUTE compute_normals (coûteux sur
                    # le main thread) MAIS on garde le rendu mat lumineux (mêmes
                    # ambient/diffuse/specular que la voie PBR). Avant, ambient=0.12 /
                    # diffuse=0.88 donnait des ombres dures très moches à l'export couleur.
                    self._plotter.add_mesh(
                        pv_obj, color=color, show_edges=False,
                        smooth_shading=True,
                        pbr=False,
                        specular=rq["specular"],
                        ambient=rq["ambient"],
                        diffuse=rq["diffuse"],
                        name=f"obj_{obj.object_id}",
                    )
            except Exception as _e:
                logger.warning(f"Objet {obj.name} non affiché : {_e}")

        # 5) Caméra sur le bounding box global arrangé
        try:
            _elev = math.radians(25)
            _far  = 1e6
            self._plotter.camera.position = (0.0, -math.cos(_elev) * _far,
                                              math.sin(_elev) * _far)
            self._plotter.camera.focal_point = (0.0, 0.0, 0.0)
            self._plotter.camera.up = (0.0, 0.0, 1.0)
            _pad = float(_bb.max()) * 0.5
            _hw = float(_bb[0]) / 2 + _pad
            _hd = float(_bb[1]) / 2 + _pad
            _ht = float(_bb[2]) + _pad
            try:
                self._plotter.reset_camera(bounds=[-_hw, _hw, -_hd, _hd, -_pad * 0.2, _ht])
            except TypeError:
                self._plotter.reset_camera()
            self._plotter.renderer.ResetCameraClippingRange()
        except Exception as _ce:
            logger.warning(f"Camera setup multipart échoué : {_ce}")
            self._plotter.reset_camera()

        self._plotter.render()
        logger.info(f"3MF multipart affiché : {threemf_data.object_count} objets · {threemf_data.slot_count} slot(s) · {threemf_data.plate_count} plateau(x)")

    # ── Barres de fragilité flottantes ────────────────────────────────────────

    def show_fragility_bars(self, bars: list[dict]) -> None:
        """Barres de fragilité flottantes style jeu vidéo — toujours face caméra.

        Utilise des vtkFollower (sprite billboard) pour que les barres s'orientent
        automatiquement vers la caméra quelle que soit la rotation de la scène.

        bars : liste de dicts {cx, cy, cz, score, label}
        """
        if not HAS_PYVISTA or self._plotter is None:
            return

        # Sauvegarder les données pour pouvoir recréer les barres après un
        # changement de thème (refresh_theme → colorize_overhangs → plotter.clear()
        # efface les vtkFollower, sinon les barres disparaissent au switch de thème).
        self._fragility_bars_data = list(bars)

        self.hide_fragility_bars(clear_data=False)

        try:
            from vtk import vtkFollower, vtkPolyDataMapper
        except ImportError:
            logger.warning("vtkFollower non disponible — barres fragilité ignorées")
            return

        BAR_W  = 40.0   # largeur totale (mm)
        BAR_H  = 5.5    # hauteur (mm)
        LIFT   = 20.0   # hauteur au-dessus de la pièce (mm)

        camera = self._plotter.renderer.GetActiveCamera()
        self._fragility_followers: list = []

        def _hex_to_rgb(h: str) -> tuple[float, float, float]:
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

        def _add_follower(plane_pv, pos, color_hex: str, z_offset: float = 0.0,
                          opacity: float = 1.0):
            mapper = vtkPolyDataMapper()
            mapper.SetInputData(plane_pv)
            actor = vtkFollower()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*_hex_to_rgb(color_hex))
            actor.GetProperty().SetOpacity(opacity)
            actor.GetProperty().LightingOff()
            actor.SetPosition(pos[0], pos[1], pos[2] + z_offset)
            actor.SetCamera(camera)
            self._plotter.renderer.AddActor(actor)
            self._fragility_followers.append(actor)

        for i, b in enumerate(bars):
            cx   = float(b["cx"])
            cy   = float(b["cy"])
            top_z = float(b["cz"]) + LIFT
            score = max(0.0, min(1.0, float(b.get("score", 0.0))))
            label = b.get("label", f"Lot {i+1}")

            fill_color = "#2ECC71" if score < 0.30 else "#F39C12" if score < 0.60 else "#E74C3C"

            try:
                # ── Fond gris foncé (plein) ──
                bg = pv.Plane(
                    center=(0.0, 0.0, 0.0),
                    direction=(0.0, 0.0, 1.0),
                    i_size=BAR_W, j_size=BAR_H,
                    i_resolution=1, j_resolution=1,
                )
                # ── Barre combinée : fond + fill en un seul follower ──────────
                # Un seul acteur = pas de parallaxe/décalage lors des rotations.
                # On crée un mesh combiné avec couleurs par cellule.
                fill_w = max(BAR_W * score, 0.5)
                try:
                    from vtk import vtkFollower, vtkPolyDataMapper, vtkAppendPolyData
                    # Fond noir complet
                    bg_pts = np.array([
                        [-BAR_W/2, -BAR_H/2, 0], [ BAR_W/2, -BAR_H/2, 0],
                        [ BAR_W/2,  BAR_H/2, 0], [-BAR_W/2,  BAR_H/2, 0],
                    ], dtype=np.float32)
                    # Fill coloré (depuis bord gauche)
                    fx = -BAR_W/2 + fill_w
                    fill_pts = np.array([
                        [-BAR_W/2, -BAR_H/2-0.2, 0.15], [fx, -BAR_H/2-0.2, 0.15],
                        [fx,        BAR_H/2+0.2, 0.15], [-BAR_W/2, BAR_H/2+0.2, 0.15],
                    ], dtype=np.float32)

                    def _make_quad(pts, color_hex):
                        poly = pv.PolyData()
                        poly.points = pts
                        poly.faces = np.array([4, 0, 1, 2, 3])
                        rgb = np.array([[int(color_hex[j:j+2],16) for j in (1,3,5)]], dtype=np.uint8)
                        poly.cell_data["RGB"] = rgb
                        return poly

                    bar_bg   = _make_quad(bg_pts,   "#1E2025")
                    bar_fill = _make_quad(fill_pts, fill_color)
                    combined = bar_bg.merge(bar_fill)

                    mapper = vtkPolyDataMapper()
                    mapper.SetInputData(combined)
                    mapper.SetScalarModeToUseCellData()
                    mapper.SelectColorArray("RGB")
                    mapper.SetColorModeToDirectScalars()

                    actor = vtkFollower()
                    actor.SetMapper(mapper)
                    actor.GetProperty().SetOpacity(0.93)
                    actor.GetProperty().LightingOff()   # barres toujours à couleur constante
                    actor.SetPosition(cx, cy, top_z)
                    actor.SetCamera(camera)
                    self._plotter.renderer.AddActor(actor)
                    self._fragility_followers.append(actor)
                except Exception as _eb:
                    # Fallback si vtkAppendPolyData indispo
                    _add_follower(bg, (cx, cy, top_z), "#1E2025", opacity=0.92)

                # ── Texte centré au-dessus de la barre ──
                pct_text = f"{score * 100:.0f}%"
                label_text = f"{label}  {pct_text}"
                self._plotter.add_point_labels(
                    np.array([[cx, cy, top_z + BAR_H / 2 + 4.5]]),
                    [label_text],
                    font_size=13, text_color="white", bold=True,
                    show_points=False, always_visible=True,
                    shape=None, name=f"frag_label_{i}",
                    justification_horizontal="center",
                )
            except Exception as _e:
                logger.warning(f"Barre fragilité groupe {i} : {_e}")

        self._plotter.render()

    def hide_fragility_bars(self, clear_data: bool = True) -> None:
        """Supprime toutes les barres de fragilité (followers + labels).

        clear_data=False : appelé en interne par show_fragility_bars (ne pas
        oublier les données nécessaires à la recréation au switch de thème).
        clear_data=True : masquage réel (nouvelle pièce) → on oublie les barres.
        """
        if clear_data:
            self._fragility_bars_data = None
        if self._plotter is None:
            return
        # Supprimer les vtkFollower actors
        for actor in getattr(self, "_fragility_followers", []):
            try:
                self._plotter.renderer.RemoveActor(actor)
            except Exception:
                pass
        self._fragility_followers = []
        # Supprimer les labels
        for name in list(self._plotter.actors.keys()):
            if name.startswith("frag_label_"):
                try:
                    self._plotter.remove_actor(name, render=False)
                except Exception:
                    pass
        self._plotter.render()

    def load_mesh(self, mesh) -> None:
        """Affiche un trimesh.Trimesh ou ThreeMFData."""
        if not HAS_PYVISTA or self._plotter is None:
            return

        # Nouvelle pièce → oublier les barres de fragilité de la pièce précédente
        # (sinon elles réapparaîtraient au switch de thème). Si la nouvelle pièce
        # est un 3MF multi-plateau, main_window rappellera show_fragility_bars.
        self._fragility_bars_data = None

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
                raw_pv, color="#f2ede8", show_edges=False,
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
                    # split_vertices : indispensable sur un mesh SOUDÉ (STL CAO,
                    # unions booléennes) — sans lui les normales sont moyennées à
                    # travers les arêtes vives -> relief « fondu », tout blanc.
                    # (Aligné sur le chemin multi-objets qui l'avait déjà.)
                    split_vertices=True,
                    flip_normals=False,
                    consistent_normals=True,
                )
                self._apply_pbr_mesh(pv_mesh, rq)
            except Exception as exc:
                logger.warning(f"Phase 2 normals échouée : {exc}")

        QTimer.singleShot(300, _phase2)

    def afficher_carte(self, scene) -> None:
        """Aperçu COLORÉ d'une carte de visite. Scene attendue : un corps
        « socle » + un corps « el_<i> » par élément (voir construire_apercu).
        MISE À JOUR EN PLACE : on remplace seulement les acteurs modifiés, SANS
        vider la scène ni recadrer la caméra -> aucun clignotement quand on tape.
        La caméra ne se met en vue de dessus qu'à la PREMIÈRE ouverture."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        import trimesh as _tm
        premiere = getattr(self, "_view_mode", "") != "carte"
        corps = dict(scene.geometry)
        if not corps:
            return
        fusion = _tm.util.concatenate(list(corps.values()))
        self._mesh = fusion
        self._face_colors = None
        self._view_mode = "carte"
        if premiere:
            self._cancel_mesh_prep()
            self.stop_auto_rotate()
            self._plotter.clear()
            self._setup_lights()
            self._add_build_plate(fusion)
            self._carte_actors = {}          # nom acteur -> index élément (drag)
            self._carte_vtk = {}             # nom acteur -> vtkActor (matching pick)
            self._carte_sel = None           # nom de l'élément sélectionné

        # décalage COMMUN (centre la carte sur le plateau, base à z=0)
        b = fusion.bounds
        off = [-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]]
        self._carte_offset = off
        vus = set()
        mapping = {}
        for nom, g in corps.items():
            try:
                col = g.visual.face_colors[0][:3] / 255.0
            except Exception:
                col = (0.9, 0.9, 0.9)
            pvm = self._trimesh_to_pyvista(g)
            pvm.translate(off, inplace=True)
            acteur = f"carte_{nom}"
            _a = self._plotter.add_mesh(pvm, color=col, show_edges=False,
                                        smooth_shading=False, name=acteur,
                                        reset_camera=False)
            vus.add(acteur)
            if nom.startswith("el_"):
                try:
                    mapping[acteur] = int(nom[3:])
                    self._carte_vtk[acteur] = _a       # vtkActor pour le pick
                except ValueError:
                    pass
                # ré-applique la surbrillance si c'est l'élément sélectionné
                if acteur == getattr(self, "_carte_sel", None):
                    self._surligner_carte(acteur, True)
        # retirer les acteurs d'éléments SUPPRIMÉS depuis le dernier aperçu
        for ancien in list(getattr(self, "_carte_actors", {})):
            if ancien not in vus:
                try:
                    self._plotter.remove_actor(ancien, reset_camera=False)
                except Exception:
                    pass
        self._carte_actors = mapping

        if premiere:
            fus = fusion.copy(); fus.apply_translation(off)
            self.vue_dessus(fus)
            self._install_carte_drag()
        self._plotter.render()

    def quitter_mode_carte(self) -> None:
        """À appeler quand on ferme l'éditeur de carte : réarme un affichage
        normal au prochain chargement de pièce."""
        self._view_mode = "normal"
        self._carte_actors = {}

    # ── Sélection + déplacement des éléments à la souris ─────────────────────
    def _surligner_carte(self, nom: str, on: bool) -> None:
        """Surbrillance d'un élément de carte : contour cyan épais."""
        a = getattr(self, "_carte_vtk", {}).get(nom)
        if a is None:
            return
        try:
            p = a.GetProperty()
            p.SetEdgeVisibility(bool(on))
            if on:
                p.SetEdgeColor(0.13, 0.83, 0.93)
                p.SetLineWidth(3)
        except Exception:
            pass

    def _install_carte_drag(self) -> None:
        """Clic sur un élément -> il se SÉLECTIONNE (surbrillance cyan) ; on peut
        alors le GLISSER dans le plan de la carte (le socle n'est pas
        sélectionnable). Au relâcher, le décalage est renvoyé au panneau (signal
        element_deplace) qui met à jour dx/dy. Clic dans le vide -> désélection."""
        if getattr(self, "_carte_drag_installe", False) or self._plotter is None:
            return
        try:
            from vtkmodules.vtkRenderingCore import vtkPropPicker
        except Exception:
            return
        iren = getattr(self._plotter, "iren", None)
        iren = getattr(iren, "interactor", None) if iren else None
        if iren is None:
            return
        picker = vtkPropPicker()
        ren = self._plotter.renderer
        st = {"drag": False, "nom": None, "idx": -1, "last": (0.0, 0.0),
              "tot": [0.0, 0.0]}

        def _world_xy(x, y, zp=0.0):
            # rayon écran -> monde, intersection avec le plan z = zp (robuste,
            # quelle que soit la caméra ; l'ancienne conversion visait le plan
            # proche -> décalage faux).
            ren.SetDisplayPoint(float(x), float(y), 0.0); ren.DisplayToWorld()
            w0 = ren.GetWorldPoint()
            ren.SetDisplayPoint(float(x), float(y), 1.0); ren.DisplayToWorld()
            w1 = ren.GetWorldPoint()
            p0 = np.array(w0[:3]) / (w0[3] or 1.0)
            p1 = np.array(w1[:3]) / (w1[3] or 1.0)
            d = p1 - p0
            if abs(d[2]) < 1e-9:
                return p0[0], p0[1]
            t = (zp - p0[2]) / d[2]
            p = p0 + t * d
            return float(p[0]), float(p[1])

        def _nom_pique():
            x, y = iren.GetEventPosition()
            picker.Pick(x, y, 0, ren)
            act = picker.GetActor()
            if act is None:
                return None
            try:
                ad = act.GetAddressAsString("")
            except Exception:
                return None
            for nom, a in getattr(self, "_carte_vtk", {}).items():
                try:
                    if a.GetAddressAsString("") == ad:
                        return nom
                except Exception:
                    pass
            return None

        def _press(caller, ev):
            try:
                nom = _nom_pique()
                # désélectionne l'ancien si on change de cible / clic dans le vide
                anc = getattr(self, "_carte_sel", None)
                if anc and anc != nom:
                    self._surligner_carte(anc, False)
                    self._carte_sel = None
                if nom and nom in getattr(self, "_carte_actors", {}):
                    self._carte_sel = nom
                    self._surligner_carte(nom, True)
                    x, y = iren.GetEventPosition()
                    st.update(drag=True, nom=nom, idx=self._carte_actors[nom],
                              last=_world_xy(x, y), tot=[0.0, 0.0])
                    caller.SetAbortFlag(1)       # empêche l'orbite caméra
                    self._plotter.render()
            except Exception:
                pass

        def _move(caller, ev):
            if not st["drag"]:
                return
            try:
                x, y = iren.GetEventPosition()
                wx, wy = _world_xy(x, y)
                dx, dy = wx - st["last"][0], wy - st["last"][1]
                a = self._carte_vtk.get(st["nom"])
                if a is not None:
                    a.AddPosition(dx, dy, 0.0)   # suit la souris (visuel)
                    st["tot"][0] += dx; st["tot"][1] += dy
                    st["last"] = (wx, wy)
                    caller.SetAbortFlag(1)
                    self._plotter.render()
            except Exception:
                pass

        def _release(caller, ev):
            if st["drag"]:
                st["drag"] = False
                if abs(st["tot"][0]) > 0.05 or abs(st["tot"][1]) > 0.05:
                    try:
                        self.element_deplace.emit(st["idx"], st["tot"][0], st["tot"][1])
                    except Exception:
                        pass

        iren.AddObserver("LeftButtonPressEvent", _press, 10.0)   # priorité > caméra
        iren.AddObserver("MouseMoveEvent", _move, 10.0)
        iren.AddObserver("LeftButtonReleaseEvent", _release, 10.0)
        self._carte_drag_installe = True

    def vue_dessus(self, mesh=None) -> None:
        """Caméra pile au-dessus du plateau, regardant vers le bas — la carte
        (à plat) est vue de dessus, bien centrée. `up` = +Y (haut de la carte
        vers le haut de l'écran)."""
        if self._plotter is None:
            return
        m = mesh if mesh is not None else self._mesh
        try:
            self._plotter.camera.position = (0.0, 0.0, 1e6)
            self._plotter.camera.focal_point = (0.0, 0.0, 0.0)
            self._plotter.camera.up = (0.0, 1.0, 0.0)
            if m is not None:
                pv = self._place_on_plate(self._trimesh_to_pyvista(m))
                pb = pv.bounds
                pad = float(m.bounding_box.extents.max()) * 0.18
                try:
                    self._plotter.reset_camera(
                        bounds=[pb[0]-pad, pb[1]+pad, pb[2]-pad, pb[3]+pad,
                                pb[4], pb[5]])
                except TypeError:
                    self._plotter.reset_camera()
            else:
                self._plotter.reset_camera()
            self._plotter.renderer.ResetCameraClippingRange()
            self._plotter.render()
        except Exception as exc:
            logger.warning(f"vue_dessus échouée : {exc}")

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
                color="#f2ede8",
                show_edges=False,
                smooth_shading=True,
                # Non-PBR : rendu mat lumineux identique au mode surplombs
                # (ambient élevé), au lieu du PBR vernis/grisé.
                pbr=False,
                ambient=rq["ambient"],
                diffuse=rq["diffuse"],
                specular=rq["specular"],
                name="main_mesh",
                reset_camera=False,
            )
            self._plotter.render()
        except Exception as _me:
            logger.warning(f"PBR upgrade échoué : {_me}")

    def set_slot_colors(self, mapping: dict) -> None:
        """Re-colore en direct chaque objet d'un 3MF multi-objets selon la couleur
        choisie pour son slot. `mapping` = {slot:int -> couleur hex}. Sans effet si
        aucun 3MF multi-objets n'est affiche. Utilise pour la previsualisation des
        couleurs a l'export."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        ids = getattr(self, "_slot_object_ids", None)
        if not ids or not mapping:
            return
        changed = False
        for object_id, slot in ids:
            hexc = mapping.get(slot) or mapping.get(int(slot))
            if not hexc:
                continue
            actor = self._plotter.actors.get(f"obj_{object_id}")
            if actor is None:
                continue
            try:
                actor.prop.color = hexc
                changed = True
            except Exception:
                pass
        if changed:
            try:
                self._plotter.render()
            except Exception:
                pass

    def colorize_overhangs(self, mesh, face_colors: np.ndarray, _keep_camera: bool = False) -> None:
        """Recolorie le mesh selon les zones de surplomb — rendu smooth par vertex."""
        if not HAS_PYVISTA or self._plotter is None:
            return

        self._view_mode = "analysis"
        self._face_colors = face_colors
        self._plotter.clear()
        self._setup_lights()
        self._add_build_plate(mesh)
        pv_mesh = self._place_on_plate(self._trimesh_to_pyvista(mesh))

        # Safety : face count mismatch (ex: per-object analysis vs viewer mesh corrigé)
        # → re-calculer les couleurs sur le mesh du viewer directement
        if len(face_colors) != len(mesh.faces):
            logger.warning(
                f"colorize_overhangs: mismatch {len(face_colors)} colors vs {len(mesh.faces)} faces — recalcul"
            )
            try:
                from core.geometry.overhang_detector import analyze_overhangs, overhang_face_colors as _ofc
                _ov = analyze_overhangs(mesh, smooth=True, check_floating=False)
                face_colors = _ofc(mesh, _ov)
                self._face_colors = face_colors
            except Exception:
                self._plotter.render()
                return

        # ── Scalaires par FACE (cell_data) — aucun bleeding entre faces ────────
        # Chaque face reçoit sa propre valeur de sévérité. Zéro interpolation possible
        # entre face surplomb et face safe adjacente. Même approche que Bambu Studio.
        face_sev_raw = face_colors[:, 0].astype(np.float32) / 255.0
        ovh_mask     = face_colors[:, 1] == 0   # True = face surplomb

        # Sévérité par face : valeur brute uniquement sur les faces surplombs
        face_sev = np.where(ovh_mask, face_sev_raw, 0.0).astype(np.float32)

        pv_mesh.cell_data["overhang"] = face_sev
        self._plotter.add_mesh(
            pv_mesh,
            scalars="overhang",
            cmap=_OVERHANG_CMAP_DARK if _T.is_dark() else _OVERHANG_CMAP_LIGHT,
            clim=[0.0, 1.0],
            show_scalar_bar=False,
            smooth_shading=False,
            # ambient élevé = couleurs surplomb dominent
            ambient=0.82,
            diffuse=0.18,
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
                # Blanc MAT LUMINEUX, identique au mode surplombs (très apprécié) :
                # ambient élevé (0.80) → blanc franc et non grisé, diffuse faible,
                # spéculaire nul → aucun reflet vernis. Rendu non-PBR (cf.
                # _apply_pbr_mesh) pour coller exactement au rendu surplombs.
                "metallic": 0.0, "roughness": 0.62, "specular": 0.0,
                "ambient": 0.80,  "diffuse":  0.20,
                # feature_angle élevé → seules les arêtes vraiment vives (>75°) sont dures,
                # les panneaux lisses et transitions douces restent smooth → pas de triangles
                "feature_angle": 75.0,
                "ssao": None,
            },
            "balanced": {
                "metallic": 0.10, "roughness": 0.22, "specular": 0.55,
                "ambient": 0.05,  "diffuse":  0.92,
                "feature_angle": 30.0,
                "ssao": dict(radius=1.0, bias=0.008, kernel_size=128, blur=True),
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
