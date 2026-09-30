# -*- coding: utf-8 -*-
"""Boîte + couvercle : la répartition sur deux plateaux.

Idée de Pierre Mathez (formulaire du site, 2026-09-28) : « J'ai voulu faire une
boîte ronde avec couvercle de 155 mm de diamètre. neoSlice m'a indiqué que la
pièce est trop grande pour le plateau choisi. Serait-il possible de séparer le
couvercle de la boîte, soit en positionnant sur deux plateaux, soit de générer
le couvercle et le fond séparément ? »

Le couvercle était toujours posé À CÔTÉ de la boîte, à 16 mm d'elle. Chaque
pièce tenait sur le plateau, jamais les deux ensemble.

⚠ La recette ne connaît PAS l'imprimante choisie : `construire()` ne lui passe
que ses propres paramètres. Le mode automatique s'appuie donc sur un seuil fixe
de 250 mm, en dessous du plateau le plus répandu, et les deux réglages manuels
priment. C'est le compromis, il est testé comme tel.
"""
import importlib.util
from pathlib import Path

import pytest

_GEN = Path(__file__).resolve().parents[1] / "tools" / "gen_neogen_objets.py"
FORMES = ("ronde", "carree", "rectangulaire")


@pytest.fixture(scope="module")
def boite():
    spec = importlib.util.spec_from_file_location("gen_boite", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {o["id"]: o for o in mod.OBJETS}["boite"]


def _construire(obj, **extra):
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts
    ns = _defauts(obj)
    ns.update(extra)
    return L.executer_sandbox(str(obj["code"]), ns)


def _plateaux(piece):
    """Le numéro de plateau porté par chaque corps de la scène."""
    geo = getattr(piece, "geometry", {})
    return [(v.metadata or {}).get("neoslice_plate") for v in geo.values()]


def _emprise(piece):
    b = piece.bounds
    return float(b[1][0] - b[0][0]), float(b[1][1] - b[0][1])


# ── Le cas exact de Pierre ─────────────────────────────────────────────────
def test_la_boite_ronde_de_155_tient_sur_un_plateau(boite):
    """155 mm de diamètre, réglages par défaut. Côte à côte, l'ensemble faisait
    336 mm de profondeur et ne rentrait sur aucun plateau."""
    piece = _construire(boite, forme="ronde", taille=155, hauteur=60)
    x, y = _emprise(piece)
    assert max(x, y) < 256, f"{x:.0f} x {y:.0f} mm, toujours trop grand"
    assert sorted(_plateaux(piece)) == [0, 1], "les deux pièces doivent être séparées"


def test_le_defaut_d_avant_est_bien_reproductible(boite):
    """On garde le comportement d'origine accessible, et on vérifie qu'il est
    bien celui qui débordait : c'est ce qui prouve que le correctif sert."""
    piece = _construire(boite, forme="ronde", taille=155, hauteur=60,
                        disposition="cote")
    _x, y = _emprise(piece)
    assert y > 256, "côte à côte, une boîte de 155 doit bien déborder"


# ── Le mode automatique ────────────────────────────────────────────────────
@pytest.mark.parametrize("forme", FORMES)
def test_une_petite_boite_reste_sur_un_seul_plateau(forme, boite):
    """Séparer systématiquement obligerait à lancer deux impressions pour une
    boîte de 5 cm. Le mode automatique doit rester côte à côte tant que ça
    tient."""
    piece = _construire(boite, forme=forme, taille=50, longueur=90, largeur=60)
    assert _plateaux(piece) == [None, None], f"{forme} : séparée pour rien"


@pytest.mark.parametrize("forme", FORMES)
def test_une_grande_boite_passe_sur_deux_plateaux(forme, boite):
    piece = _construire(boite, forme=forme, taille=170, longueur=200,
                        largeur=170, hauteur=50)
    assert sorted(_plateaux(piece)) == [0, 1], forme


def test_le_couvercle_coulissant_suit_la_meme_regle(boite):
    """La quatrième branche du code, celle du couvercle qui glisse."""
    grand = _construire(boite, coulissant=True, forme="rectangulaire",
                        longueur=220, largeur=180, hauteur=60)
    assert sorted(_plateaux(grand)) == [0, 1]
    petit = _construire(boite, coulissant=True, forme="rectangulaire",
                        longueur=90, largeur=60, hauteur=30)
    assert petit == petit and _plateaux(petit) == [None, None]


# ── Les deux réglages manuels ──────────────────────────────────────────────
@pytest.mark.parametrize("forme", FORMES)
def test_on_peut_forcer_les_deux_plateaux_sur_une_petite_boite(forme, boite):
    """Pour imprimer le couvercle dans une autre couleur, par exemple."""
    piece = _construire(boite, forme=forme, taille=50, disposition="plateaux")
    assert sorted(_plateaux(piece)) == [0, 1], forme


@pytest.mark.parametrize("forme", FORMES)
def test_on_peut_forcer_le_cote_a_cote_sur_une_grande_boite(forme, boite):
    """Celui qui a un plateau de 350 mm ne doit pas subir notre seuil."""
    piece = _construire(boite, forme=forme, taille=170, longueur=200,
                        largeur=170, disposition="cote")
    assert _plateaux(piece) == [None, None], forme


# ── Rien d'autre n'a bougé ─────────────────────────────────────────────────
@pytest.mark.parametrize("forme", FORMES)
@pytest.mark.parametrize("disposition", ["auto", "cote", "plateaux"])
def test_la_boite_reste_saine_dans_tous_les_cas(forme, disposition, boite):
    """Taille choisie pour que le côte à côte reste sous la limite du
    validateur : on teste la santé de la pièce, pas la limite."""
    from core.neogen import libre as L
    piece = _construire(boite, forme=forme, taille=100, longueur=110,
                        largeur=90, hauteur=45, disposition=disposition)
    assert L.verifier(piece) is None, (forme, disposition)
    assert len(piece.geometry) == 2, "il faut toujours la boîte ET le couvercle"


def test_forcer_le_cote_a_cote_trop_grand_reste_refuse(boite):
    """Mesuré : le validateur refuse toute scène dépassant 256 mm, et il le
    faisait DÉJÀ avant ce correctif. Forcer le côte à côte sur une grande boîte
    retombe donc sur l'ancienne limite, c'est normal et c'est la raison d'être
    des deux autres modes. Ce test existe pour que personne ne prenne ce refus
    pour une régression."""
    from core.neogen import libre as L
    grande = _construire(boite, forme="ronde", taille=155, hauteur=60,
                         disposition="cote")
    assert L.verifier(grande) is not None, "le garde-fou doit rester actif"

    separee = _construire(boite, forme="ronde", taille=155, hauteur=60,
                          disposition="plateaux")
    assert L.verifier(separee) is None, "séparée, la même boîte doit passer"


def test_les_deux_pieces_ne_se_chevauchent_jamais_cote_a_cote(boite):
    """Sur un seul plateau, elles doivent rester séparées : c'était le rôle du
    décalage de 16 mm, que le correctif recalcule au lieu de le figer."""
    piece = _construire(boite, forme="ronde", taille=80, disposition="cote")
    corps, couvercle = list(piece.geometry.values())
    assert min(couvercle.bounds[0][1], corps.bounds[0][1]) < 0
    ecart = couvercle.bounds[0][1] - corps.bounds[1][1]
    assert ecart == pytest.approx(16.0, abs=1.0), f"écart de {ecart:.1f} mm"


def test_toutes_les_options_passent_la_validation(boite):
    """Exactement ce que fait l'installation chez l'utilisateur."""
    from core.neogen.objets_module import _defauts, verifier_variantes
    assert verifier_variantes(boite, _defauts(boite)) is None
