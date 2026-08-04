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
    # Fragilité (thermomap par objet) : vert (solide) → jaune → orange → rouge (fragile)
    _FRAGILITY_CMAP = _LSC.from_list("neoslice_frag",
        [(0.0, "#2ECC71"), (0.35, "#F1C40F"), (0.62, "#F39C12"), (1.0, "#E74C3C")])
    # ── Variantes MODE DALTONIEN (palette Okabe-Ito, sûre deutéra/protanopie) ──
    # Axe BLEU → jaune → vermillon (évite le vert↔rouge indistinguable) + la
    # luminosité croît (lisible même sans perception des teintes). Zones safe des
    # surplombs = neutre inchangé, seul le highlight passe bleu→vermillon.
    _FRAGILITY_CMAP_CB = _LSC.from_list("neoslice_frag_cb",
        [(0.0, "#0072B2"), (0.35, "#56B4E9"), (0.62, "#F0E442"), (1.0, "#D55E00")])
    _OVERHANG_CMAP_DARK_CB = _LSC.from_list("neoslice_oh_dk_cb",
        [(0.0, "#C8C4BE"), (0.22, "#56B4E9"), (0.55, "#F0E442"), (0.82, "#E69F00"), (1.0, "#D55E00")])
    _OVERHANG_CMAP_LIGHT_CB = _LSC.from_list("neoslice_oh_lt_cb",
        [(0.0, "#D4D0CA"), (0.22, "#56B4E9"), (0.55, "#F0E442"), (0.82, "#E69F00"), (1.0, "#D55E00")])
except Exception:
    _OVERHANG_CMAP_DARK  = "RdYlGn_r"
    _OVERHANG_CMAP_LIGHT = "RdYlGn_r"
    _FRAGILITY_CMAP = "RdYlGn_r"
    _FRAGILITY_CMAP_CB = "cividis"
    _OVERHANG_CMAP_DARK_CB = "cividis"
    _OVERHANG_CMAP_LIGHT_CB = "cividis"


def _mode_daltonien() -> bool:
    """Vrai si le mode daltonien est actif (PREFS)."""
    try:
        from core.prefs import PREFS
        return bool(PREFS.get("colorblind_mode", False))
    except Exception:
        return False


def _frag_cmap():
    """Colormap de la thermomap de fragilité (daltonien-safe si activé)."""
    return _FRAGILITY_CMAP_CB if _mode_daltonien() else _FRAGILITY_CMAP


def _overhang_cmap(is_dark: bool):
    """Colormap des surplombs (daltonien-safe si activé), selon le thème."""
    if _mode_daltonien():
        return _OVERHANG_CMAP_DARK_CB if is_dark else _OVERHANG_CMAP_LIGHT_CB
    return _OVERHANG_CMAP_DARK if is_dark else _OVERHANG_CMAP_LIGHT


# Pastilles de la légende « Fragilité par pièce » selon le mode (alignées sur les
# points d'ancrage des colormaps ci-dessus).
_FRAG_LEGEND_COLORS        = ("#2ECC71", "#F1C40F", "#E74C3C")   # vert / jaune / rouge
_FRAG_LEGEND_COLORS_CB     = ("#0072B2", "#F0E442", "#D55E00")   # bleu / jaune / vermillon


