# -*- coding: utf-8 -*-
"""Base neoGen — poignées du Bac empilable et Cheville de meuble.

Ces deux recettes vivent dans tools/gen_neogen_objets.py (données de la base
téléchargeable). Elles corrigent deux retours vécus :

  - la poignée dessinée par Nicolas est une ENCOCHE qui interrompt le bord du
    haut, pas un trou fermé (« regarde bien l'image ») ; Emmanuel a ensuite
    demandé de GARDER aussi l'ancienne poignée fermée, avec le même choix rond
    ou nid d'abeille, d'où les quatre styles ;
  - les cannelures de la cheville étaient coupées net par les chanfreins des
    deux bouts : bouchées, elles n'évacuaient ni la colle ni l'air.

Le balayage d'options du générateur n'essaie qu'UNE option à la fois : il teste
donc les styles de poignée avec la case « Poignées » DÉCOCHÉE, et ne voit rien.
D'où ces mesures explicites.
"""
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

_GEN = Path(__file__).resolve().parents[1] / "tools" / "gen_neogen_objets.py"
_STYLES_OUVERTS = ("alveolee", "ovale")
_STYLES_FERMES = ("fermee_alveolee", "fermee_ovale")
_TOUS = _STYLES_OUVERTS + _STYLES_FERMES


