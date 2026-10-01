# -*- coding: utf-8 -*-
"""Ranger les pièces d'un projet sur les plateaux de SON imprimante.

eleovna BERGES, Elegoo Neptune 4 Max, 2026-10-01 : « il serait judicieux que
le logiciel en tienne compte dans la répartition des éléments par plateau sur
un projet volumineux ». Sa capture montrait 23 plateaux côte à côte, un par
pièce, sur une machine qui en tient neuf par plateau.

Deux choses étaient en cause et les deux sont corrigées :
  * neoSlice croyait toutes les imprimantes en 256 mm (test_plateau_reel_par_imprimante) ;
  * à l'import il recopiait les plateaux déclarés DANS LE FICHIER, qui viennent
    souvent d'une machine plus petite, sans jamais proposer de les refaire.

⚠ Deux pièges tenaces, tous deux testés ici :
  * l'écrivain 3MF centre le GROUPE de chaque plateau et compte sur les
    positions relatives des pièces. L'export passait des maillages déjà
    centrés un par un, ce qui EMPILE toutes les pièces d'un même plateau.
    Le défaut dormait tant qu'il n'y avait qu'une pièce par plateau ;
  * le viewer recompacte un plateau dont les pièces s'étalent sur plus de
    300 mm, garde-fou prévu pour les transforms Bambu corrompus. Sur un
    plateau de 420 mm il montrerait autre chose que ce qui sera imprimé.
"""
import math
import random

import pytest

from core.geometry.replateau import Plan, Pose, gain, repartir
from core.geometry.serie import ESPACEMENT_MM, MARGE_MM


def _rectangles(pieces, plan):
    """{plateau: [(id, x0, y0, x1, y1)]} après application du plan."""
    taille = {p[0]: (p[3] - p[1], p[4] - p[2]) for p in pieces}
    origine = {p[0]: (p[1], p[2]) for p in pieces}
    par = {}
    for q in plan.poses:
        w, h = taille[q.id]
        x0 = origine[q.id][0] + q.dx
        y0 = origine[q.id][1] + q.dy
        par.setdefault(q.plateau, []).append((q.id, x0, y0, x0 + w, y0 + h))
    return par


def _chevauchements(rects):
    mauvais = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            if (a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6
                    and a[2] < b[4] - 1e-6 and b[2] < a[4] - 1e-6):
                mauvais.append((a[0], b[0]))
    return mauvais


# ── Le cas d'eleovna ──────────────────────────────────────────────────────
def test_vingt_trois_pieces_tiennent_sur_trois_plateaux():
    pieces = [(f"p{i}", 0.0, 0.0, 100.0, 100.0) for i in range(23)]
    plan = repartir(pieces, (420.0, 420.0))
    assert plan.plateaux == 3
    assert len(plan.poses) == 23
    assert not plan.trop_grandes


def test_la_meme_piece_sur_un_plateau_plus_petit_en_demande_plus():
    pieces = [(f"p{i}", 0.0, 0.0, 100.0, 100.0) for i in range(23)]
    grand = repartir(pieces, (420.0, 420.0))
    petit = repartir(pieces, (256.0, 256.0))
    assert petit.plateaux > grand.plateaux
    assert gain(petit.plateaux, grand) == petit.plateaux - grand.plateaux


def test_gain_nul_quand_il_n_y_a_rien_a_gagner():
    plan = repartir([("a", 0.0, 0.0, 50.0, 50.0)], (420.0, 420.0))
    assert gain(1, plan) == 0


# ── Les invariants : jamais de pièces l'une sur l'autre ───────────────────
@pytest.mark.parametrize("bed", [(180, 180), (256, 256), (350, 320), (420, 420)])
def test_aucun_chevauchement_sur_tailles_melangees(bed):
    random.seed(11)
    pieces = [(f"q{i}", 0.0, 0.0, random.uniform(20, 140), random.uniform(20, 140))
              for i in range(35)]
    plan = repartir(pieces, bed)
    for _p, rects in _rectangles(pieces, plan).items():
        assert not _chevauchements(rects)


def test_aucune_piece_ne_depasse_du_plateau():
    random.seed(12)
    pieces = [(f"q{i}", 0.0, 0.0, random.uniform(10, 180), random.uniform(10, 180))
              for i in range(50)]
    bed = (420.0, 420.0)
    plan = repartir(pieces, bed)
    for _p, rects in _rectangles(pieces, plan).items():
        larg = max(r[3] for r in rects) - min(r[1] for r in rects)
        haut = max(r[4] for r in rects) - min(r[2] for r in rects)
        assert larg <= bed[0] - 2 * MARGE_MM + 1e-6
        assert haut <= bed[1] - 2 * MARGE_MM + 1e-6


