# -*- coding: utf-8 -*-
"""Lecture des chiffres exacts d'un fichier découpé (devis/stock sans estimation)."""
import zipfile

import pytest

from core.slicer_report import lire_fichier_tranche, _parse_duree


def _faux_gcode_3mf(tmp_path, plates_xml: str, nom="piece.gcode.3mf"):
    p = tmp_path / nom
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Metadata/slice_info.config",
                   f'<?xml version="1.0"?><config>{plates_xml}</config>')
    return p


def test_bambu_gcode_3mf_mono_plate(tmp_path):
    p = _faux_gcode_3mf(tmp_path, """
      <plate>
        <metadata key="index" value="1"/>
        <metadata key="prediction" value="5581"/>
        <metadata key="weight" value="42.45"/>
        <filament id="1" type="PLA" color="#FFFFFF" used_m="4.2" used_g="30.1"/>
        <filament id="2" type="PLA" color="#111111" used_m="1.7" used_g="12.35"/>
      </plate>""")
    r = lire_fichier_tranche(p)
    assert r["exact"] is True and r["source"] == "bambu"
    assert r["poids_g"] == pytest.approx(42.45)
    assert r["duree_s"] == 5581
    assert [f["grams"] for f in r["par_filament"]] == [30.1, 12.35]
    assert r["par_filament"][1]["couleur"] == "#111111"


def test_bambu_multi_plateaux_agrege(tmp_path):
    p = _faux_gcode_3mf(tmp_path, """
      <plate><metadata key="prediction" value="1000"/>
             <metadata key="weight" value="10.0"/>
             <filament id="1" type="PLA" used_g="10.0"/></plate>
      <plate><metadata key="prediction" value="2000"/>
             <metadata key="weight" value="15.5"/>
             <filament id="1" type="PLA" used_g="15.5"/></plate>""")
    r = lire_fichier_tranche(p)
    assert r["poids_g"] == pytest.approx(25.5)
    assert r["duree_s"] == 3000
    assert r["par_filament"][0]["grams"] == pytest.approx(25.5)  # cumul par slot


def test_prusa_gcode(tmp_path):
    p = tmp_path / "piece.gcode"
    p.write_text("G1 X0\n" * 10 +
                 "; filament used [g] = 12.34\n"
                 "; estimated printing time (normal mode) = 1h 32m 10s\n",
                 encoding="utf-8")
    r = lire_fichier_tranche(p)
    assert r["exact"] is True
    assert r["poids_g"] == pytest.approx(12.34)
    assert r["duree_s"] == 1 * 3600 + 32 * 60 + 10


def test_cura_gcode_approximatif(tmp_path):
    p = tmp_path / "cura.gcode"
    p.write_text(";TIME:5581\n;Filament used: 2.0m\nG1 X0\n", encoding="utf-8")
    r = lire_fichier_tranche(p)
    assert r["exact"] is False                    # poids par densité = approx
    assert r["duree_s"] == 5581
    assert r["poids_g"] == pytest.approx(5.96, abs=0.05)


def test_fichiers_invalides(tmp_path):
    vide = tmp_path / "vide.gcode"
    vide.write_text("G1 X0\nG1 Y0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lire_fichier_tranche(vide)
    with pytest.raises(ValueError):
        lire_fichier_tranche(tmp_path / "absent.gcode")
    autre = tmp_path / "modele.stl"
    autre.write_text("solid x", encoding="utf-8")
    with pytest.raises(ValueError):
        lire_fichier_tranche(autre)


def test_calculateur_importe_les_chiffres(tmp_path, monkeypatch):
    """Le bouton d'import remplit poids/durée, la note passe en « exact », et
    une saisie manuelle ultérieure retire l'étiquette (honnêteté)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog
    QApplication.instance() or QApplication([])
    from ui.components import cost_calculator as cc

    p = _faux_gcode_3mf(tmp_path, """
      <plate><metadata key="prediction" value="7200"/>
             <metadata key="weight" value="50.0"/>
             <filament id="1" type="PLA" used_g="50.0"/></plate>""")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(p), "")))
    dlg = cc.CostCalculatorDialog(est_weight_g=33.0, est_time_h=1.0)
    assert dlg._estimated is True                       # état de départ : estimé
    dlg._importer_fichier_tranche()
    assert dlg._weight_edit.text() == "50.00"
    assert dlg._time_edit.text() == "2.00"
    assert dlg._exact_source and dlg._estimated is False
    # saisie manuelle → l'étiquette « exact » disparaît
    dlg._weight_edit.setText("51")
    assert dlg._exact_source is None


def test_parse_duree():
    assert _parse_duree("1h 32m 10s") == 5530
    assert _parse_duree("2d 1h") == 2 * 86400 + 3600
    assert _parse_duree("45m") == 2700
    assert _parse_duree("90s") == 90
