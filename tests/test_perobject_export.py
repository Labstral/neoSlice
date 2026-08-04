"""Tests de l'export « réglages par objet » (édition multi-objets).

Couvre les briques testables sans slicer ni OpenGL :
- table de capacités par slicer ;
- calcul des surcharges par objet (diff, aplatissement, liste blanche) ;
- injection de metadata <object> dans model_settings.config (format Bambu réel) ;
- non-régression : sans surcharges, model_settings.config est inchangé ;
- bout-en-bout sur un vrai 3MF Bambu si disponible.
"""
import glob
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from core.export.perobject_capabilities import (
    BAMBU_PER_OBJECT_KEYS,
    diff_per_object_overrides,
    is_bambu_family,
    supports_per_object_one_file,
)
from core.export.tmf_builder import (
    ThreeMFBuilder,
    _patch_model_settings_per_object,
    bambu_per_object_overrides,
)
from core.parameters.parameter_engine import PrintConfig


# ── model_settings.config synthétique minimal (2 objets, format Bambu) ────────
_MS = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="2">
    <metadata key="name" value="A"/>
    <metadata key="extruder" value="1"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="A"/>
      <mesh_stat face_count="10"/>
    </part>
  </object>
  <object id="6">
    <metadata key="name" value="B"/>
    <metadata key="extruder" value="1"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="B"/>
      <mesh_stat face_count="20"/>
    </part>
  </object>
  <plate index="0">
    <model_instance objectid="2" instance_id="0"/>
    <model_instance objectid="6" instance_id="1"/>
  </plate>
