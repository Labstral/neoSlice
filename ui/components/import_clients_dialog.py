# -*- coding: utf-8 -*-
"""Boîte d'import de clients depuis un CSV (Espace Pro → Clients).

Montre chaque colonne du fichier avec un exemple de valeur et le champ client
deviné ; l'utilisateur corrige si besoin, voit combien de fiches seront
importées, puis confirme. Toute la logique est dans core.business.csv_io.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.business import csv_io
from core.i18n import _
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO


_MAX_CAR = 30        # au-delà, texte abrégé (complet en info-bulle)


def _abrege(texte: str) -> str:
    t = (texte or "").replace("\n", " ")
    return t if len(t) <= _MAX_CAR else t[:_MAX_CAR - 1] + "…"


def _exemple(lignes: list[list[str]], i: int) -> str:
    """Première valeur non vide de la colonne i."""
    for r in lignes:
        if i < len(r) and r[i]:
            return r[i]
    return ""


class ImportClientsDialog(QDialog):
    def __init__(self, parent, entetes: list[str], lignes: list[list[str]],
                 nom_fichier: str = ""):
        super().__init__(parent)
        self._entetes = entetes
        self._lignes = lignes
        self._fichier = nom_fichier
        self._combos: list[QComboBox] = []
        self.setWindowTitle(_("csvio.title"))
        self.setMinimumWidth(640)
        self._build()
        self._apply_theme()
        self._ajuster_hauteur()
        self._maj_resume()

    def _ajuster_hauteur(self):
        """Zone des colonnes à la hauteur EXACTE de son contenu (aucune ligne
        cachée pour un fichier courant), défilement au-delà de 440 px seulement.
        Calculée APRÈS le thème : le style agrandit les listes, une hauteur prise
        avant cachait la dernière colonne (vu à l'audit)."""
        for w in [self._hote] + self._combos:
            w.ensurePolished()
        self._hote.adjustSize()
        self._scroll.setFixedHeight(min(self._hote.sizeHint().height() + 4, 440))
        # Largeur : jamais de défilement horizontal, la fenêtre s'élargit à son
        # contenu (marges + barre verticale comprises), bornée pour les écrans.
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        barre = self._scroll.verticalScrollBar().sizeHint().width()
        besoin = self._hote.sizeHint().width() + barre + 40 + 8
        self.setMinimumWidth(max(640, min(besoin, 960)))

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        self._title = QLabel(_("csvio.title"))
        self._title.setFont(QFont(FONT_MAIN, 12, QFont.Bold))
        lay.addWidget(self._title)

        self._info = QLabel(_("csvio.info", n=len(self._lignes), fichier=self._fichier))
        self._info.setFont(QFont(FONT_MAIN, 9))
        self._info.setWordWrap(True)
        lay.addWidget(self._info)

        # Colonnes : nom dans le fichier | exemple | champ neoSlice
        self._hote = QWidget()
        grille = QGridLayout(self._hote)
        grille.setContentsMargins(0, 0, 6, 0)
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(6)
        self._entetes_lbl = []
        for col, cle in enumerate(("csvio.col_file", "csvio.col_example", "csvio.col_field")):
            h = QLabel(_(cle).upper())
            h.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            self._entetes_lbl.append(h)
            grille.addWidget(h, 0, col)

        devines = csv_io.deviner_colonnes(self._entetes)
        self._noms = []
        self._exemples = []
        for i, entete in enumerate(self._entetes):
            # En-têtes et exemples ABRÉGÉS au-delà de 30 caractères (texte complet
            # en info-bulle) : un vrai export Limova (« Nom du Garage / Raison
            # Sociale », adresses complètes) poussait la colonne « Correspond à »
            # hors de la fenêtre.
            brut = entete or f"#{i + 1}"
            nom = QLabel(_abrege(brut))
            nom.setToolTip(brut)
            nom.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
            valeur = _exemple(self._lignes, i)
            ex = QLabel(_abrege(valeur))
            ex.setToolTip(valeur)
            ex.setFont(QFont(FONT_MONO, 8))
            cb = QComboBox()
            cb.setFont(QFont(FONT_MAIN, 9))
            cb.setMinimumWidth(230)          # « Prénom (ajouté au contact) » en entier
            cb.addItem(_("csvio.ignore"), "")
            for cle in csv_io.CLES_CLIENT:
                cb.addItem(_(csv_io.LIBELLES_CHAMPS[cle]), cle)
            cb.setCurrentIndex(max(0, cb.findData(devines[i])))
            cb.currentIndexChanged.connect(self._maj_resume)
            grille.addWidget(nom, i + 1, 0)
            grille.addWidget(ex, i + 1, 1)
            grille.addWidget(cb, i + 1, 2)
            self._noms.append(nom)
            self._exemples.append(ex)
            self._combos.append(cb)
        grille.setColumnStretch(1, 1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._hote)       # hauteur : voir _ajuster_hauteur
        lay.addWidget(self._scroll, 1)

        self._hint = QLabel(_("csvio.dedup_hint"))
        self._hint.setFont(QFont(FONT_MAIN, 8))
        self._hint.setWordWrap(True)
        lay.addWidget(self._hint)

        self._resume = QLabel("")
        self._resume.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._resume.setWordWrap(True)
        lay.addWidget(self._resume)

        btns = QHBoxLayout()
        btns.addStretch()
        self._cancel = QPushButton(_("client.cancel"))
        self._cancel.clicked.connect(self.reject)
        self._ok = QPushButton(_("csvio.do_import"))
        self._ok.clicked.connect(self.accept)
        for b in (self._cancel, self._ok):
            b.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self._cancel)
        btns.addWidget(self._ok)
        lay.addLayout(btns)

    # ── Données ────────────────────────────────────────────────────────────────
    def colonnes(self) -> list[str]:
        return [cb.currentData() or "" for cb in self._combos]

    def clients(self) -> list[dict]:
        return csv_io.preparer_clients(self._lignes, self.colonnes())

    def _maj_resume(self, *_a):
        cols = set(self.colonnes())
        utile = bool(cols & {"nom", "prenom", "societe", "email"})
        n = len(self.clients()) if utile else 0
        self._ok.setEnabled(utile and n > 0)
        self._resume_ok = utile and n > 0
        self._resume.setText(_("csvio.summary", n=n) if utile
                             else _("csvio.none_mapped"))
        self._style_resume()

    # ── Thème ──────────────────────────────────────────────────────────────────
    def _style_resume(self):
        pal = _T.palette()
        col = pal["TELE_GREEN"] if getattr(self, "_resume_ok", False) else pal["AMBER"]
        self._resume.setStyleSheet(f"color: {col}; background: transparent;")

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        # Hôte + viewport TRANSPARENTS : sans style ils peignent la palette Qt par
        # défaut (sombre) → bande noire en thème clair (vécu sur l'export couleurs).
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._hote.setStyleSheet("background: transparent;")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        for lbl in (self._info, self._hint):
            lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        for h in self._entetes_lbl:
            h.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; "
                            f"letter-spacing: 1px;")
        for nom in self._noms:
            nom.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        for ex in self._exemples:
            ex.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        # Flèche = ICÔNE du thème (celle des compteurs) : le triangle dessiné en
        # bordures CSS sortait en petit trait ou petit carré sous Windows (vu à
        # l'audit visuel, dans les deux thèmes).
        from ui.styles.theme import arrow_icon
        fleche = arrow_icon("down", pal["TEXT_SECONDARY"]).replace("\\", "/")
        css = (f"QComboBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
               f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; "
               f"padding: 3px 6px; min-height: 22px; }}"
               f"QComboBox:hover {{ border-color: {pal['ACCENT']}; }}"
               f"QComboBox::drop-down {{ border: none; width: 20px; }}"
               f"QComboBox::down-arrow {{ image: url(\"{fleche}\"); width: 9px; height: 6px; }}"
               f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
               f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")
        for cb in self._combos:
            cb.setStyleSheet(css)
        self._ok.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}"
            f"QPushButton:disabled {{ background: {pal['INACTIVE']}; "
            f"color: {pal['TEXT_LABEL']}; }}")
        self._cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}")
        self._style_resume()
