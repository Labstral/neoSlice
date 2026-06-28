"""Utilitaires de mise en page PDF tolérants à la police.

Les PDF QPdfWriter dessinent dans des boîtes à largeur fixe. Comme la police
dépend de l'OS (Segoe UI sur Windows, SF Pro Text sur macOS, Ubuntu sur Linux),
un même texte n'a pas la même largeur partout → risque de débordement/rognage.

`fit_font` réduit la taille d'un titre jusqu'à ce qu'il rentre ; `elided`
tronque proprement un texte trop long avec « … ». À utiliser sur tout ce qui
pourrait varier selon la langue/police (titres, désignations, noms).
"""
from __future__ import annotations


def fit_font(base_font, text: str, max_w: float, min_pt: int = 9):
    """Renvoie une copie de `base_font` réduite pour que `text` tienne dans
    `max_w` (jamais sous `min_pt`)."""
    from PySide6.QtGui import QFont, QFontMetrics
    f = QFont(base_font)
    if not text:
        return f
    while f.pointSize() > min_pt and QFontMetrics(f).horizontalAdvance(str(text)) > max_w:
        f.setPointSize(f.pointSize() - 1)
    return f


def elided(font, text, max_w: float) -> str:
    """Texte tronqué avec « … » s'il dépasse `max_w` (sinon inchangé)."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtCore import Qt
    if text is None:
        return ""
    return QFontMetrics(font).elidedText(str(text), Qt.TextElideMode.ElideRight, int(max_w))
