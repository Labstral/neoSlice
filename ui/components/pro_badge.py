"""Badge « Pro » au dégradé cyan → violet, style futuriste.

Widget réutilisable : utilisé dans la barre du haut (à côté de « neoSlice »)
et dans le titre du PaywallDialog, pour un rendu identique partout.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen

from PySide6.QtWidgets import QLabel

from ui.styles.theme import FONT_MAIN

# Dégradé futuriste cyan → violet
PRO_CYAN = "#22D3EE"
PRO_VIOLET = "#A855F7"


class ProBadge(QLabel):
    """Affiche un texte (« Pro ») peint avec un dégradé cyan → violet."""

    def __init__(self, text: str = "Pro", point_size: int = 11,
                 letter_spacing: float = 1.5, parent=None):
        super().__init__(text, parent)
        font = QFont(FONT_MAIN, point_size, QFont.Bold)
        if letter_spacing:
            font.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
        self.setFont(font)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(PRO_CYAN))
        grad.setColorAt(1.0, QColor(PRO_VIOLET))
        painter.setPen(QPen(QBrush(grad), 0))
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(Qt.AlignCenter), self.text())
