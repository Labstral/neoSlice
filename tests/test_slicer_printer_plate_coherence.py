# -*- coding: utf-8 -*-
"""Cohérence GLOBALE slicer de sortie → imprimantes → buses → plateaux → export.

Emmanuel (2026-07-20) : « quand on sélectionne un slicer de sortie, les imprimantes
qu'on peut choisir ensuite, les plateaux, doivent être cohérents et exister tous. »

Pour CHACUN des 9 slicers, on énumère TOUTES les imprimantes réellement proposées
par le sélecteur (même logique que FilamentPrinterSelector._printer_groups) et on
vérifie, imprimante par imprimante :
  - au moins une buse disponible ;
  - le prérequis d'export existe (profil/preset/def/machineId selon le slicer) ;
et pour le slicer : la liste de plateaux est valide (défaut présent dans la liste),
ou volontairement masquée (FlashPrint, pas de type de plateau).
"""
from __future__ import annotations

import pytest

from core.prefs import PREFS
from data.printers import (
    PRINTERS,
    catalogue_brands, models_for_brand, nozzles_for_model, profile_name_for,
    machine_config_for, is_catalogue_model,
    prusa_models, prusa_nozzles_for_model, prusa_preset_for,
    cura_models, cura_nozzles_for_model, cura_machine_for,
    flashprint_models_for_brand, flashprint_brands, flashprint_nozzles_for_model,
    flashprint_machine_for,
)
from ui.components.filament_printer_selector import _plates_for_slicer

_CATALOGUE_SLICERS = ["bambu", "orca", "creality", "elegoo", "anycubic", "snapmaker"]
_ALL_SLICERS = _CATALOGUE_SLICERS + ["prusa", "cura", "flashprint"]


def _printers_for(slicer: str) -> list[str]:
    """Toutes les CLÉS d'imprimante proposées par le sélecteur pour ce slicer."""
    if slicer == "prusa":
        return [mk for _d, mk in prusa_models()]
    if slicer == "cura":
        return [mk for _d, mk in cura_models()]
    if slicer == "flashprint":
        return [mk for b in flashprint_brands() for _d, mk in flashprint_models_for_brand(b)]
    # Bambu Lab n'est proposé que sous Bambu Studio / OrcaSlicer (pas les forks fabricant)
    keys = list(PRINTERS.keys()) if slicer in ("bambu", "orca") else []
    for b in catalogue_brands(slicer):
        keys += [mk for _d, mk in models_for_brand(b, slicer)]
    return keys


@pytest.mark.parametrize("slicer", _ALL_SLICERS)
def test_imprimantes_existent_et_ont_des_buses(slicer):
    printers = _printers_for(slicer)
    assert printers, f"AUCUNE imprimante proposée pour le slicer « {slicer} »"
    manquantes = []
    for key in printers:
        if slicer == "prusa":
            nz = prusa_nozzles_for_model(key)
        elif slicer == "cura":
            nz = cura_nozzles_for_model(key)
        elif slicer == "flashprint":
            nz = flashprint_nozzles_for_model(key)
        elif key in PRINTERS:                          # Bambu Lab : buses standard
            nz = [0.2, 0.4, 0.6, 0.8]
        else:
            nz = nozzles_for_model(key)
        if not nz:
            manquantes.append(key)
    assert not manquantes, f"[{slicer}] imprimantes SANS buse : {manquantes[:10]}"


@pytest.mark.parametrize("slicer", _ALL_SLICERS)
def test_prerequis_export_resolus(slicer):
    """Chaque imprimante proposée doit résoudre ce dont l'export a besoin."""
    printers = _printers_for(slicer)
    casse = []
    for key in printers:
        try:
            if slicer == "prusa":
                nz = prusa_nozzles_for_model(key)
                ok = bool(prusa_preset_for(key, nz[0]))
            elif slicer == "cura":
                m = cura_machine_for(key)
                ok = bool(m.get("def_raw") and m.get("extruder_defs"))
            elif slicer == "flashprint":
                m = flashprint_machine_for(key)
                ok = m.get("machine_id", -1) >= 0 and bool(m.get("nozzles"))
            elif key in PRINTERS:
                ok = True                              # Bambu Lab : profils système BS
            else:                                      # catalogue tiers
                nz = nozzles_for_model(key)
                pn = profile_name_for(key, nz[0])
                ok = bool(pn) and bool(machine_config_for(pn))
        except Exception as e:                         # noqa
            ok = False
            key = f"{key} ({type(e).__name__}: {e})"
        if not ok:
            casse.append(key)
    assert not casse, f"[{slicer}] export non résoluble : {casse[:10]}"


@pytest.mark.parametrize("slicer", _ALL_SLICERS)
def test_plateaux_coherents(slicer):
    plates, default = _plates_for_slicer(slicer)
    assert plates, f"[{slicer}] liste de plateaux vide"
    values = [v for _label, v in plates]
    assert default in values, (
        f"[{slicer}] plateau défaut « {default} » absent de la liste {values} "
        f"(le sélecteur planterait sur values.index(default))")


def test_flashprint_plateau_masque_pas_de_faux_choix():
    """FlashPrint : plateau fixe par machine → une seule entrée neutre (masquée en UI)."""
    plates, _default = _plates_for_slicer("flashprint")
    assert len(plates) == 1, "FlashPrint ne doit pas proposer de choix de plateau"


