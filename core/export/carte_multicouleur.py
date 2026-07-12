# -*- coding: utf-8 -*-
"""Export MULTICOULEUR d'une carte de visite → vrai 3MF avec un slot de filament
par couleur choisie dans l'éditeur, compatible avec le slicer de sortie
sélectionné (famille Bambu/OrcaSlicer + forks Creality/Elegoo/Anycubic/Snapmaker,
et PrusaSlicer).

Principe : on part d'un 3MF mono-objet VALIDE produit par le pipeline habituel
(ThreeMFBuilder / PrusaThreeMFBuilder → bons réglages machine + procédé), puis on
REMPLACE la géométrie par N corps (un par couleur), chacun assigné à un extrudeur,
et on pose la palette `filament_colour`. Le slicer ouvre alors la carte avec N
slots pré-remplis.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import trimesh


def _bodies_par_couleur(spec):
    """[(mesh, hex), …] : un corps fusionné par couleur (ordre = ordre des slots)."""
    from core.neogen.carte_visite import construire
    scene, couleurs = construire(spec)
    # regrouper les géométries de la scène par couleur visuelle
    corps: dict[str, list] = {}
    for _nom, g in scene.geometry.items():
        try:
            c = g.visual.face_colors[0][:3]
            hexa = "#{:02X}{:02X}{:02X}".format(int(c[0]), int(c[1]), int(c[2]))
        except Exception:
            hexa = "#FFFFFF"
        corps.setdefault(hexa, []).append(g)
    out = []
    for hexa in couleurs:                       # respecte l'ordre socle → éléments
        gs = corps.pop(hexa, None)
        if gs:
            out.append((trimesh.util.concatenate(gs) if len(gs) > 1 else gs[0], hexa))
    for hexa, gs in corps.items():              # couleurs restantes éventuelles
        out.append((trimesh.util.concatenate(gs) if len(gs) > 1 else gs[0], hexa))
    return out


def _mesh_xml(mesh, indent="    ") -> tuple[str, str]:
    v = "\n".join(f'{indent}  <vertex x="{p[0]:.4f}" y="{p[1]:.4f}" z="{p[2]:.4f}"/>'
                  for p in mesh.vertices)
    t = "\n".join(f'{indent}  <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>'
                  for f in mesh.faces)
    return v, t


def _build_multi_model(bodies, base_model_xml: str) -> str:
    """3dmodel.model multi-objets : chaque corps = un <object> nommé « couleur_i »
    (trimesh renomme la géométrie d'après ce name au rechargement → l'ID de part
    de model_settings.config peut le retrouver). Assemblés en UN objet imprimable."""
    import re
    import uuid
    ns = re.search(r'<model[^>]*>', base_model_xml).group(0)
    transform = "1 0 0 0 1 0 0 0 1 0 0 0"
    m = re.search(r'<item objectid="1"[^>]*transform="([^"]+)"', base_model_xml)
    if m:
        transform = m.group(1)
    meta = re.search(r'(<metadata name="Application">.*?</metadata>.*?<metadata name="Title">[^<]*</metadata>)',
                     base_model_xml, re.S)
    meta_xml = meta.group(1) if meta else ""

    # Structure Bambu Studio VALIDE (relevée sur un vrai 3MF dual BS) : la
    # géométrie est dans un fichier EXTERNE 3D/Objects/object_1.model ; le
    # 3dmodel.model ne contient qu'UN objet assemblage dont les <component>
    # référencent ces objets par p:path + objectid. p:UUID partout.
    comps = []
    for i, (_mesh, _hex) in enumerate(bodies):
        eid = i + 1                                    # objectid dans le fichier externe
        comps.append(
            f'    <component p:path="/3D/Objects/object_1.model" objectid="{eid}" '
            f'p:UUID="{uuid.uuid4()}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
    assembly = (f'  <object id="100" p:UUID="{uuid.uuid4()}" type="model" name="Carte de visite">\n'
                '   <components>\n' + "\n".join(comps) + '\n   </components>\n  </object>')
    return (f'{ns}\n {meta_xml}\n <resources>\n' + assembly + '\n </resources>\n'
            + f' <build p:UUID="{uuid.uuid4()}">\n'
            + f'  <item objectid="100" p:UUID="{uuid.uuid4()}" transform="{transform}" printable="1"/>\n'
            + ' </build>\n</model>')


def _external_objects_model(bodies) -> str:
    """3D/Objects/object_1.model : les N maillages (un par couleur), objectid 1..N,
    référencés par p:path depuis l'assemblage (structure Bambu Studio)."""
    import uuid
    objs = []
    for i, (mesh, _hex) in enumerate(bodies):
        eid = i + 1
        vx, tx = _mesh_xml(mesh, indent="   ")
        objs.append(
            f'  <object id="{eid}" p:UUID="{uuid.uuid4()}" type="model">\n'
            f'   <mesh>\n    <vertices>\n{vx}\n    </vertices>\n'
            f'    <triangles>\n{tx}\n    </triangles>\n   </mesh>\n  </object>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
            'requiredextensions="p">\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            ' <resources>\n' + "\n".join(objs) + '\n </resources>\n</model>')


def _build_multi_settings(bodies) -> str:
    """model_settings.config : l'objet assemblage (id 100) contient N parts (part id
    = objectid externe 1..N), chacune assignée à un extrudeur."""
    parts = []
    for i, (mesh, _hex) in enumerate(bodies):
        eid = i + 1
        fc = len(mesh.faces)
        parts.append(
            f'    <part id="{eid}" subtype="normal_part">\n'
            f'      <metadata key="name" value="couleur_{i+1}"/>\n'
            f'      <metadata key="extruder" value="{i+1}"/>\n'
            f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'      <mesh_stat face_count="{fc}" edges_fixed="0" degenerate_facets="0" '
            f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
            f'    </part>')
    total_faces = sum(len(m.faces) for m, _ in bodies)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
            '  <object id="100">\n'
            '    <metadata key="name" value="Carte de visite"/>\n'
            '    <metadata key="extruder" value="1"/>\n'
            f'    <metadata face_count="{total_faces}"/>\n'
            + "\n".join(parts) + "\n"
            + '  </object>\n'
            '  <plate index="0">\n'
            '    <metadata key="plater_id" value="1"/>\n'
            '    <model_instance objectid="100" instance_id="0" identify_id="0" plater_id="0" printable="true"/>\n'
            '  </plate>\n</config>')


