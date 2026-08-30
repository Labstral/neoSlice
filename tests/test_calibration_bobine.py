# -*- coding: utf-8 -*-
"""Calibration par bobine — réglages fins mémorisés bobine par bobine
(Espace Pro), badge CALIBRÉE et section dédiée dans la fiche PDF."""
import pytest

from core.business import store


@pytest.fixture(autouse=True)
def _isole_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_SPOOLS", tmp_path / "spools.json")
    yield


def test_defauts_calibration_presents():
    d = store._spool_defaults()
    assert set(d["calibration"]) == {"temp_buse", "temp_plateau", "debit_pct",
                                     "retraction_mm", "retraction_vit", "notes"}
    assert not store.spool_est_calibree(d)


def test_est_calibree():
    assert not store.spool_est_calibree({})                    # pas de bloc du tout
    assert store.spool_est_calibree({"calibration": {"temp_buse": 215}})
    assert store.spool_est_calibree({"calibration": {"debit_pct": 97.5}})
    # des notes seules comptent (ex. « imprimer à 90 % de vitesse »)
    assert store.spool_est_calibree({"calibration": {"notes": "ralentir à 90 %"}})
    assert not store.spool_est_calibree({"calibration": {"notes": "   "}})


def test_filtre_materiau_et_archivees():
    store.add_spool({"materiau": "PLA", "marque": "A",
                     "calibration": {"temp_buse": 215}})
    store.add_spool({"materiau": "PETG", "marque": "B",
                     "calibration": {"temp_buse": 240}})
    store.add_spool({"materiau": "PLA", "marque": "C"})            # non calibrée
    store.add_spool({"materiau": "PLA", "marque": "D", "archivee": True,
                     "calibration": {"temp_buse": 200}})           # archivée
    assert [s["marque"] for s in store.spools_calibrees()] == ["A", "B"]
    assert [s["marque"] for s in store.spools_calibrees("pla")] == ["A"]
    assert store.spools_calibrees("ABS") == []


def test_i18n_cles_calibration():
    from core.i18n import _FR, _EN
    for cle in ("spool.cal_title", "spool.cal_hint", "spool.cal_temp_buse",
                "spool.cal_temp_plateau", "spool.cal_debit", "spool.cal_retraction",
                "spool.cal_retraction_vit", "spool.cal_notes", "spool.cal_badge",
                "pdf.sec_spools_cal", "pdf.spools_cal_note", "pdf.cal_buse",
                "pdf.cal_plateau", "pdf.cal_debit", "pdf.cal_retract",
                "pdf.cal_retract_vit"):
        assert cle in _FR, f"FR manquante : {cle}"
        assert cle in _EN, f"EN manquante : {cle}"


def test_pdf_avec_bobines_calibrees(tmp_path, monkeypatch):
    """Le PDF filament se génère avec ET sans la section Pro (jamais bloquant)."""
    pytest.importorskip("reportlab")
    import core.licensing as lic
    from core.export.pdf_generator import generate_filament_pdf

    store.add_spool({"materiau": "PLA", "marque": "PolyTerra",
                     "couleur_nom": "Bleu",
                     "calibration": {"temp_buse": 212, "debit_pct": 97.0,
                                     "retraction_mm": 0.8, "retraction_vit": 40.0,
                                     "notes": "Tour de temp 2026-08"}})
    for pro in (True, False):
        monkeypatch.setattr(lic, "est_pro", lambda: pro)
        sortie = tmp_path / f"fiche_{pro}.pdf"
        assert generate_filament_pdf("PLA", "Bambu Lab X1 Carbon", sortie) is True
        assert sortie.exists() and sortie.stat().st_size > 1000
