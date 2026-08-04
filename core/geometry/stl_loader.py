from __future__ import annotations
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh
from loguru import logger

from .threemf_data import ThreeMFData, MeshObject


class STLLoadError(Exception):
    pass


# fill_holes est extrêmement lent sur les maillages complexes non-watertight.
# On le saute dès 100k faces. process=False (pas de merge_vertices) seulement
# au-dessus de 1M faces — en dessous la topologie doit rester correcte pour l'analyse.
_FACE_SKIP_FILL_HOLES = 100_000
_FACE_SKIP_PROCESS    = 1_000_000


def _estimate_stl_faces(path: Path) -> int:
    """Estime le nombre de faces d'un fichier STL binaire via sa taille."""
    try:
        size = path.stat().st_size
        # Format binaire : 80 header + 4 count + N*50 bytes
        if size > 84:
            return int((size - 84) / 50)
    except Exception:
        pass
    return 0


# Espace de noms 3MF « core »
_3MF_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"

# Au-delà de ce coût (nb composants externes × octets du/des .model référencés),
# le loader 3MF de trimesh devient pathologique (il relit TOUT le .model externe
# UNE FOIS PAR COMPOSANT) → on bascule sur notre chargement dédié. En dessous,
# trimesh gère très bien : on ne dévie pas (zéro risque pour les cas validés).
_SPLIT_3MF_COST_THRESHOLD = 120_000_000


def _read_mesh_fast(mesh_el) -> tuple[np.ndarray, np.ndarray]:
    """Lit vertices/triangles d'un <mesh> 3MF en une passe (np.fromstring)."""
    verts = mesh_el.find(f"{_3MF_NS}vertices")
    tris = mesh_el.find(f"{_3MF_NS}triangles")
    if verts is None or tris is None:
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    vs = " ".join(f"{v.get('x')} {v.get('y')} {v.get('z')}" for v in verts)
    v_arr = np.fromstring(vs, dtype=np.float64, sep=" ").reshape((-1, 3))
    fs = " ".join(f"{t.get('v1')} {t.get('v2')} {t.get('v3')}" for t in tris)
    f_arr = np.fromstring(fs, dtype=np.int64, sep=" ").reshape((-1, 3))
    return v_arr, f_arr


def _fast_load_split_3mf(path: Path) -> "trimesh.Scene | None":
    """Charge un 3MF Bambu « split-model » sans le bug O(composants × fichier).

    Motif Bambu : le modèle principal (3dmodel.model) contient des <component>
    qui référencent des sous-objets d'un .model EXTERNE (Objects/object_1.model)
    via p:path + objectid. trimesh relit l'INTÉGRALITÉ du .model externe pour
    CHAQUE composant → sur 73 composants × 17 MB, le chargement ne finit jamais.

    Ici on relit chaque .model externe UNE seule fois, puis on assemble une
    trimesh.Scene correcte (géométrie par objectid + transform de chaque
    instance = build_item ∘ component). Retourne None si le motif est absent ou
    peu coûteux (→ on laisse le chemin trimesh normal, éprouvé sur les cas validés).
    """
    try:
        from lxml import etree
        from trimesh.exchange.threemf import _attrib_to_transform
    except Exception:
        return None
    try:
        if not zipfile.is_zipfile(path):
            return None
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "3D/3dmodel.model" not in names:
                return None
            root = etree.fromstring(zf.read("3D/3dmodel.model"))

            # 1) Recenser les composants qui référencent un .model EXTERNE
            ext_refs = []  # (parent_obj_id, sub_objid, transform_4x4, zippath)
            for obj in root.iter(f"{_3MF_NS}object"):
                comps = obj.find(f"{_3MF_NS}components")
                if comps is None:
                    continue
                for c in comps.iter(f"{_3MF_NS}component"):
                    zp = next((v.strip("/") for k, v in c.attrib.items()
                               if k.endswith("path")), None)
                    sub_id = c.attrib.get("objectid")
                    if zp and sub_id:
                        ext_refs.append((obj.get("id"), sub_id,
                                         _attrib_to_transform(c.attrib), zp))
            if not ext_refs:
                return None  # pas le motif split-model → trimesh normal

            # 2) Filtre coût : ne dévier que si trimesh serait pathologique
            ext_paths = {zp for *_, zp in ext_refs}
            ext_bytes = sum(zf.getinfo(p).file_size for p in ext_paths if p in names)
            cost = len(ext_refs) * ext_bytes
            if cost < _SPLIT_3MF_COST_THRESHOLD:
                return None
            logger.info(
                f"[3MF] motif split-model coûteux (composants={len(ext_refs)}, "
                f"externe={ext_bytes // 1024} KB, coût={cost:,}) → chargement rapide dédié"
            )

            # 3) Parser chaque .model externe UNE fois : {zippath: {objid: (v, f)}}
            geom_cache: dict[str, dict[str, tuple]] = {}
            for zp in ext_paths:
                if zp not in names:
                    continue
                sub: dict[str, tuple] = {}
                sroot = etree.fromstring(zf.read(zp))
                for so in sroot.iter(f"{_3MF_NS}object"):
                    m = so.find(f"{_3MF_NS}mesh")
                    if m is None:
                        continue
                    v, f = _read_mesh_fast(m)
                    if len(v) and len(f):
                        sub[so.get("id")] = (v, f)
                geom_cache[zp] = sub

            # 4) Transforms des build items (objet top-level → monde)
            build_tf: dict[str, np.ndarray] = {}
            build = root.find(f"{_3MF_NS}build")
            if build is not None:
                for it in build.iter(f"{_3MF_NS}item"):
                    build_tf[it.attrib.get("objectid")] = _attrib_to_transform(it.attrib)

            # 5) Assembler la Scene : une géométrie par INSTANCE + transform monde.
            # ⚠️ Les objectid se répètent entre assemblages (ex. « Table de
            # chevet » : object_25.model ids 11/12/13 référencés par les objets
            # racine 14 ET 18, avec des transforms différents ; parts partagées
            # entre plateaux). Nommer les géométries par le seul sub_id faisait
            # que trimesh écrasait scene.geometry[sub_id] (le dernier mesh
            # gagnait pour TOUTES les instances) → mauvais meshes, doublons,
            # scène étalée sur des mètres. → noms uniques par instance
            # "parent_sub" ; le mesh (gros tableau de vertices) reste PARTAGÉ
            # entre instances via mesh_cache (même objet Trimesh sous plusieurs
            # clés — _parse_threemf_multiobject fait .copy() par objet).
            scene = trimesh.Scene()
            mesh_cache: dict[tuple[str, str], trimesh.Trimesh] = {}
            inst_counts: dict[str, int] = {}
            for parent_id, sub_id, comp_tf, zp in ext_refs:
                vf = geom_cache.get(zp, {}).get(sub_id)
                if vf is None:
                    continue
                mesh = mesh_cache.get((zp, sub_id))
                if mesh is None:
                    v, f = vf
                    mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
                    mesh_cache[(zp, sub_id)] = mesh
                bt = build_tf.get(parent_id)
                world_tf = comp_tf if bt is None else np.dot(bt, comp_tf)
                # Nom d'instance = "parent_sub" → matche (object id, part id)
                # de model_settings.config dans _parse_threemf_multiobject.
                inst = f"{parent_id}_{sub_id}"
                n = inst_counts.get(inst, 0)
                inst_counts[inst] = n + 1
                if n:  # même part répétée dans le même assemblage → suffixe
                    inst = f"{inst}#{n}"
                scene.add_geometry(mesh, geom_name=inst,
                                   node_name=inst, transform=world_tf)
            if not scene.geometry:
                return None
            # Marqueur : les geom keys sont "parent_sub" (matching dédié dans
            # _parse_threemf_multiobject, à ne PAS appliquer aux scènes trimesh).
            scene.metadata["neoslice_split_fast"] = True
            logger.info(f"[3MF] chargement rapide split-model : {len(scene.geometry)} géométries")
            return scene
    except Exception as e:
        logger.warning(f"[3MF] chargement rapide split-model échoué ({e!r}) — repli trimesh")
        return None


