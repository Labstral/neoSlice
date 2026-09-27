# -*- coding: utf-8 -*-
"""Cadre et anneau : des contours, vides au milieu.

« Ces formes sont pleines au milieu, c'est pour ça que je veux des formes
plates avec juste les contours, comme des cadres dont on peut régler
l'épaisseur, la largeur » (Emmanuel, 2026-09-26).

Deux formes couvrent la demande : le CADRE à côtés droits, dont le nombre de
côtés fait le triangle (3), le carré ou le rectangle (4) et l'hexagone (6), et
l'ANNEAU rond, qui peut aussi être ovale. Les deux naissent plats et se règlent
en largeur, profondeur, hauteur et épaisseur de bord.
"""
import math

import numpy as np
import pytest
import trimesh

from neoforge.noyau import maillage as M
from neoforge.noyau.construction import Constructeur
from neoforge.projet import ergonomie as E
from neoforge.projet.mesures import cotes
from neoforge.projet.modele import Forme, Projet


def _piece(forme, dim, **kw):
    f = Forme(forme, "matiere", [0.0, 0.0, dim[2] / 2.0], [float(v) for v in dim])
    for cle, valeur in kw.items():
        setattr(f, cle, valeur)
    p = Projet.nouveau()
    p.etapes = [f]
    res = Constructeur().construire(p)
    assert res[-1].erreur is None, res[-1].erreur
    V, F = M.trianguler(res[-1].forme)
    return trimesh.Trimesh(vertices=V, faces=F), f


def _bord_mesure(maillee, dim):
    """Largeur du premier bloc de matière rencontré en traversant la pièce."""
    xs = np.linspace(-dim[0] / 2.0, dim[0] / 2.0, 1601)
    pts = np.column_stack([xs, np.zeros_like(xs), np.full_like(xs, dim[2] / 2.0)])
    dedans = maillee.contains(pts)
    n = 0
    for d in dedans:
        if d:
            n += 1
        elif n:
            break
    return n * float(xs[1] - xs[0])


# ── Le milieu est VIDE, c'est tout l'objet de ces formes ───────────────────
@pytest.mark.parametrize("forme,cotes_n", [("cadre", 4), ("cadre", 3),
                                           ("cadre", 6), ("anneau", 4)])
def test_le_milieu_est_vide(forme, cotes_n):
    dim = [40.0, 40.0, 4.0]
    m, _f = _piece(forme, dim, cotes=cotes_n, bord=4.0)
    assert not m.contains(np.array([[0.0, 0.0, dim[2] / 2.0]]))[0]
    # et le bord, lui, est bien de la matière. On sonde au milieu du côté du
    # BAS, plat sur toutes ces formes : sonder à gauche tombe hors d'un
    # triangle, qui n'a aucune matière là à mi hauteur.
    assert m.contains(np.array([[0.0, -dim[1] / 2.0 + 2.0, dim[2] / 2.0]]))[0]


@pytest.mark.parametrize("forme", ["cadre", "anneau"])
def test_un_contour_pese_moins_qu_une_forme_pleine(forme):
    creux, _ = _piece(forme, [40.0, 40.0, 4.0], cotes=4, bord=4.0)
    plein, _ = _piece("cube" if forme == "cadre" else "cylindre",
                      [40.0, 40.0, 4.0])
    assert creux.volume < plein.volume * 0.65


# ── Les chiffres du panneau sont les VRAIES cotes ──────────────────────────
@pytest.mark.parametrize("cotes_n", [3, 4, 5, 6, 8])
def test_la_boite_fait_exactement_les_cotes_demandees(cotes_n):
    """Un triangle inscrit dans un cercle ne remplit pas sa boîte : sans
    normalisation, « largeur 40 » rendait une pièce de 34,6 mm."""
    dim = [40.0, 30.0, 4.0]
    m, _f = _piece("cadre", dim, cotes=cotes_n, bord=3.0)
    etendue = m.bounds[1] - m.bounds[0]
    assert etendue[0] == pytest.approx(dim[0], abs=0.05), cotes_n
    assert etendue[1] == pytest.approx(dim[1], abs=0.05), cotes_n
    assert etendue[2] == pytest.approx(dim[2], abs=0.05), cotes_n