def _poser_palette(project_settings: dict, couleurs: list[str]) -> None:
    """Pose la palette de couleurs et ÉTEND de façon COHÉRENTE tous les tableaux
    filament à N slots (BS refuse la config si les longueurs diffèrent)."""
    n = len(couleurs)
    for k, v in list(project_settings.items()):
        if k.startswith("filament_") and isinstance(v, list) and v:
            project_settings[k] = [v[0]] * n
    project_settings["filament_colour"] = list(couleurs)


def build_carte_multicouleur(spec, config, output_path: Path,
                             printer_ui_name: str, filament_ui_name: str,
                             nozzle_diameter_mm: float) -> Path:
    """Construit le 3MF multicouleur final selon le slicer de sortie sélectionné."""
    from core.prefs import PREFS
    slicer = PREFS.get("slicer_output", "bambu")
    bodies = _bodies_par_couleur(spec)
    couleurs = [hexa for _m, hexa in bodies]
    combined = trimesh.util.concatenate([m for m, _ in bodies])

    if slicer == "prusa":
        return _build_prusa(spec, config, output_path, printer_ui_name,
                            filament_ui_name, nozzle_diameter_mm, bodies, couleurs, combined)

    # Famille Bambu/Orca : 3MF mono-objet valide, puis patch multi-objets + palette
    from core.export.tmf_builder import ThreeMFBuilder
    tmp = output_path.with_suffix(".mono.3mf")
    ThreeMFBuilder().build(combined, config, tmp, object_name="Carte de visite",
                           printer_ui_name=printer_ui_name,
                           filament_ui_name=filament_ui_name,
                           nozzle_diameter_mm=nozzle_diameter_mm)
    with zipfile.ZipFile(tmp) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    base_model = data["3D/3dmodel.model"].decode("utf-8")
    ps = json.loads(data["Metadata/project_settings.config"].decode("utf-8"))
    _poser_palette(ps, couleurs)
    data["3D/Objects/object_1.model"] = _external_objects_model(bodies).encode("utf-8")
    data["3D/3dmodel.model"] = _build_multi_model(bodies, base_model).encode("utf-8")
    data["Metadata/model_settings.config"] = _build_multi_settings(bodies).encode("utf-8")
    data["Metadata/project_settings.config"] = json.dumps(ps, indent=4, ensure_ascii=False).encode("utf-8")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    try:
        tmp.unlink()
    except Exception:
        pass
    return output_path


