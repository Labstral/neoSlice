"""Générateur de 3MF **UltiMaker Cura** (projet ouvrable, réglages appliqués).

Cura structure ses profils TRÈS différemment de la famille Bambu/Orca et de
PrusaSlicer : pas de gros JSON/INI unique, mais une pile de CONTENEURS (machine
globale + un conteneur par extrudeur), chacun un fichier INI séparé dans
« Cura/<id>.<suffixe> » à l'intérieur du 3MF. La géométrie est un 3MF standard
(sans extension "production" p:UUID — Cura ne l'utilise pas).

Format reconstitué depuis le CODE SOURCE du lecteur installé
(plugins/3MFReader/ThreeMFWorkspaceReader.py) — exigences DURES vérifiées :
  1. preRead exige EXACTEMENT UN « Cura/<id>.def.json » de type machine dans
     l'archive (sinon : « pas un projet », import mesh silencieux — vécu) ;
  2. tout variant/matériau/quality_changes référencé par une pile et non
     « empty » DOIT être présent dans l'archive (sinon KeyError) ;
  3. le matériau passe par le .xml.fdm_material embarqué (reverse map id→racine) ;
  4. les réglages voyagent dans des conteneurs quality_changes nommés (le
     lecteur les RECRÉE et copie leurs [values] — lignes 88-109 de
     _processQualityChanges) ; leur metadata quality_type pilote la résolution
     du profil de base via ContainerTree ;
  5. Cura/preferences.cfg doit être en version 7 (Preferences.Version) ;
  6. ordre des conteneurs des piles : 0=user, 1=quality_changes, 2=intent,
     3=quality, 4=material, 5=variant, 6=definition_changes, 7=definition
     (cura/Settings/CuraContainerStack._ContainerIndexes).

Données machine : data/cura_printers.json + data/cura_materials.json (extraits
des ressources officielles — tools/extract_cura_printers.py).
"""
from __future__ import annotations

import configparser
import json
import urllib.parse
import uuid
import zipfile
from datetime import date
from io import StringIO
from pathlib import Path

import trimesh
from loguru import logger

from core.parameters.print_config import PrintConfig

_NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_NS_CURA = "http://software.ultimaker.com/xml/cura/3mf/2015/10"
_DATA = Path(__file__).resolve().parent.parent.parent / "data"
_SETTING_VERSION = "22"          # Cura 5.6

# Réglages visibles par défaut (liste standard Cura — relevée d'une install réelle)
_VISIBLE_SETTINGS = (
    "layer_height;line_width;wall_thickness;wall_line_count;top_bottom_thickness;"
    "top_layers;bottom_layers;infill_sparse_density;infill_pattern;"
    "material_print_temperature;material_bed_temperature;speed_print;speed_wall_0;"
    "speed_wall_x;speed_infill;speed_topbottom;retraction_enable;cool_fan_enabled;"
    "cool_fan_speed;support_enable;support_structure;support_angle;adhesion_type;"
    "brim_width;prime_tower_enable"
)

# TOUTES les valeurs vont dans le quality_changes GLOBAL : le lecteur Cura
# re-dispatche lui-même chaque clé (globale → conteneur global, par-extrudeur →
# conteneur extrudeur 0) avec SA résolution settable_per_extruder
# (_processQualityChanges lignes 989-993) — chemin historique des vieux profils
# mono-extrudeur, bien plus fiable que notre propre répartition (l'infill 80 %
# posé dans le qc par-extrudeur n'était pas appliqué chez le testeur).

_FILL_PATTERN = {
    "grid": "grid", "gyroid": "gyroid", "honeycomb": "cross", "cubic": "cubic",
    "adaptivecubic": "cubicsubdiv", "lightning": "lightning", "zig-zag": "zigzag",
}
_SUPPORT_PATTERN = {"rectilinear": "zigzag", "concentric": "concentric",
                    "auto": "zigzag"}
_ADHESION = {"no_brim": "skirt", "outer_only": "brim", "inner_only": "brim",
            "outer_and_inner": "brim"}
_SEAM = {"aligned": "sharpest_corner", "nearest": "shortest",
         "random": "random", "back": "back"}