@pytest.fixture(scope="module")
def objets():
    spec = importlib.util.spec_from_file_location("gen_bac", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {o["id"]: o for o in mod.OBJETS}


def _construire(obj, extra=None):
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts
    ns = _defauts(obj)
    ns.update(extra or {})
    return L.poser_au_sol(L.executer_sandbox(str(obj["code"]), ns))


def _bac(objets, style, **extra):
    opts = {"motif": "nid_abeille", "poignees": True, "style_poignee": style}
    opts.update(extra)
    return _construire(objets["bac_empilable"], opts)


# ── Bac empilable : les quatre styles de poignée ────────────────────────────
def test_les_quatre_styles_sont_declares(objets):
    """Le formulaire est construit à partir de cette déclaration : les anciennes
    poignées fermées doivent rester proposées (demande d'Emmanuel)."""
    choix = {c[0]: c for c in objets["bac_empilable"]["choix"]}
    ids = [v[0] for v in choix["style_poignee"][3]]
    assert ids == list(_TOUS)
    assert choix["style_poignee"][4] == "alveolee"      # l'encoche par défaut


@pytest.mark.parametrize("style", _TOUS)
@pytest.mark.parametrize("dims", [(60, 50, 25), (120, 90, 50), (220, 180, 100)])
def test_poignee_saine_a_toutes_les_tailles(objets, style, dims):
    from core.neogen import libre as L
    lg, la, h = dims
    m = _bac(objets, style, longueur=lg, largeur=la, hauteur=h)
    assert L.verifier(m) is None, (style, dims)
    assert m.is_watertight and m.bounds[0][2] < 0.01
    # l'encombrement ne bouge pas d'un cheveu : le bac s'empile toujours.
    # (Il dépasse les cotes demandées de 2,3 mm par côté : c'est la collerette
    # évasée, qui reçoit le bac du dessus. On compare donc au même bac sans
    # poignée, pas aux cotes saisies.)
    nu = _bac(objets, style, longueur=lg, largeur=la, hauteur=h, poignees=False)
    ecart = abs((m.bounds[1] - m.bounds[0]) - (nu.bounds[1] - nu.bounds[0]))
    assert ecart.max() < 0.01, (style, dims)


@pytest.mark.parametrize("style", _TOUS)
def test_poignee_ouvre_vraiment_la_paroi(objets, style):
    """Une option qui ne retire rien EN SILENCE est un défaut, pas un choix.

    Mesuré sur des parois PLEINES : en nid d'abeille, la poignée écarte aussi
    les alvéoles qu'elle effleure (sinon il reste des éclats de paroi), et un
    trou fermé peut alors rendre un peu plus de matière qu'il n'en retire."""
    sans = _bac(objets, style, motif="plein", poignees=False)
    avec = _bac(objets, style, motif="plein")
    assert avec.volume < sans.volume - 2000.0, style


@pytest.mark.parametrize("style", _TOUS)
def test_encoche_coupe_le_bord_le_trou_ferme_le_garde(objets, style):
    """LA différence entre les deux familles, mesurée au bon endroit.

    La collerette évasée déborde de 2,3 mm : on sonde donc au milieu de SON
    épaisseur, pas au droit du mur droit (sonder le mur à cette hauteur ne
    prouve rien, il n'y a plus de matière là de toute façon)."""
    lg, h = 120.0, 50.0
    m = _bac(objets, style, longueur=lg, largeur=90, hauteur=h)
    x = lg / 2.0 + 2.3 - 1.0
    bord = m.contains(np.array([[x, 0.0, h - 1.0], [-x, 0.0, h - 1.0]]))
    if style in _STYLES_OUVERTS:
        assert not bord.any(), f"{style} : le bord du haut doit être entaillé"
    else:
        assert bord.all(), f"{style} : le bord du haut doit rester plein"


@pytest.mark.parametrize("style", _STYLES_FERMES)
def test_trou_ferme_bien_dans_la_paroi(objets, style):
    """L'ancienne poignée : un trou centré sur la bande, la main passe dedans."""
    lg, h = 120.0, 50.0
    m = _bac(objets, style, motif="plein", longueur=lg, largeur=90, hauteur=h)
    x = lg / 2.0 - 1.0                       # milieu du mur droit
    zc = ((2.4 + 4.0) + (h - 8.0 - 4.0)) / 2.0
    assert not m.contains(np.array([[x, 0.0, zc], [-x, 0.0, zc]])).any()
    # et la paroi reste pleine juste au dessus du fond
    assert m.contains(np.array([[x, 0.0, 3.4], [-x, 0.0, 3.4]])).all()


def _carte_petit_cote(m, mini, n_u=96, n_z=24):
    """Carte matière/vide au milieu de l'épaisseur d'un petit côté, échantillonnée
    symétriquement pour pouvoir la comparer à son miroir."""
    b0, b1 = m.bounds
    ep = 3.3                       # débord de collerette (2,3) + demi paroi (1,0)
    x = (b0[0] + ep) if mini else (b1[0] - ep)
    us = np.linspace(b0[1] + 4.0, b1[1] - 4.0, n_u)
    zs = np.linspace(b0[2] + 8.0, b1[2] - 14.0, n_z)
    pts = np.zeros((n_z * n_u, 3))
    pts[:, 0] = x
    pts[:, 1] = np.tile(us, n_z)
    pts[:, 2] = np.repeat(zs, n_u)
    return m.contains(pts).reshape(n_z, n_u)


@pytest.mark.parametrize("style", _TOUS)
def test_poignee_percee_des_DEUX_cotes_et_symetrique(objets, style):
    """« J'ai deux trous à gauche de la poignée et un seul à droite, c'est pas
    beau. » Les deux petits côtés sont ouverts, à l'identique, et chaque face
    est son propre miroir."""
    m = _bac(objets, style, longueur=120, largeur=90, hauteur=50)
    vides = []
    for mini in (True, False):
        carte = _carte_petit_cote(m, mini)
        assert np.array_equal(carte, carte[:, ::-1]), f"{style} mini={mini}"
        vides.append(int((~carte).sum()))
    assert all(v > 40 for v in vides), (style, vides)
    assert abs(vides[0] - vides[1]) <= 2, (style, vides)


# ── Cheville de meuble : les cannelures traversent les chanfreins ───────────
def _aire_section(m, z):
    sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return 0.0
    return sum(p.area for p in sec.to_2D()[0].polygons_full)


def test_cheville_dimensions_exactes(objets):
    from core.neogen import libre as L
    d, lg = 8.0, 35.0
    m = _construire(objets["cheville"], {"diametre": d, "longueur": lg})
    assert L.verifier(m) is None
    b = m.bounds[1] - m.bounds[0]
    # Le fût est un polygone à facettes, donc inscrit : il mesure 0,09 mm de
    # moins que le cercle idéal. C'est du bon côté pour une cheville, qui doit
    # entrer dans un trou percé à la cote, jamais forcer.
    assert d - 0.15 <= b[0] <= d and d - 0.15 <= b[1] <= d
    assert b[2] == pytest.approx(lg, abs=0.05)
    # chanfreinée aux DEUX bouts : la section y est plus petite que le fût
    assert _aire_section(m, 0.2) < _aire_section(m, lg / 2.0) * 0.7
    assert _aire_section(m, lg - 0.2) < _aire_section(m, lg / 2.0) * 0.7


@pytest.mark.parametrize("d,lg", [(8, 35), (6, 30), (16, 80), (4, 12)])
def test_cannelures_traversent_les_chanfreins(objets, d, lg):
    """Retour de Nicolas, capture à l'appui : arrêtées au pied du chanfrein, les
    cannelures étaient bouchées aux deux bouts et l'air restait piégé au fond du
    trou. Elles doivent mordre DANS le chanfrein, des deux côtés, et s'y perdre
    d'elles mêmes quand le cône passe sous le fond de la rainure.

    On compare la même section avec et sans cannelures : à cette hauteur, le
    rayon de la pièce est identique, seule la rainure peut faire la différence
    (sonder un rayon fixe échoue, on tombe soit sous le fond de rainure, soit
    hors de la pièce)."""
    c = min(1.5, d * 0.18)
    avec = _construire(objets["cheville"], {"diametre": d, "longueur": lg})
    sans = _construire(objets["cheville"],
                       {"diametre": d, "longueur": lg, "cannelures": False})
    assert avec.volume < sans.volume
    for z in (c * 0.85, lg - c * 0.85):               # DANS le chanfrein
        a, b = _aire_section(avec, z), _aire_section(sans, z)
        assert a < b - 0.05, f"d={d} lg={lg} z={z:.2f} : {a:.2f} vs {b:.2f}"


def test_cannelures_ouvertes_sur_toute_la_longueur(objets):
    """Le canal ne doit se refermer nulle part entre les deux bouts."""
    d, lg = 8.0, 35.0
    m = _construire(objets["cheville"], {"diametre": d, "longueur": lg})
    sans = _construire(objets["cheville"],
                       {"diametre": d, "longueur": lg, "cannelures": False})
    for z in np.linspace(1.6, lg - 1.6, 25):
        assert _aire_section(m, z) < _aire_section(sans, z) - 0.5, z


def test_cheville_sans_cannelures_reste_ronde(objets):
    """La case décochée rend un tourillon lisse, à la cote."""
    d, lg = 8.0, 35.0
    m = _construire(objets["cheville"],
                    {"diametre": d, "longueur": lg, "cannelures": False})
    assert _aire_section(m, lg / 2.0) == pytest.approx(math.pi * (d / 2.0) ** 2,
                                                       rel=0.01)
