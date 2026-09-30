# -*- coding: utf-8 -*-
"""Une zone dans le vide est un surplomb, même juste au-dessus du plateau.

Emmanuel, 2026-09-30, sur son `Chute_Cover.stl` (52 × 57 × 16 mm) annoncé à
0,00 % de surplombs alors qu'il en a : « à partir du moment où on considère
qu'une imprimante ne peut pas imprimer une zone qui est dans le vide, même
très proche du plateau, il faut la considérer comme un surplomb, c'est
évident ».

DEUX filtres se cumulaient pour effacer ses surplombs, et il a fallu suivre
le parcours étape par étape pour les isoler. Mesuré sur son fichier :

    1. filtre angulaire        188 faces   21,34 % de la surface
    2. exclusion plateau        54 faces    2,07 %
    3. matière en dessous       54 faces    2,07 %
    4. amas et ponts             0 faces    0,00 %   <- tout disparaissait ici

**Premier filtre, la tolérance plateau.** Elle valait 5,00 mm sur une pièce de
16 mm de haut, et jusqu'à 9,6 mm sur une tour de 120 mm. Les surplombs de sa
pièce sont à 1,37 jusqu'à 2,80 mm : tous avalés. Ramenée à l'épaisseur d'une
première couche, elle ne sert plus qu'à absorber un fond incliné ou bruité.

**Second filtre, et le vrai coupable, le test de pont.** N'importe quelle face
voisine comptait comme un APPUI, y compris la face verticale extérieure d'un
rebord, qui pend elle même dans le vide. Un simple porte-à-faux était donc pris
pour un pont posé sur deux appuis, et ignoré. Un vrai appui DESCEND sous le
surplomb qu'il porte.
"""
import numpy as np
import pytest
import trimesh

from core.geometry.overhang_detector import analyze_overhangs

CHUTE = r"D:\Impression 3D\Chute_Cover.stl"


def _ratio(m):
    m = m.copy()
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    return analyze_overhangs(m, smooth=True, check_floating=False).overhang_ratio


def _rebord_bas():
    """Un rebord qui déborde à 2 mm du plateau : le cas d'Emmanuel, en simple."""
    socle = trimesh.creation.box(extents=(40, 40, 2))
    socle.apply_translation((0, 0, 1))
    rebord = trimesh.creation.box(extents=(60, 40, 3))
    rebord.apply_translation((0, 0, 3.5))
    return trimesh.boolean.union([socle, rebord], engine="manifold")


def _pont(ecart_mm):
    """Deux piliers et une traverse : un VRAI pont, imprimable sans support."""
    demi = ecart_mm / 2.0 + 3.0
    g = trimesh.creation.box(extents=(6, 20, 20)); g.apply_translation((-demi, 0, 10))
    d = trimesh.creation.box(extents=(6, 20, 20)); d.apply_translation((demi, 0, 10))
    t = trimesh.creation.box(extents=(2 * demi + 6, 20, 4)); t.apply_translation((0, 0, 22))
    return trimesh.boolean.union([g, d, t], engine="manifold")


# ── Ce qui doit ressortir ─────────────────────────────────────────────────
def test_un_rebord_a_deux_millimetres_du_plateau_est_un_surplomb():
    """Le cœur de sa remarque. Il ressortait à 0,00 %."""
    assert _ratio(_rebord_bas()) > 0.05


@pytest.mark.parametrize("hauteur", [0.8, 1.5, 3.0, 6.0])
def test_la_hauteur_du_porte_a_faux_ne_change_rien(hauteur):
    """Un porte-à-faux à 0,8 mm du plateau est aussi impossible à imprimer
    qu'à 6 mm. L'ancienne tolérance en avalait tout jusqu'à 5 mm."""
    socle = trimesh.creation.box(extents=(40, 40, hauteur))
    socle.apply_translation((0, 0, hauteur / 2))
    rebord = trimesh.creation.box(extents=(60, 40, 3))
    rebord.apply_translation((0, 0, hauteur + 1.5))
    m = trimesh.boolean.union([socle, rebord], engine="manifold")
    assert _ratio(m) > 0.05, f"porte-à-faux à {hauteur} mm ignoré"


def test_une_console_en_T_reste_detectee():
    pied = trimesh.creation.box(extents=(10, 10, 20)); pied.apply_translation((0, 0, 10))
    chapeau = trimesh.creation.box(extents=(50, 50, 4)); chapeau.apply_translation((0, 0, 22))
    assert _ratio(trimesh.boolean.union([pied, chapeau], engine="manifold")) > 0.2


def test_une_sphere_posee_a_bien_un_surplomb_sous_elle():
    s = trimesh.creation.icosphere(subdivisions=3, radius=20)
    s.apply_translation([0, 0, 20])
    assert _ratio(s) > 0.05


# ── Ce qui ne doit PAS ressortir ──────────────────────────────────────────
@pytest.mark.parametrize("nom,forme", [
    ("cube", trimesh.creation.box(extents=(40, 40, 40))),
    ("plaque", trimesh.creation.box(extents=(60, 60, 3))),
    ("tour", trimesh.creation.box(extents=(20, 20, 120))),
    ("cylindre", trimesh.creation.cylinder(radius=10, height=40)),
])
def test_une_piece_a_fond_plat_n_a_aucun_surplomb(nom, forme):
    """Le risque du correctif : prendre le dessous d'une pièce posée pour un
    surplomb, et couvrir tout le monde de supports inutiles."""
    assert _ratio(forme) < 0.002, nom


@pytest.mark.parametrize("ecart", [4.0, 10.0, 18.0])
def test_un_vrai_pont_reste_ignore(ecart):
    """Deux piliers qui DESCENDENT jusqu'au plateau : le pont s'imprime sans
    support, il ne doit pas être signalé. C'est ce que le filtre protège, et
    il fallait le garder en resserrant le critère d'appui."""
    assert _ratio(_pont(ecart)) < 0.002, f"pont de {ecart} mm signalé à tort"


# ── La vraie pièce, si elle est là ────────────────────────────────────────
def test_le_chute_cover_ressort_enfin():
    from pathlib import Path
    if not Path(CHUTE).exists():
        pytest.skip("Chute_Cover.stl absent de cette machine")
    m = trimesh.load(CHUTE, force="mesh")
    assert _ratio(m) > 0.005, "la pièce d'Emmanuel doit enfin montrer ses surplombs"


# ── Les deux seuils eux-mêmes ─────────────────────────────────────────────
def test_la_tolerance_plateau_reste_a_l_echelle_d_une_premiere_couche():
    """Elle montait à 5 mm sur une pièce basse et 9,6 mm sur une tour."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "core" / "geometry" / "overhang_detector.py").read_text(encoding="utf-8")
    bloc = src[src.index("# ── 3. Exclusion plateau"):]
    bloc = bloc[:bloc.index("face_centroids")]
    assert "min(max(0.4, z_height * 0.01), 1.0)" in bloc
    assert "_base_tol" not in bloc, "l'ancienne allocation généreuse doit avoir sauté"


def test_un_appui_doit_descendre_sous_le_surplomb():
    """Sans ce critère, la paroi extérieure d'un rebord se faisait passer pour
    un pilier."""
    from core.geometry.overhang_detector import _ANCRE_DESCENTE_MIN
    assert 0.0 < _ANCRE_DESCENTE_MIN <= 0.5