</config>"""


# ── Capacités par slicer ──────────────────────────────────────────────────────
def test_capabilities_per_slicer():
    assert supports_per_object_one_file("bambu")
    assert supports_per_object_one_file("orca")
    assert supports_per_object_one_file("BAMBU")           # insensible à la casse
    for s in ("cura", "flashprint", "prusa", "creality", "elegoo"):
        assert not supports_per_object_one_file(s), s
    assert supports_per_object_one_file(None)              # défaut = bambu


def test_bambu_family():
    for s in ("bambu", "orca", "creality", "elegoo", "anycubic", "snapmaker"):
        assert is_bambu_family(s), s
    for s in ("prusa", "cura", "flashprint"):
        assert not is_bambu_family(s), s


# ── diff / aplatissement / liste blanche ──────────────────────────────────────
def test_diff_only_differences_and_whitelist():
    base = {"wall_loops": "2", "layer_height": "0.2", "printer_model": "X1C"}
    obj = {"wall_loops": "4", "layer_height": "0.2", "printer_model": "A1"}
    d = diff_per_object_overrides(base, obj)
    assert d == {"wall_loops": "4"}          # layer_height identique → ignoré
    assert "printer_model" not in d          # hors liste blanche → jamais per-object


def test_diff_flattens_speed_arrays():
    base = {"outer_wall_speed": ["200", "200"]}
    obj = {"outer_wall_speed": ["80", "80"]}
    d = diff_per_object_overrides(base, obj)
    assert d == {"outer_wall_speed": "80"}   # tableau aplati en chaîne simple


def test_diff_new_key_when_absent_from_base():
    d = diff_per_object_overrides({}, {"enable_support": "1"})
    assert d == {"enable_support": "1"}


def test_bambu_per_object_overrides_from_config():
    base = PrintConfig()
    obj = PrintConfig()
    obj.wall_loops = 6
    obj.infill_density = 90
    ov = bambu_per_object_overrides(base, obj)
    assert ov.get("wall_loops") == "6"
    assert ov.get("sparse_infill_density") == "90%"
    # toutes les clés produites sont dans la liste blanche
    assert set(ov).issubset(BAMBU_PER_OBJECT_KEYS)
    # valeurs = chaînes simples (jamais de tableau)
    assert all(isinstance(v, str) for v in ov.values())


# ── patch model_settings.config ───────────────────────────────────────────────
def test_patch_inserts_before_part():
    po = {"2": {"wall_loops": "5", "sparse_infill_density": "75%"}}
    out, n = _patch_model_settings_per_object(_MS, po)
    assert n == 1
    root = ET.fromstring(out)
    obj = next(o for o in root.findall("object") if o.get("id") == "2")
    got = {m.get("key"): m.get("value") for m in obj.findall("metadata")}
    assert got["wall_loops"] == "5"
    assert got["sparse_infill_density"] == "75%"
    # les metadata surchargées précèdent le <part>
    tags = [c.tag for c in list(obj)]
    assert tags.index("part") > tags.count("metadata") - 1
    assert all(t == "metadata" for t in tags[:tags.index("part")])


def test_patch_idempotent_no_duplicates():
    po = {"2": {"wall_loops": "5"}}
    once, _ = _patch_model_settings_per_object(_MS, po)
    twice, _ = _patch_model_settings_per_object(once, po)
    obj = next(o for o in ET.fromstring(twice).findall("object") if o.get("id") == "2")
    keys = [m.get("key") for m in obj.findall("metadata")]
    assert keys.count("wall_loops") == 1


def test_patch_unknown_id_ignored():
    po = {"999": {"wall_loops": "5"}}
    out, n = _patch_model_settings_per_object(_MS, po)
    assert n == 0
    # aucun objet n'a reçu wall_loops
    for o in ET.fromstring(out).findall("object"):
        assert "wall_loops" not in {m.get("key") for m in o.findall("metadata")}


def test_patch_multiple_objects():
    po = {"2": {"wall_loops": "5"}, "6": {"enable_support": "0"}}
    out, n = _patch_model_settings_per_object(_MS, po)
    assert n == 2
    root = ET.fromstring(out)
    o2 = next(o for o in root.findall("object") if o.get("id") == "2")
    o6 = next(o for o in root.findall("object") if o.get("id") == "6")
    assert "wall_loops" in {m.get("key") for m in o2.findall("metadata")}
    assert "enable_support" in {m.get("key") for m in o6.findall("metadata")}


def test_patch_malformed_xml_degrades_gracefully():
    out, n = _patch_model_settings_per_object("<not xml", {"2": {"wall_loops": "5"}})
    assert n == 0
    assert out == "<not xml"


# ── bout-en-bout sur un vrai 3MF Bambu (si disponible) ────────────────────────
def _find_multiobject_bambu_3mf():
    cands = glob.glob(r"D:/Impression 3D/*.3mf") + glob.glob("data/*.3mf")
    for f in cands:
        try:
            with zipfile.ZipFile(f) as z:
                if "Metadata/model_settings.config" not in z.namelist():
                    continue
                root = ET.fromstring(
                    z.read("Metadata/model_settings.config").decode("utf-8", "ignore"))
                if len(root.findall("object")) >= 2:
                    return f
        except Exception:
            continue
    return None


def test_inject_per_object_end_to_end(tmp_path):
    src = _find_multiobject_bambu_3mf()
    if not src:
        pytest.skip("aucun 3MF Bambu multi-objets disponible")
    with zipfile.ZipFile(src) as z:
        root = ET.fromstring(
            z.read("Metadata/model_settings.config").decode("utf-8", "ignore"))
    ids = [o.get("id") for o in root.findall("object")]
    po = {ids[0]: {"wall_loops": "6", "sparse_infill_density": "90%"},
          ids[1]: {"enable_support": "0"}}
    out = tmp_path / "ensemble.3mf"
    ThreeMFBuilder().inject_settings_into_3mf(
        source_path=Path(src), config=PrintConfig(), output_path=out,
        printer_ui_name="X1 Carbon", filament_ui_name="PLA",
        nozzle_diameter_mm=0.4, per_object_overrides=po)
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "Metadata/project_settings.config" in names
        assert "Metadata/model_settings.config" in names
        r2 = ET.fromstring(
            z.read("Metadata/model_settings.config").decode("utf-8", "ignore"))
    o0 = next(o for o in r2.findall("object") if o.get("id") == ids[0])
    got = {m.get("key"): m.get("value") for m in o0.findall("metadata")}
    assert got.get("wall_loops") == "6"
    assert got.get("sparse_infill_density") == "90%"


def test_inject_without_per_object_leaves_model_settings_untouched(tmp_path):
    """Non-régression : sans per_object_overrides, model_settings.config du 3MF
    source est copié à l'identique (seul project_settings.config change)."""
    src = _find_multiobject_bambu_3mf()
    if not src:
        pytest.skip("aucun 3MF Bambu multi-objets disponible")
    with zipfile.ZipFile(src) as z:
        original_ms = z.read("Metadata/model_settings.config")
    out = tmp_path / "sans_perobj.3mf"
    ThreeMFBuilder().inject_settings_into_3mf(
        source_path=Path(src), config=PrintConfig(), output_path=out,
        printer_ui_name="X1 Carbon", filament_ui_name="PLA",
        nozzle_diameter_mm=0.4)
    with zipfile.ZipFile(out) as z:
        assert z.read("Metadata/model_settings.config") == original_ms