@pytest.mark.parametrize("slicer", ["flashprint", "cura"])
def test_selecteur_plateau_masque(slicer):
    """FlashPrint et Cura : le sélecteur de plateau est MASQUÉ (leur builder ignore
    le type de plateau ; afficher des plateaux Bambu serait un faux choix trompeur)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ui.components.filament_printer_selector import FilamentPrinterSelector
    QApplication.instance() or QApplication([])
    prev = PREFS.get("slicer_output", "bambu")
    try:
        PREFS.set("slicer_output", slicer)
        w = FilamentPrinterSelector(); w.show()
        w._populate_plates()
        assert not w._plate_combo.isVisible(), f"[{slicer}] combo plateau devrait être masqué"
        assert not w._lbl_plate.isVisible(), f"[{slicer}] label plateau devrait être masqué"
    finally:
        PREFS.set("slicer_output", prev)


@pytest.mark.parametrize("slicer", ["bambu", "orca", "creality", "elegoo",
                                    "anycubic", "snapmaker", "prusa"])
def test_selecteur_plateau_visible(slicer):
    """Bambu/Orca (+ forks) et Prusa : le sélecteur de plateau reste VISIBLE (concept réel)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ui.components.filament_printer_selector import FilamentPrinterSelector
    QApplication.instance() or QApplication([])
    prev = PREFS.get("slicer_output", "bambu")
    try:
        PREFS.set("slicer_output", slicer)
        w = FilamentPrinterSelector(); w.show()
        w._populate_plates()
        assert w._plate_combo.isVisible() and w._plate_combo.count() > 0
    finally:
        PREFS.set("slicer_output", prev)


def test_bambu_lab_seulement_bambu_et_orca():
    """Le groupe « Bambu Lab » n'apparaît que sous Bambu Studio et OrcaSlicer ;
    jamais sous les slicers de fabricant (Creality/Elegoo/Anycubic/Snapmaker) ni
    Prusa/Cura/FlashPrint (catalogues dédiés)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ui.components.filament_printer_selector import FilamentPrinterSelector
    QApplication.instance() or QApplication([])
    prev = PREFS.get("slicer_output", "bambu")
    try:
        for slicer in _ALL_SLICERS:
            PREFS.set("slicer_output", slicer)
            w = FilamentPrinterSelector()
            labels = [g[0] for g in w._printer_groups()]
            has_bambu = "Bambu Lab" in labels
            assert has_bambu == (slicer in ("bambu", "orca")), \
                f"[{slicer}] groupe Bambu Lab présent={has_bambu} (attendu {slicer in ('bambu','orca')})"
    finally:
        PREFS.set("slicer_output", prev)


def test_plateaux_par_imprimante():
    """Les plateaux s'adaptent à l'imprimante (ensemble complet MOINS not_support du
    modèle, data/bed_types.json extrait d'OrcaSlicer)."""
    from ui.components.filament_printer_selector import _plates_for_printer
    # X1 Carbon : aucun not_support → ensemble complet (5 plateaux à code interne sûr)
    x1, _ = _plates_for_printer("bambu", "X1 Carbon")
    assert len(x1) == 5
    # A1 mini : not_support Cool/Engineering/Smooth Cool → liste réduite, SANS eux
    a1, _ = _plates_for_printer("bambu", "A1 Mini")
    a1_vals = [v for _l, v in a1]
    assert "Engineering Plate" not in a1_vals and "Smooth Cool Plate" not in a1_vals
    assert len(a1) < len(x1)
    # Artillery M1 Pro (tiers) : ses propres restrictions
    art, _ = _plates_for_printer("orca", "Artillery M1 Pro")
    art_vals = [v for _l, v in art]
    assert "Engineering Plate" not in art_vals and "Textured Cool Plate" not in art_vals
    # défaut toujours présent dans la liste
    for slicer, printer in [("bambu", "A1 Mini"), ("orca", "Artillery M1 Pro"),
                            ("bambu", "H2D")]:
        plates, default = _plates_for_printer(slicer, printer)
        assert default in [v for _l, v in plates]


def test_export_ecrit_curr_bed_type(tmp_path):
    """L'export Bambu écrit curr_bed_type = plateau choisi (et rien si non fourni)."""
    import trimesh, zipfile, json
    from core.parameters.print_config import PrintConfig
    from core.export.tmf_builder import ThreeMFBuilder

    def _bed(p):
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith("project_settings.config"):
                    return json.loads(z.read(n)).get("curr_bed_type", None)
        return None

    b = ThreeMFBuilder()
    box = trimesh.creation.box((20, 20, 10))
    out = tmp_path / "with.3mf"
    b.build(box, PrintConfig(), out, printer_ui_name="X1 Carbon",
            filament_ui_name="PLA", nozzle_diameter_mm=0.4, plate_type="Cool Plate")
    assert _bed(out) == "Cool Plate"
    out2 = tmp_path / "without.3mf"
    b.build(box, PrintConfig(), out2, printer_ui_name="X1 Carbon",
            filament_ui_name="PLA", nozzle_diameter_mm=0.4)
    assert _bed(out2) is None                         # pas de régression si non fourni


@pytest.mark.parametrize("slicer", _ALL_SLICERS)
def test_selecteur_ne_plante_pas(slicer):
    """Le sélecteur construit ses groupes + plateaux sans lever pour ce slicer."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ui.components.filament_printer_selector import FilamentPrinterSelector
    app = QApplication.instance() or QApplication([])
    prev = PREFS.get("slicer_output", "bambu")
    try:
        PREFS.set("slicer_output", slicer)
        w = FilamentPrinterSelector()
        w._populate_printers()
        w._populate_plates()
        assert w._printer_groups(), f"[{slicer}] groupes d'imprimantes vides"
    finally:
        PREFS.set("slicer_output", prev)
