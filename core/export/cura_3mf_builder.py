"""Générateur de 3MF **UltiMaker Cura** (projet ouvrable, réglages appliqués).

Cura structure ses profils TRÈS différemment de la famille Bambu/Orca et de
PrusaSlicer : pas de gros JSON/INI unique, mais une pile de CONTENEURS (machine
globale + un conteneur par extrudeur), chacun un fichier INI séparé dans
« Cura/<id>.<suffixe> » à l'intérieur du 3MF (`.global.cfg`, `.extruder.cfg`,
`.inst.cfg` pour les surcharges "definition_changes"/"user"). La géométrie,
elle, est un 3MF **standard** (aucune extension "production" p:UUID contrairement
à Bambu — Cura ne l'utilise pas).

Format entièrement reconstitué depuis :
  - le CODE SOURCE de Cura installé (plugins/3MFWriter, 3MFReader) ;
  - un VRAI profil machine généré par Cura (AppData/Roaming/cura/5.6/…) pour la
    structure exacte des conteneurs (ordre, noms de section, valeurs "True"/
    "False") ;
  - les définitions officielles (share/cura/resources/definitions/*.def.json)
    pour les dimensions/g-code/extrudeurs (voir tools/extract_cura_printers.py).

Stratégie robuste : les réglages neoSlice sont posés dans les conteneurs
« user » (priorité la PLUS HAUTE dans la pile Cura, gagne quel que soit le
profil qualité/matériau sélectionné) ; qualité/matériau/buse pointent vers les
sentinelles universelles de Cura (`empty_quality`/`empty_material`/
`empty_variant`, présentes dans TOUTE installation) plutôt que de deviner un ID
de profil précis par imprimante — sans jamais casser le chargement, et les
valeurs neoSlice s'appliquent de toute façon par-dessus.
"""
from __future__ import annotations

import configparser
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

# Clés GLOBALES (settable_per_extruder=False dans fdmprinter.def.json) : vivent
# dans le conteneur "user" de la pile MACHINE. Tout le reste va sur l'extrudeur.
_GLOBAL_KEYS = {
    "layer_height", "support_enable", "support_structure", "adhesion_type",
    "material_bed_temperature", "material_bed_temperature_layer_0",
}

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


def _b(v: bool) -> str:
    """Bool -> littéral tel que sérialisé par Cura ('True'/'False', pas '1'/'0')."""
    return "True" if v else "False"


def _config_to_cura(config: PrintConfig, filament_name: str = "") -> dict:
    """PrintConfig neoSlice -> {clé Cura: valeur str}, à répartir ensuite entre
    conteneur machine (clés globales) et conteneur extrudeur (le reste)."""
    o: dict[str, str] = {}

    # Couches / parois
    o["layer_height"] = f"{config.layer_height}"
    o["layer_height_0"] = f"{config.first_layer_height}"
    o["wall_line_count"] = f"{config.wall_loops}"
    o["top_layers"] = f"{config.top_shell_layers}"
    o["bottom_layers"] = f"{config.bottom_shell_layers}"

    # Remplissage
    o["infill_sparse_density"] = f"{config.infill_density}"
    o["infill_pattern"] = _FILL_PATTERN.get(config.infill_pattern, "grid")

    # Vitesses (mm/s)
    o["speed_wall_0"] = f"{config.outer_wall_speed}"
    o["speed_wall_x"] = f"{config.inner_wall_speed}"
    o["speed_infill"] = f"{config.infill_speed}"
    o["speed_topbottom"] = f"{config.top_surface_speed}"
    o["speed_layer_0"] = f"{config.first_layer_speed}"
    o["speed_print"] = f"{config.inner_wall_speed}"

    # Températures
    o["material_print_temperature"] = f"{config.nozzle_temperature}"
    o["material_print_temperature_layer_0"] = f"{config.nozzle_temperature}"
    o["material_bed_temperature"] = f"{config.bed_temperature}"
    o["material_bed_temperature_layer_0"] = f"{config.bed_temperature}"

    # Ventilation — suit le MATÉRIAU (comme pour PrusaSlicer : un ABS/PA plein
    # ventilateur délamine entre couches).
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

    # Supports
    has_support = config.support_type != "none"
    o["support_enable"] = _b(has_support)
    o["support_structure"] = "tree" if config.support_type.startswith("tree") else "normal"
    o["support_angle"] = f"{90 - int(config.support_threshold_angle)}"  # Cura = angle depuis la verticale
    o["support_infill_rate"] = "15"
    o["support_z_distance"] = f"{config.support_top_z_distance}"
    o["support_top_distance"] = f"{config.support_top_z_distance}"
    o["support_bottom_distance"] = f"{config.support_bottom_z_distance}"
    o["support_xy_distance"] = f"{config.support_object_xy_distance}"
    o["support_pattern"] = _SUPPORT_PATTERN.get(config.support_interface_pattern, "zigzag")

    # Adhérence
    o["adhesion_type"] = _ADHESION.get(config.brim_type, "skirt")
    if config.brim_type != "no_brim":
        o["brim_width"] = f"{max(2.0, config.brim_width)}"

    # Qualité / couture
    o["z_seam_type"] = _SEAM.get(config.seam_position, "sharpest_corner")
    o["retraction_enable"] = _b(True)
    o["material_flow"] = f"{config.bridge_flow * 100:.0f}"

    return o


