# -*- coding: utf-8 -*-
"""Base neoGen — rangement de jeu de société.

Idée de Sébastien Dehay (formulaire du site, 2026-09-27) : « pour la
bibliothèque de neoGen, étant grand fan de jeu de société, des inserts pour
mettre des cartes et jeton ou meeple ».

Un seul bac, avec un CONTENU au choix : un logement de cartes avec son
échancrure, des godets ronds pour les jetons, ou des cases pour les meeples.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_GEN = Path(__file__).resolve().parents[1] / "tools" / "gen_neogen_objets.py"
CONTENUS = ("cartes", "jetons", "meeples")


@pytest.fixture(scope="module")
def rangement():
    spec = importlib.util.spec_from_file_location("gen_rangement", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {o["id"]: o for o in mod.OBJETS}["rangement_jeu"]


def _construire(obj, **extra):
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts
    ns = _defauts(obj)
    ns.update(extra)
    return L.poser_au_sol(L.executer_sandbox(str(obj["code"]), ns))


# ── Un bac creux, pas un pavé ──────────────────────────────────────────────
@pytest.mark.parametrize("contenu", CONTENUS)
def test_le_bac_est_creuse(contenu, rangement):
    """⚠️ Le bac se taille dans un bloc PLEIN. Creuser la boîte d'abord ne
    laisserait aucune cloison entre les cases : mon premier essai rendait un
    bac vide, sans séparation."""
    from core.neogen import libre as L
    longueur, largeur, hauteur = 140.0, 90.0, 30.0
    m = _construire(rangement, contenu=contenu, longueur=longueur,
                    largeur=largeur, hauteur=hauteur)
    assert L.verifier(m) is None, contenu
    assert m.body_count == 1, contenu
    plein = longueur * largeur * hauteur
    assert m.volume < plein * 0.75, f"{contenu} : rien n'a été creusé"


@pytest.mark.parametrize("contenu", CONTENUS)
def test_l_encombrement_est_celui_demande(contenu, rangement):
    """Un insert se glisse dans une boîte : il ne doit pas dépasser d'un
    millimètre de ce qu'on a saisi."""
    m = _construire(rangement, contenu=contenu, longueur=120.0, largeur=80.0,
                    hauteur=25.0)
    etendue = m.bounds[1] - m.bounds[0]
    assert etendue[0] == pytest.approx(120.0, abs=0.05)
    assert etendue[1] == pytest.approx(80.0, abs=0.05)
    assert etendue[2] == pytest.approx(25.0, abs=0.05)


@pytest.mark.parametrize("contenu", CONTENUS)
def test_le_fond_reste_plein(contenu, rangement):
    """Sinon le contenu tombe dans la boîte."""
    m = _construire(rangement, contenu=contenu)
    assert m.contains(np.array([[0.0, 0.0, 0.5]]))[0], contenu


# ── Le logement de cartes ──────────────────────────────────────────────────
def test_le_logement_suit_la_taille_de_la_carte(rangement):
    petit = _construire(rangement, contenu="cartes", carte_largeur=45,
                        carte_hauteur=68, longueur=120, largeur=100)
    grand = _construire(rangement, contenu="cartes", carte_largeur=70,
                        carte_hauteur=120, longueur=120, largeur=140)
    assert grand.volume / (120 * 140) < petit.volume / (120 * 100)


def test_la_pochette_laisse_plus_de_jeu(rangement):
    """Une carte sous pochette est plus épaisse ET plus large : sans ce jeu
    supplémentaire, le paquet frotte et ne se sort plus à une main."""
    nu = _construire(rangement, contenu="cartes", sous_pochette=False)
    sous = _construire(rangement, contenu="cartes", sous_pochette=True)
    assert sous.volume < nu.volume            # logement plus grand, donc moins de matière


