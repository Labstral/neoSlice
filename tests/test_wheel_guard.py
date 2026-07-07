"""Garde-molette : la molette au survol ne change plus les valeurs, elle fait
défiler la page (Qt offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QScrollArea, QScrollBar, QVBoxLayout, QWidget)

from ui.wheel_guard import WheelGuard, install


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    install(a)
    return a


def _wheel(app, w):
    pos = w.rect().center()
    ev = QWheelEvent(pos, w.mapToGlobal(pos), QPoint(0, -120), QPoint(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
    app.sendEvent(w, ev)


def test_combo_inchange_au_survol(app):
    cb = QComboBox()
    cb.addItems(["A", "B", "C", "D"])
    cb.setCurrentIndex(1)
    _wheel(app, cb)
    assert cb.currentIndex() == 1


def test_spinbox_inchange_au_survol(app):
    sp = QDoubleSpinBox()
    sp.setRange(0, 100)
    sp.setValue(50.0)
    _wheel(app, sp)
    assert sp.value() == 50.0


def test_scrollarea_parente_defile(app):
    sa = QScrollArea()
    inner = QWidget()
    lay = QVBoxLayout(inner)
    combos = []
    for _ in range(40):
        c = QComboBox()
        c.addItems(["x", "y", "z"])
        lay.addWidget(c)
        combos.append(c)
    sa.setWidget(inner)
    sa.setWidgetResizable(True)
    sa.resize(200, 150)
    sa.show()
    app.processEvents()
    before = sa.verticalScrollBar().value()
    _wheel(app, combos[5])          # molette SUR un combo dans la zone défilante
    app.processEvents()
    assert sa.verticalScrollBar().value() > before   # la page a défilé
    assert combos[5].currentIndex() == 0             # le combo n'a pas bougé


def test_scrollbar_hors_cible():
    # QScrollBar (defilement normal) ne doit PAS être bloquée par le garde
    assert not isinstance(QScrollBar(), WheelGuard._TARGETS)
