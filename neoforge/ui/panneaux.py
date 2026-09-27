# -*- coding: utf-8 -*-
"""Réglages de l'étape sélectionnée : dimensions, position, rotation pour une
forme ; genre, taille et choix des arêtes pour un arrondi.

Mise en page compacte (retour d'Emmanuel) : la valeur colle à son libellé au
lieu d'être repoussée à droite, et les boutons sont empilés les uns sous les
autres, ce qui laisse de la place et se lit d'un coup d'œil."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from neoforge.projet import unites as U
from neoforge.projet.modele import Arrondi, Coupe, Forme
from neoforge.ui import style as S
from neoforge.ui.textes import T
from ui.styles.theme import FONT_MAIN

OPS = ("matiere", "creux", "intersection")
REGLES = ("toutes", "haut", "bas", "verticales", "liste")
LARGEUR_VALEUR = 96          # pixels : les compteurs restent près de leur libellé


def _spin(mini: float, maxi: float, pas: float = 1.0, decimales: int = 1) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    # Bornes gardées en MILLIMÈTRES : changer d'unité les reconvertit sans jamais
    # les recalculer de mémoire (voir `Proprietes.definir_unite`).
    s._mm = (float(mini), float(maxi))
    s.setRange(mini, maxi)
    s.setSingleStep(pas)
    s.setDecimals(decimales)
    s.setFont(QFont(FONT_MAIN, 9))
    s.setKeyboardTracking(False)
    s.setFixedWidth(LARGEUR_VALEUR)
    return s


class Proprietes(QWidget):
    """Panneau de droite. `modifie` part à chaque changement de valeur."""
    modifie = Signal()
    geste = Signal(str)                  # poser / centrer
    choisir_aretes = Signal(bool)        # entrer / sortir du mode clic sur les arêtes
    collage_change = Signal(bool)
    coupe_validee = Signal()             # le bouton Valider d'une découpe

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panneau")
        self._etape = None
        self._silence = False
        # Renseigné par la fenêtre : dit si la forme affichée est la PREMIÈRE
        # forme active, auquel cas elle ne peut être que de la matière.
        self.est_premiere = None
        # Rendue creusable : la fenêtre sait descendre la première forme sous
        # une autre, ce qui lui permet enfin de creuser.
        self.peut_creuser = None
        self.rendre_creusable = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.addWidget(S.titre_section(T("proprietes")))

        self._vide = S.etiquette(T("pile_vide"), 9)
        self._vide.setWordWrap(True)
        lay.addWidget(self._vide)

        # ── Forme ───────────────────────────────────────────────────────────
        self._bloc_forme = QWidget()
        gf = QVBoxLayout(self._bloc_forme)
        gf.setContentsMargins(0, 0, 0, 0)
        gf.setSpacing(8)

        self._ops = QButtonGroup(self)
        colonne_op = QVBoxLayout()
        colonne_op.setSpacing(4)
        self._btn_ops = {}
        for op in OPS:
            b = self._bouton(T(op), lambda _c=False, o=op: self._changer_op(o))
            b.setCheckable(True)
            self._ops.addButton(b)
            colonne_op.addWidget(b)
            self._btn_ops[op] = b
        gf.addLayout(colonne_op)

        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(8)
        self._grille.setVerticalSpacing(5)
        self._grille.setColumnStretch(0, 0)
        self._grille.setColumnStretch(1, 0)
        self._grille.setColumnStretch(2, 1)      # tout le vide part à DROITE
        gf.addLayout(self._grille)
        self._dim_lbl = [S.etiquette(""), S.etiquette(""), S.etiquette("")]
        self._dim = [_spin(0.1, 1000.0), _spin(0.0, 1000.0), _spin(0.1, 1000.0)]
        self._pos = [_spin(-1000.0, 1000.0), _spin(-1000.0, 1000.0), _spin(-1000.0, 1000.0)]
        self._rot = [_spin(-360.0, 360.0, 15.0, 0), _spin(-360.0, 360.0, 15.0, 0),
                     _spin(-360.0, 360.0, 15.0, 0)]
        self._lbl_dim_titre = S.titre_section(T("dimensions"))
        self._lbl_pos_titre = S.titre_section(T("position"))
        self._lbl_rot_titre = S.titre_section(T("rotation"))
        # Cadenas des deux premières cotes : elles bougent ensemble, donc un
        # cylindre reste rond et une roue reste ronde (demande d'Emmanuel).
        self._cadenas = QPushButton()
        self._cadenas.setCheckable(True)
        self._cadenas.setCursor(Qt.PointingHandCursor)
        self._cadenas.setFixedSize(26, 44)
        self._cadenas.setIconSize(QSize(16, 16))
        self._cadenas.toggled.connect(self._changer_cadenas)
        ligne = 0
        self._grille.addWidget(self._lbl_dim_titre, ligne, 0, 1, 3)
        for i in range(3):
            ligne += 1
            self._grille.addWidget(self._dim_lbl[i], ligne, 0)
            self._grille.addWidget(self._dim[i], ligne, 1)
            if i == 0:
                # à cheval sur les deux lignes qu'il relie
                self._grille.addWidget(self._cadenas, ligne, 2, 2, 1,
                                       Qt.AlignLeft | Qt.AlignVCenter)
        ligne += 1
        self._grille.addWidget(self._lbl_pos_titre, ligne, 0, 1, 3)
        for i, axe in enumerate("XYZ"):
            ligne += 1
            self._grille.addWidget(S.etiquette(axe), ligne, 0)
            self._grille.addWidget(self._pos[i], ligne, 1)
        ligne += 1
        self._grille.addWidget(self._lbl_rot_titre, ligne, 0, 1, 3)
        for i, axe in enumerate("XYZ"):
            ligne += 1
            self._grille.addWidget(S.etiquette(f"{axe}  °"), ligne, 0)
            self._grille.addWidget(self._rot[i], ligne, 1)
        for s in (*self._dim, *self._pos, *self._rot):
            s.valueChanged.connect(self._valeurs_changees)

        # Nombre de côtés : n'a de sens que pour un prisme régulier, la ligne
        # n'apparaît donc que pour lui (six côtés donnent l'écrou).
        self._ligne_cotes = QWidget()
        rang = QHBoxLayout(self._ligne_cotes)
        rang.setContentsMargins(0, 0, 0, 0)
        rang.setSpacing(8)
        self._lbl_cotes = S.etiquette(T("nombre_cotes"))
        self._cotes = _spin(3, 24, 1.0, 0)
        self._cotes.valueChanged.connect(self._valeurs_changees)
        rang.addWidget(self._lbl_cotes)
        rang.addWidget(self._cotes)
        rang.addStretch()
        gf.addWidget(self._ligne_cotes)

        # Épaisseur du bord : pour le cadre et l'anneau, qui sont VIDES au
        # milieu. Sans elle, on ne pourrait régler que leur encombrement.
        self._ligne_bord = QWidget()
        rang_bord = QHBoxLayout(self._ligne_bord)
        rang_bord.setContentsMargins(0, 0, 0, 0)
        rang_bord.setSpacing(8)
        self._lbl_bord = S.etiquette(T("epaisseur_bord"))
        self._bord = _spin(0.2, 500.0)
        self._bord.valueChanged.connect(self._valeurs_changees)
        rang_bord.addWidget(self._lbl_bord)
        rang_bord.addWidget(self._bord)
        rang_bord.addStretch()
        gf.addWidget(self._ligne_bord)

        # Profil des dents : pour l'engrenage seulement.
        self._ligne_profil = QWidget()
        rang_profil = QVBoxLayout(self._ligne_profil)
        rang_profil.setContentsMargins(0, 0, 0, 0)
        rang_profil.setSpacing(4)
        rang_profil.addWidget(S.etiquette(T("profil_dents")))
        self._btn_profils = {}
        for nom in ("droit", "arrondi", "pointu"):
            b = self._bouton(T(f"dent_{nom}"),
                             lambda _c=False, v=nom: self._changer_profil(v))
            b.setCheckable(True)
            rang_profil.addWidget(b)
            self._btn_profils[nom] = b
        gf.addWidget(self._ligne_profil)

        # Pas de vis : pour le trou taraudé seulement.
        self._ligne_pas = QWidget()
        rang_pas = QHBoxLayout(self._ligne_pas)
        rang_pas.setContentsMargins(0, 0, 0, 0)
        rang_pas.setSpacing(8)
        self._lbl_pas = S.etiquette(T("pas_de_vis"))
        self._pas = _spin(0.15, 6.0, 0.05, 2)
        self._pas.valueChanged.connect(self._valeurs_changees)
        rang_pas.addWidget(self._lbl_pas)
        rang_pas.addWidget(self._pas)
        rang_pas.addStretch()
        gf.addWidget(self._ligne_pas)

        # Angle de la pente : pour le coin seulement. Régler l'angle ajuste la
        # HAUTEUR, la longueur restant celle qu'on a choisie (demande d'Emmanuel).
        self._ligne_angle = QWidget()
        rang_angle = QHBoxLayout(self._ligne_angle)
        rang_angle.setContentsMargins(0, 0, 0, 0)
        rang_angle.setSpacing(8)
        self._lbl_angle = S.etiquette(T("angle_pente"))
        self._angle = _spin(1.0, 89.0, 1.0, 1)
        self._angle.valueChanged.connect(self._changer_angle)
        rang_angle.addWidget(self._lbl_angle)
        rang_angle.addWidget(self._angle)
        rang_angle.addStretch()
        gf.addWidget(self._ligne_angle)

        self._btn_poser = self._bouton(T("poser"), lambda: self.geste.emit("poser"))
        self._btn_centrer = self._bouton(T("centrer"), lambda: self.geste.emit("centrer"))
        gf.addWidget(self._btn_poser)
        gf.addWidget(self._btn_centrer)
        self._btn_plateau = self._bouton(T("centrer_plateau"),
                                         lambda: self.geste.emit("centrer_plateau"))
        gf.addWidget(self._btn_plateau)

        # Les pièces se collent, ou elles se traversent : choix explicite.
        self._btn_contact = {}
        for nom, colle in (("collent", True), ("traversent", False)):
            b = self._bouton(T(nom), lambda _c=False, v=colle: self._changer_contact(v))
            b.setCheckable(True)
            gf.addWidget(b)
            self._btn_contact[colle] = b
        lay.addWidget(self._bloc_forme)

        # ── Arrondi ─────────────────────────────────────────────────────────
        self._bloc_arrondi = QWidget()
        ga = QVBoxLayout(self._bloc_arrondi)
        ga.setContentsMargins(0, 0, 0, 0)
        ga.setSpacing(6)
        self._btn_genres = {}
        for genre in ("conge", "chanfrein"):
            b = self._bouton(T(genre), lambda _c=False, g=genre: self._changer_genre(g))
            b.setCheckable(True)
            ga.addWidget(b)
            self._btn_genres[genre] = b
        ligne_taille = QHBoxLayout()
        ligne_taille.setSpacing(8)
        self._lbl_taille = S.etiquette(T("taille_conge"))
        self._taille = _spin(0.1, 200.0, 0.5)
        self._taille.valueChanged.connect(self._valeurs_changees)
        ligne_taille.addWidget(self._lbl_taille)
        ligne_taille.addWidget(self._taille)
        ligne_taille.addStretch()
        ga.addLayout(ligne_taille)
        ga.addWidget(S.titre_section(T("aretes")))
        self._regle = QComboBox()
        for r in REGLES:
            self._regle.addItem(T(f"regle_{r}"), r)
        self._regle.currentIndexChanged.connect(self._changer_regle)
        ga.addWidget(self._regle)
        self._btn_choix = self._bouton(T("choisir_aretes"), None)
        self._btn_choix.setCheckable(True)
        self._btn_choix.toggled.connect(self._basculer_choix)
        ga.addWidget(self._btn_choix)
        self._aide_choix = S.etiquette(T("choisir_aretes_aide"), 8)
        self._aide_choix.setWordWrap(True)
        ga.addWidget(self._aide_choix)
        self._compte_aretes = S.etiquette("", 8)
        ga.addWidget(self._compte_aretes)
        # Un vrai bouton pour finir, plutôt que recliquer sur « Choisir les
        # arêtes » (plus intuitif, demande d'Emmanuel).
        self._btn_valider = self._bouton(T("termine"), self.sortir_du_choix)
        ga.addWidget(self._btn_valider)
        lay.addWidget(self._bloc_arrondi)

        # ── Découpe par un plan ─────────────────────────────────────────────
        self._bloc_coupe = QWidget()
        gc = QVBoxLayout(self._bloc_coupe)
        gc.setContentsMargins(0, 0, 0, 0)
        gc.setSpacing(6)
        self._titre_axe = S.titre_section(T("axe_coupe"))
        gc.addWidget(self._titre_axe)
        rang_axes = QHBoxLayout()
        rang_axes.setSpacing(4)
        self._btn_axes = {}
        for i, lettre in enumerate("XYZ"):
            b = self._bouton(lettre, lambda _c=False, a=i: self._changer_axe(a))
            b.setCheckable(True)
            rang_axes.addWidget(b)
            self._btn_axes[i] = b
        gc.addLayout(rang_axes)
        ligne_pos = QHBoxLayout()
        ligne_pos.setSpacing(8)
        self._lbl_coupe = S.etiquette(T("position_coupe"))
        self._pos_coupe = _spin(-1000.0, 1000.0)
        self._pos_coupe.valueChanged.connect(self._valeurs_changees)
        ligne_pos.addWidget(self._lbl_coupe)
        ligne_pos.addWidget(self._pos_coupe)
        ligne_pos.addStretch()
        gc.addLayout(ligne_pos)
        self._btn_garder = {}
        for cle in ("dessous", "dessus", "les_deux"):
            b = self._bouton(T(f"garder_{cle}"),
                             lambda _c=False, g=cle: self._changer_garder(g))
            b.setCheckable(True)
            gc.addWidget(b)
            self._btn_garder[cle] = b
        # Une coupe se VALIDE par ce bouton. Avant, il fallait cliquer dans le
        # vide, ce qui n'annonçait rien et ne se devinait pas (demande
        # d'Emmanuel) ; ce même clic dans le vide abandonne désormais la coupe.
        self._btn_valider_coupe = self._bouton(T("valider_coupe"),
                                               self.coupe_validee.emit)
        gc.addWidget(self._btn_valider_coupe)
        lay.addWidget(self._bloc_coupe)

        lay.addStretch()
        self.refresh_theme()
        self.set_etape(None)

    def _bouton(self, texte: str, action) -> QPushButton:
        b = QPushButton(texte)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(26)
        if action is not None:
            b.clicked.connect(lambda _c=False: action())
        return b

    # ── Remplissage ────────────────────────────────────────────────────────
    def set_etape(self, etape, collage: bool = True):
        self._etape = etape
        # Retenu pour `definir_unite`, qui repasse par ici : sans cela, changer
        # d'unité remettait le collage à sa valeur par défaut.
        self._collage_vu = bool(collage)
        self._silence = True
        est_forme = isinstance(etape, Forme)
        est_arrondi = isinstance(etape, Arrondi)
        est_coupe = isinstance(etape, Coupe)
        self._vide.setVisible(etape is None)
        self._bloc_forme.setVisible(est_forme)
        self._bloc_arrondi.setVisible(est_arrondi)
        self._bloc_coupe.setVisible(est_coupe)
        if est_coupe:
            for i, b in self._btn_axes.items():
                b.setChecked(i == etape.axe)
            self._pos_coupe.setValue(U.vers(etape.position, U.courante()))
            for cle, b in self._btn_garder.items():
                b.setChecked(cle == etape.garder)
        if est_forme:
            for colle, b in self._btn_contact.items():
                b.setChecked(colle == bool(collage))
            # La première forme active ne peut pas creuser : il n'y a rien avant
            # elle. Le moteur le forçait DÉJÀ, mais en silence, si bien que le
            # bouton semblait accepté sans rien faire (retour d'Emmanuel sur le
            # cône). On rend l'impossibilité visible plutôt que muette.
            # Bloquée seulement s'il n'y a VRAIMENT rien à creuser, c'est à
            # dire pas d'autre forme dans la pièce.
            bloquee = not (self.peut_creuser(etape) if self.peut_creuser
                           else not (self.est_premiere and self.est_premiere(etape)))
            for op, b in self._btn_ops.items():
                b.setChecked(etape.op == op)
                b.setEnabled(not (bloquee and op != "matiere"))
                b.setToolTip(T("premiere_matiere") if bloquee and op != "matiere"
                             else "")
            noms = self._noms_dimensions(etape.forme)
            for i in range(3):
                visible = noms[i] is not None
                self._dim_lbl[i].setVisible(visible)
                self._dim[i].setVisible(visible)
                if visible:
                    self._dim_lbl[i].setText(noms[i])
                    # Le modèle est en millimètres, l'affichage dans l'unité
                    # choisie : la conversion se fait ici et nulle part ailleurs.
                    self._dim[i].setValue(U.vers(etape.dim[i], U.courante()))
            # Le cadenas n'a de sens que si les deux premières cotes existent
            # et ne sont pas déjà liées d'office (la sphère n'a qu'un diamètre).
            liable = (noms[0] is not None and noms[1] is not None
                      and etape.forme != "sphere")
            self._cadenas.setVisible(liable)
            if liable:
                self._cadenas.setChecked(bool(getattr(etape, "lien_xy", False)))
            self._maj_cadenas()
            for i in range(3):
                self._pos[i].setValue(U.vers(etape.pos[i], U.courante()))
                self._rot[i].setValue(float(etape.rot[i]))   # des degrés
            # Le nombre de côtés vaut pour le prisme ET pour le cadre :
            # 3 donne un triangle, 4 un carré ou un rectangle, 6 un hexagone.
            # Le nombre de côtés devient le nombre de DENTS sur un engrenage,
            # avec ses propres bornes : 6 dents au moins, 120 au plus.
            roue = etape.forme == "engrenage"
            a_des_cotes = roue or etape.forme in ("prisme", "cadre")
            self._ligne_cotes.setVisible(a_des_cotes)
            if a_des_cotes:
                self._lbl_cotes.setText(T("nombre_dents") if roue
                                        else T("nombre_cotes"))
                self._cotes.setRange(6 if roue else 3, 120 if roue else 24)
                self._cotes.setValue(float(etape.cotes))
            self._ligne_profil.setVisible(roue)
            if roue:
                courant = etape.variante or "droit"
                for nom, b in self._btn_profils.items():
                    b.setChecked(nom == courant)
            contour = etape.forme in ("cadre", "anneau")
            self._ligne_bord.setVisible(contour)
            if contour:
                self._bord.setValue(U.vers(etape.bord, U.courante()))
            filete = etape.forme == "taraudage"
            self._ligne_pas.setVisible(filete)
            if filete:
                self._pas.setValue(U.vers(etape.pas, U.courante()))
            coin = etape.forme == "coin"
            self._ligne_angle.setVisible(coin)
            if coin:
                import math
                longueur = max(1e-6, float(etape.dim[0]))
                pente = math.degrees(math.atan2(float(etape.dim[2]), longueur))
                self._angle.setValue(max(1.0, min(89.0, round(pente, 1))))
        elif est_arrondi:
            for genre, b in self._btn_genres.items():
                b.setChecked(etape.genre_arrondi == genre)
            self._lbl_taille.setText(T("taille_conge" if etape.genre_arrondi == "conge"
                                       else "taille_chanfrein"))
            self._taille.setValue(U.vers(etape.taille, U.courante()))
            self._regle.setCurrentIndex(max(0, self._regle.findData(etape.regle)))
            liste = etape.regle == "liste"
            choix = liste and self._btn_choix.isChecked()
            self._btn_choix.setVisible(liste and not choix)
            self._aide_choix.setVisible(choix)
            self._btn_valider.setVisible(choix)
            self._compte_aretes.setVisible(liste)
            self._compte_aretes.setText(T("aretes_n", n=len(etape.aretes)))
        self._silence = False

    @staticmethod
    def _noms_dimensions(forme: str) -> list[str | None]:
        if forme == "cube":
            return [T("largeur"), T("profondeur"), T("hauteur")]
        if forme == "sphere":
            return [T("diametre"), None, None]
        if forme == "cylindre":
            # Deux diamètres : un cylindre peut être OVALE (demande d'Emmanuel).
            # Égaux, il est rond, ce qui reste le cas par défaut.
            return [T("diametre_x"), T("diametre_y"), T("hauteur")]
        if forme == "tore":
            return [T("diametre"), T("diametre_tube"), None]
        if forme == "cadre":
            return [T("largeur"), T("profondeur"), T("hauteur")]
        if forme == "anneau":
            return [T("diametre_x"), T("diametre_y"), T("hauteur")]
        if forme == "taraudage":
            return [T("diametre"), None, T("profondeur_trou")]
        if forme == "engrenage":
            return [T("largeur"), T("profondeur"), T("epaisseur_roue")]
        if forme == "coin":
            return [T("largeur"), T("profondeur"), T("hauteur")]
        if forme == "prisme":
            return [T("diametre"), None, T("hauteur")]
        return [T("diametre_bas"), T("diametre_haut"), T("hauteur")]

    def maj_compte_aretes(self, n: int):
        self._compte_aretes.setText(T("aretes_n", n=n))

    def entrer_dans_le_choix(self):
        """Ouvre directement le choix des arêtes, sans passer par le bouton."""
        if isinstance(self._etape, Arrondi) and not self._btn_choix.isChecked():
            self._btn_choix.setChecked(True)

    def sortir_du_choix(self):
        if self._btn_choix.isChecked():
            self._btn_choix.setChecked(False)

    # ── Changements ────────────────────────────────────────────────────────
    def definir_unite(self, unite: str):
        """Rhabille tous les compteurs de LONGUEUR dans l'unité choisie.

        Leurs bornes sont gardées en millimètres sur chaque compteur (voir
        `_spin`) et reconverties ici : une pièce peut ainsi toujours atteindre
        1000 mm, ce qui fait 39,370 pouces et non 1000 pouces. La rotation, le
        nombre de côtés et l'angle de pente ne sont pas des longueurs : ils ne
        bougent pas."""
        # VERROU indispensable, et mesuré au pilote : les compteurs affichent
        # encore l'ancienne unité, si bien que changer leurs décimales réarrondit
        # la valeur en place (1,181 pouce devenait 1,2). `setDecimals` et
        # `setRange` émettent `valueChanged`, la saisie se croyait modifiée et
        # réécrivait ce 1,2 dans le modèle : une pièce de 30 mm se retrouvait à
        # 1,2 mm pour avoir simplement changé d'unité.
        self._silence = True
        try:
            for s in (*self._dim, *self._pos, self._pos_coupe, self._taille):
                mini, maxi = getattr(s, "_mm", (0.0, 1000.0))
                s.setDecimals(U.decimales(unite))
                s.setSingleStep(U.pas(unite))
                s.setRange(U.vers(mini, unite), U.vers(maxi, unite))
        finally:
            self._silence = False
        # Les valeurs affichées se refont depuis le modèle, qui reste en mm.
        self.set_etape(self._etape, getattr(self, "_collage_vu", True))

    def _valeurs_changees(self, *_a):
        if self._silence or self._etape is None:
            return
        unite = U.courante()
        self._dim_avant = (list(self._etape.dim) if isinstance(self._etape, Forme)
                           else [0.0, 0.0, 0.0])
        if isinstance(self._etape, Forme):
            for i in range(3):
                # Saisi dans l'unité choisie, rangé en millimètres : le modèle,
                # le noyau et les fichiers exportés n'en connaissent pas d'autre.
                if self._dim[i].isVisible():
                    self._etape.dim[i] = U.depuis(self._dim[i].value(), unite)
                self._etape.pos[i] = U.depuis(self._pos[i].value(), unite)
                self._etape.rot[i] = float(self._rot[i].value())
            if getattr(self._etape, "lien_xy", False):
                # Cadenas fermé : on suit celle des deux cotes qui vient de
                # changer, et on recopie sur l'autre.
                change = next((i for i in (0, 1)
                               if abs(self._etape.dim[i] - self._dim_avant[i]) > 1e-9),
                              None)
                if change is not None:
                    self._etape.dim[1 - change] = self._etape.dim[change]
            if self._etape.forme == "sphere":
                self._etape.dim[1] = self._etape.dim[2] = self._etape.dim[0]
            elif self._etape.forme in ("prisme", "cadre"):
                self._etape.cotes = max(3, min(24, int(self._cotes.value())))
            elif self._etape.forme == "engrenage":
                self._etape.cotes = max(6, min(120, int(self._cotes.value())))
            if self._etape.forme in ("cadre", "anneau"):
                self._etape.bord = max(0.2, U.depuis(self._bord.value(), unite))
            if self._etape.forme == "taraudage":
                # Le trou est rond : le second diamètre suit le premier, sinon
                # la boîte englobante et le collage se trompent de largeur.
                self._etape.dim[1] = self._etape.dim[0]
                self._etape.pas = max(0.15, U.depuis(self._pas.value(), unite))
        elif isinstance(self._etape, Coupe):
            self._etape.position = U.depuis(self._pos_coupe.value(), unite)
        else:
            self._etape.taille = U.depuis(self._taille.value(), unite)
        self.modifie.emit()

    def _changer_angle(self, *_a):
        """L'angle pilote la HAUTEUR de la rampe : la longueur ne bouge pas,
        c'est elle qu'on a posée sur la pièce."""
        if self._silence or not isinstance(self._etape, Forme) \
                or self._etape.forme != "coin":
            return
        import math
        angle = max(1.0, min(89.0, float(self._angle.value())))
        self._etape.dim[2] = max(0.1, float(self._etape.dim[0])
                                 * math.tan(math.radians(angle)))
        self._silence = True
        self._dim[2].setValue(U.vers(self._etape.dim[2], U.courante()))
        self._silence = False
        self.modifie.emit()

    def _changer_axe(self, axe: int):
        if not isinstance(self._etape, Coupe) or self._silence:
            return
        self._etape.axe = int(axe)
        for i, b in self._btn_axes.items():
            b.setChecked(i == axe)
        self.modifie.emit()

    def _changer_garder(self, garder: str):
        if not isinstance(self._etape, Coupe) or self._silence:
            return
        self._etape.garder = garder
        for cle, b in self._btn_garder.items():
            b.setChecked(cle == garder)
        self.modifie.emit()

    def _changer_op(self, op: str):
        if self._etape is None or self._silence:
            return
        if op != "matiere" and self.est_premiere and self.est_premiere(self._etape):
            # La première forme ne peut rien creuser : il n'y a rien avant
            # elle. Mais si une AUTRE forme existe, c'est qu'on veut creuser
            # celle là : on descend donc la nôtre juste en dessous, plutôt que
            # de refuser le clic (retour d'Emmanuel sur l'anneau posé en
            # premier, à qui Creuser restait refusé même après avoir ajouté
            # une deuxième pièce).
            if not (self.rendre_creusable and self.rendre_creusable(self._etape)):
                return
        self._etape.op = op
        self.modifie.emit()

    def _maj_cadenas(self):
        ferme = self._cadenas.isChecked()
        self._cadenas.setIcon(S.icone_cadenas(ferme))
        self._cadenas.setToolTip(T("lier_xy_ferme" if ferme else "lier_xy_ouvert"))

    def _changer_cadenas(self, ferme: bool):
        self._maj_cadenas()
        if self._etape is None or self._silence or not isinstance(self._etape, Forme):
            return
        self._etape.lien_xy = bool(ferme)
        if ferme and abs(self._etape.dim[0] - self._etape.dim[1]) > 1e-9:
            # On ferme le cadenas sur une pièce déjà ovale : elle redevient
            # ronde tout de suite, sur la plus grande des deux cotes.
            grand = max(self._etape.dim[0], self._etape.dim[1])
            self._etape.dim[0] = self._etape.dim[1] = grand
            self._silence = True
            for i in (0, 1):
                self._dim[i].setValue(U.vers(grand, U.courante()))
            self._silence = False
        self.modifie.emit()

    def _changer_profil(self, profil: str):
        if self._etape is None or self._silence:
            return
        self._etape.variante = profil
        for nom, b in self._btn_profils.items():
            b.setChecked(nom == profil)
        self.modifie.emit()

    def _changer_genre(self, genre: str):
        if self._etape is None or self._silence:
            return
        self._etape.genre_arrondi = genre
        self._lbl_taille.setText(T("taille_conge" if genre == "conge" else "taille_chanfrein"))
        for g, b in self._btn_genres.items():
            b.setChecked(g == genre)
        self.modifie.emit()

    def _changer_regle(self, *_a):
        if self._etape is None or self._silence:
            return
        self._etape.regle = self._regle.currentData()
        liste = self._etape.regle == "liste"
        self._btn_choix.setVisible(liste)
        self._compte_aretes.setVisible(liste)
        if not liste:
            self.sortir_du_choix()
        self.modifie.emit()

    def _changer_contact(self, collent: bool):
        for colle, b in self._btn_contact.items():
            b.setChecked(colle == collent)
        self.collage_change.emit(collent)

    def _basculer_choix(self, actif: bool):
        """En cours de choix, le bouton d'entrée laisse la place à « Terminé »."""
        self._aide_choix.setVisible(actif)
        self._btn_valider.setVisible(actif)
        self._btn_choix.setVisible(not actif)
        self.choisir_aretes.emit(actif)

    def refresh_theme(self):
        S.rhabiller(self)     # aucune etiquette oubliee
        self.setStyleSheet(S.qss_panneau() + S.qss_champs())
        for b in (*self._btn_ops.values(), *self._btn_genres.values(),
                  *self._btn_contact.values(), *self._btn_axes.values(),
                  *self._btn_garder.values(), *self._btn_profils.values(),
                  self._btn_poser, self._btn_centrer, self._btn_plateau,
                  self._btn_choix):
            b.setStyleSheet(S.qss_bouton())
        # Les deux boutons qui CONCLUENT une action sont en accent : « Terminé »
        # pour le choix des arêtes, « Valider la coupe » pour une découpe. Un
        # bouton qu'on oublie ici garde la palette par défaut de Qt et devient
        # illisible en thème clair (piège récurrent du projet).
        for b in (self._btn_valider, self._btn_valider_coupe):
            b.setStyleSheet(S.qss_bouton("accent"))
        p = S.pal()
        self._cadenas.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; }}"
            f"QPushButton:hover {{ background: {p['BG_ELEVATED']};"
            f" border-radius: 3px; }}")
        self._maj_cadenas()
        for lbl in (*self._dim_lbl, self._lbl_taille, self._lbl_cotes,
                    self._lbl_angle, self._lbl_coupe, self._compte_aretes,
                    self._lbl_bord, self._lbl_pas,
                    self._aide_choix, self._vide):
            lbl.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;")
