"""Non-régression : le slot filament des 3MF exportés suit le MATÉRIAU choisi.

Bug d'origine (retour utilisateur, Sunlu Easy PA) : le slot était figé sur
« Generic PLA » à 220 °C plein ventilateur — un nylon slicé tel quel partait
à température de PLA et délaminait. Désormais :
  - Bambu : filament_settings_id = preset générique du matériau (Generic PA…),
    valeurs embarquées (temps/ventilation/plateaux) = celles du matériau ;
  - Prusa/Orca : ventilation du matériau dans les overrides.
"""
import json
import zipfile

import pytest
import trimesh

from core.parameters.print_config import PrintConfig


def _mini_mesh():
    return trimesh.creation.box((20, 20, 10))


def _build_3mf(tmp_path, filament: str):
    from core.export.tmf_builder import ThreeMFBuilder, _find_bambu_template
    if not _find_bambu_template():
        pytest.skip("Bambu Studio non installé (pas de template)")
    out = tmp_path / f"test_{filament.replace(' ', '_')}.3mf"
    ThreeMFBuilder().build(_mini_mesh(), PrintConfig(), out,
                           printer_ui_name="X1 Carbon", filament_ui_name=filament)
    with zipfile.ZipFile(out) as zf:
        return json.loads(zf.read("Metadata/project_settings.config"))


def test_bambu_slot_nylon(tmp_path):
    ps = _build_3mf(tmp_path, "Nylon")
    assert ps["filament_settings_id"] == ["Generic PA"]
    assert ps["filament_type"] == ["PA"]
    # températures du catalogue (buse_1ere=260, buse_autres=255, plateau=70)
    assert ps["nozzle_temperature_initial_layer"] == ["260"]
    assert ps["nozzle_temperature"] == ["255"]
    # ventilation du matériau (clés mises à jour si présentes dans le template)
    if "fan_max_speed" in ps:
        assert int(ps["fan_max_speed"][0]) <= 30, "un PA plein ventilo délamine"
    if "hot_plate_temp" in ps:
        assert ps["hot_plate_temp"] == ["70"]


def test_bambu_slot_pla_inchange(tmp_path):
    """Rétro-compatibilité : le PLA garde exactement l'ancien comportement."""
    ps = _build_3mf(tmp_path, "PLA")
    assert ps["filament_settings_id"] == ["Generic PLA"]
    assert ps["filament_type"] == ["PLA"]
    assert ps["nozzle_temperature"] == ["220"]
    assert ps["required_nozzle_HRC"] == ["3"]


def test_bambu_slot_pacf_buse_durcie(tmp_path):
    ps = _build_3mf(tmp_path, "PA-CF")
    assert ps["filament_settings_id"] == ["Generic PA-CF"]
    assert ps["required_nozzle_HRC"] == ["40"], "fibre de carbone = buse durcie"


def test_bambu_filament_inconnu_retombe_pla(tmp_path):
    """Un nom hors catalogue reprend le slot neutre historique (220 °C PLA)."""
    ps = _build_3mf(tmp_path, "FilamentMystere")
    assert ps["filament_settings_id"] == ["Generic PLA"]
    assert ps["filament_type"] == ["PLA"]
    assert ps["nozzle_temperature"] == ["220"]


def test_inject_3mf_nu_identite_machine(tmp_path):
    """RÉGRESSION (cadre photo neoGen) : un 3MF SANS réglages internes (écrit
    par trimesh) injecté vers X1C doit déclarer la X1C. Avant : la sortie
    n'avait AUCUN project_settings (la boucle ne faisait que REMPLACER) et
    Bambu Studio retombait sur sa dernière imprimante (A1 chez l'utilisateur,
    X1C sélectionnée dans neoSlice)."""
    import json as _json
    import zipfile as _zip
    from core.export.tmf_builder import ThreeMFBuilder, _find_bambu_template
    if not _find_bambu_template():
        pytest.skip("Bambu Studio non installé (pas de template)")
    src = tmp_path / "piece_neogen.3mf"
    sc = trimesh.Scene()
    sc.add_geometry(trimesh.creation.box((20, 20, 10)), geom_name="cadre")
    sc.add_geometry(trimesh.creation.box((15, 15, 2)).apply_translation((30, 0, 0)),
                    geom_name="fond")
    sc.export(src)
    out = tmp_path / "out.3mf"
    ThreeMFBuilder().inject_settings_into_3mf(
        src, PrintConfig(), out,
        printer_ui_name="X1 Carbon", filament_ui_name="Nylon")
    ps = _json.loads(_zip.ZipFile(out).read("Metadata/project_settings.config"))
    assert ps["printer_model"] == "Bambu Lab X1 Carbon"
    assert ps["printer_settings_id"].startswith("Bambu Lab X1 Carbon")
    assert ps["filament_settings_id"] == ["Generic PA"]     # matériau suivi aussi
    assert len(ps) > 300, "base = template complet, pas un fichier quasi vide"


def test_prusa_ventilation_suit_le_materiau():
    from core.export.prusa_3mf_builder import _config_to_prusa
    o = _config_to_prusa(PrintConfig(), {}, 0.4, filament_name="Nylon")
    assert int(o["max_fan_speed"]) <= 30
    assert o["fan_always_on"] == "0"
    assert o["disable_fan_first_layers"] == "1"
    o_pla = _config_to_prusa(PrintConfig(), {}, 0.4, filament_name="PLA")
    assert int(o_pla["max_fan_speed"]) >= 90
    # sans nom de filament : aucune clé ventilation (comportement historique)
    o_vide = _config_to_prusa(PrintConfig(), {}, 0.4)
    assert "max_fan_speed" not in o_vide