def _parse_threemf_multiobject(path: Path, scene: trimesh.Scene) -> ThreeMFData | None:
    """Parse un 3MF Bambu multi-objets et retourne ThreeMFData si multi-objets.

    Lit model_settings.config pour les assignations de slots, construit
    la liste des MeshObject, et retourne None si fichier mono-objet simple.
    """
    if not zipfile.is_zipfile(path):
        return None

    try:
        with zipfile.ZipFile(path) as zf:
            # Lire model_settings.config (assignations slots/extruder)
            model_settings_xml = ""
            extruder_by_id: dict[str, int] = {}  # part_id → extruder
            name_by_id: dict[str, str] = {}

            _znames = zf.namelist()
            _has_config = "Metadata/model_settings.config" in _znames

            # root = arbre XML de model_settings.config. None si absent (3MF exporté
            # par Fusion/trimesh…) : les boucles qui le lisent sont alors sautées au
            # lieu de lever UnboundLocalError (bug connu post-0.1.6). Même précaution
            # pour les collections remplies dans ce bloc mais lues plus bas.
            root = None
            modifier_part_ids: set[str] = set()  # IDs des parts non-imprimables
            part_to_obj_id: dict[str, str] = {}  # part_id → parent object_id
            # Dicts composites "obj_part" : la MÊME part peut être normal_part
            # sous un objet et negative_part sous un autre (ids réutilisés entre
            # assemblages) → les dicts à plat par part_id sont ambigus. Utilisés
            # par le matching dédié split-model (geom keys "parent_sub").
            config_obj_ids: set[str] = set()
            name_by_key: dict[str, str] = {}      # "obj_part" → nom
            extruder_by_key: dict[str, int] = {}  # "obj_part" → extruder
            modifier_keys: set[str] = set()       # "obj_part" non-imprimables
            if _has_config:
                model_settings_xml = zf.read("Metadata/model_settings.config").decode("utf-8")
                root = ET.fromstring(model_settings_xml)
                # Subtypes non-imprimables à exclure du rendu et de l'analyse.
                # negative_part = bloqueur de support / volume négatif (BS/Prusa)
                # support_enforcer / support_blocker = modificateurs de support
                _SKIP_SUBTYPES = {
                    "negative_part", "support_enforcer", "support_blocker",
                    "support_modifier", "modifier",
                    "modifier_part",   # Generic-Cube, Generic-Cylinder, etc. (Infill Display)
                }
                for obj in root.findall("object"):
                    obj_id = obj.get("id", "")
                    config_obj_ids.add(obj_id)
                    # Extruder au niveau objet (fallback). Bambu le stocke en
                    # ENFANT <metadata key="extruder" value="N"/>, PAS en attribut de
                    # <object> → lire les deux (priorité au metadata). Sans ça, tous les
                    # objets retombaient sur l'extruder 1 → une seule couleur détectée
                    # sur un 3MF multi-couleurs (bug détection slots).
                    obj_extruder = int(obj.get("extruder", 1))
                    for meta in obj.findall("metadata"):
                        if meta.get("key") == "extruder":
                            try:
                                obj_extruder = int(meta.get("value", obj_extruder))
                            except (TypeError, ValueError):
                                pass
                    for part in obj.findall("part"):
                        # Ignorer les pièces non-imprimables (bloqueurs de support, etc.)
                        subtype = part.get("subtype", "normal_part")
                        part_id = part.get("id", obj_id)
                        part_to_obj_id[str(part_id)] = obj_id  # toujours enregistrer le lien
                        _ckey = f"{obj_id}_{part_id}"
                        if subtype in _SKIP_SUBTYPES:
                            logger.debug(f"Part {part_id} (obj {obj_id}) ignorée (subtype={subtype})")
                            modifier_part_ids.add(str(part_id))
                            modifier_keys.add(_ckey)
                            continue
                        # Nom depuis metadata
                        for meta in part.findall("metadata"):
                            if meta.get("key") == "name":
                                name_by_id[part_id] = meta.get("value", f"Part {part_id}")
                                name_by_key[_ckey] = name_by_id[part_id]
                        # Extruder au niveau part (priorité) ou objet
                        ext_val = obj_extruder
                        for meta in part.findall("metadata"):
                            if meta.get("key") == "extruder":
                                ext_val = int(meta.get("value", 1))
                        extruder_by_id[part_id] = ext_val
                        extruder_by_key[_ckey] = ext_val

            # Lire les matrices de placement Bambu + plate_index par objet.
            # Bambu stocke scale/rotation/translation dans metadata "matrix" au niveau <object>,
            # PAS dans les transforms <item> 3MF standard lus par trimesh.
            # Format: 12 valeurs row-major (3×3 rotation/scale + 1×3 translation)
            matrix_by_obj_id: dict[str, np.ndarray] = {}
            plate_by_obj_id: dict[str, int] = {}   # obj_id → numéro de plateau (1-based)

            def _parse_matrix_str(s: str) -> np.ndarray | None:
                """Parse matrice BS column-major 3×4 → 4×4 numpy."""
                try:
                    v = [float(x) for x in s.split()]
                    if len(v) != 12:
                        return None
                    return np.array([
                        [v[0], v[3], v[6], v[9]],
                        [v[1], v[4], v[7], v[10]],
                        [v[2], v[5], v[8], v[11]],
                        [0.0,  0.0,  0.0,  1.0  ],
                    ], dtype=np.float64)
                except (ValueError, IndexError):
                    return None

            for obj in (root.findall("object") if root is not None else []):
                _oid = obj.get("id", "")
                # plate_index au niveau objet (nouvelle structure BS)
                for meta in obj.findall("metadata"):
                    if meta.get("key") in ("plate_index", "bed_index"):
                        try:
                            plate_by_obj_id[_oid] = int(meta.get("value", 1))
                        except ValueError:
                            pass
                # Matrix cherchée à deux niveaux :
                # 1) Directement sous <object> (ancienne structure)
                for meta in obj.findall("metadata"):
                    if meta.get("key") == "matrix":
                        m = _parse_matrix_str(meta.get("value", ""))
                        if m is not None:
                            matrix_by_obj_id[_oid] = m
                # 2) Sous <part> (nouvelle structure BS — VolumeMetadata)
                for part in obj.findall("part"):
                    _pid = part.get("id", _oid)
                    for meta in part.findall("metadata"):
                        if meta.get("key") == "matrix":
                            m = _parse_matrix_str(meta.get("value", ""))
                            if m is not None:
                                matrix_by_obj_id[_pid] = m
                                matrix_by_obj_id[_oid] = m  # aussi par obj_id

            # plate_index dans <plate> — deux formats selon la version BS :
            # Format A (BS récent): <model_instance objectid="X"/>
            # Format B (BS ancienne): <model_instance><metadata key="object_id" value="X"/></model_instance>
            # plater_id dans <metadata key="plater_id" value="N"/> (1-based → converti 0-based)
            for plate_el in (root.findall("plate") if root is not None else []):
                # plater_id : dans metadata ou attribut index
                _plate_num = 0
                _pid_attr = plate_el.get("index", plate_el.get("id", None))
                if _pid_attr:
                    try:
                        _plate_num = int(_pid_attr) - 1  # 1-based → 0-based
                    except ValueError:
                        pass
                else:
                    for meta in plate_el.findall("metadata"):
                        if meta.get("key") in ("plater_id", "plate_id"):
                            try:
                                _plate_num = int(meta.get("value", 1)) - 1
                            except ValueError:
                                pass
                # model_instance : format A (attribut) ou format B (metadata enfant)
                for inst in plate_el.findall("model_instance"):
                    _inst_oid = inst.get("objectid", "")
                    if not _inst_oid:
                        # Format B : chercher dans les metadata enfants
                        for meta in inst.findall("metadata"):
                            if meta.get("key") in ("object_id", "obj_id"):
                                _inst_oid = meta.get("value", "")
                                break
                    if _inst_oid:
                        plate_by_obj_id[_inst_oid] = _plate_num

            if matrix_by_obj_id:
                logger.info(f"[3MF] matrices trouvées: {len(matrix_by_obj_id)} obj(s), "
                            f"plates: {dict(list(plate_by_obj_id.items())[:5])}")

            # Lire 3dmodel.model
            model_xml = ""
            if "3D/3dmodel.model" in zf.namelist():
                model_xml = zf.read("3D/3dmodel.model").decode("utf-8")

            # Construire la carte : build_object_id → premier_composant_propre.
            # Pour les objets avec modifier_parts, on veut seulement le premier composant
            # (la géométrie normale sans les cubes Generic). Le second composant est le modifier.
            # {build_obj_id: (zip_path, sub_object_id)} → géométrie du composant propre
            _clean_geom_by_obj: dict[str, trimesh.Trimesh] = {}
            if model_xml:
                try:
                    _mroot = ET.fromstring(model_xml)
                    _mns = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
                    _mnsp = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
                    _resources = _mroot.find(f'{_mns}resources')
                    if _resources is not None:
                        for _mobj in _resources.findall(f'{_mns}object'):
                            _oid = _mobj.get('id', '')
                            _comps = _mobj.find(f'{_mns}components')
                            if _comps is None:
                                continue
                            _comp_list = _comps.findall(f'{_mns}component')
                            # Ce mecanisme "geometrie propre" ne sert QU'AU cas du
                            # modifier fusionne (Generic-Cube) : un objet dont un
                            # composant est un modifier_part. Pour un objet
                            # multi-parts MULTICOLORE sans modifier, il ne faut PAS
                            # collapser, sinon les N parts deviennent N copies de la
                            # 1re (badge multicolore affiche en doublons decales).
                            _has_modifier = (_mobj.get('id', '') in modifier_part_ids) or any(
                                str(c.get('objectid', '')) in modifier_part_ids
                                for c in _comp_list)
                            if not _has_modifier:
                                continue
                            _normal_comp = None
                            for _c in _comp_list:
                                _sub_id = _c.get('objectid', '')
                                _c_path = _c.get(f'{_mnsp}path', '')
                                if _sub_id and _sub_id not in modifier_part_ids and _c_path:
                                    _normal_comp = (_c_path.lstrip('/'), _sub_id)
                                    break
                            if _normal_comp and len(_comp_list) > 1:
                                # Lire la géométrie propre directement depuis le fichier ZIP
                                _zip_path, _sub_obj_id = _normal_comp
                                try:
                                    with zipfile.ZipFile(path) as _zf2:
                                        if _zip_path in _zf2.namelist():
                                            _sub_data = _zf2.read(_zip_path).decode('utf-8')
                                            _sub_root = ET.fromstring(_sub_data)
                                            for _so in _sub_root.find(f'{_mns}resources').findall(f'{_mns}object'):
                                                if _so.get('id') == _sub_obj_id:
                                                    _sm = _so.find(f'{_mns}mesh')
                                                    if _sm is not None:
                                                        _verts = np.array([
                                                            [float(v.get('x')), float(v.get('y')), float(v.get('z'))]
                                                            for v in _sm.find(f'{_mns}vertices').findall(f'{_mns}vertex')
                                                        ])
                                                        _faces = np.array([
                                                            [int(t.get('v1')), int(t.get('v2')), int(t.get('v3'))]
                                                            for t in _sm.find(f'{_mns}triangles').findall(f'{_mns}triangle')
                                                        ])
                                                        _clean_geom_by_obj[_oid] = trimesh.Trimesh(
                                                            vertices=_verts, faces=_faces, process=False)
                                                        break
                                except Exception as _ge:
                                    logger.debug(f"Clean geom pour obj {_oid} échoué: {_ge}")
                except Exception as _pe:
                    logger.debug(f"Parse 3dmodel.model pour clean geoms: {_pe}")

            if _clean_geom_by_obj:
                logger.info(f"[3MF] {len(_clean_geom_by_obj)} géométries propres (sans modifier) prêtes")

            # Multi-parts MULTICOLORE : quand un objet est compose de composants
            # referencant des sous-objets d'un .model EXTERNE, trimesh renvoie le
            # mesh FUSIONNE (somme de toutes les parts) pour CHAQUE composant -> les
            # N parts deviennent N copies identiques (badge multicolore affiche en
            # doublons decales). On relit donc chaque sous-objet distinctement pour
            # rendre a chaque part sa vraie geometrie.
            _part_geom_by_id: dict[str, "trimesh.Trimesh"] = {}
            if model_xml:
                try:
                    _mns = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
                    _mnsp = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
                    _mroot2 = ET.fromstring(model_xml)
                    _res2 = _mroot2.find(f'{_mns}resources')
                    _sub_cache: dict[str, dict] = {}   # zip_path -> {sub_id: <object el>}

                    def _sub_index(zip_path: str) -> dict:
                        if zip_path in _sub_cache:
                            return _sub_cache[zip_path]
                        idx: dict = {}
                        try:
                            with zipfile.ZipFile(path) as _zf3:
                                if zip_path in _zf3.namelist():
                                    _r = ET.fromstring(_zf3.read(zip_path).decode('utf-8'))
                                    _rr = _r.find(f'{_mns}resources')
                                    if _rr is not None:
                                        for _so in _rr.findall(f'{_mns}object'):
                                            idx[_so.get('id')] = _so
                        except Exception as _e:
                            logger.debug(f"index sous-modele {zip_path}: {_e}")
                        _sub_cache[zip_path] = idx
                        return idx

                    if _res2 is not None:
                        for _mobj in _res2.findall(f'{_mns}object'):
                            _comps = _mobj.find(f'{_mns}components')
                            if _comps is None:
                                continue
                            _cl = _comps.findall(f'{_mns}component')
                            if len(_cl) < 2:
                                continue
                            for _c in _cl:
                                _sid = _c.get('objectid', '')
                                _cp = _c.get(f'{_mnsp}path', '')
                                if (not _sid or not _cp or _sid in modifier_part_ids
                                        or _sid in _part_geom_by_id):
                                    continue
                                _so = _sub_index(_cp.lstrip('/')).get(_sid)
                                _sm = _so.find(f'{_mns}mesh') if _so is not None else None
                                if _sm is None:
                                    continue
                                try:
                                    _vs = _sm.find(f'{_mns}vertices')
                                    _ts = _sm.find(f'{_mns}triangles')
                                    _verts = np.array([[float(v.get('x')), float(v.get('y')), float(v.get('z'))]
                                                       for v in _vs.findall(f'{_mns}vertex')])
                                    _faces = np.array([[int(t.get('v1')), int(t.get('v2')), int(t.get('v3'))]
                                                       for t in _ts.findall(f'{_mns}triangle')])
                                    if len(_verts) and len(_faces):
                                        _part_geom_by_id[_sid] = trimesh.Trimesh(
                                            vertices=_verts, faces=_faces, process=False)
                                except Exception as _ge2:
                                    logger.debug(f"part geom {_sid}: {_ge2}")
                except Exception as _pe2:
                    logger.debug(f"Parse per-part geoms: {_pe2}")
            if _part_geom_by_id:
                logger.info(f"[3MF] {len(_part_geom_by_id)} géométries de parts distinctes (multi-composants)")

    except Exception as e:
        logger.debug(f"3MF multi-objet parse error : {e}")
        return None

    meshes = {k: v for k, v in scene.geometry.items() if isinstance(v, trimesh.Trimesh)}
    logger.debug(
        f"[3MF] geom keys: {list(meshes.keys())} | "
        f"matrix_ids: {list(matrix_by_obj_id.keys())} | "
        f"extruder_ids: {list(extruder_by_id.keys())[:5]}"
    )
    if len(meshes) < 1:
        return None  # aucun mesh, rien à faire

    # Compter les plateaux réels (plate_N.png strict — exclut plate_N_small.png
    # et plate_no_light_N.png, sinon le compte est doublé : 7 plateaux → 14)
    plate_count = 1
    try:
        import re as _re
        with zipfile.ZipFile(path) as _zf2:
            plate_count = max(1, len([
                n for n in _zf2.namelist()
                if _re.fullmatch(r"Metadata/plate_\d+\.png", n)
            ]))
    except Exception:
        pass

    # Construire la liste des objets en gérant les instances multiples.
    # scene.graph.geometry_nodes : geom_id → [node_name, ...]
    # scene.graph.get(node_name) → (matrix_4x4, frame_name)  ← ordre correct
    objects: list[MeshObject] = []
    modifier_objects: list[MeshObject] = []
    geom_nodes: dict = getattr(scene.graph, "geometry_nodes", {})

    def _resolve_id(key: str, *dicts) -> str | None:
        """Résout un geom_key vers un ID connu dans les dicts (essaie key, puis prefix)."""
        candidates = [key] + ([key.split("_")[0]] if "_" in key else [])
        for c in candidates:
            if any(c in d for d in dicts):
                return c
        return None

    # Scène issue de _fast_load_split_3mf : geom keys "parent_sub" UNIQUES par
    # instance (les objectid se répètent entre assemblages → noms uniques par
    # instance). Matching DIRECT par (objet parent, part) : les dicts à plat
    # sont ambigus (ex. part 11 = normal_part sous l'objet 18 mais
    # negative_part sous l'objet 14). Transform = celui de la scène
    # (build_item ∘ component, déjà monde) ; plateau = celui du parent.
    _split_fast = bool(getattr(scene, "metadata", {}).get("neoslice_split_fast"))

    for geom_id, mesh in meshes.items():
        geom_key = str(geom_id)
        if _split_fast and "_" in geom_key:
            _base = geom_key.split("#")[0]          # "14_11#1" → "14_11"
            _p_oid, _, _s_pid = _base.partition("_")
            if _p_oid in config_obj_ids and (
                    _base in extruder_by_key or _base in name_by_key
                    or _base in modifier_keys):
                try:
                    _xf, _ = scene.graph.get(geom_key)
                    if not isinstance(_xf, np.ndarray) or _xf.shape != (4, 4):
                        _xf = np.eye(4)
                except Exception:
                    _xf = np.eye(4)
                if _base in modifier_keys:
                    modifier_objects.append(MeshObject(
                        object_id=f"mod_{geom_key}",
                        name=f"modifier_{geom_key}",
                        extruder=0,
                        mesh=mesh.copy(),
                        transform=_xf,
                    ))
                else:
                    objects.append(MeshObject(
                        object_id=geom_key,
                        name=name_by_key.get(_base, f"Part {_s_pid}"),
                        extruder=extruder_by_key.get(_base, 1),
                        mesh=mesh.copy(),
                        transform=_xf,
                        plate_index=plate_by_obj_id.get(_p_oid, 0),
                    ))
                continue
        # Matching flexible : geom_key "2_1" → essaie "2_1" et "2"
        _matched = _resolve_id(geom_key, extruder_by_id, name_by_id, matrix_by_obj_id)
        is_known_part = _matched is not None
        is_modifier = (geom_key in modifier_part_ids or
                       any(geom_key.startswith(pid + "_") or geom_key == pid
                           for pid in modifier_part_ids))
        nodes = geom_nodes.get(geom_key, [geom_key])

        extruder = extruder_by_id.get(_matched or geom_key, extruder_by_id.get(geom_key, 1))
        name = name_by_id.get(_matched or geom_key, name_by_id.get(geom_key, f"Part {geom_id}"))

        if not is_known_part and len(nodes) > 0:
            has_named_node = any(
                str(n) in name_by_id or str(n) in extruder_by_id for n in nodes
            )
            if not has_named_node:
                logger.debug(f"Géométrie {geom_id} sans part connu — skip (probable modificateur)")
                if mesh.is_watertight or is_modifier:
                    for node_name in nodes:
                        _mx_key2 = _resolve_id(str(node_name), matrix_by_obj_id) \
                                   or _resolve_id(geom_key, matrix_by_obj_id)
                        if _mx_key2 is not None:
                            xform = matrix_by_obj_id[_mx_key2]
                        else:
                            try:
                                xform, _ = scene.graph.get(str(node_name))
                                if not isinstance(xform, np.ndarray) or xform.shape != (4, 4):
                                    xform = np.eye(4)
                            except Exception:
                                xform = np.eye(4)
                        modifier_objects.append(MeshObject(
                            object_id=f"mod_{geom_id}_{node_name}",
                            name=f"modifier_{geom_id}",
                            extruder=0,
                            mesh=mesh.copy(),
                            transform=xform,
                        ))
                continue

        for node_name in nodes:
            # Priorité : matrice Bambu (model_settings.config) — contient scale/rot/trans complet.
            # Fallback : scene.graph (transforms 3MF standards, sans scale Bambu).
            _mx_key = _resolve_id(str(node_name), matrix_by_obj_id) \
                      or _resolve_id(geom_key, matrix_by_obj_id)
            if _mx_key is not None:
                xform = matrix_by_obj_id[_mx_key]
            else:
                try:
                    xform, _ = scene.graph.get(str(node_name))
                    if not isinstance(xform, np.ndarray) or xform.shape != (4, 4):
                        xform = np.eye(4)
                except Exception:
                    xform = np.eye(4)

            # Résoudre le plate_index via : part_id → parent object_id → plate_by_obj_id.
            # Crucial : part_id "42" ≠ build object_id "44". Sans ce mapping, la base board
            # reçoit plate_index=0 au lieu de 1, causant son inclusion dans le combined_mesh.
            _pid_for_plate = _matched or geom_key
            _parent_oid = part_to_obj_id.get(_pid_for_plate, _pid_for_plate)
            _plate_idx = plate_by_obj_id.get(
                _parent_oid,
                plate_by_obj_id.get(_pid_for_plate, 0)
            )
            # Utiliser la géométrie propre (sans modifier fusionné) si disponible.
            # Sans ça, geom 1_19 = flat_tile(188f) + generic_cube(12f) × 20 = 4000 faces
            # et les cubes Generic apparaissent dans le viewer.
            # Priorite : geom "propre" (cas modifier) ; sinon geom de la part relue
            # distinctement (cas multi-composants externe) ; sinon le mesh trimesh.
            _display_mesh = _clean_geom_by_obj.get(_parent_oid)
            if _display_mesh is None:
                _display_mesh = (_part_geom_by_id.get(str(geom_id))
                                 or _part_geom_by_id.get(str(_matched or "")))
            if _display_mesh is None:
                _display_mesh = mesh
            _display_mesh = _display_mesh.copy()
            objects.append(MeshObject(
                object_id=f"{geom_id}_{node_name}" if len(nodes) > 1 else str(geom_id),
                name=name,
                extruder=extruder,
                mesh=_display_mesh,
                transform=xform,
                plate_index=_plate_idx,
            ))

    if not objects and len(meshes) > 1:
        # Fallback générique : aucun objet identifié via metadata (3MF sans config complet,
        # calibration files, infill display, etc.) → traiter toutes les géom non-modifier.
        logger.info(f"3MF: aucun objet identifié — fallback générique sur {len(meshes)} géom(s)")
        for _fgeom_id, _fmesh in meshes.items():
            _fkey = str(_fgeom_id)
            if (_fkey in modifier_part_ids or
                    any(_fkey.startswith(p + "_") or _fkey == p for p in modifier_part_ids)):
                continue
            _fnodes = geom_nodes.get(_fkey, [_fkey])
            for _fnode in _fnodes:
                _fmx = _resolve_id(str(_fnode), matrix_by_obj_id) \
                       or _resolve_id(_fkey, matrix_by_obj_id)
                if _fmx:
                    _fxform = matrix_by_obj_id[_fmx]
                else:
                    try:
                        _fxform, _ = scene.graph.get(str(_fnode))
                        if not isinstance(_fxform, np.ndarray) or _fxform.shape != (4, 4):
                            _fxform = np.eye(4)
                    except Exception:
                        _fxform = np.eye(4)
                objects.append(MeshObject(
                    object_id=f"fb_{_fgeom_id}_{_fnode}",
                    name=f"Part_{_fgeom_id}",
                    extruder=1,
                    mesh=_fmesh.copy(),
                    transform=_fxform,
                ))

    if not objects:
        return None

    # Mesh combiné pour l'analyse — utiliser le mesh propre (min faces) pour les copies.
    face_counts = [len(o.mesh.faces) for o in objects]
    min_fc = min(face_counts) if face_counts else 0
    clean_idx = face_counts.index(min_fc) if face_counts else 0
    clean_mesh_ref = objects[clean_idx].mesh if objects else None

    # combined_mesh = TOUS les objets, dans l'ordre de `objects` : le pipeline
    # d'affichage/couleurs (colorize surplombs multipart, thermomap fragilité)
    # aligne ses tableaux par face sur CETTE concaténation — filtrer ici (ex.
    # premier plateau seul) désaligne tout et fait DISPARAÎTRE les autres
    # plateaux de la vue analyse (vécu : Table de chevet, 1 objet affiché sur 29).
    if plate_by_obj_id:
        logger.info(f"[3MF] plateaux: {sorted(set(plate_by_obj_id.values()))}")

    combined_parts = []
    for obj, fc in zip(objects, face_counts):
        deviation = abs(fc - min_fc) / max(min_fc, 1) if min_fc > 0 else 0
        m = (clean_mesh_ref.copy() if deviation > 0 and deviation < 0.05
             else obj.mesh.copy())
        if not np.allclose(obj.transform, np.eye(4)):
            logger.debug(
                f"  Transform {obj.object_id}: t={obj.transform[:3,3].round(1)}, "
                f"scale≈{np.linalg.norm(obj.transform[:3,:3], axis=0).round(3)}"
            )
            m.apply_transform(obj.transform)
        combined_parts.append(m)
    if not combined_parts:
        # Fallback : si aucun objet plateau 1 trouvé, tout inclure
        for obj, fc in zip(objects, face_counts):
            deviation = abs(fc - min_fc) / max(min_fc, 1) if min_fc > 0 else 0
            m = (clean_mesh_ref.copy() if deviation > 0 and deviation < 0.05
                 else obj.mesh.copy())
            if not np.allclose(obj.transform, np.eye(4)):
                m.apply_transform(obj.transform)
            combined_parts.append(m)
    if combined_parts:
        combined = trimesh.util.concatenate(combined_parts)
        _bb = combined.bounding_box.extents
        logger.info(f"3MF combined mesh (tous plateaux): {_bb.round(1)} mm")
    else:
        combined = objects[0].mesh

    # Assemblage multicolore : les parts s'imbriquent pour former UN solide qui
    # s'imprime a plat (les couches de couleur remplissent les creux de la base).
    # Le mesh combine (parts qui se chevauchent) n'est PAS manifold -> la detection
    # de regions flottantes y voit des faces internes comme flottantes et propose
    # des supports fantomes. On marque donc l'assemblage pour que l'analyse
    # N'AJOUTE PAS de supports pour flottant (voir has_color_assembly). L'AFFICHAGE
    # garde bien les 4 parts (lisse), on ne touche pas combined.
    # UNIQUEMENT le vrai cas : un assemblage couleur imbriqué s'imprime à plat sur UN
    # SEUL plateau. Un 3MF multi-couleurs réparti sur plusieurs plateaux (ex. casque
    # découpé en pièces) est un modèle multi-pièces normal → il FAUT analyser surplombs
    # et supports. Sans la garde plate_count, la détection multi-couleurs (extruder) tuait
    # à tort la détection de supports (report.support_needed forcé à False).
    _is_color_assembly = (
        len({o.extruder for o in objects}) > 1
        and len(objects) > 1
        and plate_count <= 1
    )

    logger.info(f"3MF multi-objets : {len(objects)} parties · {len({o.extruder for o in objects})} slot(s) · {plate_count} plateau(x) · {len(modifier_objects)} modificateur(s)")
    return ThreeMFData(
        combined_mesh=combined,
        objects=objects,
        source_path=path,
        model_settings_xml=model_settings_xml,
        model_xml=model_xml,
        plate_count=plate_count,
        modifier_meshes=modifier_objects,
        is_color_assembly=_is_color_assembly,
    )


