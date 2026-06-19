"""Overlay d'animation de confettis — célébration fluide (~60 fps).

Utilisé sur la fenêtre de remerciement après activation de neoSlice Pro.
Canon de particules depuis les deux coins bas, gravité + rotation, puis chute.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

# Palette festive (brand cyan/violet + couleurs vives)
_COLORS = ["#22D3EE", "#A855F7", "#F472B6", "#FACC15", "#34D399", "#60A5FA", "#FB7185"]


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "size", "angle", "vangle", "color", "shape", "life")

    def __init__(self, x: float, y: float, vx: float, vy: float):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = random.uniform(6.0, 11.0)
        self.angle = random.uniform(0, 360)
        self.vangle = random.uniform(-14, 14)
        self.color = QColor(random.choice(_COLORS))
        self.shape = random.choice(("rect", "rect", "circle"))
        self.life = 0.0


class ConfettiOverlay(QWidget):
    """Widget transparent posé par-dessus son parent ; `burst()` lance l'animation."""

    GRAVITY = 0.42
    DRAG = 0.992

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self._particles: list[_Particle] = []
        self._timer = QTimer(self)
        self._timer.setInterval(16)   # ~60 fps
        self._timer.timeout.connect(self._tick)

    def burst(self, count: int = 90):
        """Lance un canon de confettis depuis les deux coins bas."""
        if self.parent() is not None:
            self.resize(self.parent().size())
        w = self.width() or 440
        h = self.height() or 400
        half = count // 2
        for _ in range(half):
            ang = math.radians(random.uniform(58, 78))   # vers le haut-droite
            spd = random.uniform(13, 22)
            self._particles.append(_Particle(0, h, math.cos(ang) * spd, -math.sin(ang) * spd))
        for _ in range(count - half):
            ang = math.radians(random.uniform(58, 78))   # vers le haut-gauche
            spd = random.uniform(13, 22)
            self._particles.append(_Particle(w, h, -math.cos(ang) * spd, -math.sin(ang) * spd))
        self.raise_()
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        h = self.height()
        alive = []
        for p in self._particles:
            p.vy += self.GRAVITY
            p.vx *= self.DRAG
            p.x += p.vx
            p.y += p.vy
            p.angle += p.vangle
            p.life += 1
            if p.y < h + 40:
                alive.append(p)
        self._particles = alive
        if not self._particles:
            self._timer.stop()
        self.update()

    def paintEvent(self, _event):
        if not self._particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for p in self._particles:
            painter.save()
            painter.translate(p.x, p.y)
            painter.rotate(p.angle)
            painter.setBrush(p.color)
            s = p.size
            if p.shape == "circle":
                painter.drawEllipse(QPointF(0, 0), s / 2, s / 2)
            else:
                painter.drawRect(int(-s / 2), int(-s / 3), int(s), int(s * 0.66))
            painter.restore()
