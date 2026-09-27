# -*- coding: utf-8 -*-
"""Rotation d'un ensemble : ce qui est collé à la pièce tourne avec elle.

Demande d'Emmanuel (2026-09-12) : « quand une pièce est collée à un objet ou
qu'on a fait un trou dedans, quand on tourne cet objet il faut que toutes les
pièces collées tournent également »."""
import pytest

from neoforge.projet import ergonomie as E
from neoforge.projet.modele import Forme, Projet


def _plaque_percee():
    """Le trou et le bloc sont RATTACHÉS à la plaque.

    Depuis le 2026-09-12, le lien est explicite (parent et enfants) et non plus
    déduit du contact : sans cela, on ne pouvait plus ajuster une petite pièce
    contre une grande sans emmener la grande (choix d'Emmanuel)."""
    plaque = Forme("cube", "matiere", [0, 0, 5], [80, 40, 10])
    return Projet([
        plaque,
        Forme("cylindre", "creux", [30, 0, 5], [8, 8, 30], parent=plaque.ident),
        Forme("cube", "matiere", [0, 0, 16], [20, 20, 12], parent=plaque.ident),
        Forme("cube", "matiere", [200, 0, 5], [10, 10, 10]),    # pièce éloignée
    ])


def test_les_pieces_rattachees_sont_reconnues():
    p = _plaque_percee()
    assert E.enfants(p, 0) == [1, 2]
    assert E.descendants(p, 0) == [1, 2]         # le trou et le bloc
    assert E.groupe(p, 0) == [0, 1, 2]
    assert E.descendants(p, 3) == []             # la lointaine n'a rien sous elle


def test_un_enfant_d_enfant_suit_aussi():
    p = _plaque_percee()
    p.etapes[3].parent = p.etapes[2].ident       # la lointaine sous le bloc
    assert E.enfants(p, 0) == [1, 2]             # pas elle en direct
    assert E.descendants(p, 0) == [1, 2, 3]      # mais bien dans la descendance


def test_pas_de_boucle_possible():
    p = _plaque_percee()
    assert not E.peut_recevoir(p, 0, 0)          # pas sur soi même
    assert not E.peut_recevoir(p, 0, 1)          # pas sous son propre enfant
    assert E.peut_recevoir(p, 3, 0)
    assert E.rattacher(p, 3, 0) and p.etapes[3].parent == p.etapes[0].ident
    assert E.rattacher(p, 3, None) and p.etapes[3].parent == ""


def test_un_quart_de_tour_emmene_le_trou_et_le_bloc():
    p = _plaque_percee()
    bouges = E.tourner_groupe(p, 0, (0, 0, 1), 90.0)
    assert sorted(bouges) == [0, 1, 2]
    # le trou était à +30 en X, il passe à +30 en Y (rotation autour du centre)
    assert p.etapes[1].pos == pytest.approx([0, 30, 5], abs=1e-6)
    assert p.etapes[1].rot[2] == pytest.approx(90)
    assert p.etapes[2].pos == pytest.approx([0, 0, 16], abs=1e-6)   # bloc centré
    assert p.etapes[0].rot[2] == pytest.approx(90)
    assert p.etapes[3].pos == pytest.approx([200, 0, 5])            # la lointaine dort


def test_le_trou_reste_dans_la_matiere_apres_rotation():
    p = _plaque_percee()
    E.tourner_groupe(p, 0, (0, 0, 1), 37.0)
    plaque, trou = p.etapes[0], p.etapes[1]
    mini, maxi = E.boite(plaque)
    centre = trou.pos
    assert all(mini[k] - 1e-6 <= centre[k] <= maxi[k] + 1e-6 for k in range(3))


def test_rotation_autour_d_un_axe_quelconque_puis_retour():
    p = _plaque_percee()
    depart = [list(e.pos) for e in p.etapes], [list(e.rot) for e in p.etapes]
    E.tourner_groupe(p, 0, (1, 1, 0), 40.0)
    E.tourner_groupe(p, 0, (1, 1, 0), -40.0)
    for i, e in enumerate(p.etapes):
        assert e.pos == pytest.approx(depart[0][i], abs=1e-6)
        for axe in range(3):
            attendu = depart[1][i][axe] % 360.0
            assert min(abs(e.rot[axe] - attendu), 360 - abs(e.rot[axe] - attendu)) < 1e-3


def test_angles_et_matrice_sont_coherents():
    for rot in ([0, 0, 0], [30, 0, 0], [0, 45, 0], [0, 0, 90], [15, 25, 35]):
        M = E.matrice_rotation(rot)
        retour = E.angles_depuis_matrice(M)
        M2 = E.matrice_rotation(retour)
        for i in range(3):
            assert M2[i] == pytest.approx(M[i], abs=1e-6)