def _is_sliced_3mf(path: Path) -> bool:
    """Vrai si le 3MF est un fichier TRANCHÉ (G-code) exporté par un slicer, pas un
    modèle à préparer. Cas Bambu Studio « Exporter le fichier tranché du plateau »
    → « …gcode.3mf » contenant « Metadata/plate_N.gcode ». Détecté par le nom
    (.gcode.3mf) OU par la présence d'un G-code de plateau dans l'archive."""
    if path.name.lower().endswith(".gcode.3mf"):
        return True
    try:
        with zipfile.ZipFile(path) as zf:
            for n in zf.namelist():
                nl = n.lower().replace("\\", "/")
                # G-code de plateau (sliced) — n'existe PAS dans un modèle/projet normal
                if nl.startswith("metadata/plate_") and nl.endswith(".gcode"):
                    return True
    except Exception:
        pass
    return False


def load_stl(path: Path) -> "trimesh.Trimesh | ThreeMFData":
    """Charge, valide et normalise un fichier STL.

    Retourne un Trimesh centré sur l'origine, orienté avec Z vers le haut,
    posé sur le plan Z=0.
    """
    t0 = time.perf_counter()
    logger.info(f"Chargement STL : {path.name}")

    if not path.exists():
        raise STLLoadError(f"Fichier introuvable : {path.name}")
    if path.suffix.lower() not in (".stl", ".obj", ".3mf"):
        raise STLLoadError(f"Format non supporté : {path.suffix}")

    # Estimation avant chargement — adapte le niveau de traitement à la taille
    _is_stl  = path.suffix.lower() == ".stl"
    _is_3mf  = path.suffix.lower() == ".3mf"
    _file_sz = path.stat().st_size

    # STL : estimation exacte depuis la taille du fichier (50 octets/face)
    # 3MF : estimation grossière — 1 octet compressé ≈ 5 octets décompressés ≈ 1 face
    # Pour les fichiers > 200 MB, préférer process=False même pour les 3MF.
    _estimated_faces = _estimate_stl_faces(path) if _is_stl else int(_file_sz * 5 / 50) if _is_3mf else 0
    _skip_process    = _estimated_faces > _FACE_SKIP_PROCESS
    _skip_fill_holes = _estimated_faces > _FACE_SKIP_FILL_HOLES

    # Seuil de fichier 3MF très grand : >50 MB → forcer process=False indépendamment de l'estimation
    _3mf_large = _is_3mf and _file_sz > 50 * 1024 * 1024  # 50 MB
    if _3mf_large:
        _skip_process = True
        _skip_fill_holes = True

    if _skip_process:
        logger.info(
            f"Mesh très grand (~{_estimated_faces:,} faces estimées, {_file_sz//1024//1024}MB) — "
            "chargement rapide sans réparations (process=False)."
        )
    elif _skip_fill_holes:
        logger.info(
            f"Mesh large (~{_estimated_faces:,} faces estimées) — "
            "fill_holes désactivé."
        )

    if _is_3mf:
        # Fichier TRANCHÉ (G-code) exporté depuis un slicer : ce n'est pas un modèle
        # à préparer. On refuse tôt avec un message clair (sinon chargement infini /
        # géométrie de charabia — cas remonté par un testeur avec « …gcode.3mf »).
        if _is_sliced_3mf(path):
            raise STLLoadError(
                "Ce fichier est un fichier TRANCHÉ (G-code), pas un modèle 3D.\n\n"
                "Il a été créé par « Exporter le fichier tranché du plateau » dans "
                "Bambu Studio. neoSlice a besoin du MODÈLE à préparer, pas du fichier "
                "déjà tranché.\n\n"
                "Dans Bambu Studio : faites un CLIC DROIT sur l'objet puis "
                "« Convertir en un seul STL », et chargez ce fichier STL dans neoSlice."
            )
        # Charger avec process=False si fichier très grand (évite le crash mémoire sur 40M faces)
        _load_kwargs = {"process": False} if _skip_process else {}
        # Motif Bambu « split-model » (composants → .model externe) : trimesh relit
        # le .model UNE FOIS PAR COMPOSANT → hang sur les gros assemblages
        # (ex. « Cover Fan Aux.3mf », 73 composants × 17 MB). On charge nous-mêmes ;
        # None = motif absent/peu coûteux → chemin trimesh normal inchangé.
        raw = None
        try:
            raw = _fast_load_split_3mf(path)
        except Exception as _fe:
            logger.warning(f"[3MF] _fast_load_split_3mf a levé ({_fe!r}) — repli trimesh")
            raw = None
        try:
            if raw is None:
                raw = trimesh.load(str(path), **_load_kwargs)
        except Exception as _le:
            # Certains 3MF (Bambu .gcode.3mf, graphe de scène incomplet) font échouer
            # le chargement en Scene par trimesh — typiquement KeyError 'world'. On
            # se rabat alors sur un chargement en MAILLAGE UNIQUE (force=mesh), qui
            # ignore le graphe de scène et récupère quand même la géométrie.
            logger.warning(f"Chargement 3MF en Scene échoué ({_le!r}) — repli force=mesh")
            raw = trimesh.load(str(path), force="mesh", **_load_kwargs)
        # Tentative de parse multi-objets avant la fusion (protégée : un graphe de
        # scène cassé ne doit pas faire échouer TOUT le chargement).
        if isinstance(raw, trimesh.Scene) and len(raw.geometry) >= 1:
            try:
                threemf = _parse_threemf_multiobject(path, raw)
            except Exception as _pe:
                logger.warning(f"Parse 3MF multi-objets échoué ({_pe!r}) — fusion standard")
                threemf = None
            if threemf is not None:
                logger.info(f"3MF multi-objets chargé : {threemf.summary()}")
                return threemf
    elif _skip_process:
        # process=False seulement pour les très grands meshes (> 1M faces) :
        # évite merge_vertices sur 10M+ vertices (prend des minutes).
        raw = trimesh.load(str(path), force="mesh", process=False)
    else:
        raw = trimesh.load(str(path), force="mesh")

    # Si la scène contient des objets, dump() applique TOUS les transforms de scene.graph
    # (scale, rotation, translation). Critique pour les 3MF avec scale matrix (ex: toupie ×0.1).
    # Sans ça, les objets sont exportés à la mauvaise taille.
    if isinstance(raw, trimesh.Scene):
        try:
            dumped = raw.dump(concatenate=True)
            if isinstance(dumped, trimesh.Trimesh) and len(dumped.faces) > 0:
                mesh = dumped
                logger.info(f"Scene 3MF dumpée avec transforms ({len(raw.geometry)} géom(s)).")
            else:
                raise ValueError("dump() vide")
        except Exception as _de:
            logger.warning(f"Scene dump() échoué ({_de}) — fallback géométrie brute")
            meshes = [g for g in raw.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                raise STLLoadError("Aucun mesh valide trouvé dans le fichier.")
            mesh = trimesh.util.concatenate(meshes)
    elif isinstance(raw, trimesh.Trimesh):
        mesh = raw
    else:
        raise STLLoadError("Format de fichier non reconnu.")

    if len(mesh.faces) == 0:
        raise STLLoadError("Le mesh est vide (aucune face).")

    if not _skip_process:
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fix_winding(mesh)
        if not _skip_fill_holes and not mesh.is_watertight:
            logger.info("Mesh non-watertight — réparation automatique...")
            trimesh.repair.fill_holes(mesh)
        mesh.merge_vertices(merge_tex=False)
        unique_mask = trimesh.triangles.area(mesh.triangles) > 1e-10
        if not unique_mask.all():
            mesh.update_faces(unique_mask)
            logger.info(f"Faces dégénérées supprimées : {(~unique_mask).sum()}")

    if len(mesh.faces) == 0:
        raise STLLoadError("Le mesh est vide après réparation (aucune face valide).")

    # ── Limite de faces pour éviter le crash mémoire/RAM ──────────────────────
    # Un STL de 40M faces non-mergés occupe ~3.6 GB de RAM (120M vertices).
    # Au-dessus de 15M faces : décimer à 2M faces pour rendre le fichier utilisable.
    # La géométrie reste fidèle pour l'analyse ; l'export utilise toujours le mesh d'origine.
    _MAX_FACES_RENDER = 15_000_000
    if len(mesh.faces) > _MAX_FACES_RENDER:
        _orig_count = len(mesh.faces)
        try:
            import trimesh.simplify as _simp
            # Décimation à 2M faces — conserve la forme générale
            mesh = mesh.simplify_quadric_decimation(face_count=2_000_000)
            logger.warning(
                f"Mesh ultra-dense ({_orig_count:,} faces) décimé à "
                f"{len(mesh.faces):,} faces pour l'analyse et le rendu. "
                "La géométrie reste précise pour l'export."
            )
        except Exception as _se:
            logger.warning(f"Décimation échouée ({_se}) — mesh utilisé tel quel ({_orig_count:,} faces)")

    # ── Détection et correction des unités ──────────────────────────────────
    # STL n'encode pas les unités, mais la VASTE majorité des STL sont déjà en mm.
    # RÈGLE : on ne convertit QUE si la taille est implausible en mm (trop petite
    # pour être une vraie pièce → probablement exportée en mètres/cm/pouces).
    # Une pièce déjà dans une plage normale (≥ 1 mm) n'est JAMAIS touchée.
    #
    # ⚠️ NE PAS revenir à l'ancienne logique qui testait les conversions sans
    # vérifier d'abord la taille actuelle : elle gonflait ×10 une pièce de 40 mm
    # parfaitement valide (40 × 10 = 400, qui tombait dans la plage cible).
    _max_extent = float(mesh.bounding_box.extents.max())
    _PLAUSIBLE_MIN, _PLAUSIBLE_MAX = 1.0, 600.0
    if _max_extent < _PLAUSIBLE_MIN:
        # Taille absurde en mm → tenter une conversion d'unité (mètres en priorité).
        for _factor, _unit in [
            (1000.0, "mètres"),      # 0.04 → 40 mm (Fusion 360, FreeCAD)
            (100.0,  "décimètres"),
            (25.4,   "pouces"),
            (10.0,   "centimètres"),
        ]:
            _scaled = _max_extent * _factor
            if _PLAUSIBLE_MIN <= _scaled <= _PLAUSIBLE_MAX:
                mesh.apply_scale(_factor)
                logger.warning(
                    f"STL en {_unit} détecté (max extent = {_max_extent:.4f}) — "
                    f"converti en mm (×{_factor} → {_scaled:.1f} mm)."
                )
                break
    elif _max_extent > _PLAUSIBLE_MAX:
        logger.warning(
            f"Pièce très grande détectée (max extent = {_max_extent:.1f} mm). "
            f"Vérifiez l'unité d'export du STL."
        )

    # Normalisation : poser sur Z=0, centrer sur XY
    mesh.apply_translation(-mesh.bounds[0])               # coin min → origine
    center_xy = [(mesh.bounds[1][0]) / 2, (mesh.bounds[1][1]) / 2, 0]
    mesh.apply_translation([-center_xy[0], -center_xy[1], 0])

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        f"STL chargé en {elapsed:.1f}ms — "
        f"{len(mesh.vertices)} vertices, {len(mesh.faces)} faces, "
        f"watertight={mesh.is_watertight}"
    )
    return mesh


def mesh_info(mesh: trimesh.Trimesh) -> dict:
    """Retourne un dict de métadonnées rapides sur le mesh."""
    bb = mesh.bounding_box.extents
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "bounding_box_mm": bb.tolist(),
        "volume_cm3": abs(mesh.volume) / 1000,
        "surface_area_cm2": mesh.area / 100,
        "is_watertight": mesh.is_watertight,
    }
