"""Export 3MF MULTI-PLATEAUX avec réglages par objet (Bambu Studio / OrcaSlicer).

Cas d'usage : lithophanie + boîte lumineuse — le couvercle (lithophane) doit
s'imprimer avec le profil lithophanie (remplissage 100 %) sur le plateau 1, la
boîte en réglages standard sur le plateau 2, le tout dans UN seul projet 3MF à
deux plateaux. Généralisable à toute scène neoGen dont les corps portent un tag
de plateau/profil (voir DSL `plateau()`/`profil()`).

Repli slicers non Bambu/Orca : l'appelant exporte plutôt un fichier par plateau
(le format multi-plateaux + réglages par objet n'y est pas garanti).

On PART d'un 3MF mono valide (ThreeMFBuilder) pour hériter d'un
project_settings.config + fichiers structurels + marque du slicer corrects, puis
on réécrit 3D/3dmodel.model (N objets) et model_settings.config (N objets + N
plateaux) — géométrie inline, réglages par objet en metadata <object>.
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

import numpy as np
import trimesh


def _mesh_inline_xml(mesh: trimesh.Trimesh) -> tuple[str, str, int]:
    """(vertices_xml, triangles_xml, face_count) — vertices mergés (cf. tmf_builder :
    sans merge, BS voit le mesh ouvert et met des supports dedans)."""
    m = mesh
    if len(mesh.vertices) > len(mesh.faces):
        try:
            m = mesh.copy()
            m.merge_vertices(merge_tex=False)
        except Exception:
            m = mesh
    verts = "\n".join(
        f'      <vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>'
        for v in m.vertices)
    tris = "\n".join(
        f'      <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>'
        for f in m.faces)
    return verts, tris, len(m.faces)


def _poses_par_plateau(objects: list[dict], bx: float, by: float) -> list[str]:
    """Transforms 3MF (une par objet) : le GROUPE de chaque plateau est centré
    sur (bx, by) en PRÉSERVANT les positions relatives des pièces du groupe.

    Centrer chaque pièce individuellement superposait toutes les pièces d'un
    même plateau au centre (audit export — dormant tant qu'il n'y avait qu'une
    pièce par plateau, garanti faux dès deux pièces).
    """
    import collections
    groupes = collections.defaultdict(list)
    for i, o in enumerate(objects):
        groupes[int(o.get("plate", 0))].append(i)
    out = [""] * len(objects)
    for idx_list in groupes.values():
        los = np.array([objects[i]["mesh"].bounds[0] for i in idx_list])
        his = np.array([objects[i]["mesh"].bounds[1] for i in idx_list])
        glo, ghi = los.min(axis=0), his.max(axis=0)
        dx = bx - (glo[0] + ghi[0]) / 2          # centre du GROUPE → centre plateau
        dy = by - (glo[1] + ghi[1]) / 2
        for i in idx_list:
            lo = objects[i]["mesh"].bounds[0]
            out[i] = f"1 0 0 0 1 0 0 0 1 {dx:.4f} {dy:.4f} {-lo[2]:.4f}"
    return out


def build_multiplate_bambu(objects: list[dict], base_config, output_path: Path,
                           printer_ui_name: str, filament_ui_name: str,
                           nozzle_diameter_mm: float, plate_type: str = "") -> Path:
    """UN 3MF Bambu/Orca, N objets répartis sur leurs plateaux, chacun ses réglages.

    `objects` : liste de dicts `{mesh, config, plate, name}`.
      - `config` : PrintConfig de l'objet (ex. profil litho pour le couvercle).
      - `plate`  : index de plateau 0-based.
    `base_config` : config COMMUNE (project_settings global). Chaque objet écrit en
      metadata <object> uniquement ce qui DIFFÈRE de `base_config` (surcharge).
    """
    from core.export.tmf_builder import (
        ThreeMFBuilder, _bed_center, _BED_TYPE_CODE, _BED_TYPE_CODE_DEFAULT,
        _UI_TO_PRINTER_ID, _apply_non_bambu_machine, bambu_per_object_overrides,
        _NS_3MF, _NS_BBL, _NS_PROD, _slicer_branding)
    from data.printers import is_catalogue_model

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) 3MF mono de base (mesh combiné + base_config) → project_settings + structure.
    combined = trimesh.util.concatenate([o["mesh"] for o in objects])
    tmp = output_path.with_suffix(".mono.3mf")
    ThreeMFBuilder().build(
        combined, base_config, tmp, object_name=objects[0].get("name", "Objet"),
        printer_ui_name=printer_ui_name, filament_ui_name=filament_ui_name,
        nozzle_diameter_mm=nozzle_diameter_mm, plate_type=plate_type)
    with zipfile.ZipFile(tmp) as z:
        data = {n: z.read(n) for n in z.namelist()}
    try:
        tmp.unlink()
    except Exception:
        pass

    # 2) Centre du plateau (même logique que _build_native).
    _machine = None
    try:
        if is_catalogue_model(printer_ui_name):
            _machine = _apply_non_bambu_machine(
                dict(json.loads(data["Metadata/project_settings.config"])),
                printer_ui_name, nozzle_diameter_mm, filament_ui_name)
    except Exception:
        _machine = None
    bx, by = _bed_center(_machine) if _machine else (128.0, 128.0)

    bed_code = _BED_TYPE_CODE.get(plate_type, _BED_TYPE_CODE_DEFAULT)
    app_name = _slicer_branding()["application"]

    # 3) 3D/3dmodel.model : N objets inline + N items. Les pièces d'un même
    # plateau gardent leurs positions RELATIVES (groupe centré sur le plateau).
    from xml.sax.saxutils import escape as _xesc
    transforms = _poses_par_plateau(objects, bx, by)
    res_blocks, build_items, ms_objects, ms_plates = [], [], [], []
    for i, o in enumerate(objects):
        oid = i + 1
        # Échappement XML : un nom avec & < > " casserait le 3MF (audit export).
        name = _xesc(str(o.get("name", f"objet_{oid}")), {'"': "&quot;"})
        plate = int(o.get("plate", 0))
        verts, tris, fc = _mesh_inline_xml(o["mesh"])
        res_blocks.append(
            f'  <object id="{oid}" p:UUID="{uuid.uuid4()}" type="model" name="{name}">\n'
            f'   <mesh>\n    <vertices>\n{verts}\n    </vertices>\n'
            f'    <triangles>\n{tris}\n    </triangles>\n   </mesh>\n'
            f'   <BambuStudio:Stats edges_fixed="0" degenerate_facets="0" '
            f'facets_removed="0" facets_reversed="0"/>\n  </object>')
        build_items.append(
            f'  <item objectid="{oid}" p:UUID="{uuid.uuid4()}" '
            f'transform="{transforms[i]}" printable="1"/>')

        # Surcharges par objet = diff vs base commune (uniquement clés per-object).
        overrides = bambu_per_object_overrides(base_config, o["config"])
        ov_xml = "".join(
            f'    <metadata key="{k}" value="{v}"/>\n' for k, v in overrides.items())
        ms_objects.append(
            f'  <object id="{oid}">\n'
            f'    <metadata key="name" value="{name}"/>\n'
            f'    <metadata key="extruder" value="1"/>\n'
            f'    <metadata face_count="{fc}"/>\n'
            f'{ov_xml}'
            f'    <part id="1" subtype="normal_part">\n'
            f'      <metadata key="name" value="{name}"/>\n'
            f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'      <mesh_stat face_count="{fc}" edges_fixed="0" degenerate_facets="0" '
            f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
            f'    </part>\n  </object>')

    # Un plateau par index présent (ordonné) ; chaque objet sur SON plateau.
    plate_indices = sorted({int(o.get("plate", 0)) for o in objects})
    plate_of_pos = {pi: pos for pos, pi in enumerate(plate_indices)}
    for pi in plate_indices:
        plater_id = plate_of_pos[pi] + 1
        instances = "".join(
            f'    <model_instance objectid="{i + 1}" instance_id="0" '
            f'identify_id="{i}" plater_id="{plate_of_pos[pi]}" printable="true"/>\n'
            for i, o in enumerate(objects) if int(o.get("plate", 0)) == pi)
        ms_plates.append(
            f'  <plate index="{plate_of_pos[pi]}">\n'
            f'    <metadata key="plater_id" value="{plater_id}"/>\n'
            f'    <metadata key="plater_name" value=""/>\n'
            f'    <metadata key="locked" value="false"/>\n'
            f'    <metadata key="bed_type" value="{bed_code}"/>\n'
            f'    <metadata key="thumbnail_file" value=""/>\n'
            f'{instances}'
            f'  </plate>')

    model_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{_NS_3MF}" '
        f'xmlns:BambuStudio="{_NS_BBL}" xmlns:p="{_NS_PROD}" requiredextensions="p">\n'
        f' <metadata name="Application">{app_name}</metadata>\n'
        ' <metadata name="BambuStudio:3mfVersion">1.9.0</metadata>\n'
        ' <resources>\n' + "\n".join(res_blocks) + '\n </resources>\n'
        f' <build p:UUID="{uuid.uuid4()}">\n' + "\n".join(build_items) +
        '\n </build>\n</model>')

    model_settings = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        + "\n".join(ms_objects) + "\n" + "\n".join(ms_plates) + "\n</config>")

    data["3D/3dmodel.model"] = model_xml.encode("utf-8")
    data["Metadata/model_settings.config"] = model_settings.encode("utf-8")
    # Le mono inline n'a pas de géométrie externe ; on retire d'éventuels résidus.
    data.pop("3D/Objects/object_1.model", None)
    data.pop("3D/_rels/3dmodel.model.rels", None)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    return output_path
