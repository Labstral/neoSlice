# -*- coding: utf-8 -*-
"""La colonne de gauche : ce qui compose la pièce.

DEUX listes séparées (choix d'Emmanuel) : les FORMES en haut, qui sont les
objets de la scène avec leurs parents et leurs enfants, et les ARRONDIS en
dessous, dans leur propre section. Auparavant tout était mêlé dans une seule
liste d'« étapes » où arrondir des arêtes ajoutait une ligne au milieu des
objets, ce qui brouillait la lecture.

Chaque ligne porte deux commandes à gauche, plutôt que des entrées de menu :
  un ŒIL      ouvert ou fermé, qui montre ou masque ;
  un CADENAS  (formes seulement) qui soude la pièce à son parent : fermé, elle
              ne bouge plus toute seule, c'est tout l'ensemble qui suit.

Les enfants sont DÉCALÉS sous leur parent et reliés par un trait.

Vers l'extérieur, tous les index échangés restent des index d'ÉTAPES : les
deux listes traduisent leurs lignes, la fenêtre n'a pas à le savoir."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QDrag, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QStyle, QStyleOptionViewItem, QStyledItemDelegate, QVBoxLayout,
    QWidget,
)

from neoforge.projet.modele import Arrondi, Coupe, Forme
from neoforge.ui import style as S
from neoforge.ui.textes import T
from ui.styles.theme import FONT_MAIN

FORMES = ("cube", "sphere", "cylindre", "cone", "tore", "coin", "prisme",
          "cadre", "anneau", "engrenage")
MESSAGES = {"vide": "err_vide", "geometrie": "err_geometrie",
            "rien_a_arrondir": "err_rien_a_arrondir", "aucune_arete": "err_aucune_arete",
            "introuvables": "err_introuvables", "trop_grand": "err_trop_grand"}

ROLE_NIVEAU = Qt.ItemDataRole.UserRole + 1      # profondeur dans l'assemblage
ROLE_ACTIF = Qt.ItemDataRole.UserRole + 2
ROLE_VERROU = Qt.ItemDataRole.UserRole + 3
ROLE_FORME = Qt.ItemDataRole.UserRole + 4       # une forme, pas un arrondi
ROLE_LIEE = Qt.ItemDataRole.UserRole + 5        # rattachée à une autre pièce
ROLE_PARTIE = Qt.ItemDataRole.UserRole + 6      # « bas » / « haut » d'une découpe

OEIL_X, CADENAS_X, TEXTE_X, PAS = 15, 37, 56, 20
ZONE_OEIL, ZONE_CADENAS = 27, 49                 # limites de clic, en pixels


def resume(etape, indice: int) -> str:
    if isinstance(etape, Forme):
        d = etape.dim
        if etape.forme == "cube":
            mesures = f"{d[0]:g} × {d[1]:g} × {d[2]:g}"
        elif etape.forme == "sphere":
            mesures = f"Ø{d[0]:g}"
        elif etape.forme == "cylindre":
            # Ovale : on montre les DEUX diamètres, sinon deux cylindres très
            # différents portent la même étiquette dans la liste.
            mesures = (f"Ø{d[0]:g} × {d[2]:g}" if abs(d[0] - d[1]) < 1e-6
                       else f"Ø{d[0]:g} × Ø{d[1]:g} × {d[2]:g}")
        elif etape.forme == "tore":
            mesures = f"Ø{d[0]:g} tube Ø{d[1]:g}"
        elif etape.forme == "coin":
            mesures = f"{d[0]:g} × {d[1]:g} × {d[2]:g}"
        elif etape.forme == "prisme":
            mesures = (f"{T('cotes_n', n=etape.cotes)}  Ø{d[0]:g} × {d[2]:g}")
        elif etape.forme == "cadre":
            mesures = (f"{T('cotes_n', n=etape.cotes)}  {d[0]:g} × {d[1]:g} × "
                       f"{d[2]:g}  bord {etape.bord:g}")
        elif etape.forme == "engrenage":
            mesures = (f"{T('dents_n', n=etape.cotes)}  {d[0]:g} × {d[1]:g} × "
                       f"{d[2]:g}")
        elif etape.forme == "taraudage":
            mesures = f"Ø{d[0]:g} pas {etape.pas:g} × {d[2]:g}"
        elif etape.forme == "anneau":
            mesures = (f"Ø{d[0]:g} × Ø{d[1]:g} × {d[2]:g}  bord {etape.bord:g}"
                       if abs(d[0] - d[1]) > 1e-6 else
                       f"Ø{d[0]:g} × {d[2]:g}  bord {etape.bord:g}")
        else:
            mesures = f"Ø{d[0]:g} → Ø{d[1]:g} × {d[2]:g}"
        marque = {"matiere": "+", "creux": "−", "intersection": "×"}[etape.op]
        return f"{indice}. {marque} {T(etape.forme)}  {mesures} mm"
    if isinstance(etape, Coupe):
        return (f"{indice}. {T('coupe')}  {'XYZ'[etape.axe]} {etape.position:g} mm"
                f"  ({T('garder_' + etape.garder).lower()})")
    regle = {"toutes": "regle_toutes", "haut": "regle_haut", "bas": "regle_bas",
             "verticales": "regle_verticales", "liste": "regle_liste"}[etape.regle]
    return (f"{indice}. {T(etape.genre_arrondi)}  {etape.taille:g} mm  "
            f"({T(regle).lower()})")


def niveau(etapes: list, i: int) -> int:
    """Profondeur de la pièce dans l'assemblage (0 = elle ne dépend de rien)."""
    par_id = {e.ident: e for e in etapes if isinstance(e, Forme)}
    e, n, vus = etapes[i], 0, set()
    while isinstance(e, Forme) and e.parent and e.parent in par_id \
            and e.parent not in vus:
        vus.add(e.parent)
        e = par_id[e.parent]
        n += 1
    return n


