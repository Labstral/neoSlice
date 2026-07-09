"""Non-régression : la procédure forcée d'identité printer doit garantir que le profil
neoSlice/cible PRIME toujours, quel que soit le profil d'origine du 3MF importé.

Bug d'origine (Darth Vader) : un 3MF créé pour une P1P, réexporté vers A1, gardait des
références P1P (inherits_group « 0.16mm Optimal @BBL P1P », filament/compatible…) →
Bambu Studio rechargeait le preset P1P (couche 0.16, supports off) par-dessus nos réglages.
"""
from core.export.tmf_builder import _force_printer_identity


def _p1p_project_settings() -> dict:
    """project_settings typique d'un 3MF authored pour P1P (extrait réel simplifié)."""
    return {
        "print_settings_id": "neoSlice 0.20mm @BBL A1",       # déjà cible (ne doit pas bouger)
        "printer_settings_id": "Bambu Lab A1 0.4 nozzle",
        "default_print_profile": "0.20mm Standard @BBL P1P",  # ← P1P résiduel
        "filament_settings_id": ["Generic PLA @BBL P1P"],      # ← P1P résiduel
        "inherits_group": ["0.16mm Optimal @BBL P1P", "", "", ""],  # ← DOIT disparaître
        "print_compatible_printers": ["Bambu Lab P1P 0.4 nozzle"],  # ← P1P résiduel
        "inherits": "0.16mm Optimal @BBL P1P",                 # ← DOIT disparaître
        "different_settings_to_system": ["layer_height"],      # ← DOIT disparaître
        "layer_height": "0.2",
        "enable_support": "1",
    }


def test_force_identity_neutralizes_inheritance():
    ps = _p1p_project_settings()
    _force_printer_identity(ps, "A1", "Bambu Lab A1 0.4 nozzle")
    # inherits_group DOIT rester présent (sinon BS rejette le 3MF) mais VIDE
    assert "inherits_group" in ps
    assert all(x == "" for x in ps["inherits_group"])
    assert ps.get("inherits") == ""
    # different_settings_to_system peut être retiré (toléré par BS)
    assert "different_settings_to_system" not in ps


def test_force_identity_retargets_all_bbl_refs():
    ps = _p1p_project_settings()
    _force_printer_identity(ps, "A1", "Bambu Lab A1 0.4 nozzle")
    import json
    blob = json.dumps(ps)
    assert "P1P" not in blob, f"référence P1P résiduelle : {blob}"
    assert "P1S" not in blob
    # Toutes les références « @BBL … » doivent viser A1
    assert ps["default_print_profile"] == "0.20mm Standard @BBL A1"
    assert ps["filament_settings_id"] == ["Generic PLA @BBL A1"]


def test_force_identity_preserves_neoslice_and_values():
    ps = _p1p_project_settings()
    _force_printer_identity(ps, "A1", "Bambu Lab A1 0.4 nozzle")
    # Le print_settings_id neoSlice (inconnu de BS) reste intact et ciblé
    assert ps["print_settings_id"] == "neoSlice 0.20mm @BBL A1"
    # Les réglages neoSlice ne sont pas touchés
    assert ps["layer_height"] == "0.2"
    assert ps["enable_support"] == "1"


def test_force_identity_idempotent():
    ps = _p1p_project_settings()
    _force_printer_identity(ps, "A1", "Bambu Lab A1 0.4 nozzle")
    once = dict(ps)
    _force_printer_identity(ps, "A1", "Bambu Lab A1 0.4 nozzle")
    assert ps == once


import pytest


@pytest.mark.parametrize("src_model,target_bbl,target_machine", [
    ("X1C", "A1",  "Bambu Lab A1 0.4 nozzle"),
    ("P1S", "X1C", "Bambu Lab X1 Carbon 0.4 nozzle"),
    ("A1M", "P1P", "Bambu Lab P1P 0.4 nozzle"),
    ("H2D", "A1",  "Bambu Lab A1 0.4 nozzle"),
])
def test_force_identity_generic_any_source(src_model, target_bbl, target_machine):
    """Générique : n'importe quel profil source doit être écrasé par le profil cible."""
    ps = {
        "print_settings_id": f"0.16mm Optimal @BBL {src_model}",
        "printer_settings_id": f"Bambu Lab {src_model} 0.4 nozzle",
        "default_print_profile": f"0.20mm Standard @BBL {src_model}",
        "filament_settings_id": [f"Generic PLA @BBL {src_model}"],
        "inherits_group": [f"0.16mm Optimal @BBL {src_model}", "", "", ""],
        "print_compatible_printers": [f"Bambu Lab {src_model} 0.4 nozzle"],
    }
    _force_printer_identity(ps, target_bbl, target_machine)
    import json
    blob = json.dumps(ps)
    assert src_model not in blob, f"référence source {src_model} résiduelle : {blob}"
    # inherits_group présent mais vidé (structure valide, aucun héritage)
    assert "inherits_group" in ps and all(x == "" for x in ps["inherits_group"])
    assert ps["default_print_profile"] == f"0.20mm Standard @BBL {target_bbl}"
    assert ps["print_compatible_printers"] == [target_machine]
