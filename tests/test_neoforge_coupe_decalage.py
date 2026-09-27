# -*- coding: utf-8 -*-
"""La partie HAUTE d'une coupe « garder les deux » se déplace toute seule.

Choix d'Emmanuel : après une coupe en gardant les deux, on doit retrouver deux
pièces dans la liste de gauche, et pouvoir les écarter l'une de l'autre. Le
déplacement de la partie haute est rangé sur la découpe elle même, en plus de
l'écart automatique qui les sépare déjà."""
import pytest

from neoforge.noyau import occ as O
from neoforge.noyau.construction import ECART_COUPE, Constructeur
from neoforge.projet.modele import Coupe, Forme, Projet


def _cube():
    """Un cube de 30 posé au plateau : de z = 0 à z = 30, x et y de -15 à 15."""
    return Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])


def _forme(*etapes):
    return Constructeur().construire(Projet(list(etapes)))[-1].forme


def _corps(forme) -> int:
    n, ex = 0, O.TopExp_Explorer(forme, O.TopAbs_SOLID)
    while ex.More():
        n += 1
        ex.Next()
    return n


def test_par_defaut_rien_ne_bouge():
    """Le comportement d'avant est intact : seul l'écart automatique sépare."""
    assert Coupe(2, 10.0, "les_deux").decalage == [0.0, 0.0, 0.0]
    (_x0, _y0, z0), (_x1, _y1, z1) = O.boite(_forme(_cube(),
                                                    Coupe(2, 10.0, "les_deux")))
    assert z0 == pytest.approx(0.0, abs=1e-6)
    assert z1 == pytest.approx(30.0 + ECART_COUPE, abs=1e-6)


def test_le_decalage_ne_deplace_QUE_la_partie_haute():
    """Le morceau du bas ne bouge pas d'un cheveu, celui du haut suit."""
    coupe = Coupe(2, 10.0, "les_deux")
    coupe.decalage = [5.0, 0.0, 0.0]
    (x0, _y0, z0), (x1, _y1, z1) = O.boite(_forme(_cube(), coupe))
    assert x0 == pytest.approx(-15.0, abs=1e-6)          # le bas reste en place
    assert x1 == pytest.approx(15.0 + 5.0, abs=1e-6)     # le haut a suivi
    assert z0 == pytest.approx(0.0, abs=1e-6)
    assert z1 == pytest.approx(30.0 + ECART_COUPE, abs=1e-6)


def test_deplacer_la_partie_haute_ne_change_NI_le_volume_NI_le_nombre_de_corps():
    coupe = Coupe(2, 10.0, "les_deux")
    coupe.decalage = [12.0, -8.0, 3.0]
    forme = _forme(_cube(), coupe)
    assert O.volume(forme) == pytest.approx(27000.0, rel=1e-6)
    assert _corps(forme) == 2


def test_le_decalage_ne_sert_QUE_si_l_on_garde_les_deux():
    """Garder un seul morceau ne déplace rien : il n'y a pas d'autre pièce."""
    for garder, attendu in (("dessous", 30 * 30 * 10), ("dessus", 30 * 30 * 20)):
        coupe = Coupe(2, 10.0, garder)
        coupe.decalage = [50.0, 0.0, 0.0]
        forme = _forme(_cube(), coupe)
        assert O.volume(forme) == pytest.approx(attendu, rel=1e-6)
        (x0, _y0, _z0), (x1, _y1, _z1) = O.boite(forme)
        assert (x0, x1) == (pytest.approx(-15.0), pytest.approx(15.0))


def test_le_decalage_survit_a_l_enregistrement():
    coupe = Coupe(1, -3.5, "les_deux")
    coupe.decalage = [1.5, 2.5, -3.5]
    relu = Projet.depuis_dico(Projet([_cube(), coupe]).dico()).etapes[1]
    assert relu.decalage == [1.5, 2.5, -3.5]
    assert (relu.axe, relu.position, relu.garder) == (1, -3.5, "les_deux")


@pytest.mark.parametrize("abime", [None, "oups", [1, 2], [1, 2, 3, 4],
                                   ["a", "b", "c"], {}])
def test_un_decalage_abime_retombe_a_zero(abime):
    """Un fichier plus ancien n'a pas ce champ, un fichier abîmé a n'importe
    quoi : ni l'un ni l'autre ne doit empêcher d'ouvrir la pièce."""
    coupe = Coupe.depuis_dico({"type": "coupe", "axe": 2, "position": 4.0,
                               "garder": "les_deux", "decalage": abime})
    assert coupe.decalage == [0.0, 0.0, 0.0]


def test_un_fichier_d_avant_s_ouvre_sans_decalage():
    coupe = Coupe.depuis_dico({"type": "coupe", "axe": 2, "position": 4.0,
                               "garder": "les_deux"})
    assert coupe.decalage == [0.0, 0.0, 0.0] and coupe.garder == "les_deux"


def test_deux_coupes_gardent_chacune_le_sien():
    """Les découpes ne partagent pas leur déplacement : la liste par défaut
    d'une dataclass est un piège classique (une seule liste pour toutes)."""
    a, b = Coupe(2, 1.0, "les_deux"), Coupe(2, 2.0, "les_deux")
    a.decalage[0] = 9.0
    assert b.decalage == [0.0, 0.0, 0.0]
