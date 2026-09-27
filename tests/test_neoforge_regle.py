# -*- coding: utf-8 -*-
"""La règle : mesurer d'un point A à un point B, avec l'aide qui vise.

« Il serait bien également d'ajouter un système de règle pour pouvoir mesurer
une distance A à B, avec une aide qui cible les points sur les lignes, les
arêtes, les angles » (Emmanuel, 2026-09-26).

L'accrochage se décide À L'ÉCRAN et non dans l'espace : c'est ce que vise la
souris qui compte. Une arête cachée derrière la pièce peut passer à deux pixels
du curseur, et ce n'est pas elle qu'on veut.
"""
import numpy as np
import pytest

from neoforge.projet.regle import Accroche, accrocher, mesure


def _carre():
    """Un carré de 100 pixels de côté, qui vaut 20 mm dans le monde. Quatre
    arêtes, comme le dessus d'un cube vu de haut."""
    coins_ecran = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    coins_monde = [(0.0, 0.0, 0.0), (20.0, 0.0, 0.0), (20.0, 20.0, 0.0), (0.0, 20.0, 0.0)]
    ecran, monde = [], []
    for i in range(4):
        j = (i + 1) % 4
        a2, b2 = np.array(coins_ecran[i]), np.array(coins_ecran[j])
        a3, b3 = np.array(coins_monde[i]), np.array(coins_monde[j])
        t = np.linspace(0.0, 1.0, 9)[:, None]
        ecran.append(a2 + (b2 - a2) * t)
        monde.append(a3 + (b3 - a3) * t)
    return ecran, monde


# ── Ce que la souris accroche ──────────────────────────────────────────────
def test_un_coin_s_accroche():
    ecran, monde = _carre()
    a = accrocher((3.0, 2.0), ecran, monde)
    assert a is not None and a.genre == "sommet"
    assert a.point == pytest.approx((0.0, 0.0, 0.0))


def test_le_milieu_d_une_arete_s_accroche():
    ecran, monde = _carre()
    a = accrocher((50.0, 3.0), ecran, monde)
    assert a is not None and a.genre == "milieu"
    assert a.point == pytest.approx((10.0, 0.0, 0.0))


def test_un_point_quelconque_sur_une_ligne_s_accroche():
    ecran, monde = _carre()
    a = accrocher((25.0, 4.0), ecran, monde)
    assert a is not None and a.genre == "arete"
    assert a.point[0] == pytest.approx(5.0, abs=0.6)
    assert a.point[1] == pytest.approx(0.0, abs=0.01)


def test_le_coin_l_emporte_sur_la_ligne_qui_passe_par_lui():
    """Sans cette priorité, viser un angle donnerait le point de la ligne le
    plus proche, jamais le coin lui même : la mesure serait toujours à côté."""
    ecran, monde = _carre()
    a = accrocher((6.0, 1.0), ecran, monde)
    assert a.genre == "sommet"
    assert a.point == pytest.approx((0.0, 0.0, 0.0))


def test_rien_a_viser_ne_renvoie_rien():
    ecran, monde = _carre()
    assert accrocher((50.0, 50.0), ecran, monde) is None      # le milieu du carré
    assert accrocher((-80.0, -80.0), ecran, monde) is None


def test_la_souris_choisit_la_plus_proche_a_l_ecran():
    """Deux arêtes superposées dans l'espace mais distinctes à l'écran : c'est
    celle qu'on voit près du curseur qui gagne."""
    ecran = [np.array([[0.0, 0.0], [100.0, 0.0]]),
             np.array([[0.0, 60.0], [100.0, 60.0]])]
    monde = [np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0]]),
             np.array([[0.0, 0.0, 30.0], [20.0, 0.0, 30.0]])]
    assert accrocher((50.0, 58.0), ecran, monde).point[2] == pytest.approx(30.0)
    assert accrocher((50.0, 2.0), ecran, monde).point[2] == pytest.approx(0.0)


def test_une_ligne_abimee_ne_casse_rien():
    """Un seul point, ou deux listes de tailles différentes : on l'ignore."""
    assert accrocher((0.0, 0.0), [np.array([[0.0, 0.0]])],
                     [np.array([[0.0, 0.0, 0.0]])]) is None
    assert accrocher((0.0, 0.0), [np.array([[0.0, 0.0], [1.0, 1.0]])],
                     [np.array([[0.0, 0.0, 0.0]])]) is None


def test_le_rayon_de_visee_se_regle():
    ecran, monde = _carre()
    # (20, 30) est DANS le carré, à 20 pixels de l'arête de gauche. Viser
    # (0, 30) ne prouverait rien : ce point est PILE sur l'arête, donc à zéro
    # pixel d'elle, et il s'accrocherait quel que soit le rayon.
    assert accrocher((20.0, 30.0), ecran, monde, rayon=4.0) is None
    assert accrocher((20.0, 30.0), ecran, monde, rayon=40.0) is not None


# ── Ce qu'on lit entre les deux points ─────────────────────────────────────
def test_la_mesure_donne_la_distance_et_les_trois_ecarts():
    m = mesure((0.0, 0.0, 0.0), (3.0, 4.0, 12.0))
    assert m["distance"] == pytest.approx(13.0)
    assert (m["dx"], m["dy"], m["dz"]) == pytest.approx((3.0, 4.0, 12.0))
    assert m["milieu"] == pytest.approx((1.5, 2.0, 6.0))


def test_la_mesure_est_la_meme_dans_les_deux_sens():
    a, b = (1.0, -2.0, 5.0), (7.0, 3.0, -1.0)
    assert mesure(a, b)["distance"] == pytest.approx(mesure(b, a)["distance"])
    assert mesure(a, b)["milieu"] == pytest.approx(mesure(b, a)["milieu"])


def test_deux_points_confondus_donnent_zero():
    m = mesure((4.0, 4.0, 4.0), (4.0, 4.0, 4.0))
    assert m["distance"] == pytest.approx(0.0)


def test_l_accroche_dit_ce_qu_elle_a_vise():
    """Le genre sert à l'affichage : on écrit « coin » ou « milieu » à côté du
    repère pour que l'utilisateur sache ce qu'il a attrapé."""
    ecran, monde = _carre()
    assert isinstance(accrocher((3.0, 2.0), ecran, monde), Accroche)
    assert {a.genre for a in [accrocher((3.0, 2.0), ecran, monde),
                              accrocher((50.0, 3.0), ecran, monde),
                              accrocher((25.0, 4.0), ecran, monde)]} == {
        "sommet", "milieu", "arete"}
