# -*- coding: utf-8 -*-
"""Mode série — dupliquer une pièce en ×N exemplaires disposés en grille.

Moteur PUR (aucun Qt) : à partir de l'empreinte au sol de la pièce et des
dimensions du plateau, calcule la grille (colonnes × rangées), le nombre
d'exemplaires par plateau et les translations de chaque copie. Les exemplaires
qui ne tiennent pas sur le premier plateau débordent sur les suivants —
l'export les répartit (3MF multi-plateaux Bambu/Orca, ou un fichier par
plateau pour les autres slicers).
"""
from __future__ import annotations

MARGE_MM = 8.0        # marge au bord du plateau (zones d'amorce, clips…)
ESPACEMENT_MM = 8.0   # espace entre deux exemplaires (brim/jupe sans fusion)


def plan_grille(dx: float, dy: float, n: int, bed_x: float, bed_y: float,
                marge: float = MARGE_MM, espacement: float = ESPACEMENT_MM) -> dict:
    """Grille pour N exemplaires d'empreinte (dx × dy) mm sur un plateau
    (bed_x × bed_y) mm. ValueError si UN SEUL exemplaire ne tient pas.

    Retour : {cols, rows, par_plateau, plateaux, offsets} — `offsets` liste,
    par plateau, les translations (tx, ty) de chaque exemplaire par rapport à
    la position d'origine de la pièce (grille locale au plateau ; le writer
    centre ensuite chaque groupe sur son plateau)."""
    if n < 1:
        raise ValueError("n doit être >= 1")
    utile_x = bed_x - 2 * marge
    utile_y = bed_y - 2 * marge
    if dx > utile_x or dy > utile_y:
        raise ValueError(
            f"empreinte {dx:.0f}×{dy:.0f} mm > plateau utile "
            f"{utile_x:.0f}×{utile_y:.0f} mm")
    cols = max(1, int((utile_x + espacement) // (dx + espacement)))
    rows = max(1, int((utile_y + espacement) // (dy + espacement)))
    par_plateau = cols * rows
    plateaux = (n + par_plateau - 1) // par_plateau
    offsets: list[list[tuple[float, float]]] = []
    for p in range(plateaux):
        grp = []
        debut = p * par_plateau
        for k in range(debut, min(debut + par_plateau, n)):
            r, c = divmod(k - debut, cols)
            grp.append((c * (dx + espacement), r * (dy + espacement)))
        offsets.append(grp)
    return {"cols": cols, "rows": rows, "par_plateau": par_plateau,
            "plateaux": plateaux, "offsets": offsets}


def copies_serie(mesh, n: int, bed_xy: tuple[float, float],
                 marge: float = MARGE_MM, espacement: float = ESPACEMENT_MM) -> list:
    """Copies translatées de `mesh` (trimesh), groupées par plateau :
    list[plateau] -> list[Trimesh]. ValueError si la pièce ne tient pas."""
    lo, hi = mesh.bounds
    dx, dy = float(hi[0] - lo[0]), float(hi[1] - lo[1])
    plan = plan_grille(dx, dy, n, bed_xy[0], bed_xy[1], marge, espacement)
    plateaux = []
    for grp in plan["offsets"]:
        copies = []
        for tx, ty in grp:
            c = mesh.copy()
            c.apply_translation((tx, ty, 0.0))
            copies.append(c)
        plateaux.append(copies)
    return plateaux