def test_l_echancrure_perce_une_seule_paroi(rangement):
    """De part en part, le bac perdrait ses deux faces et tiendrait beaucoup
    moins bien. On vérifie que la paroi ARRIÈRE reste pleine."""
    largeur, paroi = 90.0, 1.6
    m = _construire(rangement, contenu="cartes", largeur=largeur, encoche=True)
    devant = np.array([[0.0, -largeur / 2.0 + paroi / 2.0, 14.0]])
    derriere = np.array([[0.0, largeur / 2.0 - paroi / 2.0, 14.0]])
    assert not m.contains(devant)[0], "l'échancrure doit ouvrir la paroi avant"
    assert m.contains(derriere)[0], "la paroi arrière doit rester pleine"


def test_l_echancrure_se_desactive(rangement):
    largeur, paroi = 90.0, 1.6
    m = _construire(rangement, contenu="cartes", largeur=largeur, encoche=False)
    devant = np.array([[0.0, -largeur / 2.0 + paroi / 2.0, 14.0]])
    assert m.contains(devant)[0]


# ── Les cases et les godets ────────────────────────────────────────────────
@pytest.mark.parametrize("contenu", ["jetons", "meeples"])
def test_plus_de_cases_retire_plus_de_matiere(contenu, rangement):
    peu = _construire(rangement, contenu=contenu, cases_x=2, cases_y=2)
    beaucoup = _construire(rangement, contenu=contenu, cases_x=6, cases_y=4)
    assert beaucoup.volume != pytest.approx(peu.volume, rel=0.01)


@pytest.mark.parametrize("contenu", ["jetons", "meeples"])
def test_trop_de_cases_pour_le_bac_ne_rend_pas_un_bloc_plein(contenu, rangement):
    """LE défaut trouvé au balayage : demander 10 × 8 cases sur un bac de
    40 × 40 ne creusait RIEN, en silence (mesuré : 100 % de matière). On ramène
    désormais le nombre de cases à ce qui tient, au lieu de renoncer."""
    cote = 40.0
    m = _construire(rangement, contenu=contenu, cases_x=10, cases_y=8,
                    longueur=cote, largeur=cote, hauteur=30.0)
    plein = cote * cote * 30.0
    assert m.volume < plein * 0.85, f"{contenu} : bloc plein, rien n'a été creusé"


@pytest.mark.parametrize("contenu", ["jetons", "meeples"])
def test_une_seule_case_marche_aussi(contenu, rangement):
    from core.neogen import libre as L
    m = _construire(rangement, contenu=contenu, cases_x=1, cases_y=1)
    assert L.verifier(m) is None
    assert m.volume < 140 * 90 * 30 * 0.75


def test_les_godets_sont_ronds_et_les_cases_carrees(rangement):
    """Deux contenus, deux formes : à réglages égaux, un godet rond laisse plus
    de matière dans les coins qu'une case carrée."""
    ronds = _construire(rangement, contenu="jetons", cases_x=4, cases_y=3)
    carres = _construire(rangement, contenu="meeples", cases_x=4, cases_y=3)
    assert ronds.volume > carres.volume


# ── Les bornes et le formulaire ────────────────────────────────────────────
@pytest.mark.parametrize("dims", [(40, 40, 10), (140, 90, 30), (250, 250, 90)])
@pytest.mark.parametrize("contenu", CONTENUS)
def test_saine_d_un_bout_a_l_autre_des_bornes(dims, contenu, rangement):
    from core.neogen import libre as L
    longueur, largeur, hauteur = dims
    m = _construire(rangement, contenu=contenu, longueur=longueur,
                    largeur=largeur, hauteur=hauteur)
    assert L.verifier(m) is None, (contenu, dims)
    assert m.body_count == 1


def test_les_reglages_se_masquent_selon_le_contenu(rangement):
    """Le diamètre d'une carte n'a aucun sens quand on range des jetons."""
    visible = rangement.get("visible_si", {})
    cache = rangement.get("cache_si", {})
    for champ in ("carte_largeur", "carte_hauteur", "sous_pochette", "encoche"):
        assert visible.get(champ) == "contenu=cartes", champ
    for champ in ("cases_x", "cases_y"):
        assert cache.get(champ) == "contenu=cartes", champ


def test_toutes_les_options_passent_la_validation(rangement):
    """Exactement ce que fait l'installation chez l'utilisateur."""
    from core.neogen.objets_module import _defauts, verifier_variantes
    assert verifier_variantes(rangement, _defauts(rangement)) is None
