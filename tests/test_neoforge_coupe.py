# -*- coding: utf-8 -*-
"""Découper la pièce par un plan (demande d'Emmanuel 2026-09-13).

Trois choix : garder le dessous, garder le dessus, ou garder LES DEUX, qui
deviennent alors deux objets séparés, pratique pour couper une pièce trop haute
en deux moitiés imprimables."""
import pytest

from neoforge.noyau import occ as O
from neoforge.noyau.construction import Constructeur
from neoforge.projet.modele import Coupe, Forme, Projet


def _cube():
    """Un cube de 30, posé au plateau : il va de z = 0 à z = 30."""
    return Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])


def _resultat(*etapes):
    return Constructeur().construire(Projet(list(etapes)))[-1]


def _corps(forme) -> int:
    """Nombre de solides distincts dans le résultat."""
    n, ex = 0, O.TopExp_Explorer(forme, O.TopAbs_SOLID)
    while ex.More():
        n += 1
        ex.Next()
    return n


def test_garder_le_dessous():
    r = _resultat(_cube(), Coupe(2, 10.0, "dessous"))
    assert r.erreur is None
    assert O.volume(r.forme) == pytest.approx(30 * 30 * 10, rel=1e-6)
    assert _corps(r.forme) == 1


def test_garder_le_dessus():
    r = _resultat(_cube(), Coupe(2, 10.0, "dessus"))
    assert r.erreur is None
    assert O.volume(r.forme) == pytest.approx(30 * 30 * 20, rel=1e-6)
    assert _corps(r.forme) == 1


def test_garder_les_deux_donne_deux_objets():
    """Rien n'est perdu, mais la pièce est désormais en deux morceaux."""
    r = _resultat(_cube(), Coupe(2, 10.0, "les_deux"))
    assert r.erreur is None
    assert O.volume(r.forme) == pytest.approx(27000, rel=1e-6)
    assert _corps(r.forme) == 2


def test_les_deux_morceaux_sont_ECARTES():
    """Au contact exact, ce ne sont pas deux parties distinctes à l'usage : il
    faut un espace visible entre elles (retour d'Emmanuel)."""
    from neoforge.noyau.construction import ECART_COUPE
    r = _resultat(_cube(), Coupe(2, 10.0, "les_deux"))
    (_x0, _y0, z0), (_x1, _y1, z1) = O.boite(r.forme)
    assert z0 == pytest.approx(0.0, abs=1e-6)
    # Le morceau du haut est monté de l'écart : la pièce est plus haute d'autant.
    assert z1 == pytest.approx(30.0 + ECART_COUPE, abs=1e-6)


def test_les_deux_morceaux_restent_deux_volumes_fermes():
    """Les deux moitiés se touchent au plan de coupe. Si le maillage les soude
    l'une à l'autre, il devient non manifold et l'impression est annoncée comme
    ratée (constaté au pilote) : chaque corps doit rester fermé de son côté."""
    from neoforge.noyau.maillage import trianguler
    r = _resultat(_cube(), Coupe(2, 10.0, "les_deux"))
    V, F = trianguler(r.forme)
    assert len(V) == 16                       # huit sommets par moitié
    bords: dict[tuple[int, int], int] = {}
    for a, b, c in F:
        for i, j in ((a, b), (b, c), (c, a)):
            bords[(min(i, j), max(i, j))] = bords.get((min(i, j), max(i, j)), 0) + 1
    assert all(n == 2 for n in bords.values()), "maillage non fermé"


@pytest.mark.parametrize("axe,attendu", [(0, 13500), (1, 13500), (2, 13500)])
def test_couper_selon_chaque_axe(axe, attendu):
    """Un plan qui passe par le milieu coupe la pièce en deux parts égales."""
    milieu = 15.0 if axe == 2 else 0.0
    r = _resultat(_cube(), Coupe(axe, milieu, "dessous"))
    assert r.erreur is None
    assert O.volume(r.forme) == pytest.approx(attendu, rel=1e-6)


def test_un_plan_hors_de_la_piece():
    """Au dessus de tout : il ne reste rien, l'étape le dit au lieu de vider la
    pièce en silence. En dessous de tout : la pièce est intacte."""
    trop_haut = _resultat(_cube(), Coupe(2, 100.0, "dessus"))
    assert trop_haut.erreur == "vide"
    assert O.volume(trop_haut.forme) == pytest.approx(27000, rel=1e-6)

    intacte = _resultat(_cube(), Coupe(2, 100.0, "dessous"))
    assert intacte.erreur is None
    assert O.volume(intacte.forme) == pytest.approx(27000, rel=1e-6)


def test_une_coupe_avant_toute_forme():
    r = _resultat(Coupe(2, 10.0, "dessous"), _cube())
    resultats = Constructeur().construire(
        Projet([Coupe(2, 10.0, "dessous"), _cube()]))
    assert resultats[0].erreur == "rien_a_arrondir"     # rien à couper encore
    assert r.forme is not None                          # la suite se calcule


def test_une_coupe_masquee_ne_fait_rien():
    coupe = Coupe(2, 10.0, "dessous")
    coupe.actif = False
    r = _resultat(_cube(), coupe)
    assert r.erreur is None
    assert O.volume(r.forme) == pytest.approx(27000, rel=1e-6)


def test_la_coupe_survit_a_l_enregistrement():
    p = Projet([_cube(), Coupe(1, -3.5, "les_deux")])
    relu = Projet.depuis_dico(p.dico())
    coupe = relu.etapes[1]
    assert isinstance(coupe, Coupe)
    assert (coupe.axe, coupe.position, coupe.garder) == (1, -3.5, "les_deux")


def test_un_fichier_abime_ne_casse_pas_la_coupe():
    coupe = Coupe.depuis_dico({"type": "coupe", "axe": 9, "position": "oups",
                               "garder": "n'importe quoi"})
    assert coupe.axe == 2 and coupe.position == 0.0 and coupe.garder == "dessous"


def test_couper_puis_creuser_reste_coherent():
    """Une coupe est une étape comme une autre : ce qui suit s'applique dessus."""
    r = _resultat(_cube(), Coupe(2, 20.0, "dessous"),
                  Forme("cylindre", "creux", [0, 0, 10], [10, 10, 60]))
    assert r.erreur is None
    attendu = 30 * 30 * 20 - 3.14159265 * 25 * 20
    assert O.volume(r.forme) == pytest.approx(attendu, rel=1e-3)
