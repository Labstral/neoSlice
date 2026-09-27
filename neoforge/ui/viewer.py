# -*- coding: utf-8 -*-
"""Vue 3D de neoForge : le plateau, la pièce, et les poignées de manipulation.

Trois modes au choix, dans le coin de la vue : taille, déplacement, rotation.

Règle de fluidité : pendant un geste, RIEN n'est recalculé. L'aperçu de la
forme et ses poignées sont construits une fois, dans le repère propre de la
forme, puis simplement replacés par une transformation, ce que la carte
graphique fait instantanément. La pièce complète n'est recalculée qu'au
relâchement du bouton.

Deux autres règles venues d'essais ratés : les poignées se dessinent en PIXELS
(des sphères en millimètres grossissent avec la pièce), et un geste ne survit
jamais au relâchement (vérifié à chaque mouvement, pas seulement sur
l'événement de relâchement, qu'une erreur pourrait faire manquer)."""
from __future__ import annotations

import time

import numpy as np
import pyvista as pv
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)
from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkCoordinate

from neoforge.ui.gizmo import MODES, VERT_COTE, Gizmo, transformation
from neoforge.ui import style as S
from neoforge.ui.style import respirer as _respirer
from neoforge.ui.textes import T
from ui.styles.theme import FONT_MAIN, MANAGER as _T

COULEUR_PIECE = {"dark": "#9AA7BE", "light": "#7C8AA3"}
VERT, ROUGE = "#3ED88E", "#F56B6B"
RAYON_VISEE = 11             # pixels autour du curseur pour attraper une poignée
RAYON_ARETE = 12             # pixels autour du curseur pour désigner une arête
ECART_ETIQUETTE = 22         # pixels entre un chiffre de cote et son trait
SEUIL_GESTE = 4              # pixels : en dessous, c'est un clic, pas un glissement
TAILLE_CUBE = 88             # pixels : le cube d'orientation, en haut à droite


def _faces_vtk(F: np.ndarray) -> np.ndarray:
    trois = np.full((len(F), 1), 3, dtype=np.int64)
    return np.hstack([trois, F]).ravel()



def position_reculee(position, foyer, facteur: float):
    """Nouvelle position d'une caméra qu'on éloigne de `facteur` de son point de
    visée, l'objectif restant le même.

    ⚠️ C'est LA correction du défaut « la perspective a changé subitement, comme
    si tout était très étiré » : `camera.zoom(f)` ne recule rien en perspective,
    il divise l'ANGLE DE VUE par f. Mesuré : quatre reculs de facteur 2 faisaient
    passer l'objectif de 30° à 60°, 120° puis au plafond de VTK, 179°, sans que
    la caméra bouge d'un millimètre. On déplace donc la caméra pour de bon.
    """
    foyer = np.array(foyer, float)
    vers = np.array(position, float) - foyer
    if float(np.linalg.norm(vers)) < 1e-6:
        return tuple(np.array(position, float))
    return tuple(foyer + vers * float(facteur))


