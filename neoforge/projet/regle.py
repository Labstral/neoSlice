# -*- coding: utf-8 -*-
"""La règle : mesurer la distance d'un point A à un point B sur la pièce.

Tout se joue À L'ÉCRAN et non dans l'espace : c'est ce que vise la souris qui
compte, pas ce qui est le plus proche en millimètres. Une arête cachée derrière
la pièce peut passer à deux pixels du curseur ; c'est celle qu'on voit qu'il
faut accrocher, et c'est aussi ce que fait tout logiciel de CAO.

Trois sortes de points, par ordre de priorité :

  sommet   le bout d'une arête, donc un coin ou un angle. Le plus précieux, on
           l'accroche même s'il est un peu plus loin que le reste ;
  milieu   le milieu d'une arête, qui sert tout le temps pour centrer ;
  arête    n'importe quel point le long d'une ligne.

Aucune dépendance à Qt ni au noyau : ce module se teste seul.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RAYON = 16.0            # pixels : au delà, la souris ne vise plus rien
BONUS_SOMMET = 9.0      # pixels d'avance donnés à un coin sur le reste
BONUS_MILIEU = 4.0      # et au milieu d'une arête sur un point quelconque


@dataclass
class Accroche:
    point: tuple[float, float, float]    # en millimètres, dans le monde
    genre: str                           # « sommet », « milieu » ou « arete »
    ecart: float                         # distance à la souris, en pixels


def _segments(ligne: np.ndarray):
    return np.asarray(ligne[:-1], float), np.asarray(ligne[1:], float)


def _plus_proche_sur_segments(souris, a2, b2, a3, b3):
    """Point le plus proche de la souris sur une suite de segments d'écran.

    Renvoie (écart en pixels, point 3D, proportion sur le segment, indice du
    segment) : la proportion et l'indice servent à interpoler la profondeur."""
    d = b2 - a2
    longueur2 = np.einsum("ij,ij->i", d, d)
    sur = np.where(longueur2 > 1e-12,
                   np.einsum("ij,ij->i", souris - a2, d) / np.maximum(longueur2, 1e-12),
                   0.0)
    sur = np.clip(sur, 0.0, 1.0)
    projete = a2 + d * sur[:, None]
    ecarts = np.linalg.norm(projete - souris, axis=1)
    k = int(np.argmin(ecarts))
    t = float(sur[k])
    return float(ecarts[k]), tuple(a3[k] + (b3[k] - a3[k]) * t), t, k


def accrocher(souris, lignes_ecran, lignes_monde, rayon: float = RAYON,
              lignes_profondeur=None):
    """Le point de la pièce que vise la souris, ou None si elle ne vise rien.

    `lignes_ecran` et `lignes_monde` décrivent les MÊMES arêtes, l'une en
    pixels (N×2), l'autre en millimètres (N×3). `lignes_profondeur` donne, si
    on l'a, la profondeur de chaque point : petite = près de l'œil.

    ⚠️ La profondeur n'est pas un luxe. En vue isométrique, deux coins opposés
    d'un cube tombent EXACTEMENT sur le même pixel : mesuré, viser le coin
    (10, 10, 20) accrochait (-10, -10, 0), celui de derrière. À écart égal,
    c'est celui de devant qu'on veut.
    """
    souris = np.asarray(souris, float)
    candidats = []
    for i, (ecran, monde) in enumerate(zip(lignes_ecran, lignes_monde)):
        ecran = np.asarray(ecran, float)
        monde = np.asarray(monde, float)
        if len(ecran) < 2 or len(ecran) != len(monde):
            continue
        prof = (np.asarray(lignes_profondeur[i], float)
                if lignes_profondeur is not None else np.zeros(len(ecran)))
        # Les bouts de l'arête : un coin, un angle, le point qu'on veut le plus
        # souvent. Priorité 0, la plus forte.
        for k in (0, len(ecran) - 1):
            ecart = float(np.linalg.norm(ecran[k] - souris))
            if ecart <= rayon:
                candidats.append((0, ecart - BONUS_SOMMET, float(prof[k]),
                                  Accroche(tuple(monde[k]), "sommet", ecart)))
        k = len(ecran) // 2
        ecart = float(np.linalg.norm(ecran[k] - souris))
        if ecart <= rayon:
            candidats.append((1, ecart - BONUS_MILIEU, float(prof[k]),
                              Accroche(tuple(monde[k]), "milieu", ecart)))
        a2, b2 = _segments(ecran)
        a3, b3 = _segments(monde)
        ecart, point, t, k = _plus_proche_sur_segments(souris, a2, b2, a3, b3)
        if ecart <= rayon:
            p = float(prof[k] + (prof[k + 1] - prof[k]) * t)
            candidats.append((2, ecart, p, Accroche(point, "arete", ecart)))
    if not candidats:
        return None
    # On classe par NOTE d'abord (l'écart, corrigé du bonus de priorité), puis
    # par profondeur : deux points au même pixel se départagent par celui qui
    # est devant.
    candidats.sort(key=lambda c: (round(c[1], 1), c[2], c[0]))
    return candidats[0][3]


def mesure(a, b) -> dict:
    """Ce qu'il y a à lire entre deux points : la distance, et l'écart selon
    chaque axe. Les trois écarts servent autant que la distance quand on cale
    une pièce contre une autre."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ecart = b - a
    return {"distance": float(np.linalg.norm(ecart)),
            "dx": float(ecart[0]), "dy": float(ecart[1]), "dz": float(ecart[2]),
            "milieu": tuple((a + b) / 2.0)}
