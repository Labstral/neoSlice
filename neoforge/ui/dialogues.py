# -*- coding: utf-8 -*-
"""Les boîtes de dialogue de neoForge.

Elles sont construites À LA MAIN plutôt qu'avec les boutons standards de Qt :
ceux-ci sont écrits dans la langue de Qt (« Save », « Discard », « Cancel »
même en français) et ignorent la palette du thème. Emmanuel l'a constaté sur la
fenêtre de fermeture, restée en anglais et hors thème."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from neoforge.ui import style as S
from neoforge.ui.textes import T

ACCEPTER = QMessageBox.ButtonRole.AcceptRole
REFUSER = QMessageBox.ButtonRole.RejectRole
DETRUIRE = QMessageBox.ButtonRole.DestructiveRole


def _habiller(boite: QMessageBox) -> QMessageBox:
    boite.setStyleSheet(S.qss_dialogue())
    return boite


def demander(parent, titre: str, texte: str, choix: list[tuple[str, object]],
             defaut: int = 0) -> int:
    """Pose une question. `choix` donne les boutons, de gauche à droite, avec
    leur rôle ; renvoie l'indice de celui qui a été cliqué (celui de rôle
    REFUSER si la fenêtre est fermée)."""
    boite = _habiller(QMessageBox(QMessageBox.Icon.Question, titre, texte,
                                  QMessageBox.StandardButton.NoButton, parent))
    boutons = [boite.addButton(libelle, role) for libelle, role in choix]
    if 0 <= defaut < len(boutons):
        boite.setDefaultButton(boutons[defaut])
    boite.exec()
    clique = boite.clickedButton()
    for i, b in enumerate(boutons):
        if b is clique:
            return i
    return next((i for i, (_l, r) in enumerate(choix) if r == REFUSER), len(choix) - 1)


def informer(parent, titre: str, texte: str) -> None:
    boite = _habiller(QMessageBox(QMessageBox.Icon.Information, titre, texte,
                                  QMessageBox.StandardButton.NoButton, parent))
    boite.addButton(T("fermer_boite"), ACCEPTER)
    boite.exec()


def avertir(parent, titre: str, texte: str) -> None:
    boite = _habiller(QMessageBox(QMessageBox.Icon.Warning, titre, texte,
                                  QMessageBox.StandardButton.NoButton, parent))
    boite.addButton(T("fermer_boite"), ACCEPTER)
    boite.exec()
