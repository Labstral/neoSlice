"""Petite notification 'toast' non intrusive (coin bas-droit du parent).

Auto-disparait apres quelques secondes (fondu), cliquable (ouvre une action), avec
un bouton de fermeture. Utilise pour signaler discretement, par ex., qu'une mise a
jour de la base d'Oen est disponible — sans popup modale qui bloque l'utilisateur.
"""
from __future__ import annotations
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QFrame

from ui.styles.theme import FONT_MAIN, MANAGER as _T


class Toast(QFrame):
    def __init__(self, parent: QWidget, text: str, on_click: Optional[Callable] = None,
                 timeout_ms: int = 9000):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(QCursor(Qt.PointingHandCursor) if on_click else QCursor(Qt.ArrowCursor))
        pal = _T.palette()
        self.setStyleSheet(f"""
            QFrame {{
                background: {pal['BG_ELEVATED']};
                border: 1px solid {pal['ACCENT']};
                border-left: 3px solid {pal['ACCENT_BRIGHT']};
                border-radius: 6px;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 8, 10)
        lay.setSpacing(8)

        col = QVBoxLayout()
        col.setSpacing(1)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setFont(QFont(FONT_MAIN, 8))
        lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent; border: none;")
        lbl.setMaximumWidth(300)
        col.addWidget(lbl)
        lay.addLayout(col, 1)

        close = QPushButton("✕")
        close.setFixedSize(18, 18)
        close.setCursor(QCursor(Qt.PointingHandCursor))
        close.setFont(QFont(FONT_MAIN, 8))
        close.setStyleSheet(f"""
            QPushButton {{ color: {pal['TEXT_LABEL']}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {pal['ERROR_RED']}; }}
        """)
        close.clicked.connect(self._dismiss)
        lay.addWidget(close, 0, Qt.AlignTop)

        self.setFixedWidth(340)
        self.adjustSize()
        self._reposition()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade(0.0, 1.0, 220)
        QTimer.singleShot(timeout_ms, self._dismiss)

    def _reposition(self):
        p = self.parentWidget()
        if not p:
            return
        m = 20
        x = max(0, p.width() - self.width() - m)
        y = max(0, p.height() - self.height() - m)
        self.move(QPoint(x, y))

    def _fade(self, start: float, end: float, dur: int, on_done: Optional[Callable] = None):
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(dur)
        anim.setStartValue(start)
        anim.setEndValue(end)
        if on_done:
            anim.finished.connect(on_done)
        anim.start()
        self._anim = anim  # garder une reference

    def _dismiss(self):
        if not self.isVisible():
            return
        self._fade(self.windowOpacity(), 0.0, 220, self.deleteLater)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_click:
            try:
                self._on_click()
            finally:
                self._dismiss()

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition()


def show_toast(parent: QWidget, text: str, on_click: Optional[Callable] = None,
               timeout_ms: int = 9000) -> Toast:
    """Affiche un toast dans le coin bas-droit de `parent`. Renvoie l'instance."""
    return Toast(parent, text, on_click=on_click, timeout_ms=timeout_ms)