class _Arbre(QStyledItemDelegate):
    """Dessine une ligne : l'œil, le cadenas, le trait de liaison, puis le texte
    décalé selon la profondeur."""

    def sizeHint(self, option, index):
        taille = super().sizeHint(option, index)
        taille.setHeight(max(taille.height(), 28))
        return taille

    def paint(self, peintre, option, index):
        p = S.pal()
        rect = option.rect
        profond = int(index.data(ROLE_NIVEAU) or 0)
        choisie = bool(option.state & QStyle.StateFlag.State_Selected)
        peintre.save()
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if choisie:
            peintre.fillRect(rect, QColor(p["ACCENT"]))
            encre = QColor("#ffffff")
        else:
            if profond:                       # un enfant se distingue du fond
                peintre.fillRect(rect, QColor(
                    S.melange(p["BG_SURFACE"], p["ACCENT"], 0.10)))
            pinceau = index.data(Qt.ItemDataRole.ForegroundRole)
            encre = (pinceau.color() if pinceau is not None
                     else QColor(p["TEXT_PRIMARY"]))

        milieu = rect.center().y() + 1
        actif = bool(index.data(ROLE_ACTIF))
        vive = QColor("#ffffff") if choisie else QColor(p["TEXT_SECONDARY"])
        terne = QColor("#ffffff") if choisie else QColor(p["INACTIVE"])
        # Un MORCEAU de découpe ne porte ni œil ni cadenas : il n'existe que par
        # sa coupe, le masquer seul n'aurait aucun sens. Ignorer le clic ne
        # suffit pas, il faut aussi ne pas le dessiner.
        if not index.data(ROLE_PARTIE):
            self._oeil(peintre, rect.left() + OEIL_X, milieu, actif,
                       vive if actif else terne)
        if index.data(ROLE_FORME):
            verrou = bool(index.data(ROLE_VERROU))
            self._cadenas(peintre, rect.left() + CADENAS_X, milieu, verrou,
                          vive if index.data(ROLE_LIEE) else terne)

        depart = rect.left() + TEXTE_X
        if profond:                           # le trait qui relie au parent
            x = depart + (profond - 1) * PAS + 7
            peintre.setPen(QPen(QColor("#ffffff") if choisie
                                else QColor(p["TEXT_LABEL"]), 1))
            peintre.drawLine(x, rect.top(), x, milieu)
            peintre.drawLine(x, milieu, x + 10, milieu)

        zone = QRectF(depart + profond * PAS, rect.top(),
                      max(10, rect.right() - depart - profond * PAS - 6),
                      rect.height())
        police = index.data(Qt.ItemDataRole.FontRole)
        peintre.setFont(police if isinstance(police, QFont) else option.font)
        peintre.setPen(encre)
        texte = peintre.fontMetrics().elidedText(
            str(index.data() or ""), Qt.TextElideMode.ElideRight, int(zone.width()))
        peintre.drawText(zone, int(Qt.AlignmentFlag.AlignVCenter
                                   | Qt.AlignmentFlag.AlignLeft), texte)
        # Ligne survolée pendant un glisser : on voit QUI va devenir le parent.
        if getattr(self.parent(), "_survol", -1) == index.row():
            peintre.setBrush(Qt.BrushStyle.NoBrush)
            peintre.setPen(QPen(QColor(p["ACCENT"]), 2))
            peintre.drawRect(rect.adjusted(1, 1, -2, -2))
        peintre.restore()

    @staticmethod
    def _oeil(peintre, x: int, y: int, ouvert: bool, couleur: QColor):
        peintre.setPen(QPen(couleur, 1.3))
        peintre.setBrush(Qt.BrushStyle.NoBrush)
        if ouvert:
            chemin = QPainterPath(QPointF(x - 7, y))
            chemin.quadTo(QPointF(x, y - 6), QPointF(x + 7, y))
            chemin.quadTo(QPointF(x, y + 6), QPointF(x - 7, y))
            peintre.drawPath(chemin)
            peintre.setBrush(couleur)
            peintre.drawEllipse(QPointF(x, y), 2.1, 2.1)
        else:                                  # paupière baissée, avec deux cils
            chemin = QPainterPath(QPointF(x - 7, y - 1))
            chemin.quadTo(QPointF(x, y + 5), QPointF(x + 7, y - 1))
            peintre.drawPath(chemin)
            peintre.drawLine(QPointF(x - 4, y + 3), QPointF(x - 5, y + 5))
            peintre.drawLine(QPointF(x + 4, y + 3), QPointF(x + 5, y + 5))

    @staticmethod
    def _cadenas(peintre, x: int, y: int, ferme: bool, couleur: QColor):
        peintre.setPen(QPen(couleur, 1.3))
        anse = QRectF(x - 3.2, y - 6.5, 6.4, 7.0)
        peintre.setBrush(Qt.BrushStyle.NoBrush)
        if ferme:
            peintre.drawArc(anse, 0, 180 * 16)
        else:                                  # anse ouverte, décalée à droite
            peintre.drawArc(anse.translated(2.6, -0.5), 0, 150 * 16)
        corps = QRectF(x - 4.6, y - 2.0, 9.2, 7.4)
        peintre.setBrush(couleur if ferme else Qt.BrushStyle.NoBrush)
        peintre.drawRoundedRect(corps, 1.6, 1.6)


