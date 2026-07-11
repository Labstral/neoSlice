"""Bibliothèque de filaments PAR MARQUE (phase 2 du retour Sunlu Easy PA).

Un produit (« Sunlu Easy PA ») = matériau de base + surcharges de la fiche
fabricant. Il hérite de TOUTES les protections de sa base ; le chargeur borne
chaque valeur (le code a le dernier mot) ; la base se met à jour par le canal
d'assets sans rebuild.
"""
import json

import pytest

from data import filaments as F


def _restaurer():
    F.recharger_marques()


def test_produits_charges_et_heritage():
    ep = F.FILAMENTS["Sunlu Easy PA"]
    assert ep["base"] == "Nylon" and ep["marque"] == "Sunlu"
    assert ep["buse_1ere"] == 265 and ep["plateau"] == 70
    assert ep["enceinte_requise"] is False          # surcharge fiche Sunlu
    assert ep["ventilateur_max"] == 20              # hérité du Nylon
    assert ep["warnings"], "warnings de la base hérités"
    assert F.base_materiau("Sunlu Easy PA") == "Nylon"
    assert F.base_materiau("PLA") == "PLA"
    # les marques apparaissent comme groupes après les familles génériques
    assert "Sunlu" in F.FAMILLES_ORDRE and F.FAMILLES_ORDRE.index("Sunlu") >= 6


def test_moteur_applique_fiche_et_securites_de_base():
    from core.parameters.parameter_engine import ParameterEngine, IntentProfile, AnalysisReport
    cfg = ParameterEngine().generate(IntentProfile(), AnalysisReport(),
                                     filament_name="Sunlu Easy PA")
    assert cfg.nozzle_temperature == 265            # fiche Sunlu
    assert cfg.bed_temperature == 70
    assert cfg.brim_type != "no_brim", "base Nylon = warping -> brim forcé"
    assert cfg.wall_loops >= 3                      # base haute température


def test_export_3mf_produit_marque(tmp_path):
    import trimesh
    import zipfile
    from core.export.tmf_builder import ThreeMFBuilder, _find_bambu_template
    from core.parameters.print_config import PrintConfig
    if not _find_bambu_template():
        pytest.skip("Bambu Studio non installé (pas de template)")

    def _ps(filament):
        out = tmp_path / f"{filament.replace(' ', '_')}.3mf"
        ThreeMFBuilder().build(trimesh.creation.box((20, 20, 10)), PrintConfig(),
                               out, printer_ui_name="X1 Carbon",
                               filament_ui_name=filament)
        return json.loads(zipfile.ZipFile(out).read("Metadata/project_settings.config"))

    ps = _ps("Sunlu Easy PA")
    # id INCONNU de BS -> nos valeurs fiche fabricant survivent (même logique
    # que print_settings_id « neoSlice ... »)
    assert ps["filament_settings_id"] == ["neoSlice Sunlu Easy PA"]
    assert ps["filament_type"] == ["PA"]            # type = matériau de BASE
    assert ps["nozzle_temperature_initial_layer"] == ["265"]
    if "fan_max_speed" in ps:
        assert int(ps["fan_max_speed"][0]) <= 30    # ventilation héritée Nylon
    # filament Bambu -> preset RÉEL de Bambu Studio
    ps2 = _ps("Bambu Lab PLA Basic")
    assert ps2["filament_settings_id"] == ["Bambu PLA Basic"]
    assert ps2["filament_type"] == ["PLA"]


def test_compat_easy_pa_imprimante_ouverte():
    """Le Nylon générique est BLOQUÉ sur une imprimante ouverte, mais une fiche
    fabricant « sans enceinte » (Easy PA basse déformation) passe en simple
    avertissement — c'est tout l'intérêt de la bibliothèque par marque."""
    from ui.components.filament_printer_selector import check_compatibility
    st_gen, _c, _m = check_compatibility("A1", "Nylon")
    st_easy, _c, msg = check_compatibility("A1", "Sunlu Easy PA")
    assert st_gen == "error"
    assert st_easy == "warning" and "adhérence" in msg


def test_fiche_aberrante_ecartee_et_maj_locale(tmp_path, monkeypatch):
    """Le fichier UTILISATEUR (maj distante) prime s'il est plus récent, et une
    fiche hors bornes est écartée SANS bloquer les autres."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))     # Path.home() -> tmp
    monkeypatch.setenv("HOME", str(tmp_path))
    local = tmp_path / ".neoslice" / "filaments" / "brands.json"
    local.parent.mkdir(parents=True)
    local.write_text(json.dumps({
        "version": "2099-01-01",
        "marques": {
            "TestCo": {
                "Bon PLA": {"base": "PLA", "buse_1ere": 218},
                "PLA Fou": {"base": "PLA", "buse_1ere": 500},      # hors bornes
                "Mystere": {"base": "Inconnium", "buse_1ere": 200},  # base inconnue
            },
        },
    }), encoding="utf-8")
    try:
        F.recharger_marques()
        assert F.MARQUES_VERSION == "2099-01-01"
        assert F.FILAMENTS["TestCo Bon PLA"]["buse_1ere"] == 218
        assert "TestCo PLA Fou" not in F.FILAMENTS
        assert "TestCo Mystere" not in F.FILAMENTS
    finally:
        monkeypatch.undo()
        _restaurer()
    assert "TestCo Bon PLA" not in F.FILAMENTS       # base embarquée restaurée
    assert "Sunlu Easy PA" in F.FILAMENTS
