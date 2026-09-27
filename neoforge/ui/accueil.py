# -*- coding: utf-8 -*-
"""Écran d'accueil : ce qu'on voit tant qu'aucune pièce n'est ouverte. Pas de
fausse pièce ni de démo trompeuse, juste ce qu'on peut faire et les projets
déjà enregistrés."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from neoforge.ui import style as S
from neoforge.ui.textes import T
from ui.styles.theme import FONT_MAIN


class Accueil(QWidget):
    nouveau = Signal()
    ouvrir = Signal()
    ouvrir_fichier = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panneau")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 48, 48, 48)
        lay.setSpacing(10)
        lay.addStretch()

        self._titre = QLabel(T("accueil_titre"))
        self._titre.setFont(QFont(FONT_MAIN, 22, QFont.Bold))
        lay.addWidget(self._titre, 0, Qt.AlignHCenter)

        self._texte = QLabel(T("accueil_texte"))
        self._texte.setFont(QFont(FONT_MAIN, 10))
        self._texte.setWordWrap(True)
        self._texte.setAlignment(Qt.AlignHCenter)
        self._texte.setMaximumWidth(560)
        lay.addWidget(self._texte, 0, Qt.AlignHCenter)

        lay.addSpacing(18)
        boutons = QHBoxLayout()
        boutons.setSpacing(8)
        boutons.addStretch()
        self._btn_nouveau = QPushButton(T("accueil_nouveau"))
        self._btn_nouveau.clicked.connect(self.nouveau)
        self._btn_ouvrir = QPushButton(T("accueil_ouvrir"))
        self._btn_ouvrir.clicked.connect(self.ouvrir)
        for b in (self._btn_nouveau, self._btn_ouvrir):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(34)
            boutons.addWidget(b)
        boutons.addStretch()
        lay.addLayout(boutons)

        lay.addSpacing(24)
        # Les projets récents tiennent dans UN bouton à menu, comme « Ajouter
        # une forme » ou « Exporter » : une colonne de liens soulignés au
        # milieu de l'accueil faisait désordre (demande d'Emmanuel).
        self._btn_recents = QPushButton(T("accueil_recents"))
        self._btn_recents.setCursor(Qt.PointingHandCursor)
        self._btn_recents.setMinimumHeight(34)
        self._menu_recents = QMenu(self._btn_recents)
        self._btn_recents.setMenu(self._menu_recents)
        lay.addWidget(self._btn_recents, 0, Qt.AlignHCenter)
        lay.addStretch()
        self.refresh_theme()

    @staticmethod
    def _etiquettes(chemins: list[Path]) -> list[str]:
        """Le nom du fichier, et le dossier EN PLUS quand deux projets portent
        le même nom.

        Le cas se présente pour de bon : le dossier d'enregistrement est passé
        à Téléchargements, si bien qu'un « roue » de Documents et un « roue »
        de Téléchargements se retrouvent côte à côte, impossibles à
        distinguer."""
        noms = [c.stem for c in chemins]
        return [f"{c.stem}   ({c.parent.name})" if noms.count(c.stem) > 1 else c.stem
                for c in chemins]

    def maj_recents(self, chemins: list[Path]):
        self._menu_recents.clear()
        etiquettes = self._etiquettes(list(chemins))
        for chemin, etiquette in zip(chemins, etiquettes):
            action = self._menu_recents.addAction(
                etiquette, lambda p=str(chemin): self.ouvrir_fichier.emit(p))
            action.setToolTip(str(chemin))
        self._btn_recents.setVisible(bool(chemins))
        self.refresh_theme()

    def refresh_theme(self):
        S.rhabiller(self)     # aucune etiquette oubliee
        p = S.pal()
        self.setStyleSheet(S.qss_panneau())
        self._titre.setStyleSheet(f"color: {p['TEXT_PRIMARY']}; background: transparent;")
        self._texte.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; background: transparent;")
        self._btn_nouveau.setStyleSheet(S.qss_bouton("accent"))
        self._btn_ouvrir.setStyleSheet(S.qss_bouton())
        self._btn_recents.setStyleSheet(S.qss_bouton())
        self._menu_recents.setStyleSheet(S.qss_menu())
