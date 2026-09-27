# -*- coding: utf-8 -*-
"""Styles de neoForge : la palette de neoSlice, rien en dur.

Les widgets créés à la volée figent la couleur à leur construction : chaque
panneau expose `refresh_theme()` et la fenêtre les rappelle au changement de
thème (règle du projet, sinon des restes sombres traînent en thème clair)."""
from __future__ import annotations

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QLabel

from ui.styles.theme import FONT_MAIN, MANAGER as _T, arrow_icon, spinbox_qss


def pal() -> dict:
    return _T.palette()


def respirer() -> None:
    """Laisse Qt repeindre pendant une étape longue (barre de l'écran de
    chargement), sans laisser passer les clics : la fenêtre n'est pas prête."""
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


def qss_fenetre() -> str:
    p = pal()
    return (f"QMainWindow, QDialog {{ background: {p['BG_VOID']}; }}"
            f"QToolTip {{ background: {p['BG_ELEVATED']}; color: {p['TEXT_PRIMARY']}; "
            f"border: 1px solid {p['ACCENT']}; padding: 4px 8px; border-radius: 3px; }}")


def qss_panneau() -> str:
    p = pal()
    return (f"QWidget#panneau {{ background: {p['BG_PANEL']}; }}"
            f"QLabel {{ color: {p['TEXT_PRIMARY']}; background: transparent; }}")


def qss_bouton(genre: str = "secondaire") -> str:
    p = pal()
    if genre == "accent":
        return (f"QPushButton {{ background: {p['ACCENT']}; color: #ffffff; border: none;"
                f" border-radius: 3px; padding: 6px 14px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {p['ACCENT_BRIGHT']}; }}"
                f"QPushButton:disabled {{ background: {p['INACTIVE']}; color: {p['TEXT_LABEL']}; }}")
    if genre == "danger":
        return (f"QPushButton {{ background: transparent; color: {p['TEXT_SECONDARY']};"
                f" border: 1px solid {p['INACTIVE']}; border-radius: 3px; padding: 5px 10px; }}"
                f"QPushButton:hover {{ border-color: {p['ERROR_RED']}; color: {p['ERROR_RED']}; }}")
    return (f"QPushButton {{ background: transparent; color: {p['TEXT_SECONDARY']};"
            f" border: 1px solid {p['INACTIVE']}; border-radius: 3px; padding: 5px 10px; }}"
            f"QPushButton:hover {{ border-color: {p['ACCENT']}; color: {p['ACCENT_BRIGHT']}; }}"
            f"QPushButton:checked {{ border-color: {p['ACCENT']}; color: {p['ACCENT_BRIGHT']};"
            f" background: rgba(30,144,255,0.12); }}"
            f"QPushButton:disabled {{ color: {p['INACTIVE']}; border-color: {p['INACTIVE']}; }}")


def qss_champs() -> str:
    """Compteurs et menus déroulants. La flèche des menus est l'ICÔNE du thème :
    un triangle dessiné en bordures CSS sort en trait ou en carré sous Windows."""
    p = pal()
    fleche = arrow_icon("down", p["TEXT_SECONDARY"]).replace("\\", "/")
    # `spinbox_qss` ne peint que les FLÈCHES : sans la règle ci dessous, le champ
    # lui même garde la palette par défaut de Qt et les valeurs sortent en gris
    # très pâle, presque illisibles en thème clair (constaté à la capture).
    return (f"QDoubleSpinBox {{ background: {p['BG_INPUT']}; color: {p['TEXT_PRIMARY']};"
            f" border: 1px solid {p['INACTIVE']}; border-radius: 3px;"
            f" padding: 2px 22px 2px 6px; min-height: 22px;"
            f" selection-background-color: {p['ACCENT']}; selection-color: #ffffff; }}"
            f"QDoubleSpinBox:hover {{ border-color: {p['ACCENT']}; }}"
            f"QDoubleSpinBox:focus {{ border-color: {p['ACCENT']}; }}"
            f"QDoubleSpinBox:disabled {{ color: {p['TEXT_LABEL']};"
            f" border-color: {p['INACTIVE']}; }}"
            + spinbox_qss(p, p["ACCENT"])
            + f"QComboBox {{ background: {p['BG_INPUT']}; color: {p['TEXT_PRIMARY']};"
              f" border: 1px solid {p['INACTIVE']}; border-radius: 3px; padding: 3px 6px;"
              f" min-height: 22px; }}"
              f"QComboBox:hover {{ border-color: {p['ACCENT']}; }}"
              f"QComboBox::drop-down {{ border: none; width: 20px; }}"
              f'QComboBox::down-arrow {{ image: url("{fleche}"); width: 9px; height: 6px; }}'
              f"QComboBox QAbstractItemView {{ background: {p['BG_ELEVATED']};"
              f" color: {p['TEXT_PRIMARY']}; selection-background-color: {p['ACCENT']}; }}")


def melange(fond: str, dessus: str, part: float) -> str:
    """Mélange deux couleurs. Sert aux surbrillances : une teinte d'accent posée
    sur le fond se voit dans LES DEUX thèmes, là où une nuance de gris de plus
    disparaissait en clair (retour d'Emmanuel)."""
    def _rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    a, b = _rgb(fond), _rgb(dessus)
    part = max(0.0, min(1.0, float(part)))
    return "#" + "".join(f"{round(a[i] + (b[i] - a[i]) * part):02x}" for i in range(3))


