"""Garde-molette global de neoSlice.

Empeche un simple scroll de la molette EN SURVOL de modifier la valeur d'un menu
deroulant (QComboBox), d'un champ numerique (QSpinBox / QDoubleSpinBox) ou d'un
curseur (QSlider / QDial) : piege Qt classique ou, en scrollant une page, la souris
passe au-dessus d'un de ces widgets et change l'option sans que l'utilisateur le
veuille.

Comportement : au lieu de laisser le widget consommer la molette, on la REDIRIGE
vers la premiere zone defilante parente (on scrolle la page). S'il n'y a pas de zone
defilante, la molette est simplement ignoree. Dans tous les cas, la valeur ne change
jamais au survol. Pour changer une valeur, l'utilisateur clique (combo -> liste
deroulante avec son propre defilement ; spin -> fleches ou saisie).

QScrollBar est un QAbstractSlider mais N'EST PAS vise : le defilement des barres et
des zones defilantes reste parfaitement normal.

Usage (une fois, apres creation de la QApplication) :
    from ui.wheel_guard import install as install_wheel_guard
    install_wheel_guard(app)
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import (
    QApplication, QComboBox, QAbstractSpinBox, QSlider, QDial, QAbstractScrollArea,
)


class WheelGuard(QObject):
    """Filtre d'evenements a installer sur la QApplication."""

    _TARGETS = (QComboBox, QAbstractSpinBox, QSlider, QDial)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, self._TARGETS):
            # Rediriger la molette vers la premiere zone defilante parente (scroll de
            # la page), sinon simplement l'ignorer. La valeur du widget ne change pas.
            p = obj.parentWidget()
            while p is not None:
                if isinstance(p, QAbstractScrollArea):
                    QApplication.sendEvent(p.viewport(), event)
                    break
                p = p.parentWidget()
            return True
        return False


def install(app: QApplication) -> WheelGuard:
    """Installe le garde-molette sur `app`. Renvoie l'instance (gardee sur `app`
    comme attribut pour eviter le ramasse-miettes)."""
    guard = WheelGuard()
    app.installEventFilter(guard)
    app._neoslice_wheel_guard = guard   # reference anti-GC
    return guard