def _frag_legend_colors():
    return _FRAG_LEGEND_COLORS_CB if _mode_daltonien() else _FRAG_LEGEND_COLORS

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
    # index élément sélectionné dans le viewer (-1 = désélection) — encadre la
    # section correspondante dans l'éditeur de carte
    element_selectionne = Signal(int)
    # touche Suppr sur un élément sélectionné → le supprimer de l'éditeur
    element_suppr_demande = Signal(int)
    # clic sur un objet d'une scène multi-objets → l'ISOLER (édition par objet)
    objet_clique = Signal(str)          # object_id
    # bouton « ↩ Vue d'ensemble » (mode objet isolé) → revenir à tous les objets
    retour_ensemble = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mesh = None
        self._multi_actors = {}         # object_id -> vtkActor (picking par objet)
        self._multi_pick_mode = False   # True quand une scène multi-objets sélectionnable est affichée
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
        # Précharger Oen dès l'ouverture (thread démon) : le serveur Ollama démarre et
        # le modèle se charge en mémoire pendant que l'utilisateur écrit -> plus de
        # longue attente à la 1re question. Silencieux, l'appel réel réessaie si besoin.
        try:
            import threading
            from core.assistant.engine import AssistantEngine
            threading.Thread(target=lambda: AssistantEngine.instance().warmup(),
                             daemon=True).start()
        except Exception as e:
            logger.warning(f"Préchauffage Oen impossible : {e}")
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

    def _apply_ensemble_btn_style(self):
        """Style thémé du bouton « ↩ Vue d'ensemble ». Fond OPAQUE + palette
        Window de la même couleur + autoFillBackground : les coins hors du
        border-radius sont peints de la même teinte → plus de « coins blancs »
        (le rendu 3D clair transparaissait dans les angles arrondis, vécu)."""
        if not hasattr(self, "_btn_ensemble"):
            return
        is_dk = _T.is_dark()
        if is_dk:
            bg = "#0A121E"; col = "#9FC0DC"; brd = "#1A3550"
        else:
            bg = "#F0F2F5"; col = "#333333"; brd = "#C0C0C0"
        acc = _T.palette()["ACCENT"]
        # border-radius: 0 (coins CARRÉS) : un QPushButton avec stylesheet+arrondi
        # laisse ses 4 coins hors rayon TRANSPARENTS → le rendu 3D transparaît
        # (« coins blancs », vécu). Carré = aucun coin transparent, net dans les
        # deux thèmes. (autoFillBackground/palette sont ignorés dès qu'un
        # stylesheet définit background → inutiles ici.)
        self._btn_ensemble.setStyleSheet(
            f"QPushButton {{ color: {col}; background: {bg}; border: 1px solid {brd};"
            f" border-radius: 0px; padding: 5px 12px; }} "
            f"QPushButton:hover {{ border-color: {acc}; }}")

    def _apply_rot_checkbox_style(self):
        pal = _T.palette()
        is_dk = _T.is_dark()
        # Fond OPAQUE (alpha 255) : superposées au rendu 3D, ces cases laissaient
        # sinon transparaître l'ancien contenu (params) et un fantôme au resize.
        if is_dk:
            bg = 'rgb(10,18,30)'; col = '#7FA8CC'; hov = '#A9C6DE'
            ind_bg = '#060E1A'; ind_br = '#1A3550'
        else:
            bg = 'rgb(240,242,245)'; col = '#555555'; hov = '#333333'
            ind_bg = '#ffffff'; ind_br = '#c0c0c0'
        acc = pal['TELE_GREEN']
        self._rot_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {col}; background: {bg};
                spacing: 5px; padding: 2px 6px; border-radius: 0px;
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
        # Fond OPAQUE (cf. _apply_rot_checkbox_style) → pas de fantôme au resize.
        if is_dk:
            bg = 'rgb(10,18,30)'; col = '#7FA8CC'; hov = '#A9C6DE'
            ind_bg = '#060E1A'; ind_br = '#1A3550'
        else:
            bg = 'rgb(240,242,245)'; col = '#555555'; hov = '#333333'
            ind_bg = '#ffffff'; ind_br = '#c0c0c0'
        acc = pal['TELE_GREEN']
        self._plate_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {col}; background: {bg};
                spacing: 5px; padding: 2px 6px; border-radius: 0px;
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

    def _apply_frag_checkbox_style(self):
        # Identique aux autres cases (accent VERT au coché).
        from PySide6.QtGui import QColor, QPalette
        pal = _T.palette()
        is_dk = _T.is_dark()
        if is_dk:
            bg = 'rgb(10,18,30)'; bg_qc = QColor(10, 18, 30)
            col = '#7FA8CC'; hov = '#A9C6DE'
            ind_bg = '#060E1A'; ind_br = '#1A3550'
        else:
            bg = 'rgb(240,242,245)'; bg_qc = QColor(240, 242, 245)
            col = '#555555'; hov = '#333333'
            ind_bg = '#ffffff'; ind_br = '#c0c0c0'
        acc = pal['TELE_GREEN']
        self._frag_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {col}; background: {bg};
                spacing: 5px; padding: 2px 6px; border-radius: 0px;
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
        # Remplir TOUT le rectangle (coins compris) avec la couleur de fond : sinon
        # les coins hors du border-radius laissent voir le décor clair du viewer
        # derrière la case (coins « blancs » en thème sombre).
        _p = self._frag_checkbox.palette()
        _p.setColor(QPalette.Window, bg_qc)
        self._frag_checkbox.setPalette(_p)
        self._frag_checkbox.setAutoFillBackground(True)

    def set_fragility_data(self, face_severity, restore_cb=None) -> None:
        """Fournit la sévérité de fragilité par face et affiche la case à cocher
        « Fragilité » (décochée par défaut) sans changer la vue courante.

        restore_cb : callable optionnel appelé quand on DÉCOCHE la case, pour
        rétablir la vue de base (ex. recolorer un objet neoGen avec ses couleurs).
        Sinon on retombe sur la vue surplombs."""
        self._fragility_severity = np.asarray(face_severity, dtype=np.float32)
        self._has_fragility_data = True
        self._frag_restore_cb = restore_cb
        if hasattr(self, "_frag_checkbox"):
            self._frag_checkbox.blockSignals(True)
            self._frag_checkbox.setChecked(False)
            self._frag_checkbox.blockSignals(False)
            # La position/visibilité est gérée par start_auto_rotate / resizeEvent.

    def montrer_retour_ensemble(self, visible: bool) -> None:
        """Affiche/masque le bouton « ↩ Vue d'ensemble » (coin haut-gauche)."""
        if not hasattr(self, "_btn_ensemble"):
            return
        try:
            if visible:
                self._btn_ensemble.adjustSize()
                self._btn_ensemble.move(10, 10)
                self._btn_ensemble.show()
                self._btn_ensemble.raise_()
            else:
                self._btn_ensemble.hide()
        except Exception:
            pass

    def get_camera_state(self):
        """Retourne l'état complet de la caméra (position, focal, view-up) pour
        pouvoir le restaurer plus tard, ou None si indisponible."""
        if not HAS_PYVISTA or self._plotter is None:
            return None
        try:
            return self._plotter.camera_position
        except Exception:
            return None

    def set_camera_state(self, state) -> None:
        """Restaure un état caméra obtenu via get_camera_state()."""
        if not HAS_PYVISTA or self._plotter is None or state is None:
            return
        try:
            self._plotter.camera_position = state
            self._plotter.render()
        except Exception:
            pass

    def suspendre_rendu(self, actif: bool) -> None:
        """Suspend (True) / reprend (False) le rendu VTK. Permet d'enchaîner
        plusieurs opérations (chargement + caméra + recolorisation) sans afficher
        les états intermédiaires — un seul rendu final à la reprise (évite le
        « clignotement » de rafraîchissement). Cf. bascule Fragilité."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        try:
            self._plotter.suppress_rendering = bool(actif)
            if not actif:
                self._plotter.render()
        except Exception:
            pass

    def _placer_case_fragilite(self) -> None:
        """Positionne + affiche la case « Fragilité » au-dessus de « Plateau »,
        en RÉALIGNANT les trois cases sur la même largeur (sinon Plateau et
        Rotation, dimensionnées avant l'arrivée de Fragilité, restent plus
        étroites/décalées — vécu)."""
        cw = max(
            self._rot_checkbox.sizeHint().width() + 16,
            self._plate_checkbox.sizeHint().width() + 16,
            self._frag_checkbox.sizeHint().width() + 16,
        )
        _x = self.width() - cw - 8
        if self._rot_checkbox.isVisible():
            self._rot_checkbox.setGeometry(_x, self.height() - 30, cw, 22)
            self._plate_checkbox.setGeometry(_x, self.height() - 56, cw, 22)
            _y = self.height() - 82
        else:                                  # mode lite : pas de case Rotation
            self._plate_checkbox.setGeometry(_x, self.height() - 30, cw, 22)
            _y = self.height() - 56
        self._frag_checkbox.setGeometry(_x, _y, cw, 22)
        self._frag_checkbox.show()
        self._frag_checkbox.raise_()

    def montrer_case_fragilite_calcul(self) -> None:
        """Affiche la case « Fragilité » GRISÉE avec « (calcul…) » dès la fin de
        l'analyse — la thermomap se calcule en arrière-plan (~1-2 s/pièce) et la
        case s'activera à la fin. Le flag _frag_computing est respecté par
        start_auto_rotate/resizeEvent (sinon ils re-cachaient la case, vécu)."""
        if not hasattr(self, "_frag_checkbox"):
            return
        try:
            self._frag_computing = True
            self._frag_checkbox.setText(_("viewer.frag_computing"))
            self._frag_checkbox.setEnabled(False)
            self._placer_case_fragilite()
        except Exception:
            pass

    def montrer_case_fragilite(self) -> None:
        """Active la case « Fragilité » — la thermomap est PRÊTE (fin du calcul
        en arrière-plan, après start_auto_rotate qui gère normalement la
        visibilité)."""
        if not getattr(self, "_has_fragility_data", False) \
                or not hasattr(self, "_frag_checkbox"):
            return
        try:
            self._frag_computing = False
            self._frag_checkbox.setText(_("viewer.frag_toggle"))
            self._frag_checkbox.setEnabled(True)
            self._placer_case_fragilite()
        except Exception:
            pass

    def clear_fragility_data(self) -> None:
        """Aucune donnée de fragilité par pièce → masque la case et la légende,
        revient à la vue surplombs si la thermomap était affichée."""
        self._has_fragility_data = False
        self._fragility_severity = None
        self._frag_restore_cb = None
        self._frag_computing = False
        if hasattr(self, "_frag_checkbox"):
            self._frag_checkbox.blockSignals(True)
            self._frag_checkbox.setChecked(False)
            self._frag_checkbox.blockSignals(False)
            self._frag_checkbox.setText(_("viewer.frag_toggle"))   # état « calcul… » nettoyé
            self._frag_checkbox.setEnabled(True)
            self._frag_checkbox.hide()
        if hasattr(self, "_frag_legend_label"):
            self._frag_legend_label.hide()

    def _on_frag_toggle(self, state: int):
        """Bascule entre la vue surplombs (décoché) et la thermomap fragilité (coché)."""
        if self._plotter is None or self._mesh is None:
            return
        # Rendu SUSPENDU pendant la reconstruction (clear + re-ajout des acteurs) :
        # sans ça, un rendu intermédiaire affiche la scène VIDE une fraction de
        # seconde (flash) à chaque bascule, dans les deux sens.
        try:
            self._plotter.suppress_rendering = True
        except Exception:
            pass
        try:
            if state and self._fragility_severity is not None:
                # Thermomap fragilité — garder la caméra
                self.colorize_fragility(self._mesh, self._fragility_severity,
                                        _keep_camera=True)
            else:
                # Retour à la vue de BASE : callback dédié si fourni (ex. couleurs
                # neoGen), sinon surplombs, sinon mesh neutre.
                _cb = getattr(self, "_frag_restore_cb", None)
                if _cb is not None:
                    self._view_mode = "normal"
                    self._update_frag_legend_visibility()
                    _cb()
                elif getattr(self, "_face_colors", None) is not None:
                    self.colorize_overhangs(self._mesh, self._face_colors,
                                            _keep_camera=True)
                    self._update_frag_legend_visibility()
                else:
                    self._view_mode = "normal"
                    self._update_frag_legend_visibility()
            # Les cases Qt flottent au-dessus du rendu → les remonter
            self._raise_viewer_checkboxes()
        except Exception:
            logger.exception("Bascule thermomap fragilité échouée")
        finally:
            try:
                self._plotter.suppress_rendering = False
                self._plotter.render()
            except Exception:
                pass

    def _raise_viewer_checkboxes(self):
        for _cb in (getattr(self, "_frag_checkbox", None),
                    getattr(self, "_plate_checkbox", None),
                    getattr(self, "_rot_checkbox", None),
                    getattr(self, "_frag_legend_label", None)):
            try:
                if _cb is not None and _cb.isVisible():
                    _cb.raise_()
            except Exception:
                pass

    def _build_frag_legend_html(self) -> str:
        """Légende thermomap : 3 niveaux avec pastille colorée (vert/jaune/rouge)."""
        pal = _T.palette()
        txt = pal.get("TEXT_SECONDARY", "#888")
        title = pal.get("TEXT_PRIMARY", txt)
        def _row(color, label):
            return (f'<tr><td style="padding-right:5px; color:{color}; '
                    f'font-size:13px; line-height:13px;">●</td>'
                    f'<td style="color:{txt};">{label}</td></tr>')
        c_solid, c_mid, c_high = _frag_legend_colors()   # daltonien-safe si activé
        return (
            f'<div style="font-family:sans-serif; font-size:11px;">'
            f'<div style="color:{title}; font-weight:bold;">'
            f'{_("viewer.frag_legend_title")}</div>'
            f'<div style="font-size:7px; line-height:7px;">&nbsp;</div>'  # espaceur
            f'<table cellspacing="0" cellpadding="0">'
            f'{_row(c_solid, _("viewer.frag_legend_solid"))}'
            f'{_row(c_mid, _("viewer.frag_legend_mid"))}'
            f'{_row(c_high, _("viewer.frag_legend_high"))}'
            f'</table></div>'
        )

    def _update_frag_legend_visibility(self):
        """Affiche la légende SEULEMENT quand la thermomap est active (case cochée)."""
        if not hasattr(self, "_frag_legend_label"):
            return
        show = (getattr(self, "_view_mode", "normal") == "fragility"
                and hasattr(self, "_frag_checkbox")
                and self._frag_checkbox.isChecked())
        if show:
            is_dk = _T.is_dark()
            bg = 'rgba(10,18,30,235)' if is_dk else 'rgba(240,242,245,235)'
            self._frag_legend_label.setText(self._build_frag_legend_html())
            # border-radius: 0 (coins CARRÉS) : un QLabel avec background + arrondi
            # laisse ses 4 coins hors rayon TRANSPARENTS → le rendu 3D transparaît
            # (« bouts de coins blancs » en thème sombre, vécu comme sur les cases).
            self._frag_legend_label.setStyleSheet(
                f"background: {bg}; border-radius: 0px; padding: 6px 8px;")
            self._frag_legend_label.adjustSize()
            self._frag_legend_label.move(10, 10)
            self._frag_legend_label.show()
            self._frag_legend_label.raise_()
        else:
            self._frag_legend_label.hide()

    def refresh_theme(self):
        if hasattr(self, '_rot_checkbox'):
            self._apply_rot_checkbox_style()
        if hasattr(self, '_plate_checkbox'):
            self._apply_plate_checkbox_style()
        if hasattr(self, '_frag_checkbox'):
            self._apply_frag_checkbox_style()
        if hasattr(self, '_btn_ensemble'):
            self._apply_ensemble_btn_style()
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
        # Mesh — mise à jour du matériau/plateau si une pièce est chargée.
        # suspendre_rendu : la reconstruction (plateau + mesh + recolorisation)
        # enchaîne plusieurs opérations → un SEUL rendu final, pas de clignotement
        # au changement de thème (même principe que la bascule Fragilité).
        if self._mesh is not None:
            self.suspendre_rendu(True)
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
                elif getattr(self, "_view_mode", "normal") == "fragility" \
                        and getattr(self, "_fragility_severity", None) is not None:
                    self.colorize_fragility(self._mesh, self._fragility_severity, _keep_camera=True)
                self._plotter.camera_position = _saved_cam
            except Exception:
                pass
            finally:
                self.suspendre_rendu(False)
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

    def refresh_colorblind(self):
        """Bascule du mode daltonien : re-colorise la vue courante (thermomap de
        fragilité ou surplombs) avec la palette adaptée + met à jour la légende.
        Sans effet sur la vue normale (pas de couleurs par sévérité)."""
        if self._plotter is None or self._mesh is None:
            return
        mode = getattr(self, "_view_mode", "normal")
        try:
            self.suspendre_rendu(True)   # recolorisation en un seul rendu
            _cam = self._plotter.camera_position
            if mode == "analysis" and self._face_colors is not None:
                self.colorize_overhangs(self._mesh, self._face_colors, _keep_camera=True)
            elif mode == "fragility" \
                    and getattr(self, "_fragility_severity", None) is not None:
                self.colorize_fragility(self._mesh, self._fragility_severity,
                                        _keep_camera=True)
                self._update_frag_legend_visibility()
            self._plotter.camera_position = _cam
        except Exception:
            logger.debug("refresh_colorblind échoué", exc_info=True)
        finally:
            self.suspendre_rendu(False)

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
                (self._frag_checkbox.sizeHint().width() + 16)
                if hasattr(self, "_frag_checkbox") else 0,
            )
            self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
            self._plate_checkbox.setGeometry(self.width() - cw - 8, self.height() - 56, cw, 22)
            # Case Fragilité AU-DESSUS de Plateau (données prêtes OU calcul en cours)
            if hasattr(self, "_frag_checkbox") and (
                    getattr(self, "_has_fragility_data", False)
                    or getattr(self, "_frag_computing", False)):
                self._frag_checkbox.setGeometry(self.width() - cw - 8, self.height() - 82, cw, 22)
            if hasattr(self, "_frag_legend_label") and self._frag_legend_label.isVisible():
                self._frag_legend_label.move(10, 10)
            self._rafraichir_apres_deplacement_cases()
        elif hasattr(self, "_rot_checkbox"):
            cw = self._rot_checkbox.sizeHint().width() + 16
            self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
            self._rafraichir_apres_deplacement_cases()

    def _rafraichir_apres_deplacement_cases(self):
        """Après avoir déplacé les cases (Plateau / Rotation auto) superposées au
        rendu 3D, on force un re-rendu VTK : sinon la surface OpenGL garde un
        FANTÔME des cases à leur ancienne position quand la colonne se redimensionne."""
        try:
            if self._plotter is not None:
                self._plotter.render()
            for _cb in (getattr(self, "_rot_checkbox", None),
                        getattr(self, "_plate_checkbox", None),
                        getattr(self, "_frag_checkbox", None)):
                if _cb is not None and _cb.isVisible():
                    _cb.raise_()
                    _cb.update()
        except Exception:
            pass

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
        # Couleurs de la PALETTE (pas de sombre en dur) : ce message doit rester
        # lisible dans les deux thèmes (règle thème clair/sombre).
        _pp = _T.palette()
        holder.setStyleSheet(
            f"background-color: {_pp['BG_PANEL']}; border-radius: 10px;")

        label = QLabel(msg)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {_pp['TEXT_SECONDARY']}; font-size: 13px; background: transparent;")
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
            self._garder_distance_gizmo()
        except Exception as e:
            logger.debug(f"cube d'orientation indisponible : {e}")

    def _garder_distance_gizmo(self):
        """Clic sur un axe du gizmo (X/Y/Z) : réoriente la caméra MAIS garde la
        distance actuelle (avant, VTK reculait la caméra pour recadrer la scène)."""
        w = getattr(self, "_orient_widget", None)
        if w is None or self._plotter is None:
            return

        # Désactiver l'ANIMATION : sinon VTK anime la caméra sur ~1 s en la
        # reculant (recadrage), et on ne remet la distance qu'à la fin → « recul
        # puis retour ». Sans animation, la réorientation est instantanée et la
        # distance est corrigée dans la foulée → aucun recul visible.
        for _meth, _arg in (("SetAnimate", False), ("SetAnimatorTotalFrames", 1)):
            try:
                getattr(w, _meth)(_arg)
            except Exception:
                pass

        def _save(caller=None, ev=None):
            try:
                cam = self._plotter.camera
                p = np.array(cam.position); f = np.array(cam.focal_point)
                self._gizmo_dist = float(np.linalg.norm(p - f))
            except Exception:
                pass

        def _restore(caller=None, ev=None):
            d0 = getattr(self, "_gizmo_dist", None)
            if not d0:
                return
            try:
                cam = self._plotter.camera
                p = np.array(cam.position); f = np.array(cam.focal_point)
                v = p - f
                n = float(np.linalg.norm(v))
                if n > 1e-6:
                    cam.position = tuple(f + v / n * d0)   # même distance, nouvelle direction
                    self._plotter.renderer.ResetCameraClippingRange()
                    self._plotter.render()
            except Exception:
                pass
        try:
            w.AddObserver("StartInteractionEvent", _save)
            w.AddObserver("InteractionEvent", _restore)
            w.AddObserver("EndInteractionEvent", _restore)
        except Exception:
            pass

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
                    _op = 0.0 if pos[2] < 0 else self._PLATE_OPACITY
                    # TOUS les plateaux (mono « build_plate_surface » ET multi
                    # « build_plate_surface_N ») — sinon les plateaux multiples
                    # restaient opaques vus de dessous.
                    for _nm, _ac in list(self._plotter.actors.items()):
                        if _nm.startswith("build_plate_surface"):
                            _ac.prop.opacity = _op
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

        # Case « Fragilité » (thermomap) — au-DESSUS de Plateau. Décochée par
        # défaut, affichée seulement si des données de fragilité par pièce existent.
        self._has_fragility_data = False
        self._fragility_severity = None
        self._frag_restore_cb = None
        self._frag_checkbox = QCheckBox(_("viewer.frag_toggle"), self)
        self._frag_checkbox.setChecked(False)
        self._frag_checkbox.setFont(QFont(FONT_MAIN, 9))
        self._apply_frag_checkbox_style()
        self._frag_checkbox.hide()
        self._frag_checkbox.stateChanged.connect(self._on_frag_toggle)

        # Bouton « ↩ Vue d'ensemble » (mode objet isolé) — coin HAUT-GAUCHE,
        # masqué par défaut. Ramène à la scène complète multi-objets.
        self._btn_ensemble = QPushButton(_("viewer.back_overview"), self)
        self._btn_ensemble.setFont(QFont(FONT_MAIN, 9))
        self._btn_ensemble.setCursor(Qt.PointingHandCursor)
        self._apply_ensemble_btn_style()
        self._btn_ensemble.clicked.connect(self.retour_ensemble.emit)
        self._btn_ensemble.hide()

        # Légende thermomap (3 niveaux colorés) — coin haut-gauche, masquée par défaut.
        self._frag_legend_label = QLabel(self)
        self._frag_legend_label.setTextFormat(Qt.RichText)
        self._frag_legend_label.hide()

    def _on_rot_toggle(self, state: int):
        # Mémorise le CHOIX de l'utilisateur — de façon PERSISTANTE (PREFS) :
        # coché → la rotation revient à chaque pièce/session ; décoché → jamais.
        # Par défaut (jamais touché) : désactivée.
        self._rot_user_off = not bool(state)
        try:
            from core.prefs import PREFS
            PREFS.set("auto_rotate", bool(state))
        except Exception:
            pass
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

        # « calcul en cours » compte comme visible : la case grisée « (calcul…) »
        # ne doit pas être re-cachée par start_auto_rotate (vécu).
        _has_frag = (getattr(self, "_has_fragility_data", False)
                     or getattr(self, "_frag_computing", False))
        cw_frag = (self._frag_checkbox.sizeHint().width() + 16) if _has_frag else 0

        # Plateau checkbox — toujours visible après analyse, quel que soit le mode
        cw_plt = self._plate_checkbox.sizeHint().width() + 16
        if _lite:
            _cwl = max(cw_plt, cw_frag)
            self._plate_checkbox.setGeometry(self.width() - _cwl - 8, self.height() - 30, _cwl, 22)
            self._plate_checkbox.show()
            self._plate_checkbox.raise_()
            if _has_frag:
                self._frag_checkbox.setGeometry(self.width() - _cwl - 8, self.height() - 56, _cwl, 22)
                self._frag_checkbox.show()
                self._frag_checkbox.raise_()
            return

        # Respecte le choix PERSISTANT (PREFS) : rotation auto DÉSACTIVÉE par
        # défaut, partout (viewer, neoGen…) ; ne tourne que si l'utilisateur l'a
        # explicitement cochée — et ce choix survit aux rechargements/sessions.
        _actif = bool(PREFS.get("auto_rotate", False))
        self._rot_user_off = not _actif
        self._auto_rotate = _actif
        self._rot_checkbox.setEnabled(True)
        self._rot_checkbox.blockSignals(True)
        self._rot_checkbox.setChecked(_actif)
        self._rot_checkbox.blockSignals(False)
        # Positionne et affiche les checkboxes en bas à droite
        cw_rot = self._rot_checkbox.sizeHint().width() + 16
        cw = max(cw_rot, cw_plt, cw_frag)
        self._rot_checkbox.setGeometry(self.width() - cw - 8, self.height() - 30, cw, 22)
        self._rot_checkbox.show()
        self._rot_checkbox.raise_()
        self._plate_checkbox.setGeometry(self.width() - cw - 8, self.height() - 56, cw, 22)
        self._plate_checkbox.show()
        self._plate_checkbox.raise_()
        # Case Fragilité (thermomap) au-DESSUS de Plateau, seulement si données prêtes
        if _has_frag:
            self._frag_checkbox.setGeometry(self.width() - cw - 8, self.height() - 82, cw, 22)
            self._frag_checkbox.show()
            self._frag_checkbox.raise_()
        else:
            self._frag_checkbox.hide()
        if _actif:
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
        if hasattr(self, "_frag_checkbox"):
            self._frag_checkbox.hide()
        if hasattr(self, "_frag_legend_label"):
            self._frag_legend_label.hide()
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
            # Touche Suppr en mode carte avec un élément sélectionné → suppression.
            if t == QEvent.KeyPress and getattr(self, "_carte_drag_mode", False):
                from PySide6.QtCore import Qt as _Qt
                if event.key() == _Qt.Key_Delete:
                    sel = getattr(self, "_carte_sel", None)
                    idx = getattr(self, "_carte_actors", {}).get(sel) if sel else None
                    if idx is not None:
                        self._surligner_carte(sel, False)   # retire la silhouette
                        self._carte_sel = None
                        self.element_suppr_demande.emit(idx)
                        return True
            # Déplacement d'un élément de carte : press/move/release Qt (release
            # FIABLE). Si un drag est en cours, on CONSOMME l'événement (True)
            # pour empêcher l'orbite caméra.
            if getattr(self, "_carte_drag_mode", False):
                try:
                    r = self._carte_mouse(event, t)
                    if r:
                        return True
                except Exception:
                    pass
            # Sélection d'objet (scène multi-objets) : un CLIC SIMPLE (press+release
            # sans bouger — un drag = orbite caméra, on l'ignore) isole l'objet visé.
            if getattr(self, "_multi_pick_mode", False):
                from PySide6.QtCore import Qt as _Qt2
                if t == QEvent.MouseButtonPress and event.button() == _Qt2.LeftButton:
                    self._multi_press = (event.position() if hasattr(event, "position")
                                         else event.pos())
                elif t == QEvent.MouseButtonRelease and event.button() == _Qt2.LeftButton:
                    _pp = getattr(self, "_multi_press", None)
                    self._multi_press = None
                    if _pp is not None:
                        _rp = (event.position() if hasattr(event, "position")
                               else event.pos())
                        if abs(_rp.x() - _pp.x()) + abs(_rp.y() - _pp.y()) < 6:
                            try:
                                _oid = self._pick_object_id(_rp)
                                if _oid is not None:
                                    self.objet_clique.emit(_oid)
                            except Exception:
                                logger.debug("picking objet échoué", exc_info=True)
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

            # Décalage anti-Z-fighting PROPORTIONNEL à la hauteur de la pièce :
            # un écart fixe de 0.5-1mm est invisible sur une pièce de 100mm mais
            # représente ~15% d'une figurine de 6mm → elle semble LÉVITER. On cale
            # l'écart sur la taille réelle (plafonné aux anciennes valeurs).
            _gap = getattr(self, "_plate_z_gap", 0.5)
            # Surface à COINS ARRONDIS (style Bambu Studio) : polygone convexe
            # dont les 4 coins sont des arcs de rayon ∝ taille du plateau.
            _r = max(3.0, min(12.0, min(pw, ph) * 0.06))
            _zp = -2.0 * _gap
            _pts = []
            # 24 segments par coin : arc parfaitement lisse. PAS de trait de
            # contour séparé — VTK rend ses jonctions comme des « perles » dans
            # les arrondis (vécu) ; le bord de la surface fait le contour, net.
            for _ox, _oy, _start in ((cx + hw - _r, cy + hh - _r, 0.0),
                                     (cx - hw + _r, cy + hh - _r, 90.0),
                                     (cx - hw + _r, cy - hh + _r, 180.0),
                                     (cx + hw - _r, cy - hh + _r, 270.0)):
                for _a in np.linspace(_start, _start + 90.0, 25)[:-1]:
                    _rad = np.radians(_a)
                    _pts.append([_ox + _r * np.cos(_rad),
                                 _oy + _r * np.sin(_rad), _zp])
            _np_pts = np.array(_pts, dtype=np.float32)
            _n = len(_pts)
            plate = pv.PolyData(
                _np_pts, faces=np.array([_n] + list(range(_n)), dtype=np.int_)
            ).triangulate()
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
            # Lignes INTÉRIEURES seulement ([1:-1]) : les bords sont dessinés par
            # le contour arrondi — sinon les lignes de bord dépassent des coins.
            lines_v = np.linspace(cx - hw, cx + hw, nx + 1)[1:-1]
            lines_h = np.linspace(cy - hh, cy + hh, ny + 1)[1:-1]
            # Grille juste SOUS le dessous des pièces (à z=0) : évite qu'elle
            # traverse le bas des pièces selon l'angle (Z-fighting), surtout avec
            # le polygon-offset VTK actif. Écart proportionnel (cf. _gap plus haut)
            # pour rester discret sur les petites pièces sans flottement visible.
            _gz = -_gap
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
        """Ajoute un plateau dont la taille s'adapte à la pièce chargée.

        Si un chargement multi-plateaux a mémorisé ses groupes
        (_plate_groups_draw), on dessine UN plateau par groupe — fidèle à
        Bambu Studio — au lieu d'un plateau unique englobant."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        _groupes = getattr(self, "_plate_groups_draw", None)
        if _groupes:
            try:
                if mesh is not None:
                    _zext = float(mesh.bounding_box.extents[2])
                    self._plate_z_gap = min(0.5, max(0.03, _zext * 0.02))
                else:
                    self._plate_z_gap = 0.5
                for _pid, (_cx, _cy, _pw, _ph) in enumerate(_groupes):
                    self._draw_single_plate(_cx, _cy, max(_pw, _ph),
                                            suffix=f"_{_pid}",
                                            plate_w=_pw, plate_h=_ph)
                self._current_plate_size = max(max(g[2], g[3]) for g in _groupes)
                return
            except Exception:
                logger.debug("dessin multi-plateaux échoué → plateau unique",
                             exc_info=True)
        try:
            if mesh is not None:
                # Empreinte XY uniquement — ne pas utiliser Z (hauteur)
                ext = mesh.bounding_box.extents
                footprint = float(max(ext[0], ext[1]))
                # Marge adaptative : généreuse pour les petites pièces, serrée pour les grandes
                margin = max(footprint * 0.3, 60.0)
                plate_size = max(footprint + margin, 30.0)
                # Écart plateau/grille sous la pièce ∝ hauteur : discret sur une
                # figurine de 6mm (~0.12mm), inchangé (0.5mm) dès ~25mm de haut.
                _zext = float(ext[2])
                self._plate_z_gap = min(0.5, max(0.03, _zext * 0.02))
            else:
                plate_size = self._PLATE_SIZE
                self._plate_z_gap = 0.5
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

            # Écart plateau/grille ∝ hauteur max des pièces (mêmes bornes que le
            # mono-plateau) pour éviter la « lévitation » sur de petits objets.
            try:
                _hmax = max(float(m.bounding_box.extents[2]) for m in final_meshes)
                self._plate_z_gap = min(0.5, max(0.03, _hmax * 0.02))
            except Exception:
                self._plate_z_gap = 0.5

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

    @staticmethod
    def _layout_par_plateau(transformed: list, objects: list) -> tuple:
        """Disposition fidèle multi-plateaux : groupe les pièces par plate_index
        (lu du 3MF — aucune devinette spatiale), garde la disposition INTERNE de
        chaque plateau, et pose les plateaux côte à côte.

        Returns (offsets: list[(dx, dy)] par pièce, groupes: list[list[int]]).
        """
        groupes_map: dict[int, list[int]] = {}
        for i, o in enumerate(objects):
            groupes_map.setdefault(int(getattr(o, "plate_index", 0)), []).append(i)
        groupes = [groupes_map[k] for k in sorted(groupes_map)]

        PAD, GAP = 20.0, 35.0        # marge intérieure plateau / écart entre plateaux
        # Au-delà : positions intra-plateau incohérentes (certains 3MF Bambu ont
        # des transforms d'instance corrompus → pièces dispersées sur des mètres,
        # vécu : Table de chevet, plateau « 256 mm » étendu sur 3,3 m). On range
        # alors les pièces du plateau en petite grille compacte.
        SEUIL_DISPERSE = 300.0

        local = [(0.0, 0.0)] * len(transformed)   # offsets DANS le repère du groupe
        tailles = []                              # (largeur, hauteur) par groupe
        for idxs in groupes:
            xmin = min(float(transformed[i].bounds[0][0]) for i in idxs)
            ymin = min(float(transformed[i].bounds[0][1]) for i in idxs)
            xmax = max(float(transformed[i].bounds[1][0]) for i in idxs)
            ymax = max(float(transformed[i].bounds[1][1]) for i in idxs)
            w, h = xmax - xmin, ymax - ymin
            if max(w, h) > SEUIL_DISPERSE and len(idxs) > 1:
                # Compactage LOCAL en grille : cellule = plus grande pièce + marge.
                sizes = [(float(transformed[i].bounds[1][0] - transformed[i].bounds[0][0]),
                          float(transformed[i].bounds[1][1] - transformed[i].bounds[0][1]))
                         for i in idxs]
                cw = max(s[0] for s in sizes) + 12.0
                ch = max(s[1] for s in sizes) + 12.0
                cols = max(1, math.ceil(math.sqrt(len(idxs))))
                rows = math.ceil(len(idxs) / cols)
                gw, gh = cols * cw, rows * ch
                for k, i in enumerate(idxs):
                    r_, c_ = divmod(k, cols)
                    tx = (c_ + 0.5) * cw - gw / 2
                    ty = gh / 2 - (r_ + 0.5) * ch
                    b = transformed[i].bounds
                    local[i] = (tx - (b[0][0] + b[1][0]) / 2,
                                ty - (b[0][1] + b[1][1]) / 2)
                tailles.append((gw, gh))
            else:
                # Disposition interne FIDÈLE, ramenée autour de (0, 0).
                gcx, gcy = (xmin + xmax) / 2, (ymin + ymax) / 2
                for i in idxs:
                    local[i] = (-gcx, -gcy)
                tailles.append((w, h))

        # Taille UNIQUE et CARRÉE (style Bambu Studio) : le groupe le plus
        # encombrant fixe le côté de TOUS les plateaux.
        cote = max(max(w, h) for w, h in tailles) + 2 * PAD
        cote = max(cote, 30.0)

        # Grille de plateaux : 3 par rangée MAXIMUM (comme Bambu Studio), les
        # rangées les unes sous les autres — pas de ligne infinie.
        n = len(groupes)
        ncols = min(3, n)
        nrows = math.ceil(n / 3)
        cell = cote + GAP
        centres = []
        offsets = [(0.0, 0.0)] * len(transformed)
        for g, idxs in enumerate(groupes):
            r_, c_ = divmod(g, 3)
            px = (c_ - (ncols - 1) / 2) * cell
            py = ((nrows - 1) / 2 - r_) * cell
            centres.append((px, py))
            for i in idxs:
                lx, ly = local[i]
                offsets[i] = (lx + px, ly + py)
        logger.info(f"Multi-plateaux : {n} plateau(x) carrés de {cote:.0f}mm "
                    f"en {nrows} rangée(s), {len(transformed)} pièce(s)")
        return offsets, groupes, cote, centres

    def _load_multipart_mesh(self, threemf_data) -> None:
        """Affiche un 3MF multi-objets — chaque objet = acteur séparé coloré par slot."""
        import trimesh as _trimesh

        self._mesh = threemf_data.combined_mesh
        self._pv_mesh_cache = None
        self._face_colors = None
        self._view_mode = "normal"
        self._plate_groups_draw = None   # remis par ce chargement s'il est multi-plateaux
        self._plate_groups_idx = None
        self._multi_actors = {}          # object_id -> vtkActor (picking par objet)
        self._multi_pick_mode = False
        self.clear_fragility_data()   # nouvelle pièce → oublier la fragilité précédente
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

        if _has_multiplate:
            # VRAI multi-plateaux (plate_index lus du 3MF) : afficher comme Bambu
            # Studio — un plateau par groupe, côte à côte. Chaque groupe garde sa
            # disposition interne ; le dessin des plateaux suit dans
            # _add_build_plate via self._plate_groups_draw.
            do_arrange = True
            (arrange_offsets, self._plate_groups_idx,
             self._plate_cote, self._plate_centres) = \
                self._layout_par_plateau(transformed, _display_objects)
        elif threemf_data.slot_count > 1 and not _positions_huge:
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
        # object_id dans le MÊME ordre que _object_viewer_bounds (picking par position)
        self._object_ids_ordered = [str(o.object_id) for o in _display_objects]

        # Multi-plateaux : rectangles de plateaux (un par groupe) calculés sur les
        # positions FINALES (après centrage). Mémorisés dans _plate_groups_draw :
        # _add_build_plate les dessine (et les redessine à chaque recolorisation).
        _grp = getattr(self, "_plate_groups_idx", None)
        if _grp:
            # Plateaux CARRÉS de taille IDENTIQUE, dessinés sur les CENTRES DE
            # CASES calculés par _layout_par_plateau (+ centrage global gx/gy) —
            # placement exact, aucun risque de dérive/chevauchement.
            _cote = float(getattr(self, "_plate_cote", 0.0) or 30.0)
            _ctr = getattr(self, "_plate_centres", None) or []
            self._plate_groups_draw = []
            for (_px, _py) in _ctr:
                self._plate_groups_draw.append((_px + gx, _py + gy, _cote, _cote))
            self._plate_groups_idx = None
            self._plate_centres = None

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
                # Couleur de filament (slot) UNIQUEMENT pour un vrai assemblage
                # multicolore. Pour un lot de pièces mono-matière (multi-plateaux,
                # multi-objets), on affiche l'ivoire NEUTRE de base — sinon les
                # pièces « flashaient » en couleur de slot (orange…) pendant
                # l'analyse avant d'être repeintes en gris (vécu).
                color = (self._SLOT_COLORS.get(obj.extruder, "#AABBCC")
                         if _is_color_assembly else "#f2ede8")

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
                    _act = self._plotter.add_mesh(
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
                    _act = self._plotter.add_mesh(
                        pv_obj, color=color, show_edges=False,
                        smooth_shading=True,
                        pbr=False,
                        specular=rq["specular"],
                        ambient=rq["ambient"],
                        diffuse=rq["diffuse"],
                        name=f"obj_{obj.object_id}",
                    )
                # Map acteur → object_id pour le picking (isolation par objet).
                self._multi_actors[str(obj.object_id)] = _act
            except Exception as _e:
                logger.warning(f"Objet {obj.name} non affiché : {_e}")

        # Picking d'objet activé UNIQUEMENT s'il y a plusieurs pièces à isoler.
        self._multi_pick_mode = len(_display_objects) > 1

        # 5) Caméra sur le bounding box global arrangé
        try:
            _elev = math.radians(25)
            _far  = 1e6
            self._plotter.camera.position = (0.0, -math.cos(_elev) * _far,
                                              math.sin(_elev) * _far)
            self._plotter.camera.focal_point = (0.0, 0.0, 0.0)
            self._plotter.camera.up = (0.0, 0.0, 1.0)
            _groupes_cam = getattr(self, "_plate_groups_draw", None)
            if _groupes_cam:
                # Multi-plateaux : cadrage MANUEL sur la grille de plateaux.
                # reset_camera(bounds) fait cadrer la SPHÈRE englobante par VTK —
                # pire cas pour une grille plate et large : tout paraît minuscule
                # (vécu). On calcule la distance nous-mêmes depuis la taille
                # exacte de la grille, le ratio de fenêtre et l'angle de vue.
                _xs0 = min(g[0] - g[2] / 2 for g in _groupes_cam)
                _xs1 = max(g[0] + g[2] / 2 for g in _groupes_cam)
                _ys0 = min(g[1] - g[3] / 2 for g in _groupes_cam)
                _ys1 = max(g[1] + g[3] / 2 for g in _groupes_cam)
                _gw, _gh = _xs1 - _xs0, _ys1 - _ys0
                _gcx, _gcy = (_xs0 + _xs1) / 2, (_ys0 + _ys1) / 2
                _va = math.radians(float(self._plotter.camera.view_angle or 30.0))
                try:
                    _wpx, _hpx = self._plotter.window_size
                    _aspect = max(float(_wpx) / max(float(_hpx), 1.0), 0.2)
                except Exception:
                    _aspect = 1.6
                _marge = 1.10
                # distance pour que la grille tienne verticalement (profondeur
                # projetée à 25°) ET horizontalement (largeur / ratio fenêtre)
                _dv = (_gh / 2 * math.sin(_elev) * _marge) / math.tan(_va / 2)
                _dh = (_gw / 2 * _marge) / (math.tan(_va / 2) * _aspect)
                _dist = max(_dv, _dh, 80.0) + (_gh / 2) * math.cos(_elev)
                self._plotter.camera.focal_point = (_gcx, _gcy, 0.0)
                self._plotter.camera.position = (
                    _gcx, _gcy - math.cos(_elev) * _dist, math.sin(_elev) * _dist)
                self._plotter.camera.up = (0.0, 0.0, 1.0)
            else:
                # Mono-plateau : marge 50 % sur les petites scènes (inchangé),
                # plafonnée sur les grandes.
                _bmax = float(_bb.max())
                _pad = min(_bmax * 0.5, _bmax * 0.15 + 60.0)
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
        BAR_H  = 5.5    # épaisseur de la barre (mm) — fine, style barre de vie
        LIFT   = 55.0   # hauteur au-dessus de la pièce (mm) — la barre flotte haut

        # Seuil d'affichage : on ne montre une barre QUE si la pièce est vraiment
        # fragile. En dessous (vert), pas de barre du tout — inutile d'encombrer.
        SEUIL_AFFICHAGE = 0.30

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

            # Peu de fragilité → aucune barre (uniquement quand il y en a vraiment)
            if score < SEUIL_AFFICHAGE:
                continue

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

                # ── Lignes fines de la barre vers la/les pièce(s) LA/LES PLUS
                # FRAGILE(S) du lot : on voit d'un coup d'œil quelle pièce est en
                # cause (plusieurs cibles → plusieurs lignes). Repère au bout. ──
                p_bar = (cx, cy, top_z - BAR_H / 2 - 0.5)
                for k, t in enumerate(b.get("targets", [])):
                    try:
                        p_obj = (float(t["x"]), float(t["y"]), float(t["z"]) + 1.5)
                        line = pv.Line(p_bar, p_obj)
                        self._plotter.add_mesh(
                            line, color=fill_color, line_width=1.0,
                            name=f"frag_line_{i}_{k}", reset_camera=False,
                            lighting=False)
                        # petit repère (sphère) posé sur la pièce visée
                        pt = pv.Sphere(radius=0.9, center=p_obj)
                        self._plotter.add_mesh(
                            pt, color=fill_color, name=f"frag_dot_{i}_{k}",
                            reset_camera=False, lighting=False)
                    except Exception:
                        pass
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
        # Supprimer les labels, lignes indicatrices et repères
        for name in list(self._plotter.actors.keys()):
            if (name.startswith("frag_label_") or name.startswith("frag_line_")
                    or name.startswith("frag_dot_")):
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
        self._plate_groups_draw = None   # pièce simple → un seul plateau
        self._multi_pick_mode = False    # pièce simple → pas de sélection d'objet
        self.clear_fragility_data()   # nouvelle pièce → oublier la fragilité précédente
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
        self._plate_groups_draw = None   # carte = 1 plateau (pas d'héritage multi)
        self._multi_pick_mode = False    # carte → pas de sélection d'objet
        if premiere:
            self._cancel_mesh_prep()
            self.stop_auto_rotate()
            self._plotter.clear()
            self._setup_lights()
            self._add_build_plate(fusion)
            self._carte_actors = {}          # nom acteur -> index élément (drag)
            self._carte_vtk = {}             # nom acteur -> vtkActor (matching pick)
            self._carte_pv = {}              # nom acteur -> pyvista mesh (silhouette)
            self._carte_sel = None           # nom de l'élément sélectionné
            self._carte_sil = None           # acteur de silhouette (surbrillance)

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
                    self._carte_pv[acteur] = pvm       # mesh pour la silhouette
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

    def apercu_neogen(self, piece, garder_camera: bool = False) -> None:
        """Aperçu LÉGER d'un objet neoGen à la sélection / au réglage (comme la
        carte de visite) : affiche la pièce — Scene à corps colorés OU maillage
        simple — centrée sur le plateau, en vue 3D, SANS analyse ni chargement
        pipeline. Les couleurs choisies dans le formulaire apparaissent en direct.
        L'aperçu est REMPLACÉ dès qu'on clique « Générer »."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        import trimesh as _tm
        # HueForge : afficher l'APERÇU photo (relief à couleur par sommet) plutôt
        # que les bandes d'export, si la scène le fournit dans ses métadonnées.
        if isinstance(piece, _tm.Scene):
            _apc = (getattr(piece, "metadata", None) or {}).get("hueforge_apercu")
            if _apc is not None:
                piece = _apc
        if isinstance(piece, _tm.Scene):
            corps = dict(piece.geometry)
        elif isinstance(piece, _tm.Trimesh):
            corps = {"objet": piece}
        else:
            return
        if not corps:
            return

        # Rendu d'UN corps (couleurs par sommet HueForge si variées, sinon teinte
        # de face uniforme). Facteur commun aux aperçus mono- et multi-plateaux.
        def _ajouter_corps(g, off, nom):
            pvm = self._trimesh_to_pyvista(g)
            pvm.translate(off, inplace=True)
            vcols = None
            try:
                _vc = getattr(g.visual, "vertex_colors", None)
                if _vc is not None and len(_vc) == len(g.vertices) \
                        and pvm.n_points == len(_vc):
                    _arr = np.asarray(_vc)[:, :3]
                    if _arr.std() > 3.0:
                        vcols = _arr
            except Exception:
                vcols = None
            if vcols is not None:
                pvm.point_data["rgb"] = vcols
                # lighting=False → couleurs fidèles, identiques clair/sombre.
                self._plotter.add_mesh(pvm, scalars="rgb", rgb=True, show_edges=False,
                                       lighting=False, smooth_shading=True,
                                       name=f"apercu_{nom}", reset_camera=False)
            else:
                try:
                    col = g.visual.face_colors[0][:3] / 255.0
                except Exception:
                    col = (0.82, 0.82, 0.86)      # neutre si pas de couleur
                self._plotter.add_mesh(pvm, color=col, show_edges=False,
                                       smooth_shading=False, name=f"apercu_{nom}",
                                       reset_camera=False)

        # Corps répartis par PLATEAU (tag DSL neoslice_plate) — ex. boîte lumineuse :
        # couvercle lithophane sur un plateau, boîte sur un autre.
        plates: dict[int, list] = {}
        for nom, g in corps.items():
            md = getattr(g, "metadata", {}) or {}
            plates.setdefault(int(md.get("neoslice_plate", 0) or 0), []).append((nom, g))
        multi = len(plates) > 1

        # NB : on ne touche PAS self._mesh — l'aperçu est purement visuel.
        premiere = getattr(self, "_view_mode", "") != "apercu_neogen"
        _cam_gardee = None
        if not premiere or garder_camera:
            try:
                _cam_gardee = self._plotter.camera_position
            except Exception:
                _cam_gardee = None
        self._view_mode = "apercu_neogen"
        self._cancel_mesh_prep()
        self._plate_groups_draw = None
        self._multi_pick_mode = False
        # clear + plateau(x) + N corps = plusieurs rendus intermédiaires visibles
        # à chaque ajustement du formulaire → un SEUL rendu final (anti-clignotement).
        self.suspendre_rendu(True)
        self._plotter.clear()
        self._setup_lights()

        if not multi:
            fusion = _tm.util.concatenate(list(corps.values()))
            self._add_build_plate(fusion)
            b = fusion.bounds
            off = [-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]]
            for nom, g in corps.items():
                _ajouter_corps(g, off, nom)
        else:
            # Plateaux CARRÉS de taille identique (max empreinte), disposés en rangée.
            side = 0.0
            for pieces in plates.values():
                f = _tm.util.concatenate([g for _n, g in pieces])
                bb = f.bounds
                side = max(side, bb[1][0] - bb[0][0], bb[1][1] - bb[0][1])
            side = max(side + 40.0, 120.0)
            gap = 20.0
            order = sorted(plates)
            n = len(order)
            for idx, pi in enumerate(order):
                cx = (idx - (n - 1) / 2.0) * (side + gap)
                self._draw_single_plate(cx, 0.0, side, suffix=f"_p{pi}")
                pieces = plates[pi]
                f = _tm.util.concatenate([g for _n, g in pieces])
                bb = f.bounds
                off = [cx - (bb[0][0] + bb[1][0]) / 2,
                       -(bb[0][1] + bb[1][1]) / 2, -bb[0][2]]
                for nom, g in pieces:
                    _ajouter_corps(g, off, nom)

        try:
            if premiere and not garder_camera:
                self._plotter.reset_camera()
            elif _cam_gardee is not None:
                self._plotter.camera_position = _cam_gardee   # garder la vue
        except Exception:
            pass
        self.suspendre_rendu(False)   # rendu unique de l'aperçu final

    def vider_pour_carte(self) -> None:
        """Vide IMMÉDIATEMENT le viewer à l'ouverture de l'éditeur de carte :
        l'aperçu de la carte est asynchrone (_planifier_apercu), donc sans ça
        l'ANCIENNE pièce resterait affichée à gauche pendant qu'on édite la
        carte à droite → incohérent. On retire tout de suite l'objet en attendant
        le 1er aperçu coloré. Ne touche pas à _view_mode : afficher_carte doit
        rester en « première » ouverture pour se réinitialiser proprement."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        try:
            self._cancel_mesh_prep()
        except Exception:
            pass
        self.stop_auto_rotate()
        self._mesh = None
        self._face_colors = None
        self._plate_groups_draw = None   # ne pas hériter du multi-plateaux précédent
        self._multi_pick_mode = False
        try:
            self._plotter.clear()
            self._setup_lights()
            self._plotter.render()
        except Exception:
            pass

    def quitter_mode_carte(self) -> None:
        """À appeler quand on ferme l'éditeur de carte : réarme un affichage
        normal au prochain chargement de pièce et coupe le drag d'éléments."""
        self._view_mode = "normal"
        self._carte_actors = {}
        self._carte_drag_mode = False
        if getattr(self, "_carte_sel", None):
            self._surligner_carte(self._carte_sel, False)   # retire la silhouette
        self._carte_sel = None

    # ── Sélection + déplacement des éléments à la souris ─────────────────────
    def _surligner_carte(self, nom: str, on: bool) -> None:
        """Surbrillance = SILHOUETTE (contour extérieur uniquement) en cyan. Pas
        d'arêtes sur l'élément lui-même (SetEdgeVisibility traçait toutes les
        arêtes des triangles -> traits partout sur les lettres)."""
        # retire la silhouette précédente
        sil = getattr(self, "_carte_sil", None)
        if sil is not None:
            try:
                self._plotter.remove_actor(sil, reset_camera=False)
            except Exception:
                pass
            self._carte_sil = None
        if not on:
            return
        pvm = getattr(self, "_carte_pv", {}).get(nom)
        if pvm is None:
            return
        try:
            self._carte_sil = self._plotter.add_silhouette(
                pvm, color=(0.13, 0.83, 0.93), line_width=4, feature_angle=False)
            # aligne la silhouette sur la position COURANTE de l'élément (utile
            # si l'élément a été déplacé via AddPosition pendant un drag)
            a = getattr(self, "_carte_vtk", {}).get(nom)
            if a is not None and self._carte_sil is not None:
                self._carte_sil.SetPosition(a.GetPosition())
        except Exception:
            pass

    def _install_carte_drag(self) -> None:
        """Active le déplacement des éléments à la souris. On passe par les
        événements Qt (press/move/RELEASE) via l'eventFilter du plotter : dans
        pyvistaqt, le release VTK n'était pas fiable -> l'élément restait
        « collé » à la souris. Qt, lui, délivre toujours le release."""
        self._carte_drag_st = {"drag": False, "nom": None, "idx": -1,
                              "last": (0.0, 0.0), "tot": [0.0, 0.0]}
        self._carte_drag_mode = True
        try:
            self._plotter.installEventFilter(self)   # (idempotent dans Qt)
            from PySide6.QtCore import Qt as _Qt
            self._plotter.setFocusPolicy(_Qt.StrongFocus)   # reçoit la touche Suppr
        except Exception:
            pass

    def _carte_disp(self, pos):
        """QPoint(F) de widget -> coords d'affichage VTK (origine bas-gauche,
        pixels device)."""
        try:
            dpr = float(self._plotter.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        x = pos.x() * dpr
        y = pos.y() * dpr
        h = self._plotter.ren_win.GetSize()[1]
        return x, h - y

    def _carte_world_xy(self, pos, zp=0.0):
        """Position souris -> point monde (x, y) dans le plan z=zp (intersection
        rayon/plan : correct quelle que soit la caméra)."""
        ren = self._plotter.renderer
        x, y = self._carte_disp(pos)
        ren.SetDisplayPoint(x, y, 0.0); ren.DisplayToWorld()
        w0 = ren.GetWorldPoint()
        ren.SetDisplayPoint(x, y, 1.0); ren.DisplayToWorld()
        w1 = ren.GetWorldPoint()
        p0 = np.array(w0[:3]) / (w0[3] or 1.0)
        p1 = np.array(w1[:3]) / (w1[3] or 1.0)
        d = p1 - p0
        if abs(d[2]) < 1e-9:
            return float(p0[0]), float(p0[1])
        t = (zp - p0[2]) / d[2]
        p = p0 + t * d
        return float(p[0]), float(p[1])

    def _carte_pick(self, pos):
        """Nom de l'acteur d'élément sous la souris (ou None)."""
        try:
            from vtkmodules.vtkRenderingCore import vtkPropPicker
        except Exception:
            return None
        x, y = self._carte_disp(pos)
        picker = vtkPropPicker()
        picker.Pick(x, y, 0, self._plotter.renderer)
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

    def _pick_object_id(self, pos):
        """object_id de l'objet multi sous la souris (ou None) — par POSITION.

        On NE peut PAS picker par acteur : après l'analyse, colorize_overhangs
        fusionne tout en un seul acteur « main_mesh » (les acteurs obj_* n'existent
        plus). On projette donc le clic sur le plan z=0 et on cherche l'objet dont
        l'emprise XY (viewer-space, cf. _object_viewer_bounds) contient le point."""
        bounds = getattr(self, "_object_viewer_bounds", None)
        ids = getattr(self, "_object_ids_ordered", None)
        if not bounds or not ids or len(bounds) != len(ids):
            return None
        # Point 3D RÉELLEMENT touché par le rayon (mesh OU plateau) — PAS une
        # projection sur z=0 : sinon cliquer sur le HAUT d'un objet (en hauteur)
        # tombe à côté de son emprise par parallaxe (vécu : il fallait viser le
        # plateau). GetPickPosition donne le vrai (x, y) de l'impact.
        try:
            from vtkmodules.vtkRenderingCore import vtkPropPicker
            x, y = self._carte_disp(pos)
            picker = vtkPropPicker()
            if not picker.Pick(x, y, 0, self._plotter.renderer):
                return None
            _p = picker.GetPickPosition()
            wx, wy = float(_p[0]), float(_p[1])
        except Exception:
            return None
        best, best_d = None, None
        for oid, b in zip(ids, bounds):
            if b["xmin"] <= wx <= b["xmax"] and b["ymin"] <= wy <= b["ymax"]:
                cx = (b["xmin"] + b["xmax"]) / 2
                cy = (b["ymin"] + b["ymax"]) / 2
                d = (wx - cx) ** 2 + (wy - cy) ** 2
                if best_d is None or d < best_d:   # chevauchement → le plus centré
                    best, best_d = oid, d
        return best

    def _carte_mouse(self, event, t) -> bool | None:
        """Gère press/move/release pour le drag d'éléments. Renvoie True si
        l'événement est CONSOMMÉ (drag en cours -> pas d'orbite caméra), sinon
        None (laisser le viewer tourner normalement)."""
        from PySide6.QtCore import QEvent, Qt as _Qt
        st = self._carte_drag_st
        pos = event.position() if hasattr(event, "position") else event.pos()
        if t == QEvent.MouseButtonPress and event.button() == _Qt.LeftButton:
            nom = self._carte_pick(pos)
            anc = getattr(self, "_carte_sel", None)
            if anc and anc != nom:
                self._surligner_carte(anc, False)
                self._carte_sel = None
            if nom and nom in getattr(self, "_carte_actors", {}):
                self._carte_sel = nom
                self._surligner_carte(nom, True)
                idx = self._carte_actors[nom]
                st.update(drag=True, nom=nom, idx=idx,
                          last=self._carte_world_xy(pos), tot=[0.0, 0.0])
                try:
                    self.element_selectionne.emit(idx)   # encadre la section
                    self._plotter.setFocus()             # pour recevoir Suppr
                except Exception:
                    pass
                self._plotter.render()
                return True
            # rien de sélectionné (clic sur le socle / le vide) → désélection
            try:
                self.element_selectionne.emit(-1)
            except Exception:
                pass
            return None
        if t == QEvent.MouseMove and st["drag"]:
            wx, wy = self._carte_world_xy(pos)
            dx, dy = wx - st["last"][0], wy - st["last"][1]
            a = getattr(self, "_carte_vtk", {}).get(st["nom"])
            if a is not None:
                a.AddPosition(dx, dy, 0.0)
                sil = getattr(self, "_carte_sil", None)
                if sil is not None:
                    sil.AddPosition(dx, dy, 0.0)     # le contour suit l'élément
                st["tot"][0] += dx; st["tot"][1] += dy
                st["last"] = (wx, wy)
                self._plotter.render()
            return True
        if t == QEvent.MouseButtonRelease and st["drag"]:
            st["drag"] = False
            if abs(st["tot"][0]) > 0.05 or abs(st["tot"][1]) > 0.05:
                try:
                    self.element_deplace.emit(st["idx"], st["tot"][0], st["tot"][1])
                except Exception:
                    pass
            return True
        return None

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
        # Vue surplombs → la légende thermomap ne doit pas rester affichée.
        if hasattr(self, "_frag_legend_label"):
            self._frag_legend_label.hide()
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
            cmap=_overhang_cmap(_T.is_dark()),
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

    def colorize_fragility(self, mesh, face_severity: np.ndarray,
                            _keep_camera: bool = False) -> None:
        """Thermomap de fragilité PAR OBJET : chaque pièce est teintée selon SA
        fragilité (vert = solide → rouge = fragile). Plus précis que des barres
        flottantes et sans encombrement. face_severity : sévérité 0→1 par face."""
        if not HAS_PYVISTA or self._plotter is None:
            return
        # GARDE anti-flash : le thermomap ne colore JAMAIS les pièces tant que la
        # case « Fragilité » n'est pas EXPLICITEMENT cochée. Neutralise tout appel
        # parasite au chargement (flash orange 1 s, vécu), quelle qu'en soit la
        # source. Le toggle légitime coche la case AVANT d'appeler → passe.
        if hasattr(self, "_frag_checkbox") and not self._frag_checkbox.isChecked():
            logger.debug("colorize_fragility ignoré (case Fragilité décochée)")
            return

        self._view_mode = "fragility"
        # Mémorisé pour recréer la vue après un changement de thème (refresh_theme
        # fait plotter.clear()). Aligné sur le mesh combiné courant.
        fsev = np.asarray(face_severity, dtype=np.float32)
        nf = len(mesh.faces)
        if len(fsev) != nf:
            if len(fsev) > nf:
                fsev = fsev[:nf]
            else:
                fsev = np.concatenate([fsev, np.zeros(nf - len(fsev), dtype=np.float32)])
        self._fragility_severity = fsev

        self._plotter.clear()
        self._setup_lights()
        self._add_build_plate(mesh)
        pv_mesh = self._place_on_plate(self._trimesh_to_pyvista(mesh))
        pv_mesh.cell_data["fragility"] = fsev
        self._plotter.add_mesh(
            pv_mesh,
            scalars="fragility",
            cmap=_frag_cmap(),
            clim=[0.0, 1.0],
            show_scalar_bar=False,
            smooth_shading=False,
            ambient=0.82, diffuse=0.18, specular=0.0,
            name="main_mesh",
        )
        # Légende (QLabel HTML 3 niveaux colorés) — affichée seulement si la case
        # « Fragilité » est cochée (c.-à-d. quand la thermomap est réellement active).
        self._update_frag_legend_visibility()

        if not _keep_camera:
            try:
                _elev = math.radians(25); _far = 1e6
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
            # (ancien profil « balanced » supprimé : il était brillant + SSAO
            # kernel 128 — un rendu PLUS coûteux que « full » ! balanced/auto
            # retombent sur « full » via le .get() ci-dessous)
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
