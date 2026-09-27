# -*- coding: utf-8 -*-
"""Les logements d'écrou : toute la gamme imprimable, aux cotes normalisées.

Demande d'Emmanuel (2026-09-13). Un écrou se mesure ENTRE PLATS (cote « s » de
l'ISO 4032), alors qu'un prisme régulier est défini par son diamètre
circonscrit : c'est cette conversion, plus le jeu d'impression, que ces tests
verrouillent."""
import math

import pytest

from neoforge.projet import ergonomie as E
from neoforge.projet.modele import Forme, Projet


def _projet():
    return Projet([Forme("cube", "matiere", [0, 0, 10], [60, 60, 20])])


@pytest.mark.parametrize("taille", list(E.ECROUS))
def test_chaque_ecrou_retombe_sur_la_norme(taille):
    entre_plats, epaisseur = E.ECROUS[taille]
    f = E.logement_ecrou(_projet(), taille, 0)
    assert f.forme == "prisme" and f.cotes == 6
    assert f.op == "creux"                      # un logement se creuse
    plats = f.dim[0] * math.cos(math.pi / 6)    # circonscrit → entre plats
    assert plats == pytest.approx(entre_plats + E.JEU_ECROU, abs=1e-6)
    assert f.dim[2] == pytest.approx(epaisseur + E.JEU_ECROU, abs=1e-6)


def test_la_gamme_couvre_les_tailles_imprimables():
    assert list(E.ECROUS) == ["M2", "M2.5", "M3", "M4", "M5",
                              "M6", "M8", "M10", "M12"]


def test_le_jeu_existe_vraiment():
    """Sans jeu, l'écrou n'entre pas dans une pièce imprimée."""
    assert E.JEU_ECROU > 0
    f = E.logement_ecrou(_projet(), "M3", 0)
    assert f.dim[0] * math.cos(math.pi / 6) > E.ECROUS["M3"][0]


def test_le_logement_est_pose_sur_le_plateau():
    f = E.logement_ecrou(_projet(), "M3", 0)
    assert E.boite(f)[0][2] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("taille", list(E.ECROUS))
def test_le_noyau_sait_construire_le_logement(taille):
    """Volume exact d'un hexagone d'aire (√3 / 2) × entre plats²."""
    from neoforge.noyau import occ as O
    from neoforge.noyau.primitives import solide
    entre_plats, epaisseur = E.ECROUS[taille]
    f = E.logement_ecrou(_projet(), taille, 0)
    plats = entre_plats + E.JEU_ECROU
    attendu = (math.sqrt(3) / 2) * plats ** 2 * (epaisseur + E.JEU_ECROU)
    assert O.volume(solide(f)) == pytest.approx(attendu, rel=1e-6)