def test_l_anneau_peut_etre_ovale():
    m, _f = _piece("anneau", [60.0, 30.0, 4.0], bord=4.0)
    etendue = m.bounds[1] - m.bounds[0]
    assert etendue[0] == pytest.approx(60.0, abs=0.05)
    assert etendue[1] == pytest.approx(30.0, abs=0.05)


# ── L'épaisseur du bord est celle qu'on demande ────────────────────────────
@pytest.mark.parametrize("bord", [2.0, 4.0, 7.0])
def test_l_epaisseur_du_bord_est_respectee_sur_un_carre(bord):
    dim = [40.0, 40.0, 4.0]
    m, _f = _piece("cadre", dim, cotes=4, bord=bord)
    assert _bord_mesure(m, dim) == pytest.approx(bord, abs=0.1)


@pytest.mark.parametrize("bord", [2.0, 4.0, 6.0])
def test_l_epaisseur_du_bord_est_respectee_sur_un_anneau(bord):
    dim = [40.0, 40.0, 4.0]
    m, _f = _piece("anneau", dim, bord=bord)
    assert _bord_mesure(m, dim) == pytest.approx(bord, abs=0.1)


def test_le_bord_d_un_triangle_se_mesure_perpendiculairement():
    """Sur un côté oblique, une coupe horizontale est plus large que le bord.
    On compare donc au bord demandé corrigé de l'inclinaison : 30° pour un
    triangle. Rétrécir la boîte de `bord` tout court n'aurait donné que 2 mm
    de matière au lieu de 4."""
    dim = [40.0, 40.0, 4.0]
    m, _f = _piece("cadre", dim, cotes=3, bord=4.0)
    horizontal = _bord_mesure(m, dim)
    assert horizontal * math.cos(math.radians(30.0)) == pytest.approx(4.0, abs=0.35)


def test_un_bord_plus_epais_que_la_piece_rend_une_forme_pleine():
    """Plutôt qu'une pièce vide, donc invisible et impossible à imprimer."""
    m, _f = _piece("anneau", [20.0, 20.0, 4.0], bord=15.0)
    assert m.contains(np.array([[0.0, 0.0, 2.0]]))[0]
    assert m.volume == pytest.approx(math.pi * 100.0 * 4.0, rel=0.02)


# ── Réglages et interface ──────────────────────────────────────────────────
@pytest.mark.parametrize("forme", ["cadre", "anneau"])
def test_les_trois_axes_se_tirent_a_la_souris(forme):
    """« Pouvoir modifier la taille sur tous les axes. »"""
    _m, f = _piece(forme, [40.0, 30.0, 4.0], cotes=4, bord=4.0)
    assert [c.axe for c in cotes(f)] == [0, 1, 2]


@pytest.mark.parametrize("forme", ["cadre", "anneau"])
def test_une_forme_neuve_nait_plate(forme):
    """Un contour posé à plat sur le plateau, pas un cube de 20."""
    p = Projet.nouveau()
    f = E.nouvelle_forme(p, forme, None)
    assert f.dim[2] < f.dim[0] / 4.0
    assert f.bord == pytest.approx(4.0)
    assert f.pos[2] == pytest.approx(f.dim[2] / 2.0)     # posée sur le plateau


def test_l_epaisseur_du_bord_est_enregistree(tmp_path):
    from neoforge.projet import nfg
    p = Projet.nouveau()
    p.etapes = [Forme("cadre", "matiere", [0, 0, 2], [40.0, 40.0, 4.0])]
    p.etapes[0].bord, p.etapes[0].cotes = 6.5, 3
    relu = nfg.lire(nfg.ecrire(p, tmp_path / "cadre.nfg"))
    assert relu.etapes[0].bord == pytest.approx(6.5)
    assert relu.etapes[0].cotes == 3


def test_les_formes_sont_proposees_dans_le_menu():
    from neoforge.ui.pile import FORMES
    from neoforge.projet.modele import FORMES as MODELE
    for nom in ("cadre", "anneau"):
        assert nom in FORMES and nom in MODELE


def test_les_libelles_existent_dans_les_cinq_langues():
    from neoforge.ui.textes import LANGUES
    for code, mots in LANGUES.items():
        for cle in ("cadre", "anneau", "epaisseur_bord"):
            assert mots.get(cle), f"{code} : {cle} manquant"
