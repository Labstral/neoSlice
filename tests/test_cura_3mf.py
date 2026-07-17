# -*- coding: utf-8 -*-
"""Simulateur du preRead de Cura (ThreeMFWorkspaceReader) sur nos 3MF générés.

Rejoue les vérifications EXACTES du lecteur installé (plugins/3MFReader) qui
ont fait échouer les premières versions — sans avoir besoin de lancer Cura :
  - exactement UN Cura/<id>.def.json de type "machine" (ligne 267 : sinon le
    fichier est traité comme un simple mesh, réglages ignorés) ;
  - piles global/extrudeur découvertes par suffixe + [metadata] type/position ;
  - tout variant / matériau / quality_changes / user / definition_changes
    référencé et non-« empty » DOIT être présent dans l'archive (KeyError sinon) ;
  - quality_changes global (sans position) avec metadata quality_type, et un par
    extrudeur avec position ;
  - Cura/preferences.cfg en version 7 (Preferences.Version — v6 rejetée) ;
  - ordre des conteneurs (0=user … 7=definition) ;
  - centrage : transform de l'item + centre du mesh == centre plateau (équation
    du lecteur, vérifiée sur les décalages observés en vrai).
"""
from __future__ import annotations

import configparser
import json
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import trimesh

from core.export.cura_3mf_builder import CuraThreeMFBuilder
from core.parameters.print_config import PrintConfig
from data.printers import cura_machine_for

EMPTIES = {"empty", "empty_quality_changes", "empty_intent", "empty_quality",
           "empty_material", "empty_variant", "empty_definition_changes"}


def _build(tmp_path: Path, machine_id: str, nozzle: float = 0.4,
           filament: str = "PLA") -> Path:
    out = tmp_path / f"{machine_id}.3mf"
    CuraThreeMFBuilder().build(
        trimesh.creation.box((20, 20, 10)), PrintConfig(support_type="tree(auto)"),
        out, printer_ui_name=machine_id, filament_ui_name=filament,
        nozzle_diameter_mm=nozzle)
    return out


def _archive_ids(names: list[str], suffix: str) -> dict[str, str]:
    """{id (dé-quoté): nom de fichier} pour un suffixe donné (convention Cura)."""
    out = {}
    for n in names:
        if n.startswith("Cura/") and n.endswith(suffix):
            stem = n[len("Cura/"):-len(suffix)]
            out[urllib.parse.unquote_plus(stem)] = n
    return out


