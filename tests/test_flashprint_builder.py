# -*- coding: utf-8 -*-
"""Sortie FlashPrint (FlashForge) — catalogue + builder (3MF, profil QVariant, dépôt).

Le format du profil utilisateur FlashPrint a été relevé et VALIDÉ en pilotant
FlashPrint 5.8.7 (température 207 °C et couche 0.28 mm relues correctement dans
l'app). Ces tests verrouillent : catalogue complet (dont machine_id), 3MF
relisible, profil au format `[Custom]`/`[General]` avec flottants QVariant, valeurs
neoSlice appliquées (décodées depuis QVariant), garde-fous (vitesses plafonnées,
plateau non chauffant préservé, raft constructeur conservé), et dépôt sous le nom
`<machineId>_<buse>_<nom>.cfg`.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
import trimesh

from core.parameters.print_config import PrintConfig
from core.export import flashprint_builder as fpb
from core.export.flashprint_builder import FlashPrintBuilder


# ── Décodeur QVariant (miroir de _qv, pour vérifier les valeurs déposées) ──────
def _unescape(s: str) -> bytes:
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "x":                      # \xHH... (glouton) — ici toujours 2 chiffres
                j = i + 2
                hexd = ""
                while j < len(s) and s[j] in "0123456789abcdefABCDEF" and len(hexd) < 2:
                    hexd += s[j]; j += 1
                out.append(int(hexd, 16)); i = j; continue
            if n == "0":
                out.append(0); i += 2; continue
            if n == "\\":
                out.append(0x5C); i += 2; continue
            out.append(ord(n)); i += 2; continue
        out.append(ord(c)); i += 1
    return bytes(out)


def _decode_qv(raw: str) -> float:
    raw = raw.strip().strip('"')
    assert raw.startswith("@Variant(") and raw.endswith(")"), raw
    b = _unescape(raw[len("@Variant("):-1])
    return struct.unpack(">f", b[4:8])[0]      # 4 octets de type + float BE


def _parse_cfg(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("["):
            k, _, v = line.partition("=")
            out[k] = v
    return out


@pytest.fixture()
def box():
    return trimesh.creation.box(extents=(20, 20, 10))


# ── Catalogue ─────────────────────────────────────────────────────────────────
def test_catalogue_complet_avec_ids():
    from data.printers import (flashprint_brands, flashprint_models_for_brand,
                               flashprint_nozzles_for_model, flashprint_machine_for)
    assert flashprint_brands() == ["Flashforge"]
    models = flashprint_models_for_brand("Flashforge")
    assert len(models) >= 25
    for _disp, key in models:
        m = flashprint_machine_for(key)
        assert m["bed_size"] and m["printable_height"] > 0, key
        assert flashprint_nozzles_for_model(key), key
        assert m["machine_id"] >= 0, f"machine_id manquant pour {key}"


def test_machine_ids_connus():
    cat = json.loads((Path("data") / "flashprint_printers.json").read_text(encoding="utf-8"))
    ids = {k: v["machine_id"] for k, v in cat["machines"].items()}
    # ancres relevées + validées en GUI
    assert ids["FlashForge Adventurer 3 Pro 2"] == 30
    assert ids["FlashForge Adventurer 5M"] == 33
    assert ids["FlashForge Inventor II Series"] == 8
    assert len(set(ids.values())) == len(ids)          # tous distincts


def test_schema_present():
    s = json.loads((Path("data") / "flashprint_profile_schema.json").read_text(encoding="utf-8"))
    assert len(s["general_order"]) >= 190
    assert s["general"]["layerHeight"]["type"] == "variant"
    assert s["general"]["fillPattern"]["type"] == "plain"


# ── Builder : fichiers + format ───────────────────────────────────────────────
def test_build_3mf_et_cfg(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp_absent")
    b = FlashPrintBuilder()
    out = b.build(box, PrintConfig(), tmp_path / "piece.3mf",
                  "FlashForge Adventurer 5M", "PLA Basique", 0.4)
    assert out.exists()
    trimesh.load(str(out))                              # 3MF relisible
    fcfg = out.with_suffix(".fcfg")
    txt = fcfg.read_text(encoding="utf-8")
    assert txt.startswith("[Custom]\n") and "[General]" in txt
    cfg = _parse_cfg(txt)
    assert cfg["machineId"] == "33"                     # Adventurer 5M
    assert cfg["nozzleSize"].startswith("@Variant(")
    assert cfg["layerHeight"].startswith("@Variant(")
    assert len([k for k in cfg]) >= 200
    assert b.last_profile_name == "neoSlice piece"
    assert not b.last_profile_installed                 # dossier FlashPrint absent


def test_valeurs_appliquees_decodees(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp_absent")
    cfg = PrintConfig(layer_height=0.28, first_layer_height=0.28, wall_loops=5,
                      infill_density=37, nozzle_temperature=207, bed_temperature=55)
    b = FlashPrintBuilder()
    out = b.build(box, cfg, tmp_path / "p.3mf",
                  "FlashForge Inventor II Series", "PLA", 0.4)
    c = _parse_cfg(out.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert _decode_qv(c["layerHeight"]) == pytest.approx(0.28, abs=1e-4)
    assert _decode_qv(c["firstLayerHeight"]) == pytest.approx(0.28, abs=1e-4)
    assert _decode_qv(c["shellCnt"]) == pytest.approx(5.0, abs=1e-4)
    assert _decode_qv(c["extruderTemp0"]) == pytest.approx(207.0, abs=1e-3)
    assert _decode_qv(c["fillDensity"]) == pytest.approx(0.37, abs=1e-4)


def test_vitesses_plafonnees(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp_absent")
    b = FlashPrintBuilder()
    # Adventurer 5M PLA : baseSpeed constructeur 300 -> une demande à 500 est plafonnée
    out = b.build(box, PrintConfig(infill_speed=500), tmp_path / "f.3mf",
                  "FlashForge Adventurer 5M", "PLA", 0.4)
    c = _parse_cfg(out.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert _decode_qv(c["baseSpeed"]) == pytest.approx(300.0, abs=1e-2)
    out2 = b.build(box, PrintConfig(infill_speed=120), tmp_path / "s.3mf",
                   "FlashForge Adventurer 5M", "PLA", 0.4)
    c2 = _parse_cfg(out2.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert _decode_qv(c2["baseSpeed"]) == pytest.approx(120.0, abs=1e-2)


def test_plateau_non_chauffant_preserve(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp_absent")
    b = FlashPrintBuilder()
    out = b.build(box, PrintConfig(bed_temperature=60), tmp_path / "f.3mf",
                  "FlashForge Finder", "PLA", 0.4)   # Finder = plateau non chauffant
    c = _parse_cfg(out.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert _decode_qv(c["platformTemp"]) == pytest.approx(0.0, abs=1e-4)


def test_raft_constructeur_vs_brim(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp_absent")
    b = FlashPrintBuilder()
    # Adventurer 3 Series : raft constructeur ACTIF -> conservé ; on n'IMPOSE pas
    # notre largeur de brim (8) -> brimMargin reste au défaut constructeur (≠ 8).
    out = b.build(box, PrintConfig(brim_type="outer_only", brim_width=8),
                  tmp_path / "a3.3mf", "FlashForge Adventurer 3 Series", "PLA", 0.4)
    c = _parse_cfg(out.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert c["raftEnable"] == "true"
    assert _decode_qv(c["brimMargin"]) != pytest.approx(8.0, abs=1e-4)
    # 5M : pas de raft -> brim demandé appliqué (largeur 8 imposée)
    out2 = b.build(box, PrintConfig(brim_type="outer_only", brim_width=8),
                   tmp_path / "m5.3mf", "FlashForge Adventurer 5M", "PLA", 0.4)
    c2 = _parse_cfg(out2.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert c2["raftEnable"] == "false" and c2["brimMode"] == "1"
    assert _decode_qv(c2["brimMargin"]) == pytest.approx(8.0, abs=1e-4)


def test_depot_nom_fichier(tmp_path, box, monkeypatch):
    """Dépôt = `<machineId>_<buse>_<nom>.cfg` (format relevé de FlashPrint)."""
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp")
    (tmp_path / "fp").mkdir()
    b = FlashPrintBuilder()
    b.build(box, PrintConfig(), tmp_path / "piece.3mf",
            "FlashForge Inventor II Series", "PLA", 0.4)
    assert b.last_profile_installed
    dep = tmp_path / "fp" / "slice_profile" / "8_0.4_neoSlice piece.cfg"
    assert dep.exists()
    assert dep.read_text(encoding="utf-8").startswith("[Custom]\nmachineId=8\n")


def test_buse_025(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp")
    (tmp_path / "fp").mkdir()
    b = FlashPrintBuilder()
    b.build(box, PrintConfig(), tmp_path / "n.3mf",
            "FlashForge Adventurer 5M", "PLA", 0.25)
    assert (tmp_path / "fp" / "slice_profile" / "33_0.25_neoSlice n.cfg").exists()


def test_materiau_tpu(tmp_path, box, monkeypatch):
    monkeypatch.setattr(fpb, "FLASHPRINT_USER_DIR", tmp_path / "fp_absent")
    b = FlashPrintBuilder()
    out = b.build(box, PrintConfig(), tmp_path / "t.3mf",
                  "FlashForge Adventurer 5M", "TPU 95A HF", 0.4)
    c = _parse_cfg(out.with_suffix(".fcfg").read_text(encoding="utf-8"))
    assert "TPU" in c["materialName0"]
