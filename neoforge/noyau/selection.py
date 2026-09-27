# -*- coding: utf-8 -*-
"""Quelle étape a-t-on cliquée sur la pièce ?

On cherche la forme dont la SURFACE passe par le point cliqué. Cliquer le
dessus d'un socle sélectionne le socle ; cliquer la paroi d'un trou sélectionne
le trou, ce qui est exactement ce qu'on veut pour le modifier ensuite."""
from __future__ import annotations

from neoforge.noyau import occ as O
from neoforge.noyau.primitives import solide
from neoforge.projet.modele import Forme

TOLERANCE = 1.0         # mm : le maillage affiché s'écarte un peu des surfaces exactes


def distance_a_la_forme(point, forme: Forme) -> float:
    """Distance du point à la SURFACE de la forme.

    On mesure face par face, et non par rapport au volume : un point situé à
    l'intérieur d'un solide est à distance nulle de ce solide, si bien que
    cliquer la paroi d'un trou sélectionnait la pièce qui l'entoure."""
    sommet = O.BRepBuilderAPI_MakeVertex(O.gp_Pnt(*[float(v) for v in point])).Vertex()
    meilleure = float("inf")
    ex = O.TopExp_Explorer(solide(forme), O.TopAbs_FACE)
    while ex.More():
        calcul = O.BRepExtrema_DistShapeShape(sommet, O.face(ex.Current()))
        calcul.Perform()
        if calcul.IsDone():
            meilleure = min(meilleure, float(calcul.Value()))
        ex.Next()
    return meilleure


def etape_au_point(projet, point, tolerance: float = TOLERANCE) -> int | None:
    """Index de l'étape Forme dont la surface est la plus proche du point,
    ou None si le clic ne tombe sur aucune (tolérance dépassée).

    Les découpes qui SUIVENT une forme sont prises en compte : sans elles, un
    clic dans le vide laissé par une coupe sélectionnait encore la forme, comme
    si la moitié retirée était toujours là (retour d'Emmanuel)."""
    from neoforge.projet.decoupes import (coupes_apres, retiree_par, sans_ecart,
                                          sur_le_plan)

    meilleur, plus_proche = None, float(tolerance)
    for i, etape in enumerate(projet.etapes):
        if not isinstance(etape, Forme) or not etape.actif:
            continue
        coupes = coupes_apres(projet, i)
        vu = sans_ecart(point, coupes)
        if any(retiree_par(vu, c, tolerance) for c in coupes):
            continue                      # ce clic tombe dans la moitié retirée
        try:
            d = distance_a_la_forme(vu, etape)
            # La face ouverte par la coupe appartient désormais à la pièce, mais
            # à aucune surface de la primitive : on la reconnaît au plan, à
            # condition de rester dans l'emprise de la forme.
            if d >= plus_proche and any(sur_le_plan(vu, c, tolerance)
                                        for c in coupes) \
                    and _dans_l_emprise(vu, etape, tolerance):
                d = 0.0
        except Exception:
            continue
        if d < plus_proche:
            meilleur, plus_proche = i, d
    return meilleur


def _dans_l_emprise(point, forme: Forme, tolerance: float) -> bool:
    """Le point tombe-t-il dans la boîte de la forme ? Le plan d'une coupe est
    infini, la pièce non : sans cela, une forme posée ailleurs sur ce plan
    captait le clic."""
    try:
        bas, haut = O.boite(solide(forme))
    except Exception:
        return False
    return all(bas[k] - tolerance <= float(point[k]) <= haut[k] + tolerance
               for k in range(3))
