# -*- coding: utf-8 -*-
"""Les cotes et les poignées suivent la matière qui RESTE après une découpe.

Retour d'Emmanuel : « quand on a coupé une pièce, le point d'origine de la
taille, déplacer et tourner ne change pas, c'est toujours celui de la pièce
avant la coupe. Il faut modifier le point d'origine en fonction de la ou des
parties qu'on garde. »

Mesuré au pilote avant correction : sur un socle de 30 coupé à 10 mm, les
poignées restaient centrées 10 mm au dessus de la matière."""
import pytest

from neoforge.projet.mesures import geometrie_cotes_locale
from neoforge.projet.modele import Forme


def _cube():
    """Un cube de 30 posé au sol : dans SON repère il va de -15 à +15."""
    return Forme("cube", "matiere", [0.0, 0.0, 15.0], [30.0, 30.0, 30.0])


def _par_axe(cotes):
    return {c["axe"]: c for c in cotes}


def test_sans_decoupe_les_cotes_restent_autour_de_l_origine():
    """Le comportement d'avant ne change pas quand rien n'est coupé."""
    cotes = _par_axe(geometrie_cotes_locale(_cube()))
    assert cotes[2]["milieu"][2] == pytest.approx(0.0)


def test_les_cotes_suivent_le_centre_de_la_matiere_restante():
    """Coupé à 10 mm du sol, le morceau gardé est centré à -10 dans le repère
    propre du cube, ce qui fait bien 5 mm de haut dans le monde."""
    cotes = _par_axe(geometrie_cotes_locale(_cube(), demi=[15.0, 15.0, 5.0],
                                            centre=[0.0, 0.0, -10.0]))
    assert cotes[2]["milieu"][2] == pytest.approx(-10.0)
    assert cotes[0]["milieu"][2] == pytest.approx(-10.0 + 5.0 + 3.6 * 0.7)


def test_la_longueur_d_une_cote_ne_change_PAS():
    """La cote porte la DIMENSION réglable, qui reste celle de la forme : c'est
    sa place qui suit la matière, pas sa valeur."""
    entier = _par_axe(geometrie_cotes_locale(_cube()))
    coupe = _par_axe(geometrie_cotes_locale(_cube(), demi=[15.0, 15.0, 5.0],
                                            centre=[0.0, 0.0, -10.0]))
    for axe in (0, 1, 2):
        a = entier[axe]
        b = coupe[axe]
        longueur_a = abs(a["p1"][axe] - a["p0"][axe])
        longueur_b = abs(b["p1"][axe] - b["p0"][axe])
        assert longueur_a == pytest.approx(30.0)
        assert longueur_b == pytest.approx(longueur_a)


def test_le_chiffre_reste_ecarte_du_trait():
    """L'écart de l'étiquette se mesure depuis le CENTRE : avec un centre
    décalé, le calculer depuis l'origine le collait au trait."""
    cotes = _par_axe(geometrie_cotes_locale(_cube(), demi=[15.0, 15.0, 5.0],
                                            centre=[0.0, 0.0, -10.0]))
    for axe in (0, 1, 2):
        c = cotes[axe]
        milieu = [float(v) for v in c["milieu"]]
        etiquette = [float(v) for v in c["etiquette"]]
        distance = sum((etiquette[k] - milieu[k]) ** 2 for k in range(3)) ** 0.5
        assert distance > 1.0
