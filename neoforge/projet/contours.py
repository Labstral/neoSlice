# -*- coding: utf-8 -*-
"""Les contours 2D des formes, décrits UNE SEULE FOIS.

Deux mondes s'en servent et ils doivent montrer la même chose :

  le NOYAU (`noyau/primitives.py`) en fait des solides OpenCascade, c'est la
  vraie pièce, celle qu'on exporte ;

  l'APERÇU (`ui/apercu.py`) en fait un maillage en numpy, en quelques dixièmes
  de milliseconde, pour suivre la souris pendant un geste.

⚠️ C'est né d'un vrai défaut. Le cadre, l'anneau et l'engrenage ont d'abord été
écrits dans le noyau seulement ; l'aperçu, qui ne les connaissait pas, retombait
sur son cas par défaut, un cylindre. Emmanuel a donc vu « un rond vert au milieu
du cadre » qui ne suivait pas la taille. Toute forme nouvelle se décrit ici, et
les deux mondes la reçoivent ensemble.

Les contours sortent en liste de (x, y), sens trigonométrique, centrés sur
l'origine. Ceux qui sont réguliers sont RAMENÉS à une boîte de 1 × 1 : un
triangle inscrit dans un cercle ne remplit pas sa boîte, et « largeur 40 »
doit donner 40 mm de large, pas 34,6.
"""
from __future__ import annotations

import math

RESOLUTION_RONDE = 64        # points d'une ellipse : assez fin pour l'écran


def _boite(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def regulier(n: int) -> list[tuple[float, float]]:
    """Polygone régulier à n côtés, un côté PLAT en bas, ramené à une boîte
    de 1 × 1 (donc des coordonnées entre -0,5 et 0,5)."""
    n = max(3, int(n))
    depart = math.pi / 2 + math.pi / n
    pts = [(math.cos(depart + 2 * math.pi * k / n),
            math.sin(depart + 2 * math.pi * k / n)) for k in range(n)]
    x0, x1, y0, y1 = _boite(pts)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = max(1e-9, (x1 - x0) / 2.0), max(1e-9, (y1 - y0) / 2.0)
    return [((x - cx) / dx / 2.0, (y - cy) / dy / 2.0) for x, y in pts]


def polygone(n: int, rx: float, ry: float) -> list[tuple[float, float]]:
    """Polygone à n côtés dont la boîte fait exactement 2·rx sur 2·ry.

    À quatre côtés on rend un VRAI rectangle aligné sur les axes : le polygone
    régulier poserait ses sommets sur les axes et donnerait un losange, ce que
    personne n'appelle un carré."""
    if int(n) == 4:
        return [(-rx, -ry), (rx, -ry), (rx, ry), (-rx, ry)]
    return [(x * 2.0 * rx, y * 2.0 * ry) for x, y in regulier(n)]


def ellipse(rx: float, ry: float, n: int = RESOLUTION_RONDE):
    a = [2.0 * math.pi * k / n for k in range(int(n))]
    return [(rx * math.cos(t), ry * math.sin(t)) for t in a]


def _distance_au_centre(points) -> float:
    """Distance du centre au côté le PLUS PROCHE d'un contour fermé."""
    proche = None
    for i, (x0, y0) in enumerate(points):
        x1, y1 = points[(i + 1) % len(points)]
        longueur = math.hypot(x1 - x0, y1 - y0)
        if longueur < 1e-9:
            continue
        d = abs((x1 - x0) * (0 - y0) - (y1 - y0) * (0 - x0)) / longueur
        proche = d if proche is None else min(proche, d)
    return proche or 0.0


def cadre(n: int, rx: float, ry: float, bord: float):
    """Contour extérieur et contour intérieur d'un cadre à n côtés.

    L'intérieur recule de `bord` PERPENDICULAIREMENT à chaque côté. Rétrécir la
    boîte de `bord` tout court ne retirerait que `bord × cos` de matière sur un
    côté oblique : un cadre triangulaire de 4 mm n'en ferait que 2.

    Renvoie (extérieur, intérieur) ; l'intérieur vaut None quand le bord est
    plus épais que la pièce, auquel cas la forme est pleine plutôt que vide.
    """
    dehors = polygone(n, rx, ry)
    if int(n) == 4:
        rx_in, ry_in = rx - bord, ry - bord
    else:
        proche = _distance_au_centre(dehors)
        if proche <= bord:
            return dehors, None
        k = (proche - bord) / proche
        rx_in, ry_in = rx * k, ry * k
    if min(rx_in, ry_in) <= 0.05:
        return dehors, None
    return dehors, polygone(n, rx_in, ry_in)


def anneau(rx: float, ry: float, bord: float, n: int = RESOLUTION_RONDE):
    """Contour extérieur et intérieur d'un anneau, rond ou ovale."""
    dehors = ellipse(rx, ry, n)
    rx_in, ry_in = rx - bord, ry - bord
    if min(rx_in, ry_in) <= 0.05:
        return dehors, None
    return dehors, ellipse(rx_in, ry_in, n)


def engrenage(dents: int, profil: str = "droit") -> list[tuple[float, float]]:
    """Contour d'une roue dentée, ramené à une boîte de 1 × 1.

    Trois profils : droit (flancs inclinés, sommet plat, le plus solide),
    arrondi (aucun angle vif, il roule sans à coup) et pointu (décoratif).

    Les rayons suivent la règle du module : module = 2·Ra/(n+2), primitif
    Ra·n/(n+2), pied Ra·(n−2,5)/(n+2). La dent occupe 46 % du pas au pied et le
    creux 54 %, sans quoi deux roues identiques ne pourraient pas s'engrener.
    """
    n = max(6, min(120, int(dents)))
    ra = 1.0
    rf = max(0.25, ra * (n - 2.5) / (n + 2))
    pas = 2 * math.pi / n
    pts: list[tuple[float, float]] = []
    if profil == "arrondi":
        moyen, amplitude = (ra + rf) / 2.0, (ra - rf) / 2.0
        echantillons = max(10, min(16, 720 // n))
        for k in range(n * echantillons):
            a = 2 * math.pi * k / (n * echantillons)
            r = moyen + amplitude * math.cos(n * a)
            pts.append((r * math.cos(a), r * math.sin(a)))
    else:
        demi_sommet = 0.0 if profil == "pointu" else pas * 0.14
        demi_pied = pas * 0.23
        for k in range(n):
            centre = k * pas
            coins = [(rf, centre - demi_pied)]
            if demi_sommet > 0.0:
                coins += [(ra, centre - demi_sommet), (ra, centre + demi_sommet)]
            else:
                coins += [(ra, centre)]
            coins.append((rf, centre + demi_pied))
            pts += [(r * math.cos(a), r * math.sin(a)) for r, a in coins]
    x0, x1, y0, y1 = _boite(pts)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = max(1e-9, (x1 - x0) / 2.0), max(1e-9, (y1 - y0) / 2.0)
    return [((x - cx) / dx / 2.0, (y - cy) / dy / 2.0) for x, y in pts]


def roue(dents: int, profil: str, rx: float, ry: float):
    """Contour d'un engrenage dont la boîte fait 2·rx sur 2·ry."""
    return [(x * 2.0 * rx, y * 2.0 * ry) for x, y in engrenage(dents, profil)]