class _Liste(QListWidget):
    """Une des deux listes. Celle des formes accepte qu'on DÉPOSE une pièce sur
    une autre pour la lui rattacher ; déposer dans le vide la détache.

    Qt ne réorganise RIEN de lui même : les listes sont toujours reconstruites à
    partir du projet, sinon les deux se contrediraient."""
    depose = Signal(int, int)             # ligne déplacée, ligne visée (-1 = détacher)
    commande = Signal(str, int)           # « masquer » ou « verrou », ligne

    def __init__(self, deplacable: bool = False, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setItemDelegate(_Arbre(self))
        self.setTextElideMode(Qt.ElideRight)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._survol = -1                 # ligne visée pendant un glisser
        self._deplacable = bool(deplacable)
        if self._deplacable:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)

    # ── Commandes de ligne ─────────────────────────────────────────────────
    def mousePressEvent(self, evenement):
        index = self.indexAt(evenement.position().toPoint())
        if index.isValid() and evenement.button() == Qt.MouseButton.LeftButton:
            x = evenement.position().x() - self.visualRect(index).left()
            if x < ZONE_OEIL and not index.data(ROLE_PARTIE):
                self.commande.emit("masquer", index.row())
                return
            if x < ZONE_CADENAS and index.data(ROLE_FORME):
                self.commande.emit("verrou", index.row())
                return
        super().mousePressEvent(evenement)

    # ── Glisser déposer (liste des formes seulement) ───────────────────────
    def startDrag(self, actions):
        """Vignette TRANSLUCIDE de la ligne tirée, comme dans les logiciels
        courants (demande d'Emmanuel). Elle est peinte par le même délégué que
        la liste, donc elle suit le thème clair comme le sombre."""
        ligne = self.currentRow()
        if not self._deplacable or ligne < 0:
            return
        index = self.model().index(ligne, 0)
        rect = self.visualRect(index)
        if rect.width() < 4 or rect.height() < 4:
            return
        ratio = self.devicePixelRatioF()
        image = QImage(int(rect.width() * ratio), int(rect.height() * ratio),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        p = S.pal()
        peintre = QPainter(image)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        peintre.setOpacity(0.82)                      # la transparence demandée
        contour = QPainterPath()
        contour.addRoundedRect(QRectF(0.5, 0.5, rect.width() - 1,
                                      rect.height() - 1), 3, 3)
        peintre.fillPath(contour, QColor(p["BG_ELEVATED"]))
        peintre.setClipPath(contour)                  # rien ne déborde des coins
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, rect.width(), rect.height())
        option.font = self.font()
        option.state = QStyle.StateFlag.State_Enabled
        self.itemDelegate().paint(peintre, option, index)
        peintre.setClipping(False)
        peintre.setPen(QPen(QColor(p["ACCENT"]), 1))
        peintre.setBrush(Qt.BrushStyle.NoBrush)
        peintre.drawPath(contour)
        peintre.end()

        donnees = QMimeData()
        donnees.setData("application/x-neoforge-forme", str(ligne).encode())
        tirage = QDrag(self)
        tirage.setMimeData(donnees)
        tirage.setPixmap(QPixmap.fromImage(image))
        tirage.setHotSpot(QPoint(28, rect.height() // 2))
        tirage.exec(Qt.DropAction.MoveAction)
        self._viser(-1)

    def _viser(self, ligne: int):
        if ligne != self._survol:
            self._survol = ligne
            self.viewport().update()

    def dragEnterEvent(self, evenement):
        if evenement.source() is self:
            evenement.accept()
        else:
            super().dragEnterEvent(evenement)

    def dragMoveEvent(self, evenement):
        if evenement.source() is self:
            vise = self.indexAt(evenement.position().toPoint()).row()
            self._viser(vise if vise != self.currentRow() else -1)
            evenement.accept()
        else:
            super().dragMoveEvent(evenement)

    def dragLeaveEvent(self, evenement):
        self._viser(-1)
        super().dragLeaveEvent(evenement)

    def dropEvent(self, evenement):
        if evenement.source() is not self:
            super().dropEvent(evenement)
            return
        depart = self.currentRow()
        cible = self.indexAt(evenement.position().toPoint()).row()
        self._viser(-1)
        evenement.setDropAction(Qt.DropAction.IgnoreAction)
        evenement.accept()
        if depart >= 0 and depart != cible:
            self.depose.emit(depart, cible)


class Pile(QWidget):
    selection_changee = Signal(int)     # index d'ÉTAPE (-1 = plus rien)
    ajouter_forme = Signal(str)         # « cube », « sphere », « cylindre », « cone »
    ajouter_arrondi = Signal()
    ajouter_coupe = Signal()
    action = Signal(str, int)           # monter / descendre / dupliquer / supprimer
    #                                     / masquer / verrou, avec l'index d'ÉTAPE
    rattacher = Signal(int, int)        # pièce, nouveau parent (-1 = détacher)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panneau")
        self._index_formes: list[int] = []      # ligne → index d'étape
        self._index_arrondis: list[int] = []
        self._silence = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self._titre_formes = S.titre_section(T("pile"))
        lay.addWidget(self._titre_formes)
        self._liste = _Liste(deplacable=True)
        self._liste.setFont(QFont(FONT_MAIN, 9))
        self._liste.depose.connect(self._depose)
        self._liste.commande.connect(lambda nom, ligne:
                                     self._commande(nom, ligne, True))
        self._liste.currentRowChanged.connect(lambda l: self._choisir(l, True))
        self._liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self._liste.customContextMenuRequested.connect(
            lambda pos: self._menu_contextuel(pos, True))
        self._liste.installEventFilter(self)
        lay.addWidget(self._liste, 3)

        self._btn_forme = QPushButton(T("ajouter_forme"))
        self._btn_forme.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self._btn_forme)
        # Pas d'entrée « trou traversant » : n'importe quelle forme réglée sur
        # « Creuser » fait la même chose, en mieux (choix d'Emmanuel).
        for f in FORMES:
            menu.addAction(T(f), lambda f=f: self.ajouter_forme.emit(f))
        # Les logements d'écrou : un six pans creux aux cotes normalisées, de
        # M2 à M12, ce qui évite d'avoir à les calculer soi même.
        from neoforge.projet.ergonomie import ECROUS, TARAUDAGES
        menu.addSeparator()
        self._menu_ecrous = menu.addMenu(T("logement_ecrou"))
        for taille in ECROUS:
            self._menu_ecrous.addAction(
                taille, lambda t=taille: self.ajouter_forme.emit(f"ecrou:{t}"))
        # Trou fileté, dans lequel la vis se visse directement.
        self._menu_taraudages = menu.addMenu(T("trou_taraude"))
        for taille in TARAUDAGES:
            self._menu_taraudages.addAction(
                taille, lambda t=taille: self.ajouter_forme.emit(f"taraudage:{t}"))
        self._btn_forme.setMenu(menu)
        self._menu_formes = menu
        lay.addWidget(self._btn_forme)

        # ── Les arrondis, dans leur PROPRE section ──────────────────────────
        self._titre_arrondis = S.titre_section(T("arrondis"))
        lay.addWidget(self._titre_arrondis)
        self._arrondis = _Liste()
        self._arrondis.setFont(QFont(FONT_MAIN, 9))
        self._arrondis.commande.connect(lambda nom, ligne:
                                        self._commande(nom, ligne, False))
        self._arrondis.currentRowChanged.connect(lambda l: self._choisir(l, False))
        self._arrondis.setContextMenuPolicy(Qt.CustomContextMenu)
        self._arrondis.customContextMenuRequested.connect(
            lambda pos: self._menu_contextuel(pos, False))
        self._arrondis.installEventFilter(self)
        self._arrondis.setMaximumHeight(120)
        lay.addWidget(self._arrondis, 1)

        self._btn_arrondi = QPushButton(T("ajouter_arrondi"))
        self._btn_arrondi.setCursor(Qt.PointingHandCursor)
        self._btn_arrondi.clicked.connect(self.ajouter_arrondi)
        lay.addWidget(self._btn_arrondi)

        self._btn_coupe = QPushButton(T("ajouter_coupe"))
        self._btn_coupe.setCursor(Qt.PointingHandCursor)
        self._btn_coupe.clicked.connect(self.ajouter_coupe)
        lay.addWidget(self._btn_coupe)

        outils = QHBoxLayout()
        outils.setSpacing(6)
        self._boutons = {}
        # Pas de bouton « masquer » : l'œil de chaque ligne s'en charge.
        for nom, libelle in (("monter", "▲"), ("descendre", "▼"),
                             ("dupliquer", "⧉"), ("supprimer", "✕")):
            b = QPushButton(libelle)
            b.setFixedWidth(34)
            b.setToolTip(T(nom))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, n=nom: self._outil(n))
            outils.addWidget(b)
            self._boutons[nom] = b
        outils.addStretch()
        lay.addLayout(outils)
        self.refresh_theme()

    # ── Traduction ligne ↔ étape ───────────────────────────────────────────
    def _etape_de(self, ligne: int, formes: bool) -> int:
        table = self._index_formes if formes else self._index_arrondis
        return table[ligne] if 0 <= ligne < len(table) else -1

    def partie(self) -> str:
        """Quel MORCEAU d'une découpe est choisi : « bas », « haut », ou rien.

        Les deux morceaux d'une coupe « garder les deux » pointent vers la MÊME
        étape : c'est cette réponse qui dit lequel des deux on tient."""
        return getattr(self, "_partie", "")

    def _selection_courante(self) -> int:
        if self._liste.currentRow() >= 0:
            return self._etape_de(self._liste.currentRow(), True)
        return self._etape_de(self._arrondis.currentRow(), False)

    def _choisir(self, ligne: int, formes: bool):
        """Une ligne cliquée dans une liste vide la sélection de l'autre."""
        if self._silence:
            return
        autre = self._arrondis if formes else self._liste
        if ligne >= 0 and autre.currentRow() >= 0:
            self._silence = True
            autre.setCurrentRow(-1)
            autre.clearSelection()
            self._silence = False
        parties = getattr(self, "_parties", [])
        self._partie = (parties[ligne] if formes and 0 <= ligne < len(parties)
                        else "")
        self.selection_changee.emit(self._etape_de(ligne, formes) if ligne >= 0 else -1)

    def _commande(self, nom: str, ligne: int, formes: bool):
        index = self._etape_de(ligne, formes)
        if index >= 0:
            self.action.emit(nom, index)

    def _depose(self, ligne: int, cible: int):
        enfant = self._etape_de(ligne, True)
        parent = self._etape_de(cible, True) if cible >= 0 else -1
        if enfant >= 0:
            self.rattacher.emit(enfant, parent)

    def _outil(self, nom: str):
        index = self._selection_courante()
        if index >= 0:
            self.action.emit(nom, index)

    def _menu_contextuel(self, position, formes: bool):
        liste = self._liste if formes else self._arrondis
        ligne = liste.indexAt(position).row()
        if ligne < 0:
            return
        liste.setCurrentRow(ligne)
        index = self._etape_de(ligne, formes)
        menu = QMenu(self)
        # Feuille de style EXPLICITE : sans elle, le menu prend la palette par
        # défaut de Qt et la ligne survolée devenait un blanc illisible en thème
        # clair (retour d'Emmanuel).
        menu.setStyleSheet(S.qss_menu())
        for nom in ("monter", "descendre", "dupliquer", "supprimer"):
            menu.addAction(T(nom), lambda n=nom: self.action.emit(n, index))
        menu.exec(liste.mapToGlobal(position))

    def eventFilter(self, objet, evenement):
        """Suppr efface la ligne sélectionnée (demande d'Emmanuel).

        Les `getattr` ne sont pas de la prudence gratuite : poser le filtre sur
        la première liste le déclenche DÉJÀ pendant la construction, quand la
        seconde n'existe pas encore, et la fenêtre entière échouait à s'ouvrir."""
        from PySide6.QtCore import QEvent
        listes = (getattr(self, "_liste", None), getattr(self, "_arrondis", None))
        if (objet in listes
                and evenement.type() == QEvent.Type.KeyPress
                and evenement.key() == Qt.Key_Delete):
            index = self._etape_de(objet.currentRow(), objet is self._liste)
            if index >= 0:
                self.action.emit("supprimer", index)
            return True
        return super().eventFilter(objet, evenement)

    # ── Sélection depuis l'extérieur ───────────────────────────────────────
    def selectionner(self, index: int):
        """Sélection venue d'ailleurs (clic sur la pièce dans la vue 3D)."""
        for liste, table in ((self._liste, self._index_formes),
                             (self._arrondis, self._index_arrondis)):
            if index in table:
                self._silence = True
                autre = self._arrondis if liste is self._liste else self._liste
                autre.setCurrentRow(-1)
                autre.clearSelection()
                self._silence = False
                liste.setCurrentRow(table.index(index))
                return

    def deselectionner(self):
        """Plus rien de sélectionné (clic dans le vide de la vue 3D)."""
        self._silence = True
        for liste in (self._liste, self._arrondis):
            liste.setCurrentRow(-1)
            liste.clearSelection()
        self._silence = False
        self._partie = ""
        self.selection_changee.emit(-1)

    # ── Remplissage ────────────────────────────────────────────────────────
    def remplir(self, etapes: list, resultats: list, selection: int):
        p = S.pal()
        self._silence = True
        self._liste.blockSignals(True)
        self._arrondis.blockSignals(True)
        self._liste.clear()
        self._arrondis.clear()
        self._index_formes, self._index_arrondis = [], []
        # Une entrée par ligne de la liste des FORMES : vide pour une vraie
        # forme, « bas » ou « haut » pour un morceau de découpe. Elle doit rester
        # alignée sur `_index_formes`, sinon un clic choisit la mauvaise pièce.
        self._parties = []
        for i, etape in enumerate(etapes):
            forme = isinstance(etape, Forme)
            liste = self._liste if forme else self._arrondis
            table = self._index_formes if forme else self._index_arrondis
            table.append(i)
            if forme:
                self._parties.append("")
            texte = resume(etape, len(table))          # numéroté DANS sa liste
            r = resultats[i] if i < len(resultats) else None
            erreur = getattr(r, "erreur", None)
            if erreur:
                detail = (getattr(r, "detail", {}) or {})
                if erreur == "trop_grand" and detail.get("max"):
                    texte += "  ·  " + T("err_trop_grand_max", max=detail["max"])
                else:
                    texte += "  ·  " + T(MESSAGES.get(erreur, "err_geometrie"))
            elif getattr(r, "detail", {}).get("manquantes"):
                texte += "  ·  " + T("aretes_manquantes", n=r.detail["manquantes"])
            item = QListWidgetItem(texte)
            item.setToolTip(texte)                     # texte complet au survol
            item.setData(ROLE_NIVEAU, niveau(etapes, i) if forme else 0)
            item.setData(ROLE_ACTIF, bool(etape.actif))
            item.setData(ROLE_FORME, forme)
            item.setData(ROLE_VERROU, bool(getattr(etape, "verrou", False)))
            item.setData(ROLE_LIEE, bool(getattr(etape, "parent", "")))
            if erreur:
                item.setForeground(_couleur(p["ERROR_RED"]))
            elif not etape.actif:
                police = QFont(FONT_MAIN, 9)
                police.setStrikeOut(True)
                item.setFont(police)
                item.setForeground(_couleur(p["TEXT_LABEL"]))
            liste.addItem(item)
            # « Garder les deux » donne DEUX pièces : elles se listent parmi les
            # formes, là où Emmanuel s'attend à les retrouver (« je suis censé
            # retrouver deux pièces dans les formes à gauche »), tandis que la
            # découpe garde sa propre ligne pour régler le plan.
            if isinstance(etape, Coupe) and etape.garder == "les_deux" \
                    and etape.actif and not erreur:
                for cle in ("bas", "haut"):
                    self._index_formes.append(i)
                    self._parties.append(cle)
                    morceau = QListWidgetItem(
                        f"{len(self._index_formes)}. {T('partie_' + cle)}")
                    morceau.setToolTip(morceau.text())
                    morceau.setData(ROLE_NIVEAU, 0)
                    morceau.setData(ROLE_ACTIF, True)
                    morceau.setData(ROLE_FORME, False)
                    morceau.setData(ROLE_VERROU, False)
                    morceau.setData(ROLE_LIEE, False)
                    morceau.setData(ROLE_PARTIE, cle)
                    self._liste.addItem(morceau)
        # La section des arrondis ne s'affiche que s'il y en a.
        vide = not self._index_arrondis
        self._titre_arrondis.setVisible(not vide)
        self._arrondis.setVisible(not vide)
        # Les deux morceaux d'une découpe visent la MÊME étape : sans cette
        # précaution, un recalcul replaçait la sélection sur le PREMIER des deux.
        # L'application croyait alors tenir le bas alors qu'on tenait le haut, et
        # c'est la mauvaise pièce qui se déplaçait (mesuré au pilote).
        voulu = getattr(self, "_partie", "")
        candidates = [k for k, e in enumerate(self._index_formes) if e == selection]
        self._liste.setCurrentRow(
            next((k for k in candidates if self._parties[k] == voulu),
                 candidates[0] if candidates else -1))
        self._arrondis.setCurrentRow(
            self._index_arrondis.index(selection)
            if selection in self._index_arrondis else -1)
        self._liste.blockSignals(False)
        self._arrondis.blockSignals(False)
        self._silence = False
        self._maj_boutons(etapes, selection)

    def _maj_boutons(self, etapes: list, selection: int):
        valide = 0 <= selection < len(etapes)
        formes = sum(1 for e in etapes if isinstance(e, Forme))
        seule_forme = (valide and isinstance(etapes[selection], Forme) and formes <= 1)
        for b in self._boutons.values():
            b.setEnabled(valide)
        if valide:
            self._boutons["monter"].setEnabled(selection > 0)
            self._boutons["descendre"].setEnabled(selection < len(etapes) - 1)
            self._boutons["supprimer"].setEnabled(not seule_forme)
        self._btn_arrondi.setEnabled(formes > 0)

    def refresh_theme(self):
        S.rhabiller(self)     # aucune etiquette oubliee
        self.setStyleSheet(S.qss_panneau())
        for liste in (self._liste, self._arrondis):
            liste.setStyleSheet(S.qss_liste())
            liste.viewport().update()
        for b in (self._btn_forme, self._btn_arrondi, self._btn_coupe,
                  *self._boutons.values()):
            b.setStyleSheet(S.qss_bouton())
        self._menu_formes.setStyleSheet(S.qss_menu())
        self._menu_ecrous.setStyleSheet(S.qss_menu())


def _couleur(hexa: str):
    from PySide6.QtGui import QBrush, QColor as _QColor
    return QBrush(_QColor(hexa))
