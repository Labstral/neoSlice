"""Aides visuelles PARTAGÉES pour les bobines (Espace Pro et fenêtres d'export).

Objectif (retour utilisateur Dominique) : retrouver une bobine d'un coup d'œil
partout où on en choisit une — pastille de couleur dans TOUS les menus déroulants
de bobines + emplacement machine/AMS visible (« X1C — AMS 2 »).

Utilisé par : fenêtre de décompte après impression (main_window), devis
(cost_calculator), répartition des couleurs (color_export_dialog), commandes
(orders_page), liste des bobines (pro_hub).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def spool_pixmap(colors, size: int = 14) -> QPixmap:
    """Pastille RONDE d'une bobine : une couleur pleine, ou des SECTEURS égaux
    pour une bobine multi-couleur (dual/tri/quadri — demande Matthieu D.).
    `colors` : un hex seul ou une liste d'hex (max 4). Léger contour sombre
    translucide → visible même blanc sur clair ou noir sur sombre."""
    if isinstance(colors, str) or colors is None:
        colors = [colors]
    cols = []
    for c in colors[:4]:
        qc = QColor(c or "#888888")
        cols.append(qc if qc.isValid() else QColor("#888888"))
    if not cols:
        cols = [QColor("#888888")]
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    try:
        if len(cols) == 1:
            p.setBrush(cols[0])
            p.setPen(QColor(0, 0, 0, 90))
            p.drawEllipse(1, 1, size - 2, size - 2)
        else:
            # secteurs égaux, départ en haut (12 h), sens horaire — drawPie
            # compte en 1/16 de degré, sens anti-horaire depuis 3 h
            p.setPen(Qt.NoPen)
            part = 360 * 16 // len(cols)
            for i, c in enumerate(cols):
                p.setBrush(c)
                p.drawPie(1, 1, size - 2, size - 2, 90 * 16 - (i + 1) * part, part)
            p.setBrush(Qt.NoBrush)
            p.setPen(QColor(0, 0, 0, 90))
            p.drawEllipse(1, 1, size - 2, size - 2)
    finally:
        p.end()
    return pm


def spool_icon(colors, size: int = 14) -> QIcon:
    """Icône de pastille pour QComboBox.addItem(icon, …) — voir spool_pixmap.
    Accepte un hex SEUL (compat historique) ou la liste store.spool_couleurs(s)."""
    return QIcon(spool_pixmap(colors, size))


def combo_icon_size(combo) -> None:
    """Taille d'icône homogène pour un combo à pastilles."""
    combo.setIconSize(QSize(14, 14))


def emplacement_suffix(spool: dict) -> str:
    """«  ·  [X1C — AMS 2] » si l'emplacement est renseigné, sinon ""."""
    emp = str(spool.get("emplacement") or "").strip()
    return f"  ·  [{emp}]" if emp else ""
