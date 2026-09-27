# -*- coding: utf-8 -*-
"""Base neoGen — pancarte de porte.

Idée de Pierre Mathez (formulaire du site, 2026-09-26) : « pancarte à suspendre
à la poignée de porte, avec possibilité de mettre un texte, relief ou creux ».

La recette vit dans tools/gen_neogen_objets.py : c'est de la DONNÉE, livrée par
mise à jour de base, sans rebuild. Elle doit donc passer la validation
d'installation, qui ne connaît que les valeurs par défaut de chaque réglage.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_GEN = Path(__file__).resolve().parents[1] / "tools" / "gen_neogen_objets.py"


@pytest.fixture(scope="module")
def pancarte():
    spec = importlib.util.spec_from_file_location("gen_pancarte", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {o["id"]: o for o in mod.OBJETS}["pancarte_porte"]


def _construire(obj, texte="NE PAS | DERANGER", **extra):
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts
    ns = _defauts(obj)
    ns["texte"] = texte
    ns.update(extra)
    return L.poser_au_sol(L.executer_sandbox(str(obj["code"]), ns))


# ── Le réglage relief / creux, demandé par Pierre ──────────────────────────
def test_le_drapeau_grave_est_declare(pancarte):
    """⚠️ Il DOIT s'appeler « grave ».

    Pour tout objet à texte, l'interface ajoute d'office sa propre case
    « Gravé », SAUF si l'objet déclare déjà un drapeau de ce nom. Or cette case
    là n'arriverait pas dans la recette : la validation d'installation ne
    fournit que les options DÉCLARÉES, donc l'objet serait écarté dès que
    quelqu'un coche la case."""
    noms = [f[0] for f in pancarte["flags"]]
    assert "grave" in noms, noms
    assert pancarte["texte"] != "aucun"


def test_relief_ajoute_de_la_matiere_et_gravure_en_retire(pancarte):
    nue = _construire(pancarte, texte="")
    relief = _construire(pancarte)
    grave = _construire(pancarte, grave=True)
    assert relief.volume > nue.volume + 50.0
    assert grave.volume < nue.volume - 50.0


def test_le_relief_depasse_bien_de_la_plaque(pancarte):
    epaisseur = 3.0
    relief = _construire(pancarte, epaisseur=epaisseur, relief_texte=1.0)
    hauteur = float(relief.bounds[1][2] - relief.bounds[0][2])
    assert hauteur == pytest.approx(epaisseur + 1.0, abs=0.05)


@pytest.mark.parametrize("epaisseur,demande", [(2.0, 3.0), (3.0, 1.0), (8.0, 3.0)])
def test_la_gravure_ne_perce_jamais_la_pancarte(pancarte, epaisseur, demande):
    """Une gravure plus profonde que la plaque la trouerait de part en part.
    Il doit rester au moins 0,8 mm de fond, quoi qu'on demande."""
    m = _construire(pancarte, epaisseur=epaisseur, relief_texte=demande, grave=True)
    assert float(m.bounds[1][2] - m.bounds[0][2]) == pytest.approx(epaisseur, abs=0.05)
    # au centre d'une lettre, il reste de la matière sous le fond de gravure
    assert m.contains(np.array([[0.0, -25.0, 0.3]]))[0]


# ── Le texte tient TOUJOURS dans la pancarte ───────────────────────────────
@pytest.mark.parametrize("texte", [
    "NE PAS | DERANGER",
    "REUNION | EN COURS | MERCI",
    "NE PAS DERANGER MERCI BEAUCOUP VRAIMENT",      # une seule ligne, très longue
    "ANTICONSTITUTIONNELLEMENTXXXXXXXXXXXXXXXX",    # un mot interminable
    "A",
])
def test_le_texte_ne_deborde_jamais(pancarte, texte):
    """Une réduction unique, à la proportion, laissait déborder : mesuré, une
    ligne de 38 lettres sortait encore à 100 mm de large sur une pancarte de
    85, et les lettres tombées hors de la plaque faisaient une pièce en CINQ
    morceaux, donc inimprimable."""
    from core.neogen import libre as L
    largeur, hauteur = 85.0, 210.0
    m = _construire(pancarte, texte=texte, largeur=largeur, hauteur=hauteur)
    etendue = m.bounds[1] - m.bounds[0]
    assert etendue[0] == pytest.approx(largeur, abs=0.05), texte
    assert etendue[1] == pytest.approx(hauteur, abs=0.05), texte
    assert m.body_count == 1, texte
    assert L.verifier(m) is None, texte


