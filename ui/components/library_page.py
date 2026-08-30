# -*- coding: utf-8 -*-
"""Onglet Bibliothèque de l'Espace Pro — pièces exportées, réimprimables à
l'identique.

Chaque export réussi mémorise automatiquement la pièce : fichier source (chemin
+ empreinte SHA-1, PAS de copie), imprimante, filament, plateau, buse et la
config EXACTE générée, plus une vignette capturée du viewer. Des mois plus
tard, « Réimprimer à l'identique » recharge tout — plus besoin de se souvenir
des réglages qui marchaient.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox,
)

from core.i18n import _
from core.business import store
from ui.styles.theme import MANAGER as _T, FONT_MAIN


class LibraryPage(QWidget):
    reprint_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(10)
        self._intro = QLabel(_("library.intro")); self._intro.setFont(QFont(FONT_MAIN, 9))
        self._intro.setWordWrap(True)
        lay.addWidget(self._intro)

        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0); self._lay.setSpacing(8)
        self._lay.addStretch()
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, 1)

        self._empty = QLabel(_("library.none")); self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True); self._empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty)

        self.refresh()
        self.apply_theme()
        _T.register(self.apply_theme)

    def showEvent(self, event):
        # De nouveaux exports ont pu arriver depuis un autre écran.
        super().showEvent(event)
        self.refresh()

    def _box_qss(self):
        pal = _T.palette()
        return (f"QMessageBox {{ background: {pal['BG_PANEL']}; }}"
                f"QMessageBox QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }}"
                f"QMessageBox QPushButton {{ background: {pal['BG_SURFACE']}; "
                f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                f"border-radius: 3px; padding: 4px 16px; }}")

    def _ask(self, title, text) -> bool:
        m = QMessageBox(self); m.setWindowTitle(title); m.setText(text)
        m.setIcon(QMessageBox.Question)
        m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        m.setStyleSheet(self._box_qss())
        return m.exec() == QMessageBox.Yes

    def refresh(self):
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        entries = store.list_library()
        for e in entries:
            self._lay.insertWidget(self._lay.count() - 1, self._card(e))
        self._empty.setVisible(not entries)
        self._scroll.setVisible(bool(entries))

    def _card(self, e: dict) -> QFrame:
        pal = _T.palette()
        card = QFrame(); card.setObjectName("libcard")
        card.setStyleSheet(f"QFrame#libcard {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(12)

        # Vignette (capturée du viewer à l'export) ; cadre vide sinon.
        vig = QLabel()
        vig.setFixedSize(72, 54)
        vig.setAlignment(Qt.AlignCenter)
        vig.setStyleSheet(f"background: {pal['BG_SURFACE']}; border: 1px solid "
                          f"{pal['INACTIVE']}; border-radius: 4px;")
        vp = e.get("vignette") or ""
        if vp and Path(vp).exists():
            pm = QPixmap(vp)
            if not pm.isNull():
                vig.setPixmap(pm.scaled(70, 52, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation))
        lay.addWidget(vig)

        info = QVBoxLayout(); info.setSpacing(2)
        t = QLabel(e.get("nom") or "—")
        t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)
        bits = [e.get("date", ""), e.get("imprimante", ""), e.get("filament", "")]
        try:
            bits.append(f"{float(e.get('buse_mm') or 0.4):g} mm")
        except (TypeError, ValueError):
            pass
        n_exp = int(e.get("exports") or 1)
        if n_exp > 1:
            bits.append(_("library.exports", n=n_exp))
        sub = QLabel("  ·  ".join(b for b in bits if b))
        sub.setFont(QFont(FONT_MAIN, 8))
        sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        # Fichier source disparu (déplacé/supprimé) : le dire SUR la carte, pas
        # seulement au clic — l'utilisateur comprend pourquoi ça ne marchera pas.
        src = e.get("fichier") or ""
        if not src or not Path(src).exists():
            warn = QLabel(_("library.file_missing"))
            warn.setFont(QFont(FONT_MAIN, 8))
            warn.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
            info.addWidget(warn)
        lay.addLayout(info, 1)

        rep = QPushButton(_("library.reprint"))
        rep.setCursor(Qt.PointingHandCursor); rep.setFixedHeight(26)
        acc = pal["ACCENT"]
        rep.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {acc}; "
            f"border: 1px solid {acc}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {acc}; color: #fff; }}")
        rep.clicked.connect(lambda: self.reprint_requested.emit(dict(e)))
        lay.addWidget(rep)

        sup = QPushButton("✕")
        sup.setCursor(Qt.PointingHandCursor); sup.setFixedHeight(26)
        red = pal["ERROR_RED"]
        sup.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {red}; "
            f"border: 1px solid {red}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {red}; color: #fff; }}")
        sup.clicked.connect(lambda: self._delete(e))
        lay.addWidget(sup)
        return card

    def _delete(self, e: dict):
        if self._ask(_("library.delete"), _("library.delete_confirm")):
            store.delete_library_entry(e["id"])
            self.refresh()

    def apply_theme(self):
        pal = _T.palette()
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._host.setStyleSheet("background: transparent;")
        self._intro.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._empty.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        self.refresh()
