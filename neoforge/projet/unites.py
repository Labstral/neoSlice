# -*- coding: utf-8 -*-
"""L'unité dans laquelle on LIT et on SAISIT les mesures.

Demande d'Emmanuel : « j'aimerais que par défaut les mesures apparaissent en mm
et non en cm, mais qu'on puisse avoir le choix dans les réglages, et penser aux
mesures les plus utilisées dans le monde pour que ce soit compatible avec les
principaux pays. »

Le modèle, lui, reste TOUJOURS en millimètres : c'est l'unité du noyau, celle
des fichiers STL et 3MF, et celle des imprimantes. Seuls l'affichage et la
saisie convertissent, si bien qu'un projet enregistré dans un pays s'ouvre
identique dans un autre, quel que soit le réglage de chacun.

Géométrie pure : aucun Qt, aucun noyau."""
from __future__ import annotations

# clé : (millimètres pour une unité, symbole, symbole de volume, décimales, pas)
UNITES = {
    "mm": (1.0, "mm", "mm³", 1, 1.0),
    "cm": (10.0, "cm", "cm³", 2, 0.1),
    "in": (25.4, "in", "in³", 3, 0.05),
}
DEFAUT = "mm"


def connue(unite: str) -> str:
    """Ramène toujours à une unité valable : un fichier de réglages abîmé ou une
    version plus ancienne ne doit pas empêcher la fenêtre de s'ouvrir."""
    return unite if unite in UNITES else DEFAUT


_courante = DEFAUT


def courante() -> str:
    """L'unité d'affichage en cours.

    C'est un réglage de l'application entière, au même titre que le thème. Le
    tenir ici évite de le faire traverser une dizaine de signatures jusqu'aux
    chiffres gravés sur les cotes, au fond de la vue 3D."""
    return _courante


def definir(unite: str) -> str:
    """Change l'unité d'affichage et renvoie celle qui a été retenue."""
    global _courante
    _courante = connue(unite)
    return _courante


def facteur(unite: str) -> float:
    """Combien de millimètres vaut UNE unité."""
    return UNITES[connue(unite)][0]


def symbole(unite: str) -> str:
    return UNITES[connue(unite)][1]


def symbole_volume(unite: str) -> str:
    return UNITES[connue(unite)][2]


def decimales(unite: str) -> int:
    """Assez de décimales pour que le millimètre reste atteignable : au pouce,
    un dixième de millimètre vaut 0,004 pouce, d'où trois décimales."""
    return UNITES[connue(unite)][3]


def pas(unite: str) -> float:
    """Le pas d'un compteur, dans l'unité : un millimètre, un dixième de
    centimètre, un vingtième de pouce."""
    return UNITES[connue(unite)][4]


def vers(millimetres: float, unite: str) -> float:
    """Des millimètres du modèle vers l'unité affichée."""
    return float(millimetres) / facteur(unite)


def depuis(valeur: float, unite: str) -> float:
    """De l'unité saisie vers les millimètres du modèle."""
    return float(valeur) * facteur(unite)


def texte(millimetres: float, unite: str) -> str:
    """Le nombre seul, arrondi comme il se doit pour cette unité."""
    return f"{vers(millimetres, unite):.{decimales(unite)}f}"


def avec_symbole(millimetres: float, unite: str) -> str:
    return f"{texte(millimetres, unite)} {symbole(unite)}"


def volume(millimetres_cubes: float, unite: str) -> str:
    """Le volume dans l'unité choisie, cube. En millimètres cubes les nombres
    sont gros : on n'y met aucune décimale, elles n'apprendraient rien."""
    u = connue(unite)
    valeur = float(millimetres_cubes) / (facteur(u) ** 3)
    return f"{valeur:.0f}" if u == "mm" else f"{valeur:.2f}"


def court(millimetres: float, unite: str) -> str:
    """Comme `texte`, mais sans décimale inutile : c'est ce qu'on gravait sur les
    cotes dessinées dans la vue, où la place manque (« 30 » et non « 30,0 »)."""
    valeur = vers(millimetres, unite)
    arrondi = round(valeur, decimales(unite))
    return f"{arrondi:g}"
