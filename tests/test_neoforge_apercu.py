# -*- coding: utf-8 -*-
"""Le maillage de l'aperçu, fabriqué sans le noyau.

Il sert à REFAIRE l'aperçu en plein geste quand aucune mise à l'échelle ne peut
le représenter (un cône dont les deux diamètres changent). Il doit donc être
juste ET rapide : passer par OpenCascade coûtait plusieurs millisecondes par
pas de souris."""
import numpy as np
import pytest

from neoforge.projet.modele import Forme
from neoforge.ui.apercu import maillage_local


def _etendue(V):
    return (V.max(axis=0) - V.min(axis=0)).tolist()


def _est_ferme(F) -> bool:
    """Chaque arête est partagée par exactement deux triangles."""
    comptes: dict[tuple[int, int], int] = {}
    for a, b, c in F:
        for i, j in ((a, b), (b, c), (c, a)):
            comptes[(min(i, j), max(i, j))] = comptes.get((min(i, j), max(i, j)), 0) + 1
    return all(n == 2 for n in comptes.values())


@pytest.mark.parametrize("forme,dim,etendue", [
    ("cube", [20, 30, 10], [20, 30, 10]),
    ("sphere", [20, 20, 20], [20, 20, 20]),
    ("cylindre", [20, 20, 30], [20, 20, 30]),
    ("cone", [20, 8, 24], [20, 20, 24]),        # le plus grand diamètre mène
    ("cone", [20, 0, 24], [20, 20, 24]),        # cône pointu
    ("tore", [40, 10, 0], [50, 50, 10]),        # cercle porteur + tube
    ("coin", [30, 20, 12], [30, 20, 12]),       # la rampe tient dans sa boîte
    ("prisme", [20, 0, 12], [20, 17.32, 12]),   # hexagone : plat à plat 17,32
])
def test_chaque_primitive_tient_dans_ses_dimensions(forme, dim, etendue):
    V, F = maillage_local(Forme(forme, "matiere", [0, 0, 0], dim))
    assert _etendue(V) == pytest.approx(etendue, rel=0.02)
    assert V.min(axis=0) == pytest.approx([-e / 2 for e in etendue], rel=0.02)
    # Au moins un vrai solide fermé : le coin, une rampe, n'a que 8 triangles.
    assert len(F) >= 4 and F.max() < len(V)


@pytest.mark.parametrize("forme,dim", [
    ("cube", [20, 30, 10]), ("sphere", [20, 20, 20]),
    ("cylindre", [20, 20, 30]), ("cone", [20, 8, 24]), ("cone", [20, 0, 24]),
    ("tore", [40, 10, 0]), ("coin", [30, 20, 12]), ("prisme", [20, 0, 12]),
])
def test_les_maillages_sont_fermes(forme, dim):
    _V, F = maillage_local(Forme(forme, "matiere", [0, 0, 0], dim))
    assert _est_ferme(F)


@pytest.mark.parametrize("forme,dim", [
    ("cube", [20, 30, 10]), ("sphere", [20, 20, 20]),
    ("cylindre", [20, 20, 30]), ("cone", [20, 8, 24]), ("cone", [20, 0, 24]),
    ("tore", [40, 10, 0]), ("coin", [30, 20, 12]), ("prisme", [20, 0, 12]),
])
def test_les_faces_regardent_vers_l_exterieur(forme, dim):
    """Une face à l'envers DISPARAÎT quand on élimine les faces arrière : la
    sphère sélectionnée n'apparaissait plus qu'en contour vert, au lieu d'être
    pleine comme les autres formes (retour d'Emmanuel).

    Deux critères, tous deux valables quelle que soit la géométrie. Le VOLUME
    SIGNÉ n'est positif que si l'ensemble regarde dehors. Et chaque arête
    ORIENTÉE ne doit apparaître qu'une fois, ce qui attrape le retournement d'un
    seul triangle. Surtout PAS de comparaison au centre de la boîte : cela ne
    vaut que pour une forme convexe, et cela accusait à tort 768 triangles du
    tore, dont l'intérieur regarde légitimement vers l'axe."""
    V, F = maillage_local(Forme(forme, "matiere", [0, 0, 0], dim))
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    signe = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    assert signe > 0, "maillage retourné : les faces regardent vers l'intérieur"

    vues = set()
    for x, y, z in F:
        for depart, arrivee in ((x, y), (y, z), (z, x)):
            assert (depart, arrivee) not in vues, (
                f"arête {depart}→{arrivee} parcourue deux fois dans le même "
                f"sens : un triangle est retourné")
            vues.add((int(depart), int(arrivee)))


def test_le_cone_pointu_a_un_seul_sommet_en_haut():
    V, _F = maillage_local(Forme("cone", "matiere", [0, 0, 0], [20, 0, 24]))
    haut = V[np.isclose(V[:, 2], 12.0)]
    assert len(haut) == 1
    assert haut[0] == pytest.approx([0, 0, 12])


def test_une_dimension_nulle_ne_fait_pas_disparaitre_la_forme():
    """Un cône pointu a un diamètre de 0 en haut : l'aperçu ne doit pas
    s'écraser pour autant (retour d'Emmanuel sur le redimensionnement)."""
    V, F = maillage_local(Forme("cylindre", "matiere", [0, 0, 0], [0, 0, 20]))
    assert len(F) and np.isfinite(V).all()
    assert _etendue(V)[2] == pytest.approx(20)