def qss_menu() -> str:
    """Menus déroulants ET menus contextuels. Sans feuille de style, le menu
    prend la palette par défaut de Qt : en thème clair, la ligne survolée était
    un blanc presque invisible (retour d'Emmanuel)."""
    p = pal()
    return (f"QMenu {{ background: {p['BG_ELEVATED']}; color: {p['TEXT_PRIMARY']};"
            f" border: 1px solid {p['INACTIVE']}; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 20px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background: {p['ACCENT']}; color: #ffffff; }}"
            f"QMenu::item:disabled {{ color: {p['TEXT_LABEL']}; }}"
            f"QMenu::separator {{ height: 1px; background: {p['INACTIVE']};"
            f" margin: 4px 8px; }}")


def qss_liste() -> str:
    p = pal()
    survol = melange(p["BG_SURFACE"], p["ACCENT"], 0.22)
    return (f"QListWidget {{ background: {p['BG_SURFACE']}; border: 1px solid {p['INACTIVE']};"
            f" border-radius: 3px; color: {p['TEXT_PRIMARY']}; outline: none; }}"
            f"QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {p['BG_PANEL']}; }}"
            f"QListWidget::item:selected {{ background: {p['ACCENT']}; color: #ffffff; }}"
            f"QListWidget::item:hover:!selected {{ background: {survol};"
            f" color: {p['TEXT_PRIMARY']}; }}")


def qss_dialogue() -> str:
    """Boîtes de dialogue. Qt ne leur applique NI la palette du thème ni nos
    libellés : la fenêtre « Quitter neoForge » sortait en gris par-dessus le
    thème, avec des boutons en anglais (retour d'Emmanuel)."""
    p = pal()
    return (f"QMessageBox {{ background: {p['BG_PANEL']}; }}"
            f"QMessageBox QLabel {{ color: {p['TEXT_PRIMARY']};"
            f" background: transparent; }}"
            f"QMessageBox QPushButton {{ background: transparent;"
            f" color: {p['TEXT_SECONDARY']}; border: 1px solid {p['INACTIVE']};"
            f" border-radius: 3px; padding: 6px 16px; min-width: 96px; }}"
            f"QMessageBox QPushButton:hover {{ border-color: {p['ACCENT']};"
            f" color: {p['ACCENT_BRIGHT']}; }}"
            f"QMessageBox QPushButton:default {{ background: {p['ACCENT']};"
            f" color: #ffffff; border: none; font-weight: bold; }}")


def etiquette(texte: str, taille: int = 8, gras: bool = False, couleur: str | None = None) -> QLabel:
    lbl = QLabel(texte)
    lbl.setFont(QFont(FONT_MAIN, taille, QFont.Bold if gras else QFont.Normal))
    lbl.setStyleSheet(f"color: {couleur or pal()['TEXT_LABEL']}; background: transparent;")
    # Marquée pour être RECOLORÉE au changement de thème (voir rhabiller).
    # Celle qui reçoit une couleur imposée garde la sienne : son propriétaire
    # s'en occupe lui même.
    lbl.setProperty("role_neoforge", "etiquette" if couleur is None else "")
    return lbl


def titre_section(texte: str) -> QLabel:
    lbl = QLabel(texte.upper())
    lbl.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
    lbl.setStyleSheet(f"color: {pal()['TEXT_LABEL']}; background: transparent;"
                      f" letter-spacing: 1px;")
    lbl.setProperty("role_neoforge", "titre_section")
    return lbl


def rhabiller(parent) -> None:
    """Recolore TOUTES les étiquettes fabriquées ici, où qu'elles soient dans
    l'arbre du panneau.

    ⚠️ Une étiquette fige sa couleur à la construction : en thème sombre
    TEXT_LABEL vaut #2A5F8A, en clair #777777. Sans ce passage, les titres de
    section gardaient le bleu du thème sombre sur un fond clair. Les énumérer
    un par un dans chaque `refresh_theme` est exactement ce qui provoque
    l'oubli : on parcourt donc l'arbre, et rien ne peut manquer.
    """
    p = pal()
    for lbl in parent.findChildren(QLabel):
        role = lbl.property("role_neoforge")
        if role == "titre_section":
            lbl.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;"
                              f" letter-spacing: 1px;")
        elif role == "etiquette":
            lbl.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;")


def icone_cadenas(ferme: bool, couleur: str | None = None) -> QIcon:
    """Un petit cadenas dessiné, fermé ou ouvert.

    Dessiné et non écrit : neoSlice n'utilise pas d'émojis dans son interface,
    et le glyphe Unicode du cadenas n'en est pas un sur toutes les machines.
    """
    from PySide6.QtCore import QRect, QRectF, Qt as _Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
    couleur = couleur or pal()["TEXT_SECONDARY"]
    pm = QPixmap(16, 16)
    pm.fill(_Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(couleur), 1.6))
    # L'anse : un demi cercle, décalé à droite quand le cadenas est ouvert.
    decal = 0 if ferme else 3
    p.drawArc(QRectF(4.2 + decal, 1.6, 7.6, 8.0), 0, 180 * 16)
    p.drawLine(int(4.2 + decal), 5, int(4.2 + decal), 7)
    if ferme:
        p.drawLine(11, 5, 11, 7)
    p.setPen(_Qt.PenStyle.NoPen)
    p.setBrush(QColor(couleur))
    p.drawRoundedRect(QRect(3, 7, 10, 7), 1.5, 1.5)
    p.end()
    return QIcon(pm)