def test_balayage_aleatoire_large():
    """300 projets au hasard : aucun chevauchement, aucun débordement."""
    for graine in range(300):
        random.seed(graine)
        n = random.randint(1, 60)
        pieces = []
        for i in range(n):
            x, y = random.uniform(-300, 300), random.uniform(-300, 300)
            pieces.append((f"r{i}", x, y,
                           x + random.uniform(5, 200), y + random.uniform(5, 200)))
        bed = random.choice([(180, 180), (256, 256), (350, 320), (420, 420)])
        plan = repartir(pieces, bed)
        for _p, rects in _rectangles(pieces, plan).items():
            assert not _chevauchements(rects), f"graine {graine}"
            larg = max(r[3] for r in rects) - min(r[1] for r in rects)
            haut = max(r[4] for r in rects) - min(r[2] for r in rects)
            assert larg <= bed[0] - 2 * MARGE_MM + 1e-6, f"graine {graine}"
            assert haut <= bed[1] - 2 * MARGE_MM + 1e-6, f"graine {graine}"


def test_l_espacement_entre_pieces_est_respecte():
    """Deux pièces collées fusionneraient leur bordure d'adhérence."""
    pieces = [(f"p{i}", 0.0, 0.0, 60.0, 60.0) for i in range(4)]
    plan = repartir(pieces, (420.0, 420.0))
    rects = _rectangles(pieces, plan)[0]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            ecart_x = max(a[1] - b[3], b[1] - a[3])
            ecart_y = max(a[2] - b[4], b[2] - a[4])
            assert max(ecart_x, ecart_y) >= ESPACEMENT_MM - 1e-6


# ── Les cas limites ───────────────────────────────────────────────────────
def test_une_piece_trop_grande_est_signalee_pas_ecartee_en_silence():
    pieces = [("geante", 0.0, 0.0, 500.0, 500.0), ("ok", 0.0, 0.0, 50.0, 50.0)]
    plan = repartir(pieces, (256.0, 256.0))
    assert plan.trop_grandes == ["geante"]
    assert [q.id for q in plan.poses] == ["ok"]


def test_un_projet_vide_ne_fait_rien():
    plan = repartir([], (256.0, 256.0))
    assert plan.plateaux == 0 and not plan.utile and not plan.poses


def test_un_plateau_absurde_rend_tout_trop_grand():
    plan = repartir([("a", 0.0, 0.0, 10.0, 10.0)], (5.0, 5.0))
    assert plan.trop_grandes == ["a"] and not plan.poses


def test_le_resultat_ne_change_pas_d_une_execution_a_l_autre():
    """Sinon l'aperçu bougerait à chaque clic sans raison visible."""
    pieces = [(f"p{i}", 0.0, 0.0, 40.0 + i % 7, 30.0 + i % 5) for i in range(30)]
    a = repartir(pieces, (256.0, 256.0))
    b = repartir(list(reversed(pieces)), (256.0, 256.0))
    assert a.poses == b.poses and a.plateaux == b.plateaux


def test_chaque_plateau_est_centre_sur_zero():
    """L'écrivain 3MF recentre le groupe sur le plateau physique : le moteur
    doit lui livrer un groupe déjà centré sur (0, 0)."""
    pieces = [(f"p{i}", 17.0, -42.0, 17.0 + 80.0, -42.0 + 60.0) for i in range(6)]
    plan = repartir(pieces, (420.0, 420.0))
    for _p, rects in _rectangles(pieces, plan).items():
        cx = (min(r[1] for r in rects) + max(r[3] for r in rects)) / 2
        cy = (min(r[2] for r in rects) + max(r[4] for r in rects)) / 2
        assert math.isclose(cx, 0.0, abs_tol=1e-6)
        assert math.isclose(cy, 0.0, abs_tol=1e-6)


def test_trier_par_profondeur_evite_un_plateau():
    """Deux pièces hautes et deux basses sur un plateau de 256 mm. Rangées
    dans l'ordre d'arrivée, les hautes et les basses se mélangent et chaque
    rangée coûte la hauteur d'une haute : deux plateaux. Triées par
    profondeur, les hautes occupent une rangée, les basses la suivante, et
    tout tient sur un seul plateau."""
    pieces = [("hauteA", 0.0, 0.0, 100.0, 200.0),
              ("basseA", 0.0, 0.0, 100.0, 20.0),
              ("hauteB", 0.0, 0.0, 100.0, 200.0),
              ("basseB", 0.0, 0.0, 100.0, 20.0)]
    plan = repartir(pieces, (256.0, 256.0))
    assert plan.plateaux == 1


def test_le_rangement_par_rangees_ne_comble_pas_les_cotes():
    """Limite ASSUMÉE. Quatre pièces de 190 mm occupent 388 des 404 mm utiles,
    et la bande de 16 mm qui reste ne peut accueillir aucune petite pièce,
    même quand la place existe ailleurs. Un rangement par découpe récursive
    gagnerait ce second plateau, au prix d'un résultat moins prévisible.

    Si ce chiffre tombe un jour à 1, c'est que quelqu'un a changé la méthode.
    C'est une bonne nouvelle, mais qu'on veut constater sciemment."""
    pieces = ([(f"petit{i}", 0.0, 0.0, 20.0, 20.0) for i in range(20)]
              + [(f"grand{i}", 0.0, 0.0, 190.0, 190.0) for i in range(4)])
    plan = repartir(pieces, (420.0, 420.0))
    assert plan.plateaux == 2