def _pre_read_simulation(path: Path) -> dict:
    """Rejoue preRead ; retourne les infos extraites, échoue comme Cura sinon."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        cura_files = [n for n in names if n.startswith("Cura/")]

        # 1. Exactement un def.json machine (ligne 267 du lecteur)
        machine_defs, extruder_defs = [], []
        for did, fname in _archive_ids(cura_files, ".def.json").items():
            d = json.loads(z.read(fname))
            t = d.get("metadata", {}).get("type")
            (machine_defs if t == "machine" else extruder_defs).append(did)
        assert len(machine_defs) == 1, \
            f"preRead exige 1 def machine, trouvé {machine_defs}"
        machine_def_id = machine_defs[0]

        # 2. Conteneurs instance : tous parsables, indexés par id
        inst = {}
        for cid, fname in _archive_ids(cura_files, ".inst.cfg").items():
            cp = configparser.ConfigParser(interpolation=None, comment_prefixes=())
            cp.read_string(z.read(fname).decode("utf-8"))
            assert cp.has_option("metadata", "type"), f"{fname}: metadata.type absent"
            inst[cid] = cp
        materials = set(_archive_ids(cura_files, ".xml.fdm_material"))

        # 3. Pile globale : découverte par suffixe .global.cfg
        globals_ = _archive_ids(cura_files, ".global.cfg")
        assert len(globals_) == 1, f"1 pile globale attendue, trouvé {list(globals_)}"
        gid, gfile = next(iter(globals_.items()))
        gcp = configparser.ConfigParser(interpolation=None)
        gcp.read_string(z.read(gfile).decode("utf-8"))
        assert gcp.get("metadata", "type") == "machine"
        g_containers = [gcp.get("containers", str(i)) for i in range(8)]
        assert g_containers[7] == machine_def_id, \
            f"containers[7]={g_containers[7]} != def machine {machine_def_id}"

        # 4. Références de la pile globale résolvables (KeyError chez Cura sinon)
        for idx in (0, 1, 6):                      # user, quality_changes, def_changes
            cid = g_containers[idx]
            if cid not in EMPTIES:
                assert cid in inst, f"pile globale[{idx}]={cid} absent de l'archive"

        # 5. quality_changes global : sans position, avec quality_type
        qc_gid = g_containers[1]
        assert qc_gid not in EMPTIES, "quality_changes global manquant (réglages perdus)"
        qc = inst[qc_gid]
        assert not qc.has_option("metadata", "position")
        assert qc.get("metadata", "quality_type"), "quality_type absent du qc global"

        # 6. Piles extrudeur : position + références résolvables
        extruders = _archive_ids(cura_files, ".extruder.cfg")
        assert extruders, "aucune pile extrudeur"
        for eid, efile in extruders.items():
            ecp = configparser.ConfigParser(interpolation=None)
            ecp.read_string(z.read(efile).decode("utf-8"))
            assert ecp.get("metadata", "type") == "extruder_train"
            assert ecp.has_option("metadata", "position")
            e_containers = [ecp.get("containers", str(i)) for i in range(8)]
            for idx, cid in enumerate(e_containers[:7]):
                if cid in EMPTIES:
                    continue
                if idx == 4:                        # matériau -> .xml.fdm_material
                    assert cid in materials, f"matériau {cid} absent de l'archive"
                elif idx == 3:
                    pass                            # quality : registre Cura (ok absent)
                else:
                    assert cid in inst, f"extrudeur[{idx}]={cid} absent de l'archive"
            qc_e = inst[e_containers[1]]
            assert qc_e.has_option("metadata", "position"), "qc extrudeur sans position"

        # 7. preferences.cfg version 7 (Preferences.Version)
        pcp = configparser.ConfigParser(interpolation=None)
        pcp.read_string(z.read("Cura/preferences.cfg").decode("utf-8"))
        assert pcp.get("general", "version") == "7", \
            "preferences.cfg doit être en version 7 (v6 silencieusement rejetée)"
        assert pcp.has_option("general", "visible_settings")

        # 8. Géométrie + centrage (équation du lecteur : X_ui = tx + cx - W/2)
        model = z.read("3D/3dmodel.model").decode("utf-8")
        root = ET.fromstring(model)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        item = root.find(".//m:build/m:item", ns)
        tf = [float(x) for x in item.get("transform").split()]
        tx, ty = tf[9], tf[10]
        verts = [(float(v.get("x")), float(v.get("y")))
                 for v in root.findall(".//m:vertex", ns)]
        cx = (min(p[0] for p in verts) + max(p[0] for p in verts)) / 2
        cy = (min(p[1] for p in verts) + max(p[1] for p in verts)) / 2
        return {"machine_def_id": machine_def_id, "global_containers": g_containers,
                "center": (tx + cx, ty + cy), "n_extruders": len(extruders),
                "qc_values": dict(inst[qc_gid].items("values"))}


@pytest.mark.parametrize("machine_id,nozzle", [
    ("creality_ender3", 0.4),      # 1.75mm, variants dédiés, qualité famille
    ("ultimaker_s5", 0.4),         # 2.85mm, 2 extrudeurs, variants AA
    ("anycubic_kobra_max", 0.4),   # buse unique (pas de variants → def_changes)
])
def test_projet_cura_passe_pre_read(tmp_path, machine_id, nozzle):
    path = _build(tmp_path, machine_id, nozzle)
    info = _pre_read_simulation(path)
    assert info["machine_def_id"] == machine_id
    m = cura_machine_for(machine_id)
    # centrage : item + centre mesh == centre plateau (voir équation lecteur)
    assert abs(info["center"][0] - m["width"] / 2) < 0.01
    assert abs(info["center"][1] - m["depth"] / 2) < 0.01
    assert info["n_extruders"] == m["extruder_count"]


def test_reglages_dans_quality_changes(tmp_path):
    path = _build(tmp_path, "creality_ender3")
    info = _pre_read_simulation(path)
    vals = info["qc_values"]
    assert vals.get("support_enable") == "True"       # bool format Cura
    assert "layer_height" in vals                      # clé globale bien placée


def test_variant_et_materiau_embarques(tmp_path):
    path = _build(tmp_path, "creality_ender3", 0.6, "PETG")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    assert "Cura/creality_ender3_0.6.inst.cfg" in names          # variant réel
    assert "Cura/generic_petg_175.xml.fdm_material" in names     # matériau 1.75


def test_machine_inconnue_replie_avec_erreur_loggee(tmp_path):
    # Une imprimante non-Cura (ex. Bambu) ne doit pas produire un fichier cassé.
    path = _build(tmp_path, "X1 Carbon")
    info = _pre_read_simulation(path)
    assert info["machine_def_id"] == "creality_ender3"           # repli documenté