def test_une_pancarte_sans_texte_se_construit(pancarte):
    """Le champ est facultatif : vide, on veut une plaque nue, pas une erreur."""
    from core.neogen import libre as L
    for vide in ("", "   ", "|"):
        m = _construire(pancarte, texte=vide)
        assert L.verifier(m) is None, repr(vide)


def test_les_lignes_se_separent_par_une_barre(pancarte):
    """Deux lignes doivent donner un dessin DIFFÉRENT d'une seule."""
    une = _construire(pancarte, texte="NE PAS DERANGER")
    deux = _construire(pancarte, texte="NE PAS | DERANGER")
    assert abs(une.volume - deux.volume) > 1.0


# ── La suspension : le trou et la fente ────────────────────────────────────
def test_le_trou_traverse_et_la_matiere_tient_au_dessus(pancarte):
    hauteur, diametre = 210.0, 40.0
    m = _construire(pancarte, hauteur=hauteur, diametre_trou=diametre)
    y_trou = hauteur / 2.0 - max(9.0, diametre * 0.30) - diametre / 2.0
    # le trou est vide de part en part
    assert not m.contains(np.array([[0.0, y_trou, 1.5]]))[0]
    # et il reste une bande PLEINE au dessus : c'est elle qui porte le poids
    assert m.contains(np.array([[0.0, hauteur / 2.0 - 4.0, 1.5]]))[0]


def test_le_crochet_ouvre_le_bord_du_cote(pancarte):
    """Le crochet débouche sur le CÔTÉ, à mi hauteur du trou : la pancarte se
    glisse d'un geste horizontal et le poids la plaque au fond du crochet. Une
    ouverture par le BAS la ferait glisser, une ouverture par le HAUT n'aurait
    aucun intérêt puisque le trou passe déjà sur la béquille."""
    largeur, hauteur, diametre = 85.0, 210.0, 40.0
    y_trou = hauteur / 2.0 - max(9.0, diametre * 0.30) - diametre / 2.0
    cote = np.array([[-largeur / 2.0 + 1.5, y_trou, 1.5]])
    ferme = _construire(pancarte, suspension="trou")
    ouvert = _construire(pancarte, suspension="crochet")
    assert ferme.contains(cote)[0], "le trou fermé garde son bord plein"
    assert not ouvert.contains(cote)[0], "le crochet doit déboucher sur le côté"
    assert ouvert.volume < ferme.volume


@pytest.mark.parametrize("reglages", [
    {}, {"grave": True}, {"diametre_trou": 70}, {"diametre_trou": 25},
    {"largeur": 55, "hauteur": 110}, {"largeur": 140, "hauteur": 250},
    {"texte": ""},
])
def test_le_crochet_reste_une_piece_etanche(pancarte, reglages):
    """⚠️ Le crochet se dessine d'UN SEUL TENANT. En réunissant un disque et un
    couloir, l'intersection avec les facettes du disque créait des segments de
    longueur quasi nulle : contour valide en 2D, 393 sommets, et une plaque
    extrudée en CINQ à QUATORZE morceaux, non étanche donc inimprimable."""
    from core.neogen import libre as L
    m = _construire(pancarte, suspension="crochet", **reglages)
    assert m.is_watertight, reglages
    assert m.body_count == 1, reglages
    assert L.verifier(m) is None, reglages


def test_l_accroche_se_choisit(pancarte):
    choix = {c[0]: c for c in pancarte.get("choix", [])}
    assert "suspension" in choix
    assert [v[0] for v in choix["suspension"][3]] == ["trou", "crochet"]
    assert choix["suspension"][4] == "trou"
    assert "fente" not in [f[0] for f in pancarte["flags"]]


@pytest.mark.parametrize("texte", ["NE PAS\nDERANGER",
                                   "REUNION\r\nEN COURS",
                                   "A\nB | C"])
def test_la_touche_entree_fait_une_nouvelle_ligne(pancarte, texte):
    """L'interface passe à un champ multi lignes : un vrai retour à la ligne
    doit séparer les lignes comme la barre verticale le faisait."""
    from core.neogen import libre as L
    m = _construire(pancarte, texte=texte)
    assert L.verifier(m) is None, repr(texte)
    assert m.body_count == 1


def test_entree_et_barre_donnent_la_meme_pancarte(pancarte):
    par_entree = _construire(pancarte, texte="NE PAS\nDERANGER")
    par_barre = _construire(pancarte, texte="NE PAS|DERANGER")
    assert par_entree.volume == pytest.approx(par_barre.volume, rel=1e-6)
