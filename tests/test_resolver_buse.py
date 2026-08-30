# -*- coding: utf-8 -*-
"""Résolution des profils Bambu par (imprimante, BUSE) — bug utilisateur X2D 0,2.

Une X2D en buse 0,2 exportait le process X1 Carbon 0,4 : largeurs de ligne
doublées (0,42–0,50 au lieu de 0,22–0,25). Le résolveur suit désormais la vraie
chaîne « inherits » du profil Standard de la bonne buse.

Ces tests ne tournent que si Bambu Studio est installé (profils système requis).
"""
import pytest

from core.export import bambu_config_resolver as R


bs_requis = pytest.mark.skipif(
    not R._BBL_PROCESS.exists(),
    reason="Bambu Studio non installé (profils système absents)")


@bs_requis
def test_x2d_buse_02_largeurs_correctes():
    cfg = R.resolve_from_system_profiles("X2D", 0.2)
    assert cfg is not None
    assert cfg["line_width"] == "0.22"
    assert cfg["outer_wall_line_width"] == "0.22"
    assert cfg["sparse_infill_line_width"] == "0.22"
    assert cfg["support_line_width"] == "0.22"
    assert cfg["top_surface_line_width"] == "0.22"
    assert cfg["initial_layer_line_width"] == "0.25"
    # vitesses SYSTÈME X2D (l'utilisateur les croyait fausses : non — le profil
    # dual X2D officiel porte bien travel 1000 et support 150)
    assert cfg["travel_speed"] in (["1000"] * 4, "1000", ["1000"])


@bs_requis
def test_x1c_buse_04_inchangee():
    """La 0,4 (chemin historique) doit donner les mêmes largeurs qu'avant."""
    cfg = R.resolve_from_system_profiles("X1C", 0.4)
    assert cfg["line_width"] == "0.42"
    assert cfg["sparse_infill_line_width"] == "0.45"
    assert cfg["initial_layer_line_width"] == "0.5"


@bs_requis
def test_profil_standard_selection():
    """0,4 → fichier sans suffixe ; 0,2 → « 0.2 nozzle » ; hauteur ~ D/2."""
    p04 = R._profil_standard("X1C", 0.4)
    assert p04 and "nozzle" not in p04
    p02 = R._profil_standard("X1C", 0.2)
    assert p02 and p02.endswith("0.2 nozzle.json")
    assert p02.startswith("0.10mm")            # défaut Bambu buse 0,2
    assert R._profil_standard("MODELE_INEXISTANT", 0.2) is None


def test_filets_tmf_builder_par_buse():
    """Même SANS Bambu Studio, les filets du builder couvrent désormais sparse/
    support/top (ils restaient au template 0,4)."""
    src = open("core/export/tmf_builder.py", encoding="utf-8").read()
    for cle in ("sparse_infill_line_width", "support_line_width",
                "top_surface_line_width"):
        assert f'project_settings["{cle}"]' in src, cle


@bs_requis
def test_x2d_garde_son_identite():
    """X2D n'est plus mappée sur X1C : ses propres profils sont utilisés."""
    from core.export.tmf_builder import _UI_TO_BBL
    assert _UI_TO_BBL["X2D"] == "X2D"
    assert _UI_TO_BBL["P2S"] == "P2S"
    assert _UI_TO_BBL["H2D Pro"] == "H2DP"
