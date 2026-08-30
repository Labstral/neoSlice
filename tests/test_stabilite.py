"""Stabilité — modèle de l'ANGLE DE RENVERSEMENT.

Cas dont la réponse physique est évidente : le score doit les classer
correctement. L'ancien modèle (marge du CDM / rayon d'empreinte) ignorait la
hauteur : une tour 10×10×120 obtenait 0,40 et une pièce plate à grande base 0,46.
"""
import numpy as np
import trimesh

from core.geometry.stability_analyzer import analyze_stability


def _pose(mesh):
    """Repose la pièce à Z=0 (convention du pipeline)."""
    m = mesh.copy()
    m.apply_translation([0, 0, -float(m.bounds[0][2])])
    return m


def test_pieces_manifestement_stables():
    cube = _pose(trimesh.creation.box((20, 20, 20)))
    plaque = _pose(trimesh.creation.box((60, 40, 2)))
    cone = _pose(trimesh.creation.cone(radius=15, height=40, sections=64))
    for m in (cube, plaque, cone):
        assert analyze_stability(m).score > 0.6


def test_pieces_manifestement_instables():
    tour = _pose(trimesh.creation.box((10, 10, 120)))          # 12× plus haute que large
    sphere = _pose(trimesh.creation.icosphere(subdivisions=4, radius=15))
    pointe = trimesh.creation.cone(radius=15, height=40, sections=64)
    pointe.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    for m in (tour, sphere, _pose(pointe)):
        assert analyze_stability(m).score < 0.35


def test_hauteur_prise_en_compte():
    """À empreinte IDENTIQUE, plus la pièce est haute, moins elle est stable."""
    scores = []
    for h in (10, 40, 120):
        m = _pose(trimesh.creation.box((20, 20, h)))
        scores.append(analyze_stability(m).score)
    assert scores[0] > scores[1] > scores[2]


def test_cdm_hors_empreinte_bascule():
    """Bras déporté : le centre de masse sort de la base → score plancher."""
    base = trimesh.creation.box((10, 10, 60))
    base.apply_translation((0, 0, 30))
    bras = trimesh.creation.box((40, 10, 10))
    bras.apply_translation((25, 0, 55))
    m = _pose(trimesh.util.concatenate([base, bras]))
    assert analyze_stability(m).score <= 0.1


def test_les_deux_chemins_donnent_le_meme_score():
    """RÉGRESSION : `analyze_stability` (repli) et `analyze_by_layers` (chemin
    principal, qui alimente la jauge) avaient chacun leur formule → la même pièce
    obtenait deux scores très différents (sphère : 0,05 vs 0,41). Les deux
    passent désormais par `score_renversement`, avec le même seuil de contact."""
    from core.geometry.layer_slicer import analyze_by_layers
    pieces = {
        "cube": trimesh.creation.box((20, 20, 20)),
        "plaque": trimesh.creation.box((60, 40, 2)),
        "tour": trimesh.creation.box((10, 10, 120)),
        "sphere": trimesh.creation.icosphere(subdivisions=4, radius=15),
        "cone": trimesh.creation.cone(radius=15, height=40, sections=48),
    }
    for nom, m in pieces.items():
        m = _pose(m)
        a = analyze_stability(m).score
        b = analyze_by_layers(m).stability_score
        assert abs(a - b) < 0.12, f"{nom} : {a:.2f} vs {b:.2f}"


def test_brim_recommande_si_instable():
    tour = _pose(trimesh.creation.box((10, 10, 120)))
    r = analyze_stability(tour)
    assert r.brim_recommendation_mm > 0      # une pièce instable réclame un brim
    cube = _pose(trimesh.creation.box((30, 30, 30)))
    assert analyze_stability(cube).brim_recommendation_mm == 0
