"""Tests de l'export MULTI-PLATEAUX (lithophanie + boîte lumineuse).

- Tags DSL `plateau()` / `profil()` (metadata trimesh, survit à `scene()`).
- `build_multiplate_bambu` : N objets sur N plateaux, surcharges par objet
  (couvercle litho 100 % sur le plateau 1, boîte standard sur le plateau 2).

N'importe PAS `ui.*` (garde la suite saine — cf. règle apprise sur les imports UI).
"""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import trimesh

from core.neogen.libre import scene, plateau, profil
from core.parameters.parameter_engine import PrintConfig, appliquer_profil_lithophanie
from core.export.multiplate_3mf import build_multiplate_bambu

_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


# ── Tags DSL ──────────────────────────────────────────────────────────────────
def test_plateau_tag():
    b = trimesh.creation.box(extents=(10, 10, 10))
    t = plateau(b, 1)
    assert t.metadata.get("neoslice_plate") == 1
    # ne mute pas l'original
    assert "neoslice_plate" not in (b.metadata or {})


def test_profil_tag():
    b = trimesh.creation.box(extents=(10, 10, 10))
    t = profil(b, "standard")
    assert t.metadata.get("neoslice_profil") == "standard"


def test_tags_combines_survivent_scene():
    litho = plateau(trimesh.creation.box(extents=(80, 80, 3)), 0)
    boite = plateau(profil(trimesh.creation.box(extents=(90, 90, 40)), "standard"), 1)
    s = scene(litho, boite)
    tags = {(g.metadata.get("neoslice_plate"), g.metadata.get("neoslice_profil"))
            for g in s.geometry.values()}
    assert (0, None) in tags
    assert (1, "standard") in tags


# ── Export multi-plateaux Bambu/Orca ──────────────────────────────────────────
def _build(tmp_path):
    litho_cfg = appliquer_profil_lithophanie(PrintConfig())
    std_cfg = PrintConfig()
    objects = [
        {"mesh": trimesh.creation.box(extents=(80, 80, 3)),
         "config": litho_cfg, "plate": 0, "name": "lithophanie"},
        {"mesh": trimesh.creation.box(extents=(90, 90, 40)),
         "config": std_cfg, "plate": 1, "name": "boite"},
    ]
    out = tmp_path / "lightbox.3mf"
    build_multiplate_bambu(objects, std_cfg, out, "X1 Carbon", "PLA", 0.4)
    return out


def test_multiplate_two_plates_two_objects(tmp_path):
    out = _build(tmp_path)
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        ms = ET.fromstring(z.read("Metadata/model_settings.config").decode())
        mm = ET.fromstring(z.read("3D/3dmodel.model").decode())
    assert len(ms.findall("object")) == 2
    assert len(ms.findall("plate")) == 2
    # 2 objets géométriques réels
    res = mm.find(f"{_NS}resources")
    assert len(res.findall(f"{_NS}object")) == 2


def test_multiplate_object_on_its_own_plate(tmp_path):
    out = _build(tmp_path)
    with zipfile.ZipFile(out) as z:
        ms = ET.fromstring(z.read("Metadata/model_settings.config").decode())
    # chaque plateau référence UN objet distinct
    plate_to_obj = {}
    for p in ms.findall("plate"):
        insts = [mi.get("objectid") for mi in p.findall("model_instance")]
        plate_to_obj[p.get("index")] = insts
    assert plate_to_obj["0"] == ["1"]
    assert plate_to_obj["1"] == ["2"]


def test_multiplate_litho_overrides_only_on_lid(tmp_path):
    out = _build(tmp_path)
    with zipfile.ZipFile(out) as z:
        ms = ET.fromstring(z.read("Metadata/model_settings.config").decode())
    by_id = {o.get("id"): o for o in ms.findall("object")}
    litho = {m.get("key"): m.get("value") for m in by_id["1"].findall("metadata")}
    boite = {m.get("key"): m.get("value") for m in by_id["2"].findall("metadata")}
    # Couvercle (plateau 0) : remplissage 100 % surchargé par objet
    assert litho.get("sparse_infill_density") == "100%"
    assert litho.get("wall_loops") == "4"
    # Boîte (plateau 1) : PAS de surcharge remplissage (suit le global standard)
    assert "sparse_infill_density" not in boite
    assert boite.get("name") == "boite"


def test_multiplate_global_is_standard(tmp_path):
    """project_settings global = config standard (la boîte suit le global ; seul le
    couvercle surcharge) → remplissage global != 100 %."""
    import json
    out = _build(tmp_path)
    with zipfile.ZipFile(out) as z:
        ps = json.loads(z.read("Metadata/project_settings.config").decode())
    # le global n'est pas le profil litho (sinon la boîte serait à 100 %)
    assert ps.get("sparse_infill_density") not in ("100%", "100")
