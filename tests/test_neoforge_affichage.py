# -*- coding: utf-8 -*-
"""Le maillage d'AFFICHAGE, distinct du maillage étanche.

Retour d'Emmanuel : une cuvette creusée à la sphère dans une surface plane
faisait apparaître une étoile de stries sur toute la surface. Cause : le
maillage soudé partout mêle la normale du bord de cuvette à celle du plan, et
l'ombrage lisse l'étale le long des grands triangles en éventail."""
import pytest

from neoforge.noyau.maillage import trianguler, trianguler_affichage
from neoforge.noyau.primitives import solide
from neoforge.projet.modele import Forme


def _cube():
    return solide(Forme("cube", "matiere", [0, 0, 15], [30, 30, 30]))


def test_l_affichage_garde_les_faces_separees():
    V, F = trianguler(_cube())
    Va, Fa = trianguler_affichage(_cube())
    assert len(F) == len(Fa)          # exactement les mêmes triangles
    assert len(V) == 8                # soudé : les huit coins du cube
    assert len(Va) == 24              # à l'écran : six faces de quatre coins


def test_le_maillage_etanche_ne_change_pas():
    """L'export et le volume continuent d'utiliser le maillage soudé."""
    V, F = trianguler(_cube())
    assert len(V) == 8 and len(F) == 12
    bords: dict[tuple[int, int], int] = {}
    for a, b, c in F:
        for i, j in ((a, b), (b, c), (c, a)):
            bords[(min(i, j), max(i, j))] = bords.get((min(i, j), max(i, j)), 0) + 1
    assert all(n == 2 for n in bords.values())     # étanche


def test_une_cuvette_ne_soude_pas_le_bord_au_plan():
    """Le cas d'Emmanuel : une sphère creusée dans le dessus d'une plaque."""
    from neoforge.noyau.construction import Constructeur
    from neoforge.projet.modele import Projet
    projet = Projet([Forme("cube", "matiere", [0, 0, 5], [60, 60, 10]),
                     Forme("sphere", "creux", [0, 0, 12], [16, 16, 16])])
    forme = Constructeur().construire(projet)[-1].forme
    assert forme is not None
    V, _F = trianguler(forme)
    Va, _Fa = trianguler_affichage(forme)
    # Le maillage d'affichage a forcément PLUS de sommets : le bord de la
    # cuvette existe deux fois, une fois pour le plan, une fois pour la sphère.
    assert len(Va) > len(V)