class Viewer(QWidget):
    arete_cliquee = Signal(int)               # index dans la liste d'arêtes affichée
    piece_cliquee = Signal(object)            # point (x, y, z) touché sur la pièce
    fond_clique = Signal()                    # clic dans le vide : on désélectionne
    taille_modifiee = Signal(int, float, int)  # axe, variation mm, côté tiré (+1/-1)
    deplacement = Signal(int, float)          # axe, variation en mm
    rotation = Signal(int, float)             # axe, variation en degrés
    geste_termine = Signal()
    mode_change = Signal(str)
    suppression_demandee = Signal()           # touche Suppr dans la vue 3D
    plan_deplace = Signal(float)              # le plan de coupe est tiré (en mm)
    regle_demandee = Signal(bool)             # la règle est allumée ou éteinte

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        _respirer()                       # l'écran de chargement continue d'avancer
        self._plotter = QtInteractor(self)
        # Focale de reference de la vue. Tout le code cadre en DEPLACANT la
        # camera ; l'angle, lui, ne bouge jamais (voir _reculer_la_camera).
        self._angle_vue = 30.0
        self._plotter.camera.view_angle = self._angle_vue
        _respirer()
        lay.addWidget(self._plotter.interactor)
        # La vue 3D garde le clavier : sans ce filtre, la touche Suppr n'arrive
        # jamais jusqu'à la fenêtre (demande d'Emmanuel).
        self._plotter.interactor.installEventFilter(self)
        self._museler_les_touches_vtk()
        try:
            # Transparence propre : sans elle, la surbrillance verte se mélange
            # au petit bonheur avec la pièce et paraît « glitchée » (retour
            # d'Emmanuel). Certains pilotes logiciels refusent : on s'en passe.
            self._plotter.enable_depth_peeling(8)
        except Exception:
            pass

        self._acteur_piece = None
        self._acteur_fantome = None
        self._acteur_plan = None          # le plan de coupe, quand on le montre
        self._acteur_bord_plan = None
        self._clip_vue = None             # plan qui masque ce qui est devant l'objet
        self._plan: dict | None = None    # axe, position et centre du plan montré
        self._compagnons: list = []       # les autres pièces qui bougent avec elle
        self._acteur_aretes = None
        # ── La règle : mesurer d'un point A à un point B ───────────────────
        self._mode_regle = False
        self._regle_lignes = []          # polylignes des arêtes, en millimètres
        self._regle_a = None             # premier point posé
        self._regle_b = None             # second point, une fois la mesure figée
        self._regle_vise = None          # ce que la souris accroche en ce moment
        self._acteurs_regle = []
        self._acteur_choix = None
        self._acteur_survol = None
        self._acteur_etiquettes = None
        self._poly_etiquettes = None
        self._polylignes: list[np.ndarray] = []
        self._points_aretes = np.zeros((0, 3))
        self._index_aretes = np.zeros(0, dtype=np.int32)
        self._choisies: set[int] = set()
        self._survolee: int | None = None
        self._aretes_visibles = False
        self._mode_choix = False
        self._premier_rendu = True
        self._geste: dict | None = None
        self._dernier_rendu = 0.0
        self._gel = 0                     # > 0 : on prépare une image, on n'affiche pas

        self._calque = self._creer_calque()
        self._gizmo = Gizmo(self._plotter, self._calque)
        self._forme = None                # état courant : pos, rot, dim de base
        self._pos = np.zeros(3)
        self._rot = np.zeros(3)
        self._echelle = np.ones(3)
        self._dim_base = np.ones(3)
        self._cotes_locales: list[dict] = []
        self._centre_local = None         # centre de la matière restant après coupe
        self._demi_local = None           # et sa demi étendue

        self._barre_modes()
        self._plateau(256.0)
        self._cube_orientation()
        self.refresh_theme()
        # Observateurs PRIORITAIRES (priorité 10) : ils passent AVANT le style de
        # caméra de VTK, et pendant un geste on lui coupe l'événement. Sinon la
        # caméra démarre une rotation qu'elle ne termine jamais (elle ne reçoit
        # pas le relâchement) et elle continue de suivre la souris ensuite.
        brut = self._plotter.iren.interactor
        self._tag_appui = brut.AddObserver("LeftButtonPressEvent", self._sur_appui, 10.0)
        self._tag_bouge = brut.AddObserver("MouseMoveEvent", self._sur_deplacement, 10.0)
        self._tag_relache = brut.AddObserver("LeftButtonReleaseEvent",
                                             self._sur_relachement, 10.0)
        # La caméra a bougé : les chiffres se replacent (leur écart au trait se
        # mesure à l'écran, il dépend donc de l'angle de vue).
        brut.AddObserver("EndInteractionEvent", self._camera_bougee)
        # Tourner la vue à la main fait sortir du profil : ce qui était masqué
        # revient, sinon la scène reste amputée sans qu'on sache pourquoi.
        brut.AddObserver("EndInteractionEvent", self._camera_manuelle)

    # ── Calque de dessus ───────────────────────────────────────────────────
    def _creer_calque(self):
        """Un second calque de rendu, dessiné APRÈS la scène et partageant sa
        caméra. Les cotes, leurs poignées et leurs chiffres y vivent : ils
        restent entiers même quand une pièce les traverse (demande d'Emmanuel,
        une cote coupée en deux par la matière ne se lit plus)."""
        try:
            from vtkmodules.vtkRenderingCore import vtkRenderer
            calque = vtkRenderer()
            calque.SetLayer(1)
            calque.InteractiveOff()
            calque.SetActiveCamera(self._plotter.renderer.GetActiveCamera())
            fenetre = self._plotter.ren_win
            fenetre.SetNumberOfLayers(2)
            fenetre.AddRenderer(calque)
            return calque
        except Exception:
            return None                    # sans calque, on retombe sur l'ancien rendu

    def _vers_calque(self, acteur):
        if acteur is None or self._calque is None:
            return acteur
        try:
            self._plotter.renderer.remove_actor(acteur, reset_camera=False, render=False)
            self._calque.AddActor(acteur)
        except Exception:
            pass
        return acteur

    def _du_calque(self, acteur):
        if acteur is None:
            return
        try:
            self._calque.RemoveActor(acteur)
        except Exception:
            pass
        try:
            self._plotter.remove_actor(acteur, reset_camera=False, render=False)
        except Exception:
            pass

    def _museler_les_touches_vtk(self):
        """Coupe les raccourcis clavier que VTK s'attribue tout seul.

        Retour d'Emmanuel : « quand j'appuie sur S la grille a disparu ».
        Ce n'était pas un défaut d'affichage : le style d'interaction de VTK
        écoute CharEvent et répond de lui même à une dizaine de lettres. `s`
        repasse TOUS les acteurs en surface pleine, et comme la grille du
        plateau est dessinée en fil de fer, elle disparaît. Mesuré au pilote :
        représentation « fil de fer » avant, « surface » après l'appui, `w` la
        rétablissant.

        Les autres sont pires : `e` et `q` demandent la SORTIE de l'application,
        `r` recadre la caméra sans prévenir, `f` y projette la vue, `p` déclenche
        une désignation, `3` bascule en stéréo. Aucune n'est documentée nulle
        part dans neoForge, et une pièce en cours ne doit pas dépendre d'une
        lettre tapée par mégarde. On retire donc l'écoute du clavier côté VTK :
        tout ce dont neoForge a besoin passe par Qt (Suppr dans eventFilter,
        Ctrl+Z et Ctrl+Y sur la fenêtre), qui reste intact.
        """
        try:
            self._plotter.iren.clear_key_event_callbacks()
        except Exception:
            pass
        try:
            brut = self._plotter.iren.interactor
            brut.RemoveObservers("CharEvent")
            brut.RemoveObservers("KeyPressEvent")
        except Exception:
            pass

    def eventFilter(self, objet, evenement):
        """Ce que VTK ne nous laisse pas voir, Qt nous le donne.

        Le clavier d'abord : la vue 3D le garde pour elle, et sans ce filtre la
        touche Suppr n'arrive jamais à la fenêtre (demande d'Emmanuel).

        Le relâchement du bouton ensuite, et c'est le point important. Dès que
        l'appui est laissé à VTK pour qu'il puisse tourner la caméra, son style
        d'interaction appelle GrabFocus : VTK ne délivre alors PLUS les
        événements qu'à son propre gestionnaire, et notre observateur de
        relâchement n'est jamais appelé, quelle que soit sa priorité. C'est ce
        qui empêchait un clic dans le vide de désélectionner et un clic sur une
        arête d'être pris en compte. Qt, lui, nous donne toujours l'événement."""
        try:
            genre = evenement.type()
            if (genre == QEvent.Type.KeyPress
                    and evenement.key() in (Qt.Key_Delete, Qt.Key_Backspace)):
                self.suppression_demandee.emit()
                return True
            if (genre == QEvent.Type.MouseButtonRelease
                    and evenement.button() == Qt.MouseButton.LeftButton
                    and self._geste is not None):
                self._sur_relachement(position=self._en_pixels(evenement))
        except Exception:
            pass
        return super().eventFilter(objet, evenement)

    def _en_pixels(self, evenement) -> tuple[float, float]:
        """Position d'un événement Qt dans le repère de VTK : origine en bas à
        gauche, et en pixels réels (l'écran peut être agrandi par le système)."""
        point = evenement.position()
        largeur, hauteur = self._plotter.ren_win.GetSize()
        echelle = hauteur / max(1, self._plotter.interactor.height())
        return (point.x() * echelle, hauteur - point.y() * echelle)

    # ── Cube d'orientation ─────────────────────────────────────────────────
    def _cube_orientation(self):
        """Cube d'orientation CLIQUABLE en haut à droite : un clic sur un axe met
        la vue de dessus, de face ou de profil, comme dans tous les logiciels 3D
        (demande d'Emmanuel). Réglages repris tels quels du viewer de neoSlice
        pour que les deux fenêtres se ressemblent."""
        self._orient_widget = None
        self._orient_rep = None
        try:
            w = self._plotter.add_camera_orientation_widget()
            rep = w.GetRepresentation()
            rep.SetXAxisColor(0.90, 0.46, 0.46)     # rouge pâle
            rep.SetYAxisColor(0.56, 0.83, 0.44)     # vert pomme pâle
            rep.SetZAxisColor(0.42, 0.55, 0.95)     # bleu légèrement violet
            try:
                rep.SetSize(TAILLE_CUBE, TAILLE_CUBE)
                rep.SetHandleSize(0.008)
                rep.SetTotalLength(0.9)
                rep.SetContainerVisibility(0)       # pas de disque de fond
            except Exception:
                pass
            self._orient_widget, self._orient_rep = w, rep
            self._etiquettes_orientation()      # à la création : VTK fige la texture
            self._garder_distance()
        except Exception:
            pass                                    # sans cube, la vue marche quand même

    def _garder_distance(self):
        """Un clic sur un axe réoriente la caméra mais GARDE sa distance : sinon
        VTK anime un recul pour recadrer, puis revient, ce qui saute à l'œil."""
        w = self._orient_widget
        if w is None:
            return
        for methode, valeur in (("SetAnimate", False), ("SetAnimatorTotalFrames", 1)):
            try:
                getattr(w, methode)(valeur)
            except Exception:
                pass

        def _noter(*_a):
            try:
                camera = self._plotter.camera
                self._distance_cube = float(np.linalg.norm(
                    np.array(camera.position) - np.array(camera.focal_point)))
            except Exception:
                pass

        def _remettre(*_a):
            d = getattr(self, "_distance_cube", None)
            if not d:
                return
            try:
                camera = self._plotter.camera
                foyer = np.array(camera.focal_point)
                vers = np.array(camera.position) - foyer
                n = float(np.linalg.norm(vers))
                if n > 1e-6:
                    camera.position = tuple(foyer + vers / n * d)
                    self._plotter.renderer.ResetCameraClippingRange()
                    self._rendre(force=True)
            except Exception:
                pass

        try:
            w.AddObserver("StartInteractionEvent", _noter)
            w.AddObserver("InteractionEvent", _remettre)
            w.AddObserver("EndInteractionEvent", _remettre)
            # Une fois la caméra posée sur l'axe : vraie vue de profil.
            w.AddObserver("EndInteractionEvent", self._vue_axiale)
        except Exception:
            pass

    def _etiquettes_orientation(self):
        """Les lettres X/Y/Z du cube, en encre SOMBRE dans les deux thèmes.

        Deux raisons, l'une mesurée, l'autre technique. Les boules sont pâles
        (rouge, vert, bleu clairs) : du texte sombre s'y détache bien mieux que
        du blanc, en thème clair comme en sombre (vérifié à la loupe sur les
        deux captures). Et VTK ne reconstruit pas la texture des étiquettes
        après coup : une couleur changée au moment de basculer de thème ne
        s'appliquerait de toute façon jamais, seule celle posée à la création
        compte. Une teinte unique est donc à la fois plus lisible et honnête."""
        rep = getattr(self, "_orient_rep", None)
        if rep is None:
            return
        try:
            for propriete in (rep.GetXPlusLabelProperty, rep.GetXMinusLabelProperty,
                              rep.GetYPlusLabelProperty, rep.GetYMinusLabelProperty,
                              rep.GetZPlusLabelProperty, rep.GetZMinusLabelProperty):
                propriete().SetColor(0.12, 0.12, 0.16)
        except Exception:
            pass

    def _sur_le_cube(self, position) -> bool:
        """Le clic tombe-t-il sur le cube d'orientation ? Sans cette garde, il
        passerait pour un clic dans le vide et désélectionnerait tout."""
        if getattr(self, "_orient_widget", None) is None:
            return False
        try:
            largeur, hauteur = self._plotter.ren_win.GetSize()
        except Exception:
            return False
        cote = TAILLE_CUBE + 24                     # la zone du cube, avec marge
        return position[0] >= largeur - cote and position[1] >= hauteur - cote

    # ── Choix du mode, dans la vue ─────────────────────────────────────────
    def _barre_modes(self):
        self._barre = QWidget(self)
        ligne = QHBoxLayout(self._barre)
        ligne.setContentsMargins(6, 5, 6, 5)
        ligne.setSpacing(4)
        self._boutons_mode = {}
        for mode, cle in (("taille", "mode_taille"), ("deplacer", "mode_deplacer"),
                          ("tourner", "mode_tourner")):
            b = QPushButton(T(cle))
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            b.setFixedHeight(26)
            b.clicked.connect(lambda _c=False, m=mode: self.definir_mode(m))
            ligne.addWidget(b)
            self._boutons_mode[mode] = b
        # La règle n'est pas une poignée de plus : c'est un autre usage de la
        # vue. Son bouton vit dans la même barre mais s'allume tout seul.
        self._btn_regle = QPushButton(T("mode_mesurer"))
        self._btn_regle.setCheckable(True)
        self._btn_regle.setCursor(Qt.PointingHandCursor)
        self._btn_regle.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._btn_regle.setFixedHeight(26)
        self._btn_regle.clicked.connect(
            lambda coche: self.regle_demandee.emit(bool(coche)))
        ligne.addSpacing(10)
        ligne.addWidget(self._btn_regle)
        self._boutons_mode["taille"].setChecked(True)
        self._barre.move(12, 12)
        self._barre.adjustSize()
        self._barre.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._barre.move(12, 12)
        self._barre.raise_()

    def definir_mode(self, mode: str):
        if mode not in MODES:
            return
        if self._mode_regle:
            self.regle_demandee.emit(False)   # choisir une poignée sort de la règle
        self._gizmo.mode = mode
        for nom, b in self._boutons_mode.items():
            b.setChecked(nom == mode)
        self._rebatir_gizmo()
        self.mode_change.emit(mode)

    def mode(self) -> str:
        return self._gizmo.mode

    # ── Décor ──────────────────────────────────────────────────────────────
    def _plateau(self, cote: float):
        grille = pv.Plane(center=(0, 0, 0), direction=(0, 0, 1),
                          i_size=cote, j_size=cote,
                          i_resolution=int(cote // 16), j_resolution=int(cote // 16))
        self._acteur_grille = self._plotter.add_mesh(
            grille, style="wireframe", line_width=1, opacity=0.35, pickable=False,
            reset_camera=False, render=False)
        self._acteur_axe_x = self._plotter.add_mesh(
            pv.MultipleLines(np.array([[0, 0, 0], [24, 0, 0]], float)),
            color="#C0554F", line_width=2, pickable=False, reset_camera=False,
            render=False)
        self._acteur_axe_y = self._plotter.add_mesh(
            pv.MultipleLines(np.array([[0, 0, 0], [0, 24, 0]], float)),
            color="#4F8CC0", line_width=2, pickable=False, reset_camera=False,
            render=False)
        self._cote_plateau = cote
        _respirer()
        self._plotter.view_isometric()
        # Cadrage un peu plus serré, en RAPPROCHANT la caméra et non en
        # rétrécissant l'objectif : l'angle de vue reste la référence stable de
        # toute la vue (voir _reculer_la_camera).
        self._reculer_la_camera(1.0 / 1.2)
        _respirer()

    def taille_plateau(self, x: float, y: float):
        cote = max(60.0, float(max(x, y)))
        if abs(cote - self._cote_plateau) < 1.0:
            return
        for nom in ("_acteur_grille", "_acteur_axe_x", "_acteur_axe_y"):
            a = getattr(self, nom, None)
            if a is not None:
                self._plotter.remove_actor(a)
        self._plateau(cote)
        self.refresh_theme()

    def refresh_theme(self):
        pal = _T.palette()
        self._plotter.set_background(pal["VIEWER_BG"], top=pal["VIEWER_BG_TOP"])
        if getattr(self, "_acteur_grille", None) is not None:
            self._acteur_grille.GetProperty().SetColor(
                *pv.Color(pal["TEXT_LABEL"]).float_rgb)
        # Le plan de coupe suit le thème comme le reste du décor : construit en
        # sombre, il resterait sinon dans les teintes du sombre en clair.
        if getattr(self, "_acteur_plan", None) is not None:
            self._acteur_plan.GetProperty().SetColor(*pv.Color(pal["ACCENT"]).float_rgb)
        if getattr(self, "_acteur_bord_plan", None) is not None:
            self._acteur_bord_plan.GetProperty().SetColor(
                *pv.Color(pal["ACCENT_BRIGHT"]).float_rgb)
        if self._acteur_piece is not None:
            self._acteur_piece.GetProperty().SetColor(
                *pv.Color(COULEUR_PIECE[_T.name()]).float_rgb)
        from neoforge.ui import style as S
        # Fond PLEIN, pris dans la palette : en transparent, on voyait le fond
        # par défaut de Qt, resté sombre en thème clair (retour d'Emmanuel).
        # Bords DROITS : un coin arrondi laisse le pixel du coin non peint, et
        # ce trou se voyait comme une encoche noire par-dessus la vue 3D (retour
        # d'Emmanuel). Un cadre net s'accorde d'ailleurs au reste de neoSlice.
        self._barre.setStyleSheet(
            f"QWidget {{ background: {pal['BG_PANEL']}; border: 1px solid "
            f"{pal['INACTIVE']}; border-radius: 0px; }}")
        # Le bouton Mesurer est habillé AVEC les trois autres : oublié ici, il
        # gardait la palette par défaut de Qt, donc une graisse qui ne
        # ressemblait à rien et aucune surbrillance quand on l'enclenche
        # (retour d'Emmanuel). C'est le piège récurrent du projet.
        for b in (*self._boutons_mode.values(), self._btn_regle):
            b.setStyleSheet(S.qss_bouton())
        self._rendre(force=True)

    # ── Pièce et fantôme ───────────────────────────────────────────────────
    def afficher_piece(self, V: np.ndarray, F: np.ndarray):
        garder = not self._premier_rendu
        camera = self._plotter.camera_position if garder else None
        if self._acteur_piece is not None:
            # render=False : PyVista redessine par défaut en retirant un acteur,
            # et cette image là montre la scène à moitié refaite (retour
            # d'Emmanuel : l'objet « se décale un court instant »).
            self._plotter.remove_actor(self._acteur_piece, render=False)
            self._acteur_piece = None
        if len(F):
            maillage = pv.PolyData(np.asarray(V, float), _faces_vtk(np.asarray(F)))
            # Pas de `split_sharp_edges` : le maillage d'affichage garde déjà une
            # face séparée de l'autre, donc l'ombrage lisse ne déborde jamais
            # d'une face. Le découpage par angle, lui, ratait les raccords peu
            # inclinés (bord d'une cuvette) et laissait des stries.
            self._acteur_piece = self._plotter.add_mesh(
                maillage, color=COULEUR_PIECE[_T.name()], smooth_shading=True,
                specular=0.25, specular_power=18,
                reset_camera=False, render=False)
        if camera is not None:
            self._plotter.camera_position = camera
        elif len(F):
            self._plotter.reset_camera()
            self._plotter.view_isometric()
        self._premier_rendu = False
        # L'acteur vient d'être refait, donc il a perdu le plan qui masque ce qui
        # se trouve devant l'objet visé : on le repose, sinon la vue de profil
        # se rouvrirait au premier recalcul.
        plan = getattr(self, "_clip_vue", None)
        if plan is not None and self._acteur_piece is not None:
            try:
                self._acteur_piece.GetMapper().AddClippingPlane(plan)
            except Exception:
                pass
        self._rendre(force=True)

    def preparer_manipulation(self, forme, maillage_local, cotes_locales, creux: bool,
                              compagnons=None, centre_local=None, demi_local=None):
        """Prépare l'aperçu de la forme sélectionnée : son maillage est construit
        UNE fois, dans son repère propre. Ensuite, un geste ne fait que le
        replacer.

        `compagnons` : les AUTRES pièces que le geste va emmener (le parent, les
        enfants). Sans elles, on ne voyait bouger que la pièce tenue et
        l'assemblage semblait se disloquer pendant le glissement (retour
        d'Emmanuel)."""
        self._forme = forme
        self._vider_compagnons()
        if forme is None:
            self._pos, self._rot = np.zeros(3), np.zeros(3)
            self._dim_base = np.ones(3)
            self._echelle = np.ones(3)
            self._centre_local = self._demi_local = None
            self._fantome(None, None, False)
            self._gizmo.cacher()
            self._maj_etiquettes()
            self._rendre(force=True)
            return
        self._pos = np.array(forme.pos, float)
        self._rot = np.array(forme.rot, float)
        self._dim_base = np.array(forme.dim, float)
        self._echelle = np.ones(3)
        self._cotes_locales = cotes_locales
        # Retenus : changer de mode reconstruit les poignées par un AUTRE chemin
        # (`_rebatir_gizmo`), qui doit les retrouver.
        self._centre_local, self._demi_local = centre_local, demi_local
        V, F = maillage_local
        self._fantome(V, F, creux)
        self._construire_compagnons(compagnons or [])
        # `centre_local` et `demi_local` décrivent la matière qui RESTE après les
        # découpes : les poignées se posent dessus, et non plus autour de la
        # forme d'origine (retour d'Emmanuel sur le point d'origine).
        self._gizmo.montrer(forme, cotes_locales, centre_local, demi_local)
        self._placer()

    def _vider_compagnons(self):
        for acteur in self._compagnons:
            try:
                self._plotter.remove_actor(acteur, render=False)
            except Exception:
                pass
        self._compagnons = []

    def _construire_compagnons(self, liste):
        """Un aperçu par pièce entraînée, construit dans SON repère propre puis
        simplement replacé à chaque pas, comme l'aperçu principal."""
        for c in liste:
            V, F = c.get("maillage", (None, None))
            if V is None or F is None or not len(F):
                continue
            maillage = pv.PolyData(np.asarray(V, float), _faces_vtk(np.asarray(F)))
            acteur = self._plotter.add_mesh(
                maillage, color=ROUGE if c.get("creux") else VERT, opacity=0.3,
                smooth_shading=True, backface_culling=True, pickable=False,
                reset_camera=False, render=False)
            try:
                m = acteur.GetMapper()
                m.SetResolveCoincidentTopologyToPolygonOffset()
                m.SetRelativeCoincidentTopologyPolygonOffsetParameters(-8.0, -8.0)
            except Exception:
                pass
            acteur.SetUserTransform(transformation(c["pos"], c["rot"]))
            self._compagnons.append(acteur)

    def placer_compagnons(self, poses):
        """Instantané : une transformation par pièce entraînée."""
        for acteur, (pos, rot) in zip(self._compagnons, poses):
            acteur.SetUserTransform(transformation(pos, rot))

    def _fantome(self, V, F, creux: bool):
        if self._acteur_fantome is not None:
            self._plotter.remove_actor(self._acteur_fantome, render=False)
            self._acteur_fantome = None
        if V is None or F is None or not len(F):
            return
        maillage = pv.PolyData(np.asarray(V, float), _faces_vtk(np.asarray(F)))
        # `backface_culling` : sans lui on voit les faces ARRIÈRE de la
        # surbrillance à travers ses faces avant, et en perspective elles
        # dessinent un second volume à l'intérieur du premier (retour
        # d'Emmanuel : « on dirait un cube dans un cube »). Une seule peau, donc
        # une teinte uniforme.
        self._acteur_fantome = self._plotter.add_mesh(
            maillage, color=ROUGE if creux else VERT, opacity=0.45,
            smooth_shading=True, backface_culling=True, pickable=False,
            reset_camera=False, render=False)
        # La surbrillance épouse EXACTEMENT la surface de la pièce : sans
        # décalage, les deux surfaces se disputent le même plan et la couleur
        # part en plaques (« la surbrillance est glitchée », retour d'Emmanuel).
        try:
            m = self._acteur_fantome.GetMapper()
            m.SetResolveCoincidentTopologyToPolygonOffset()
            m.SetRelativeCoincidentTopologyPolygonOffsetParameters(-8.0, -8.0)
        except Exception:
            pass

    # ── Le plan de coupe ───────────────────────────────────────────────────
    def montrer_plan_coupe(self, axe: int, position: float, boite):
        """Montre le plan qui tranche la pièce, orienté selon l'axe choisi.

        Sans lui, on réglait une coupe à l'aveugle, en devinant où passait le
        plan (demande d'Emmanuel : « j'aimerais qu'on puisse voir le plan de
        coupe et que si on clique sur x, y ou z on voie le plan s'orienter »).
        Il se tire aussi à la souris : voir `_preparer_plan`."""
        from neoforge.projet.decoupes import quadrilatere

        self.cacher_plan_coupe()
        if boite is None:
            return
        try:
            centre, direction, c1, c2 = quadrilatere(axe, position, boite)
            pal = _T.palette()
            # Une seule maille : ses quatre bords donnent exactement le contour.
            plan = pv.Plane(center=centre, direction=direction, i_size=c1,
                            j_size=c2, i_resolution=1, j_resolution=1)
            self._acteur_plan = self._plotter.add_mesh(
                plan, color=pal["ACCENT"], opacity=0.22, lighting=False,
                pickable=True, reset_camera=False, render=False)
            self._acteur_bord_plan = self._plotter.add_mesh(
                plan.extract_feature_edges(), color=pal["ACCENT_BRIGHT"],
                line_width=2, lighting=False, pickable=False, reset_camera=False,
                render=False)
            self._plan = {"axe": int(axe), "position": float(position),
                          "centre": np.array(centre, float)}
        except Exception:
            self.cacher_plan_coupe()
            return
        self._rendre(force=True)

    def cacher_plan_coupe(self):
        for nom in ("_acteur_plan", "_acteur_bord_plan"):
            a = getattr(self, nom, None)
            if a is not None:
                try:
                    self._plotter.remove_actor(a, render=False)
                except Exception:
                    pass
                setattr(self, nom, None)
        self._plan = None

    def placer_plan(self, position: float):
        """Le plan suit la souris TOUT DE SUITE, sans attendre que la pièce soit
        recalculée : c'est ce qui rend le glissement continu."""
        if self._plan is None or self._acteur_plan is None:
            return
        axe = self._plan["axe"]
        decalage = [0.0, 0.0, 0.0]
        decalage[axe] = float(position) - float(self._plan["centre"][axe])
        for a in (self._acteur_plan, self._acteur_bord_plan):
            if a is not None:
                a.SetPosition(*decalage)
        self._plan["position"] = float(position)
        self._rendre(force=True)

    def _plan_sous_la_souris(self) -> bool:
        if self._acteur_plan is None:
            return False
        x, y = self._position()
        p = vtkCellPicker()
        p.SetTolerance(0.005)
        p.InitializePickList()
        p.AddPickList(self._acteur_plan)
        p.PickFromListOn()
        p.Pick(x, y, 0, self._plotter.renderer)
        return p.GetCellId() >= 0

    def _preparer_plan(self, depart):
        """Le plan se tire le long de SON axe, qui est un axe du MONDE : une
        coupe ne tourne pas avec la pièce, contrairement aux poignées."""
        if self._plan is None:
            return
        axe = self._plan["axe"]
        direction = np.zeros(3)
        direction[axe] = 1.0
        ancre = np.array(self._plan["centre"], float)
        ancre[axe] = float(self._plan["position"])
        a = self._monde_vers_ecran(ancre)
        b = self._monde_vers_ecran(ancre + direction)
        vecteur = b - a                              # pixels pour 1 mm
        if float(vecteur @ vecteur) < 1e-6:
            return                                   # plan vu exactement de bout
        self._geste = {"genre": "plan", "axe": axe, "sens": 1, "vecteur": vecteur,
                       "depart": np.array(depart, float), "applique": 0.0}

    # ── Vue de profil ──────────────────────────────────────────────────────
    def _direction_de_vue(self):
        """Direction normalisée caméra → pièce, et l'axe dont elle est proche."""
        camera = self._plotter.camera
        vue = np.array(camera.focal_point, float) - np.array(camera.position, float)
        n = float(np.linalg.norm(vue))
        if n < 1e-9:
            return None, 0, False
        vue /= n
        axe = int(np.argmax(np.abs(vue)))
        # 2e-3 sur le cosinus : environ 3,6 degrés, la tolérance du cube.
        return vue, axe, abs(abs(vue[axe]) - 1.0) < 2e-3

    def _vue_axiale(self, *_a):
        """Après un clic sur un axe du cube d'orientation : une VRAIE vue de
        profil, telle qu'on la verrait en 2D.

        Deux corrections demandées par Emmanuel. La caméra passe en projection
        PARALLÈLE : en perspective, une vue « de profil » garde de la fuite et ne
        donne donc pas le contour exact d'un plan. Et ce qui se trouve ENTRE la
        caméra et l'objet sélectionné est retiré de l'image, sinon une pièce
        posée devant cache justement celle qu'on veut regarder."""
        try:
            vue, _axe, aligne = self._direction_de_vue()
            if vue is None:
                return
            if aligne:
                self._plotter.enable_parallel_projection()
            else:
                self._plotter.disable_parallel_projection()
            self._clip_devant(vue if aligne else None)
        except Exception:
            return
        self._rendre(force=True)

    def _camera_manuelle(self, *_a):
        """Tourner la vue à la main sort du profil : la perspective revient et
        rien ne reste masqué."""
        if getattr(self, "_clip_vue", None) is None:
            return
        try:
            vue, _axe, aligne = self._direction_de_vue()
            if vue is None or aligne:
                return                    # toujours de profil : on n'y touche pas
            self._retirer_clip()
            self._plotter.disable_parallel_projection()
            self._rendre(force=True)
        except Exception:
            pass

    def _clip_devant(self, direction):
        """Retire de l'image tout ce qui est entre la caméra et l'objet visé.

        La pièce entière est UN seul acteur (elle est fusionnée pour l'ombrage) :
        on ne peut donc pas masquer un objet en cachant son acteur. On coupe
        l'IMAGE par un plan posé juste devant la face la plus proche de l'objet,
        ce qui donne le même résultat à l'écran et fonctionne quel que soit le
        nombre de pièces devant."""
        self._retirer_clip()
        if direction is None or self._acteur_piece is None:
            return
        if self._acteur_fantome is None:      # rien de sélectionné : rien à viser
            return
        b = self._acteur_fantome.GetBounds()
        coins = np.array([[b[0 + i], b[2 + j], b[4 + k]]
                          for i in (0, 1) for j in (0, 1) for k in (0, 1)], float)
        # Le coin le plus PROCHE de la caméra donne le plan ; on le décale d'un
        # cheveu vers la caméra pour ne pas raboter la face de l'objet lui-même.
        origine = coins[int(np.argmin(coins @ direction))] - direction * 0.05
        try:
            from vtkmodules.vtkCommonDataModel import vtkPlane
            plan = vtkPlane()
            plan.SetNormal(*(float(v) for v in direction))
            plan.SetOrigin(*(float(v) for v in origine))
            self._acteur_piece.GetMapper().AddClippingPlane(plan)
            self._clip_vue = plan
        except Exception:
            self._clip_vue = None

    def _retirer_clip(self):
        plan = getattr(self, "_clip_vue", None)
        if plan is None:
            return
        try:
            if self._acteur_piece is not None:
                self._acteur_piece.GetMapper().RemoveClippingPlane(plan)
        except Exception:
            pass
        self._clip_vue = None

    def placer_apercu(self, pos, rot, echelle, libelles: list[str] | None = None,
                      compagnons=None):
        """Nouvelle position, rotation et mise à l'échelle : instantané (aucun
        calcul). L'échelle vient de `mesures.echelle_apercu`, qui connaît la
        sémantique de chaque forme. `libelles` met à jour les chiffres au passage."""
        self._pos = np.array(pos, float)
        self._rot = np.array(rot, float)
        self._echelle = np.array(echelle, float)
        if libelles is not None:
            self.etiquettes(libelles)
        if compagnons:
            self.placer_compagnons(compagnons)
        self._placer()

    def _placer(self):
        t = transformation(self._pos, self._rot, self._echelle)
        if self._acteur_fantome is not None:
            self._acteur_fantome.SetUserTransform(t)
        self._gizmo.placer(self._pos, self._rot, self._echelle)
        # Pendant un geste, les étiquettes de cote ne sont PAS refaites : chaque
        # étiquette coûte un acteur, et c'est ce qui rendait le mode taille deux
        # fois plus lent que les autres. Elles repartent à la fin du geste.
        if self._geste is None:
            self._maj_etiquettes()
        self._rendre()

    def geler(self):
        """Suspend l'affichage le temps de mettre TOUTE la scène à jour.

        La pièce, les arêtes et les poignées changent en trois temps : sans ce
        gel, une image intermédiaire montre la nouvelle pièce avec l'ancien
        aperçu, et l'objet paraît sauter un court instant (retour d'Emmanuel :
        « aucun bug d'affichage ni trace de rafraîchissement »).

        On débranche carrément le dessin : plusieurs appels partent de l'intérieur
        de PyVista (retrait d'un acteur, réglage de la caméra) et ne passent pas
        par notre `_rendre`. Mesuré : 8 images par mise à jour avant, 1 après."""
        if self._gel == 0:
            self._rendu_reel = self._plotter.render
            self._plotter.render = lambda *a, **k: None
        self._gel += 1

    def degeler(self):
        self._gel = max(0, self._gel - 1)
        if self._gel == 0:
            self._plotter.render = self._rendu_reel
            self._rendre(force=True)

    def _rendre(self, force: bool = False):
        """Une image au plus toutes les 12 ms pendant un geste : au delà, on
        dessine plus vite que l'écran n'affiche, pour rien."""
        if self._gel:
            return
        maintenant = time.perf_counter()
        if not force and self._geste is not None and maintenant - self._dernier_rendu < 0.012:
            return
        self._dernier_rendu = maintenant
        if self._calque is not None:
            camera = self._plotter.renderer.GetActiveCamera()
            if self._calque.GetActiveCamera() is not camera:
                self._calque.SetActiveCamera(camera)     # les deux calques suivent la vue
        self._plotter.render()

    def _rebatir_gizmo(self):
        if self._forme is None:
            return
        if self._mode_regle:
            # On mesure : les poignées encombreraient la vue et happeraient les
            # clics destinés aux arêtes.
            self._gizmo.cacher()
            return
        # Le centre et l'étendue de la matière restante repartent ICI AUSSI :
        # changer de mode passe par ce chemin, et sans eux les flèches et les
        # cercles retombaient sur l'origine de la forme ENTIÈRE (mesuré au
        # pilote : 23,5 mm d'écart en déplacement et 10 mm en rotation, alors que
        # les cotes, qui portent leurs coordonnées avec elles, étaient justes).
        self._gizmo.montrer(self._forme, getattr(self, "_cotes_locales", []),
                            getattr(self, "_centre_local", None),
                            getattr(self, "_demi_local", None))
        self._placer()

    def _ancrages(self, etiquettes: list[tuple]) -> np.ndarray:
        """Où poser les chiffres : à ÉCART_ETIQUETTE pixels du trait, mesurés à
        l'écran, perpendiculairement au trait tel qu'il APPARAÎT.

        Un décalage calculé en 3D ne marche pas : selon l'angle de vue, une
        direction perpendiculaire dans l'espace se projette dans l'axe du trait
        et le chiffre se recolle dessus (0 pixel mesuré)."""
        milieux = np.array([p for p, _d, _t in etiquettes], float)
        ecran = self._projeter(milieux)
        bouts = self._projeter(np.array([p + d for p, d, _t in etiquettes], float))
        camera = self._plotter.renderer.GetActiveCamera()
        regard = np.array(camera.GetDirectionOfProjection(), float)
        points = []
        for i, (milieu, _d, _t) in enumerate(etiquettes):
            trait = bouts[i] - ecran[i]
            n = float(np.linalg.norm(trait))
            if n < 1e-6:
                points.append(milieu)
                continue
            perpendiculaire = np.array([-trait[1], trait[0]]) / n
            if perpendiculaire[1] < 0:            # toujours vers le haut de l'écran
                perpendiculaire = -perpendiculaire
            vise = ecran[i] + perpendiculaire * ECART_ETIQUETTE
            monde = self._point_sur_plan(int(round(vise[0])), int(round(vise[1])),
                                         milieu, regard)
            points.append(milieu if monde is None else monde)
        return np.array(points, float)

    def _maj_etiquettes(self):
        """(Re)crée les chiffres des cotes. Coûteux : un acteur par étiquette,
        donc jamais pendant un geste (voir `etiquettes`)."""
        if self._acteur_etiquettes is not None:
            self._du_calque(self._acteur_etiquettes)
            self._acteur_etiquettes = None
            self._poly_etiquettes = None
        if self._forme is None or self._gizmo.mode != "taille":
            return
        etiquettes = self._gizmo.etiquettes_monde(self._pos, self._rot, self._echelle)
        if not etiquettes:
            return
        poly = pv.PolyData(self._ancrages(etiquettes))
        self._ecrire_etiquettes(poly, [t for _p, _d, t in etiquettes])
        self._poly_etiquettes = poly
        self._acteur_etiquettes = self._plotter.add_point_labels(
            poly, "etiquettes", font_size=12, text_color="#4ADE80", shape=None,
            show_points=False, always_visible=True, pickable=False,
            reset_camera=False, render=False)
        self._vers_calque(self._acteur_etiquettes)

    def etiquettes(self, valeurs: list[str]):
        """Change les chiffres EN PLACE, sans recréer d'acteur : c'est ce qui
        permet de les voir bouger pendant qu'on tire une cote (retour
        d'Emmanuel) sans retomber dans les 36 ms par pas de la reconstruction."""
        poly = getattr(self, "_poly_etiquettes", None)
        if poly is None or self._forme is None or self._gizmo.mode != "taille":
            return
        etiquettes = self._gizmo.etiquettes_monde(self._pos, self._rot, self._echelle)
        if len(etiquettes) != poly.n_points:
            return
        poly.points = self._ancrages(etiquettes)
        self._ecrire_etiquettes(poly, [
            (valeurs[i] if i < len(valeurs) else t)
            for i, (_p, _d, t) in enumerate(etiquettes)])
        poly.Modified()

    @staticmethod
    def _ecrire_etiquettes(poly, textes: list[str]):
        """Écrit les chiffres dans le maillage.

        PyVista REFUSE les chaînes non ASCII (« String array contains non-ASCII
        characters ») : le « Ø » d'un diamètre levait une exception et faisait
        disparaître TOUS les chiffres des formes rondes, cylindres, sphères et
        cônes. On remplit donc le tableau VTK nous mêmes, en UTF-8, ce que le
        moteur de texte de VTK sait parfaitement afficher."""
        from vtkmodules.vtkCommonCore import vtkStringArray
        tableau = vtkStringArray()
        tableau.SetName("etiquettes")
        tableau.SetNumberOfValues(len(textes))
        for i, texte in enumerate(textes):
            tableau.SetValue(i, str(texte))
        donnees = poly.GetPointData()
        donnees.RemoveArray("etiquettes")
        donnees.AddArray(tableau)

    # ── Arêtes ─────────────────────────────────────────────────────────────
    def afficher_aretes(self, polylignes: list[np.ndarray], choisies: set[int] | None = None,
                        visibles: bool = True):
        self._polylignes = list(polylignes)
        self._choisies = set(choisies or set())
        self._survolee = None
        if polylignes:
            self._points_aretes = np.vstack(polylignes)
            self._index_aretes = np.concatenate(
                [np.full(len(p), i, dtype=np.int32) for i, p in enumerate(polylignes)])
        else:
            self._points_aretes = np.zeros((0, 3))
            self._index_aretes = np.zeros(0, dtype=np.int32)
        self._aretes_visibles = bool(visibles and polylignes)
        self._dessiner_aretes()

    def _dessiner_aretes(self):
        for nom in ("_acteur_aretes", "_acteur_choix", "_acteur_survol"):
            a = getattr(self, nom, None)
            if a is not None:
                self._plotter.remove_actor(a, render=False)
                setattr(self, nom, None)
        if not self._aretes_visibles:
            self._rendre(force=True)
            return
        pal = _T.palette()
        normales, retenues, survol = [], [], []
        for i, p in enumerate(self._polylignes):
            if i == self._survolee:
                survol.append(p)
            elif i in self._choisies:
                retenues.append(p)
            else:
                normales.append(p)
        self._acteur_aretes = self._tracer(normales, pal["TEXT_SECONDARY"], 2)
        self._acteur_choix = self._tracer(retenues, pal["ACCENT_BRIGHT"], 6, tube=True)
        self._acteur_survol = self._tracer(survol, "#FFFFFF", 7, tube=True)
        self._rendre(force=True)

    def _tracer(self, listes, couleur, epaisseur, tube: bool = False):
        if not listes:
            return None
        points, lignes, depart = [], [], 0
        for pts in listes:
            n = len(pts)
            points.append(pts)
            lignes.append(np.hstack([[n], np.arange(depart, depart + n)]))
            depart += n
        poly = pv.PolyData(np.vstack(points))
        poly.lines = np.hstack(lignes)
        return self._plotter.add_mesh(poly, color=couleur, line_width=epaisseur,
                                      pickable=False, render_lines_as_tubes=tube,
                                      reset_camera=False, render=False)

    # ── Visée des arêtes, en pixels ────────────────────────────────────────
    def _projeter(self, points: np.ndarray, avec_profondeur: bool = False):
        """Projette des points du monde vers l'écran, tous d'un coup.
        `avec_profondeur` renvoie aussi la profondeur (petite = près de l'œil)."""
        r = self._plotter.renderer
        largeur, hauteur = r.GetSize()
        camera = r.GetActiveCamera()
        m = camera.GetCompositeProjectionTransformMatrix(
            largeur / max(1, hauteur), -1.0, 1.0)
        M = np.array([[m.GetElement(i, j) for j in range(4)] for i in range(4)])
        Q = np.hstack([points, np.ones((len(points), 1))]) @ M.T
        w = np.where(np.abs(Q[:, 3:4]) < 1e-12, 1e-12, Q[:, 3:4])
        Q = Q[:, :3] / w
        ecran = np.column_stack([(Q[:, 0] + 1) * 0.5 * largeur,
                                 (Q[:, 1] + 1) * 0.5 * hauteur])
        return (ecran, Q[:, 2]) if avec_profondeur else ecran

    def _arete_sous_la_souris(self) -> int | None:
        """Arête la plus proche du curseur, distance mesurée au SEGMENT.

        En ne comparant qu'aux extrémités, viser le milieu d'une arête donnait
        plus de 20 pixels et ne désignait jamais rien (constaté au diagnostic)."""
        if not self._aretes_visibles or not len(self._points_aretes):
            return None
        souris = np.array(self._position(), float)
        ecran = self._projeter(self._points_aretes)
        meilleure, plus_proche = None, float(RAYON_ARETE)
        for i, polyligne in enumerate(self._polylignes):
            n = len(polyligne)
            if n < 2:
                continue
            debut = int(np.searchsorted(self._index_aretes, i))
            pts = ecran[debut:debut + n]
            a, b = pts[:-1], pts[1:]
            ab = b - a
            longueur = np.einsum("ij,ij->i", ab, ab)
            t = np.clip(np.einsum("ij,ij->i", souris - a, ab)
                        / np.where(longueur < 1e-12, 1e-12, longueur), 0.0, 1.0)
            projete = a + ab * t[:, None]
            distance = float(np.linalg.norm(projete - souris, axis=1).min())
            if distance < plus_proche:
                meilleure, plus_proche = i, distance
        return meilleure

    # ── La règle ───────────────────────────────────────────────────────────
    def mode_regle(self, actif: bool, lignes=None):
        self._btn_regle.setChecked(bool(actif))
        """Entre ou sort du mode mesure. `lignes` sont les polylignes de TOUTES
        les arêtes de la pièce, en millimètres : c'est sur elles que la souris
        s'accroche."""
        self._mode_regle = bool(actif)
        self._regle_lignes = list(lignes or [])
        self._regle_a = self._regle_b = None
        self._regle_vise = None
        self._effacer_regle()
        self._rebatir_gizmo()
        self._rendre(force=True)

    def _effacer_regle(self):
        for acteur in self._acteurs_regle:
            try:
                self._du_calque(acteur)
            except Exception:
                pass
        self._acteurs_regle = []

    def _viser_a_la_regle(self):
        """Ce que la souris accroche, recalculé à chaque déplacement."""
        from neoforge.projet import regle as R
        if not self._regle_lignes:
            return None
        try:
            projetees = [self._projeter(np.asarray(l, float), avec_profondeur=True)
                         for l in self._regle_lignes]
        except Exception:
            return None
        return R.accrocher(self._position(), [p[0] for p in projetees],
                           self._regle_lignes,
                           lignes_profondeur=[p[1] for p in projetees])

    def _dessiner_regle(self):
        """Le repère sous la souris, le point A déjà posé, et le trait entre
        les deux avec la cote écrite dessus."""
        from neoforge.projet import regle as R
        from neoforge.projet import unites as U
        self._effacer_regle()
        pal = S.pal()
        points, couleurs = [], []
        if self._regle_a is not None:
            points.append(self._regle_a)
            couleurs.append(VERT_COTE)
        if self._regle_b is not None:
            points.append(self._regle_b)
            couleurs.append(VERT_COTE)
        elif self._regle_vise is not None:
            points.append(self._regle_vise.point)
            couleurs.append(pal["ACCENT_BRIGHT"])
        for point, couleur in zip(points, couleurs):
            acteur = self._plotter.add_mesh(
                pv.PolyData(np.array([point], float)), color=couleur,
                point_size=13, render_points_as_spheres=True, pickable=False,
                reset_camera=False, render=False)
            self._acteurs_regle.append(acteur)
            self._vers_calque(acteur)
        b = self._regle_b if self._regle_b is not None else (
            self._regle_vise.point if self._regle_vise is not None else None)
        if self._regle_a is None or b is None:
            return
        trait = self._tracer([np.array([self._regle_a, b], float)],
                             VERT_COTE, 3, tube=True)
        if trait is not None:
            self._acteurs_regle.append(trait)
            self._vers_calque(trait)
        m = R.mesure(self._regle_a, b)
        unite = U.courante()
        texte = f"{U.court(m['distance'], unite)} {U.symbole(unite)}"
        # Le chiffre se pose À CÔTÉ du trait, jamais dessus : écrit au milieu
        # exact, il se confondait avec la ligne et devenait illisible (retour
        # d'Emmanuel). On l'écarte perpendiculairement au trait ET
        # parallèlement à l'écran, pour qu'il reste lisible sous n'importe quel
        # angle de vue.
        axe = np.array(b, float) - np.array(self._regle_a, float)
        camera = self._plotter.camera
        vers_oeil = np.array(camera.position, float) - np.array(camera.focal_point, float)
        ecart = np.cross(axe, vers_oeil)
        norme = float(np.linalg.norm(ecart))
        if norme < 1e-9:                       # trait vu dans l'axe de la caméra
            ecart, norme = np.array([0.0, 0.0, 1.0]), 1.0
        # L'écart se règle EN PIXELS et non en millimètres : proportionnel à la
        # longueur, il donnait 9,5 pixels sur une cote de 28 mm, soit moins que
        # la hauteur du texte, qui mordait donc encore sur le trait (mesuré).
        # On mesure combien de millimètres valent 10 mm à l'écran, et on en
        # déduit le recul qui donne toujours le même écart visuel.
        milieu = np.array(m["milieu"], float)
        direction = ecart / norme
        try:
            deux = self._projeter(np.array([milieu, milieu + direction * 10.0]))
            par_10mm = float(np.linalg.norm(deux[1] - deux[0]))
        except Exception:
            par_10mm = 0.0
        recul = (min(80.0, max(2.0, 10.0 * 26.0 / par_10mm)) if par_10mm > 0.5
                 else max(4.0, float(np.linalg.norm(axe)) * 0.14))
        poly = pv.PolyData(np.array([milieu + direction * recul], float))
        poly["mesure"] = [texte]
        etiquette = self._plotter.add_point_labels(
            poly, "mesure", font_size=14, text_color=VERT_COTE, shape=None,
            show_points=False, always_visible=True, pickable=False,
            reset_camera=False, render=False)
        self._acteurs_regle.append(etiquette)
        self._vers_calque(etiquette)

    def _clic_regle(self):
        """Un clic pose A, le suivant FIGE B, le troisième repart de zéro.

        Le second clic figeait la mesure à zéro dans un premier jet : il
        remettait A à None au lieu de garder les deux points, si bien que la
        cote disparaissait à l'instant où on venait de la poser."""
        if self._regle_vise is None:
            self._regle_a = self._regle_b = None      # clic dans le vide : on efface
        elif self._regle_a is None or self._regle_b is not None:
            self._regle_a, self._regle_b = self._regle_vise.point, None
        else:
            self._regle_b = self._regle_vise.point
        self._dessiner_regle()
        self._rendre(force=True)

    def mode_choix_aretes(self, actif: bool):
        self._mode_choix = actif
        if not actif:
            self._survolee = None
            self._dessiner_aretes()

    # ── Repères écran ↔ monde ──────────────────────────────────────────────
    def _position(self) -> tuple[int, int]:
        return self._plotter.iren.get_event_position()

    def _monde_vers_ecran(self, point) -> np.ndarray:
        c = vtkCoordinate()
        c.SetCoordinateSystemToWorld()
        c.SetValue(float(point[0]), float(point[1]), float(point[2]))
        return np.array(c.GetComputedDoubleDisplayValue(self._plotter.renderer), float)

    def _rayon(self, x: int, y: int):
        r = self._plotter.renderer
        bornes = []
        for profondeur in (0.0, 1.0):
            r.SetDisplayPoint(float(x), float(y), profondeur)
            r.DisplayToWorld()
            p = np.array(r.GetWorldPoint(), float)
            if abs(p[3]) < 1e-12:
                return None, None
            bornes.append(p[:3] / p[3])
        return bornes[0], bornes[1] - bornes[0]

    def _point_sur_plan(self, x: int, y: int, origine, normale):
        depart, direction = self._rayon(x, y)
        if depart is None:
            return None
        denominateur = float(np.dot(direction, normale))
        if abs(denominateur) < 1e-9:
            return None
        t = float(np.dot(np.array(origine, float) - depart, normale)) / denominateur
        return depart + direction * t

    def _axe_monde(self, axe: int) -> np.ndarray:
        t = transformation(np.zeros(3), self._rot)
        v = np.array(t.TransformVector(*(1.0 if i == axe else 0.0 for i in range(3))), float)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])

    # ── Gestes ─────────────────────────────────────────────────────────────
    def _cible_sous_la_souris(self):
        """Poignée visée, mesurée en PIXELS : la tolérance de VTK vaut une
        fraction de la diagonale de la vue (≈ 17 px ici) et attrapait la
        poignée d'à côté."""
        souris = np.array(self._position(), float)
        candidats = []          # (distance en pixels, profondeur, mode, axe)

        points = self._gizmo.points_monde(self._pos, self._rot, self._echelle)
        if points:
            ecran, profondeur = self._projeter(
                np.array([p for _m, _a, p in points], float), avec_profondeur=True)
            for (mode, axe, _p), e, z in zip(points, ecran, profondeur):
                candidats.append((float(np.linalg.norm(e - souris)), float(z), mode, axe))

        for mode, axe, polyligne in self._gizmo.traits_monde(self._pos, self._rot,
                                                             self._echelle):
            ecran, profondeur = self._projeter(polyligne, avec_profondeur=True)
            a, b = ecran[:-1], ecran[1:]
            ab = b - a
            longueur = np.einsum("ij,ij->i", ab, ab)
            t = np.clip(np.einsum("ij,ij->i", souris - a, ab)
                        / np.where(longueur < 1e-12, 1e-12, longueur), 0.0, 1.0)
            distances = np.linalg.norm(a + ab * t[:, None] - souris, axis=1)
            i = int(np.argmin(distances))
            candidats.append((float(distances[i]), float(profondeur[i]), mode, axe))

        proches = [c for c in candidats if c[0] <= RAYON_VISEE]
        if not proches:
            return None
        # À distance comparable (moins de 5 pixels d'écart), on prend la poignée
        # la plus PROCHE de la caméra : là où deux cercles se croisent à
        # l'écran, c'était celui de derrière qui l'emportait (retour d'Emmanuel).
        meilleure = min(proches)
        serres = [c for c in proches if c[0] <= meilleure[0] + 5.0]
        choisie = min(serres, key=lambda c: c[1])
        return (choisie[2], choisie[3])

    def _piece_sous_la_souris(self):
        """Le clic tombe-t-il sur la pièce ? On interroge UNIQUEMENT son acteur :
        sinon une poignée par dessus mangeait le clic et la pièce ne se
        sélectionnait pas."""
        if self._acteur_piece is None:
            return None
        x, y = self._position()
        p = vtkCellPicker()
        p.SetTolerance(0.005)
        p.InitializePickList()
        p.AddPickList(self._acteur_piece)
        p.PickFromListOn()
        p.Pick(x, y, 0, self._plotter.renderer)
        if p.GetCellId() < 0:
            return None
        return np.array(p.GetPickPosition(), float)

    def _camera_bougee(self, *_a):
        poly = getattr(self, "_poly_etiquettes", None)
        if poly is None or self._geste is not None:
            return
        etiquettes = self._gizmo.etiquettes_monde(self._pos, self._rot, self._echelle)
        if len(etiquettes) == poly.n_points:
            poly.points = self._ancrages(etiquettes)
            poly.Modified()
            self._rendre(force=True)

    def _couper(self, tag: int):
        """Empêche la caméra de voir cet événement (on manipule une poignée)."""
        try:
            self._plotter.iren.interactor.GetCommand(tag).AbortFlagOn()
        except Exception:
            pass

    def _manipulation(self) -> bool:
        return (self._geste or {}).get("genre") in ("taille", "deplacer", "tourner",
                                                    "plan")

    def _sur_appui(self, *_a):
        try:
            self._geste = None
            depart = np.array(self._position(), float)
            if self._sur_le_cube(depart):
                return          # le cube d'orientation garde ce clic pour lui
            if self._mode_regle:
                self._geste = {"genre": "regle", "depart": depart}
                return
            if self._mode_choix:
                self._geste = {"genre": "arete", "depart": depart}
                return
            cible = self._cible_sous_la_souris() if self._forme is not None else None
            if cible is not None:
                mode, axe = cible
                if mode == "tourner":
                    self._preparer_rotation(axe, depart)
                else:
                    self._preparer_axe(mode, axe, depart)
                if self._manipulation():
                    self._couper(self._tag_appui)     # la caméra ne bouge pas
                return
            # Le plan de coupe passe AVANT la pièce : posé au travers d'elle, il
            # doit pouvoir se saisir même là où la matière est derrière lui.
            if self._plan is not None and self._plan_sous_la_souris():
                self._preparer_plan(depart)
                if self._manipulation():
                    self._couper(self._tag_appui)
                return
            touche = self._piece_sous_la_souris()
            if touche is not None:
                self._geste = {"genre": "piece", "depart": depart, "point": touche,
                               "bouge": False}
            else:
                # Rien sous le curseur : un simple clic désélectionne, un
                # glissement reste une rotation de caméra.
                self._geste = {"genre": "vide", "depart": depart}
        except Exception:
            self._geste = None

    def _preparer_axe(self, mode: str, axe, depart):
        numero, sens = (axe if isinstance(axe, tuple) else (axe, 1))
        direction = self._axe_monde(numero)
        ancre = self._pos + direction
        a = self._monde_vers_ecran(self._pos)
        b = self._monde_vers_ecran(ancre)
        vecteur = b - a                              # pixels pour 1 mm
        if float(vecteur @ vecteur) < 1e-6:          # axe vu de bout
            return
        self._geste = {"genre": mode, "axe": numero, "sens": sens, "vecteur": vecteur,
                       "depart": depart, "applique": 0.0}

    def _preparer_rotation(self, axe: int, depart):
        normale = self._axe_monde(axe)
        point = self._point_sur_plan(int(depart[0]), int(depart[1]), self._pos, normale)
        if point is None:
            return
        self._geste = {"genre": "tourner", "axe": axe, "normale": normale,
                       "origine": point - self._pos, "depart": depart, "applique": 0.0}

    def _bouton_relache(self) -> bool:
        return not bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)

    def _sur_deplacement(self, *_a):
        g = self._geste
        if g is None:
            # Mode règle : le point visé s'allume sous le curseur, on voit donc
            # AVANT de cliquer sur quel coin ou quelle arête on va mesurer.
            if self._mode_regle:
                vise = self._viser_a_la_regle()
                ancien = self._regle_vise
                bouge = (vise is None) != (ancien is None) or (
                    vise is not None and ancien is not None
                    and vise.point != ancien.point)
                if bouge:
                    self._regle_vise = vise
                    self._dessiner_regle()
                    self._rendre(force=True)
                return
            # Mode choix d'arêtes : celle qui est sous le curseur s'éclaire, on
            # voit donc AVANT de cliquer ce qu'on va arrondir.
            if self._mode_choix:
                survolee = self._arete_sous_la_souris()
                if survolee != self._survolee:
                    self._survolee = survolee
                    self._dessiner_aretes()
            return
        if self._bouton_relache():
            self._terminer()
            return
        if self._manipulation():
            self._couper(self._tag_bouge)
        try:
            genre = g["genre"]
            if genre in ("taille", "deplacer", "plan"):
                position = np.array(self._position(), float)
                total = float((position - g["depart"]) @ g["vecteur"]) / float(
                    g["vecteur"] @ g["vecteur"])
                total = round(total, 1)
                pas = total - g["applique"]
                if abs(pas) < 0.05:
                    return
                g["applique"] = total
                if genre == "taille":
                    self.taille_modifiee.emit(g["axe"], pas * g["sens"], g["sens"])
                elif genre == "plan":
                    self.plan_deplace.emit(pas)
                else:
                    self.deplacement.emit(g["axe"], pas)
            elif genre == "tourner":
                position = self._position()
                point = self._point_sur_plan(int(position[0]), int(position[1]),
                                             self._pos, g["normale"])
                if point is None:
                    return
                courant = point - self._pos
                angle = np.degrees(np.arctan2(
                    float(np.dot(np.cross(g["origine"], courant), g["normale"])),
                    float(np.dot(g["origine"], courant))))
                angle = round(angle, 0)
                pas = angle - g["applique"]
                if abs(pas) < 0.5:
                    return
                g["applique"] = angle
                self.rotation.emit(g["axe"], pas)
            elif genre == "piece":
                if not g["bouge"] and np.linalg.norm(
                        np.array(self._position(), float) - g["depart"]) >= SEUIL_GESTE:
                    g["bouge"] = True     # glisser la pièce : la caméra tourne
        except Exception:
            self._terminer()

    def _sur_relachement(self, *_a, position=None):
        """`position` vient de Qt quand VTK nous a confisqué l'événement (voir
        eventFilter) ; sinon on lit celle de l'interacteur."""
        g = self._geste
        if g is None:
            return
        if self._manipulation():
            self._couper(self._tag_relache)
        try:
            fin = np.array(position if position is not None else self._position(), float)
            clic = np.linalg.norm(fin - g["depart"]) < SEUIL_GESTE
            if g["genre"] == "regle" and clic:
                self._clic_regle()
            elif g["genre"] == "arete" and clic:
                self._clic_arete()
            elif g["genre"] == "piece" and clic:
                self.piece_cliquee.emit(tuple(g["point"]))
            elif g["genre"] == "vide" and clic:
                self.fond_clique.emit()
        finally:
            self._terminer()

    def _terminer(self):
        genre = (self._geste or {}).get("genre")
        self._geste = None
        if genre in ("taille", "deplacer", "tourner", "plan"):
            if genre in ("taille", "deplacer"):
                self._garder_les_poignees_en_vue()
            self._maj_etiquettes()          # les chiffres reviennent, à jour
            self._rendre(force=True)
            self.geste_termine.emit()

    def _garder_les_poignees_en_vue(self):
        """Si les poignées sont sorties du cadre, on recule juste ce qu'il faut.

        Sans cela le geste ne peut plus être REPRIS : la poignée verte se
        retrouve hors de l'écran et il n'y a plus rien à attraper. C'est la vraie
        cause du prisme « qui bloque vers 10 cm » (retour d'Emmanuel) : rien ne
        bride la cote, un seul trait de souris mène de 20 à 272 mm, mais la
        poignée finit à 861 pixels dans une fenêtre qui en fait 756.

        On ne recule QUE si nécessaire, JAMAIS pendant le geste, et jamais au
        delà du strict besoin : la vue ne doit pas sauter."""
        if self._forme is None:
            return
        try:
            points = [p for _m, _a, p in
                      self._gizmo.points_monde(self._pos, self._rot, self._echelle)]
            if not points:
                return
            largeur, hauteur = self._plotter.ren_win.GetSize()
            ecran = self._projeter(np.array(points, float))
            marge = 24.0        # de quoi rattraper la poignée confortablement
            recul_max = 4.0     # plafond : la vue ne saute jamais d'un seul coup
            besoin = 1.0
            for k, taille in ((0, largeur), (1, hauteur)):
                milieu = taille / 2.0
                if milieu <= 1.0:
                    continue
                # La caméra recule autour du CENTRE de la vue : ce qui compte est
                # donc l'écart au centre, pas la largeur occupée.
                demi = max(abs(float(ecran[:, k].min()) - milieu),
                           abs(float(ecran[:, k].max()) - milieu)) + marge
                besoin = max(besoin, demi / milieu)
            if besoin <= 1.001:
                return                      # tout est déjà visible : on ne bouge pas
            self._reculer_la_camera(min(besoin, recul_max))
            self._plotter.renderer.ResetCameraClippingRange()
            self._rendre(force=True)
        except Exception:
            pass                            # une vue qui recule mal ne casse rien

    def _reculer_la_camera(self, facteur: float):
        """Éloigne la caméra de son point de visée, sans toucher à l'objectif.

        ⚠️ PIÈGE VTK, à l'origine d'un vrai défaut signalé par Emmanuel (« la
        perspective a changé subitement, comme si tout était très étiré ») :
        `camera.zoom(f)` ne recule RIEN en perspective, il DIVISE L'ANGLE DE VUE
        par f. Reculer avec `zoom(1/2)` doublait donc l'angle, et l'effet
        s'accumulait geste après geste sans jamais revenir. Mesuré : 30° puis
        60°, 120°, et le plafond de VTK à 179°, la distance ne bougeant pas d'un
        millimètre. À 179° l'image est un fisheye, ce qui est exactement ce
        qu'il a vu.

        On déplace donc la caméra le long de son axe de visée, et on remet
        l'objectif à sa focale de départ au cas où il aurait déjà dérivé.
        """
        camera = self._plotter.camera
        if abs(float(camera.view_angle) - self._angle_vue) > 0.01:
            camera.view_angle = self._angle_vue
        if camera.parallel_projection:
            # En projection parallèle il n'y a pas de fuite : c'est l'échelle
            # qui cadre, et là elle se multiplie bien.
            camera.parallel_scale = float(camera.parallel_scale) * facteur
            return
        camera.position = position_reculee(camera.position, camera.focal_point,
                                           facteur)

    def _clic_arete(self):
        """Clic sur une arête : elle est retenue (ou retirée) tout de suite."""
        i = self._arete_sous_la_souris()
        if i is None:
            return
        if i in self._choisies:
            self._choisies.discard(i)
        else:
            self._choisies.add(i)
        self._dessiner_aretes()          # réponse immédiate, sans attendre le calcul
        self.arete_cliquee.emit(i)

    def fermer(self):
        try:
            self._plotter.close()
        except Exception:
            pass