def _split_global_extruder(overrides: dict) -> tuple[dict, dict]:
    """Répartit les clés entre conteneur MACHINE (globales) et EXTRUDEUR (reste) —
    voir fdmprinter.def.json settable_per_extruder=False pour la liste exacte."""
    glob, ext = {}, {}
    for k, v in overrides.items():
        (glob if k in _GLOBAL_KEYS else ext)[k] = v
    return glob, ext


def _write_ini(cp: configparser.ConfigParser) -> str:
    buf = StringIO()
    cp.write(buf)
    return buf.getvalue()


def _container_ini(name: str, definition: str, ctype: str, extra_meta: dict,
                   values: dict) -> str:
    cp = configparser.ConfigParser(interpolation=None)
    cp.add_section("general")
    cp.set("general", "version", "4")
    cp.set("general", "name", name)
    cp.set("general", "definition", definition)
    cp.add_section("metadata")
    cp.set("metadata", "type", ctype)
    cp.set("metadata", "setting_version", "22")
    for k, v in extra_meta.items():
        cp.set("metadata", k, str(v))
    cp.add_section("values")
    for k, v in values.items():
        cp.set("values", k, str(v))
    return _write_ini(cp)


class CuraThreeMFBuilder:
    """Génère un .3MF Cura valide (projet avec machine + réglages neoSlice)."""

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

        machine_id = printer_ui_name if is_cura_model(printer_ui_name) else "creality_ender3"
        machine = cura_machine_for(machine_id) or {}
        width = float(machine.get("width", 200.0))
        depth = float(machine.get("depth", 200.0))
        n_extruders = max(1, int(machine.get("extruder_count", 1)))
        extruder_defs = machine.get("extruder_defs") or [f"{machine_id}_extruder_0"]

        overrides = _config_to_cura(config, filament_ui_name)
        overrides["machine_nozzle_size"] = f"{nozzle_diameter_mm}"
        glob_vals, ext_vals = _split_global_extruder(overrides)
        if n_extruders > 1:
            glob_vals["extruders_enabled_count"] = str(n_extruders)

        # Centrage sur le plateau (repère coin, Z posé à 0 — convention 3MF que
        # le lecteur Cura re-décale lui-même vers son repère centré interne).
        bb = mesh.bounds
        tx = width / 2 - (bb[0][0] + bb[1][0]) / 2
        ty = depth / 2 - (bb[0][1] + bb[1][1]) / 2
        tz = -bb[0][2]

        tmp = output_path.with_suffix(".3mf.tmp")
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", self._content_types())
                zf.writestr("_rels/.rels", self._rels())
                zf.writestr("3D/3dmodel.model",
                           self._model_xml(mesh, tx, ty, tz, object_name))

                # ── conteneur MACHINE (pile globale) ────────────────────────
                machine_name = object_name  # nom d'instance = simple, unique au fichier
                settings_id = f"{machine_name}_settings"
                user_id = f"{machine_name}_user"
                zf.writestr(f"Cura/{settings_id}.inst.cfg", _container_ini(
                    settings_id, machine_id, "definition_changes", {}, {}))
                zf.writestr(f"Cura/{user_id}.inst.cfg", _container_ini(
                    user_id, machine_id, "user", {"machine": machine_name}, glob_vals))
                zf.writestr(f"Cura/{machine_name}.global.cfg", self._global_stack(
                    machine_name, machine_id, user_id, settings_id))

                # ── conteneur(s) EXTRUDEUR ──────────────────────────────────
                for i in range(n_extruders):
                    ext_def = extruder_defs[i] if i < len(extruder_defs) else f"{machine_id}_extruder_{i}"
                    ext_name = f"{machine_name}_extruder_{i}"
                    e_settings_id = f"{ext_name}_settings"
                    e_user_id = f"{ext_name}_user"
                    vals = ext_vals if i == 0 else {}   # une seule matière gérée -> extrudeur 0
                    zf.writestr(f"Cura/{e_settings_id}.inst.cfg", _container_ini(
                        e_settings_id, ext_def, "definition_changes", {}, {}))
                    zf.writestr(f"Cura/{e_user_id}.inst.cfg", _container_ini(
                        e_user_id, ext_def, "user", {"extruder": ext_name}, vals))
                    zf.writestr(f"Cura/{ext_name}.extruder.cfg", self._extruder_stack(
                        ext_name, ext_def, i, e_user_id, e_settings_id))

                zf.writestr("Cura/preferences.cfg", self._preferences())
                zf.writestr("Cura/version.ini", self._version_ini())
            tmp.replace(output_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        logger.info(f"3MF Cura généré → {output_path} "
                   f"({output_path.stat().st_size // 1024} KB, machine={machine_id})")
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

    # ── Pièces « projet » Cura (pile de conteneurs) ─────────────────────────
    @staticmethod
    def _global_stack(machine_name: str, machine_id: str, user_id: str,
                      settings_id: str) -> str:
        cp = configparser.ConfigParser(interpolation=None)
        cp.add_section("general")
        cp.set("general", "version", "6")
        cp.set("general", "name", machine_name)
        cp.set("general", "id", machine_name)
        cp.add_section("metadata")
        cp.set("metadata", "setting_version", "22")
        cp.set("metadata", "type", "machine")
        cp.set("metadata", "group_id", str(uuid.uuid4()))
        cp.add_section("containers")
        # ordre RÉEL constaté (priorité décroissante) : user > quality_changes >
        # intent > quality > material > variant > definition_changes > definition.
        cp.set("containers", "0", user_id)
        cp.set("containers", "1", "empty_quality_changes")
        cp.set("containers", "2", "empty_intent")
        cp.set("containers", "3", "empty_quality")
        cp.set("containers", "4", "empty_material")
        cp.set("containers", "5", "empty_variant")
        cp.set("containers", "6", settings_id)
        cp.set("containers", "7", machine_id)
        return _write_ini(cp)

    @staticmethod
    def _extruder_stack(ext_name: str, ext_def: str, position: int,
                        user_id: str, settings_id: str) -> str:
        cp = configparser.ConfigParser(interpolation=None)
        cp.add_section("general")
        cp.set("general", "version", "6")
        cp.set("general", "name", f"Extruder {position + 1}")
        cp.set("general", "id", ext_name)
        cp.add_section("metadata")
        cp.set("metadata", "setting_version", "22")
        cp.set("metadata", "type", "extruder_train")
        cp.set("metadata", "position", str(position))
        cp.set("metadata", "machine", ext_name.rsplit("_extruder_", 1)[0])
        cp.add_section("containers")
        cp.set("containers", "0", user_id)
        cp.set("containers", "1", "empty_quality_changes")
        cp.set("containers", "2", "empty_intent")
        cp.set("containers", "3", "empty_quality")
        cp.set("containers", "4", "empty_material")
        cp.set("containers", "5", "empty_variant")
        cp.set("containers", "6", settings_id)
        cp.set("containers", "7", ext_def)
        return _write_ini(cp)

    @staticmethod
    def _preferences() -> str:
        cp = configparser.ConfigParser(interpolation=None)
        cp.add_section("general")
        cp.set("general", "version", "6")
        cp.add_section("values")
        cp.set("values", "general/visible_settings", "")
        return _write_ini(cp)

    @staticmethod
    def _version_ini() -> str:
        cp = configparser.ConfigParser(interpolation=None)
        cp.add_section("versions")
        cp.set("versions", "cura_version", "5.6.0")
        cp.set("versions", "build_type", "")
        cp.set("versions", "is_debug_mode", "False")
        return _write_ini(cp)