def _prusa_model_config_multi(ranges, name: str) -> str:
    """Slic3r_PE_model.config : un objet à N VOLUMES (plages de triangles), chaque
    volume assigné à un extrudeur → PrusaSlicer ouvre la carte en multi-matière."""
    vols = []
    for i, (a, b) in enumerate(ranges):
        vols.append(
            f'  <volume firstid="{a}" lastid="{b}">\n'
            f'   <metadata type="volume" key="name" value="couleur_{i+1}"/>\n'
            f'   <metadata type="volume" key="volume_type" value="ModelPart"/>\n'
            f'   <metadata type="volume" key="extruder" value="{i+1}"/>\n'
            f'   <metadata type="volume" key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'  </volume>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
            f' <object id="1" instances_count="1">\n'
            f'  <metadata type="object" key="name" value="{name}"/>\n'
            + "\n".join(vols) + "\n </object>\n</config>")


def _prusa_add_colors(pc: str, couleurs: list[str]) -> str:
    cols = ";".join(couleurs)
    lines = [l for l in pc.split("\n")
             if not l.strip().startswith("; extruder_colour")
             and not l.strip().startswith("; filament_colour")]
    lines.append(f"; extruder_colour = {cols}")
    lines.append(f"; filament_colour = {cols}")
    return "\n".join(lines)


def _build_prusa(spec, config, output_path, printer_ui_name, filament_ui_name,
                 nozzle_diameter_mm, bodies, couleurs, combined) -> Path:
    """PrusaSlicer : 3MF Prusa mono-objet valide, puis on remplace le volume unique
    par N volumes (une plage de triangles par couleur) assignés à un extrudeur, et
    on pose la palette extruder_colour/filament_colour."""
    from core.export.prusa_3mf_builder import PrusaThreeMFBuilder
    # plages de triangles par corps (combined = concaténation dans cet ordre)
    ranges = []
    start = 0
    for m, _h in bodies:
        n = len(m.faces)
        ranges.append((start, start + n - 1))
        start += n
    PrusaThreeMFBuilder().build(mesh=combined, config=config, output_path=output_path,
                                printer_ui_name=printer_ui_name,
                                filament_ui_name=filament_ui_name,
                                nozzle_diameter_mm=nozzle_diameter_mm)
    with zipfile.ZipFile(output_path) as z:
        data = {n: z.read(n) for n in z.namelist()}
    data["Metadata/Slic3r_PE_model.config"] = _prusa_model_config_multi(
        ranges, "Carte de visite").encode("utf-8")
    pc = data["Metadata/Slic3r_PE.config"].decode("utf-8")
    data["Metadata/Slic3r_PE.config"] = _prusa_add_colors(pc, couleurs).encode("utf-8")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    return output_path
