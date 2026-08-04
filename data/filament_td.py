# -*- coding: utf-8 -*-
"""Bibliothèque de filaments pour HueForge : couleur + TD (distance de transmission).

La **TD (Transmission Distance, en mm)** = épaisseur de matière au-delà de laquelle
le filament devient quasi opaque à la lumière. C'est LE paramètre qui régit le mélange
soustractif du HueForge : un filament clair/translucide (TD élevée) laisse voir les
couches du dessous ; un filament foncé/opaque (TD faible) les masque vite.

Valeurs de RÉFÉRENCE (mm) — approximations terrain, ordre de grandeur correct pour du
PLA standard 0.1-0.2 mm de couche. Elles sont ÉDITABLES par l'utilisateur dans l'objet
neoGen HueForge (chaque filament a un réglage TD qui prime sur la valeur d'ici).

Ordre conseillé d'une palette : du plus CLAIR (fond, imprimé en premier, en bas) au
plus FONCÉ (détails, imprimé en dernier, au-dessus).
"""
from __future__ import annotations

# nom : (couleur hex, TD mm de référence)
FILAMENTS_TD: dict[str, tuple[str, float]] = {
    "Blanc":          ("F7F7F4", 2.4),
    "Naturel":        ("F3ECDC", 4.0),
    "Beige / peau":   ("E7C9A6", 2.2),
    "Jaune":          ("F2C300", 2.6),
    "Orange":         ("E67E22", 1.8),
    "Rouge":          ("C0322B", 1.4),
    "Rose":           ("E68FAC", 2.0),
    "Vert":           ("27AE60", 1.5),
    "Cyan":           ("1FA5C4", 1.6),
    "Bleu":           ("2456A6", 1.1),
    "Violet":         ("7D3C98", 1.1),
    "Marron":         ("6B4423", 0.9),
    "Gris":           ("808A8F", 1.2),
    "Noir":           ("15171A", 0.6),
}

# Noms EN (pour l'i18n des menus déroulants).
NOMS_EN: dict[str, str] = {
    "Blanc": "White", "Naturel": "Natural", "Beige / peau": "Beige / skin",
    "Jaune": "Yellow", "Orange": "Orange", "Rouge": "Red", "Rose": "Pink",
    "Vert": "Green", "Cyan": "Cyan", "Bleu": "Blue", "Violet": "Purple",
    "Marron": "Brown", "Gris": "Gray", "Noir": "Black",
}

# Palette par défaut (4 filaments, clair -> foncé) — bon point de départ HueForge.
PALETTE_DEFAUT = ["Blanc", "Rouge", "Bleu", "Noir"]


def options_choix() -> list[tuple[str, str, str]]:
    """Options (valeur, libellé FR, libellé EN) pour un menu déroulant de filament."""
    return [(n, n, NOMS_EN.get(n, n)) for n in FILAMENTS_TD]


def noms_filaments() -> list[str]:
    """Liste ordonnée des filaments disponibles (pour les menus déroulants)."""
    return list(FILAMENTS_TD.keys())


def couleur_hex(nom: str) -> str:
    """Couleur hex d'un filament (défaut gris si inconnu)."""
    return FILAMENTS_TD.get(nom, ("808A8F", 1.2))[0]


def td_defaut(nom: str) -> float:
    """TD de référence d'un filament (défaut 1.2 mm si inconnu)."""
    return FILAMENTS_TD.get(nom, ("808A8F", 1.2))[1]