# neoSlice filament (base matériau) -> id racine matériau générique Cura.
_MATERIAL_MAP = {
    "PLA": "generic_pla", "PETG": "generic_petg", "ABS": "generic_abs",
    "ASA": "generic_asa", "TPU": "generic_tpu", "PC": "generic_pc",
    "PA": "generic_nylon", "NYLON": "generic_nylon", "PVA": "generic_pva",
    "HIPS": "generic_hips", "CPE": "generic_cpe",
}


def _q(name: str) -> str:
    """Nom de fichier d'un conteneur : id URL-quoté (convention Cura réelle,
    ex. « UltiMaker+S5.global.cfg » pour l'id « UltiMaker S5 »)."""
    return urllib.parse.quote_plus(name)


def _b(v: bool) -> str:
    return "True" if v else "False"


import functools


@functools.lru_cache(maxsize=1)
def _materials() -> dict:
    try:
        return json.loads((_DATA / "cura_materials.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _config_to_cura(config: PrintConfig, filament_name: str = "") -> dict:
    """PrintConfig neoSlice -> {clé Cura: valeur str}."""
    o: dict[str, str] = {}

    o["layer_height"] = f"{config.layer_height}"
    o["layer_height_0"] = f"{config.first_layer_height}"
    o["wall_line_count"] = f"{config.wall_loops}"
    o["top_layers"] = f"{config.top_shell_layers}"
    o["bottom_layers"] = f"{config.bottom_shell_layers}"

    o["infill_sparse_density"] = f"{config.infill_density}"
    o["infill_pattern"] = _FILL_PATTERN.get(config.infill_pattern, "grid")

    o["speed_wall_0"] = f"{config.outer_wall_speed}"
    o["speed_wall_x"] = f"{config.inner_wall_speed}"
    o["speed_infill"] = f"{config.infill_speed}"
    o["speed_topbottom"] = f"{config.top_surface_speed}"
    o["speed_layer_0"] = f"{config.first_layer_speed}"
    o["speed_print"] = f"{config.inner_wall_speed}"

    o["material_print_temperature"] = f"{config.nozzle_temperature}"
    o["material_print_temperature_layer_0"] = f"{config.nozzle_temperature}"
    o["material_bed_temperature"] = f"{config.bed_temperature}"
    o["material_bed_temperature_layer_0"] = f"{config.bed_temperature}"

    # Ventilation — suit le MATÉRIAU (un ABS/PA plein ventilateur délamine).
    try:
        from data.filaments import FILAMENTS
        fil = FILAMENTS.get(filament_name, {})
    except Exception:
        fil = {}
    if fil:
        o["cool_fan_enabled"] = _b(bool(fil.get("ventilation_active", True)))
        o["cool_fan_speed_max"] = f"{int(fil.get('ventilateur_max', 100))}"
        o["cool_fan_speed_min"] = f"{int(fil.get('ventilateur_seuil_mini', 35))}"
        o["cool_fan_speed_0"] = "0" if int(fil.get("ventilateur_1ere_couche", 0)) == 0 else \
            f"{int(fil.get('ventilateur_seuil_mini', 35))}"

    has_support = config.support_type != "none"
    o["support_enable"] = _b(has_support)
    o["support_structure"] = "tree" if config.support_type.startswith("tree") else "normal"
    o["support_angle"] = f"{90 - int(config.support_threshold_angle)}"
    o["support_z_distance"] = f"{config.support_top_z_distance}"
    o["support_top_distance"] = f"{config.support_top_z_distance}"
    o["support_bottom_distance"] = f"{config.support_bottom_z_distance}"
    o["support_xy_distance"] = f"{config.support_object_xy_distance}"
    o["support_pattern"] = _SUPPORT_PATTERN.get(config.support_interface_pattern, "zigzag")

    o["adhesion_type"] = _ADHESION.get(config.brim_type, "skirt")
    if config.brim_type != "no_brim":
        o["brim_width"] = f"{max(2.0, config.brim_width)}"

    o["z_seam_type"] = _SEAM.get(config.seam_position, "sharpest_corner")
    o["retraction_enable"] = _b(True)
    o["material_flow"] = f"{config.bridge_flow * 100:.0f}"
    return o


def _write_ini(cp: configparser.ConfigParser) -> str:
    buf = StringIO()
    cp.write(buf)
    return buf.getvalue()


def _container_ini(cid: str, name: str, definition: str, ctype: str,
                   extra_meta: dict, values: dict) -> str:
    cp = configparser.ConfigParser(interpolation=None)
    cp.add_section("general")
    cp.set("general", "version", "4")
    cp.set("general", "name", name)
    cp.set("general", "definition", definition)
    cp.add_section("metadata")
    cp.set("metadata", "type", ctype)
    cp.set("metadata", "setting_version", _SETTING_VERSION)
    for k, v in extra_meta.items():
        cp.set("metadata", k, str(v))
    cp.add_section("values")
    for k, v in values.items():
        cp.set("values", k, str(v))
    return _write_ini(cp)


def _stack_ini(cid: str, name: str, stype: str, containers: list[str],
               extra_meta: dict) -> str:
    cp = configparser.ConfigParser(interpolation=None)
    cp.add_section("general")
    cp.set("general", "version", "6")
    cp.set("general", "name", name)
    cp.set("general", "id", cid)
    cp.add_section("metadata")
    cp.set("metadata", "setting_version", _SETTING_VERSION)
    cp.set("metadata", "type", stype)
    for k, v in extra_meta.items():
        cp.set("metadata", k, str(v))
    cp.add_section("containers")
    for i, c in enumerate(containers):
        cp.set("containers", str(i), c)
    return _write_ini(cp)


def _machine_def_json(machine: dict, machine_id: str, display_name: str) -> str:
    """def.json machine embarqué — l'ORIGINAL complet (extrait des ressources
    Cura, comme le fait le writer officiel). Repli minimal si absent du
    catalogue (le registre de l'utilisateur fournit de toute façon la vraie
    définition pour nos machines)."""
    raw = machine.get("def_raw", "")
    if raw:
        return raw
    return json.dumps({
        "name": display_name,
        "version": 2,
        "inherits": "fdmprinter",
        "metadata": {"type": "machine", "visible": True},
        "settings": {},
    }, indent=1)


def _extruder_def_json(ext_def_id: str) -> str:
    from data.printers import cura_extruder_def_raw
    raw = cura_extruder_def_raw(ext_def_id)
    if raw:
        return raw
    return json.dumps({
        "name": "Extruder",
        "version": 2,
        "inherits": "fdmextruder",
        "metadata": {"type": "extruder", "visible": False},
        "settings": {},
    }, indent=1)


def _pick_material(filament_name: str, machine: dict) -> str | None:
    """Id racine du matériau générique Cura pour le filament neoSlice, adapté au
    diamètre machine (variantes _175). None -> empty_material."""
    if not machine.get("has_materials", True):
        return None
    try:
        from data.filaments import base_materiau
        base = (base_materiau(filament_name) or "PLA").upper()
    except Exception:
        base = "PLA"
    root = _MATERIAL_MAP.get(base, "generic_pla")
    mats = _materials()
    if float(machine.get("material_diameter", 2.85)) < 2.0:
        for cand in (f"{root}_175", "generic_pla_175"):
            if cand in mats:
                return cand
    if root in mats:
        return root
    preferred = machine.get("preferred_material", "generic_pla")
    return preferred if preferred in mats else None


class CuraThreeMFBuilder:
    """Génère un .3MF UltiMaker Cura valide (projet machine + réglages neoSlice)."""

    def build(
        self,
        mesh: trimesh.Trimesh,
        config: PrintConfig,
        output_path: Path,
        object_name: str = "neoSlice_Object",
        printer_ui_name: str = "creality_ender3",
        filament_ui_name: str = "PLA",
        nozzle_diameter_mm: float = 0.4,
    ) -> Path:
        from data.printers import cura_machine_for, is_cura_model
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not is_cura_model(printer_ui_name):
            # PAS de repli silencieux : c'était la cause d'un 3MF centré pour la
            # mauvaise machine (Ender-3 235×235 affiché sur un plateau S5). Mieux
            # vaut une erreur claire dans la barre de statut que ce piège.
            raise ValueError(
                f"« {printer_ui_name} » n'est pas une imprimante du catalogue Cura — "
                "re-sélectionnez votre imprimante à l'étape ① (mode UltiMaker Cura) "
                "puis validez avant d'exporter.")
        machine_id = printer_ui_name
        machine = cura_machine_for(machine_id) or {}
        display_name = machine.get("name", machine_id)
        width = float(machine.get("width", 200.0))
        depth = float(machine.get("depth", 200.0))
        n_ext = max(1, int(machine.get("extruder_count", 1)))
        extruder_defs = machine.get("extruder_defs") or [f"{machine_id}_extruder_0"]
        quality_def = machine.get("quality_definition", machine_id)
        quality_type = machine.get("preferred_quality_type", "normal")

        # Variant réel pour la buse choisie (repli : buse la plus proche, sinon empty)
        variants = machine.get("variants", {}) or {}
        variant = None
        if variants:
            key = f"{float(nozzle_diameter_mm):g}"
            if key not in variants:
                key = min(variants, key=lambda k: abs(float(k) - float(nozzle_diameter_mm)))
            variant = variants[key]
        material_id = _pick_material(filament_ui_name, machine)

        overrides = _config_to_cura(config, filament_ui_name)

        # Centrage plateau (repère coin 3MF ; le lecteur Cura re-décale de -W/2,-D/2
        # et ajoute le centre du mesh — équation vérifiée sur les décalages observés).
        bb = mesh.bounds
        tx = width / 2 - (bb[0][0] + bb[1][0]) / 2
        ty = depth / 2 - (bb[0][1] + bb[1][1]) / 2
        tz = -bb[0][2]

        N = display_name                                # nom d'instance machine
        # Nom de profil PAR MACHINE : un nom statique (« neoSlice ») réutilisé sur
        # une AUTRE machine ferait, en stratégie « override », re-remplir les
        # conteneurs existants liés à l'ancienne quality_definition → groupe
        # introuvable dans l'arbre de la machine courante → réglages PERDUS.
        qc_name = f"neoSlice {display_name}"
        qc_global_id = "neoSlice_qc_global"
        tmp = output_path.with_suffix(".3mf.tmp")
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", self._content_types())
                zf.writestr("_rels/.rels", self._rels())
                zf.writestr("3D/3dmodel.model",
                           self._model_xml(mesh, tx, ty, tz, object_name))

                # ── définitions (exigence dure : 1 def machine dans l'archive) ──
                zf.writestr(f"Cura/{_q(machine_id)}.def.json",
                           _machine_def_json(machine, machine_id, display_name))
                for ed in dict.fromkeys(extruder_defs[:n_ext]):
                    zf.writestr(f"Cura/{_q(ed)}.def.json", _extruder_def_json(ed))
                zf.writestr("Cura/packages.json", '{"packages": []}')

                # ── variant + matériau embarqués (exigés si référencés) ────────
                if variant is not None:
                    zf.writestr(f"Cura/{_q(variant['id'])}.inst.cfg", variant["cfg"])
                if material_id is not None:
                    zf.writestr(f"Cura/{_q(material_id)}.xml.fdm_material",
                               _materials()[material_id])

                # ── quality_changes (portent TOUS nos réglages, cf. dispatch) ──
                zf.writestr(f"Cura/{_q(qc_global_id)}.inst.cfg", _container_ini(
                    qc_global_id, qc_name, quality_def, "quality_changes",
                    {"quality_type": quality_type}, overrides))

                # ── pile GLOBALE ───────────────────────────────────────────────
                settings_id = f"{N}_settings"
                user_id = f"{N}_user"
                dc_vals = {"extruders_enabled_count": str(n_ext)} if n_ext > 1 else {}
                zf.writestr(f"Cura/{_q(settings_id)}.inst.cfg", _container_ini(
                    settings_id, settings_id, machine_id, "definition_changes", {}, dc_vals))
                zf.writestr(f"Cura/{_q(user_id)}.inst.cfg", _container_ini(
                    user_id, user_id, machine_id, "user", {"machine": N}, {}))
                zf.writestr(f"Cura/{_q(N)}.global.cfg", _stack_ini(
                    N, N, "machine",
                    [user_id, qc_global_id, "empty_intent", "empty_quality",
                     "empty_material", "empty_variant", settings_id, machine_id],
                    {"group_id": str(uuid.uuid4())}))

                # ── pile(s) EXTRUDEUR ──────────────────────────────────────────
                for i in range(n_ext):
                    ext_def = extruder_defs[i] if i < len(extruder_defs) else f"{machine_id}_extruder_{i}"
                    sid = f"{N}_extruder_{i}"
                    e_settings = f"{sid}_settings"
                    e_user = f"{sid}_user"
                    qc_ext_id = f"neoSlice_qc_ext_{i}"
                    e_dc_vals: dict = {}
                    if variant is None and i == 0:
                        e_dc_vals["machine_nozzle_size"] = f"{nozzle_diameter_mm}"
                    # [values] VIDES : les réglages sont TOUS dans le qc global,
                    # le lecteur les dispatche lui-même vers l'extrudeur 0
                    # (_processQualityChanges 989-993, settable_per_extruder).
                    zf.writestr(f"Cura/{_q(qc_ext_id)}.inst.cfg", _container_ini(
                        qc_ext_id, qc_name, quality_def, "quality_changes",
                        {"quality_type": quality_type, "position": str(i),
                         "intent_category": "default"}, {}))
                    zf.writestr(f"Cura/{_q(e_settings)}.inst.cfg", _container_ini(
                        e_settings, e_settings, ext_def, "definition_changes", {}, e_dc_vals))
                    zf.writestr(f"Cura/{_q(e_user)}.inst.cfg", _container_ini(
                        e_user, e_user, machine_id, "user", {"extruder": sid}, {}))
                    zf.writestr(f"Cura/{_q(sid)}.extruder.cfg", _stack_ini(
                        sid, f"Extruder {i + 1}", "extruder_train",
                        [e_user, qc_ext_id, "empty_intent", "empty_quality",
                         material_id or "empty_material",
                         (variant["id"] if variant else "empty_variant"),
                         e_settings, ext_def],
                        {"position": str(i), "machine": N}))

                zf.writestr("Cura/preferences.cfg", self._preferences())
                zf.writestr("Cura/version.ini", self._version_ini())
            tmp.replace(output_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        logger.info(f"3MF Cura généré → {output_path} "
                   f"({output_path.stat().st_size // 1024} KB, machine={machine_id}, "
                   f"variant={variant['id'] if variant else '-'}, matériau={material_id or '-'})")
        return output_path

    # ── Pièces 3MF standard (géométrie) ─────────────────────────────────────
    @staticmethod
    def _content_types() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
            '</Types>'
        )

    @staticmethod
    def _rels() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>'
        )

    @staticmethod
    def _model_xml(mesh: trimesh.Trimesh, tx: float, ty: float, tz: float,
                   title: str) -> str:
        today = date.today().isoformat()
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<model unit="millimeter" xml:lang="en-US" xmlns="{_NS_3MF}" '
            f'xmlns:cura="{_NS_CURA}">',
            ' <metadata name="Application">neoSlice</metadata>',
            f' <metadata name="CreationDate">{today}</metadata>',
            f' <metadata name="ModificationDate">{today}</metadata>',
            f' <metadata name="Title">{title}</metadata>',
            ' <resources>',
            '  <object id="1" type="model">',
            '   <mesh>',
            '    <vertices>',
        ]
        for v in mesh.vertices:
            out.append(f'     <vertex x="{v[0]:.6g}" y="{v[1]:.6g}" z="{v[2]:.6g}"/>')
        out.append('    </vertices>')
        out.append('    <triangles>')
        for f in mesh.faces:
            out.append(f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>')
        out.append('    </triangles>')
        out.append('   </mesh>')
        out.append('  </object>')
        out.append(' </resources>')
        out.append(' <build>')
        out.append(f'  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 '
                   f'{tx:.4f} {ty:.4f} {tz:.4f}" printable="1"/>')
        out.append(' </build>')
        out.append('</model>')
        return "\n".join(out)

    # ── Pièces « projet » Cura ───────────────────────────────────────────────
    @staticmethod
    def _preferences() -> str:
        """Cura/preferences.cfg — version 7 OBLIGATOIRE (Preferences.Version ;
        v6 était silencieusement rejeté) + les 4 clés que le writer officiel copie."""
        cp = configparser.ConfigParser(interpolation=None)
        cp.add_section("general")
        cp.set("general", "version", "7")
        cp.set("general", "visible_settings", _VISIBLE_SETTINGS)
        cp.add_section("cura")
        cp.set("cura", "active_mode", "1")
        cp.set("cura", "categories_expanded", "")
        cp.add_section("metadata")
        cp.set("metadata", "setting_version", _SETTING_VERSION)
        return _write_ini(cp)

    @staticmethod
    def _version_ini() -> str:
        cp = configparser.ConfigParser(interpolation=None)
        cp.add_section("versions")
        cp.set("versions", "cura_version", "5.6.0")
        cp.set("versions", "build_type", "")
        cp.set("versions", "is_debug_mode", "False")
        return _write_ini(cp)
