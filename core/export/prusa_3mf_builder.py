"""Générateur de 3MF **PrusaSlicer** (projet ouvrable avec réglages appliqués).

Contrairement au 3MF Bambu/Orca (project_settings.config = JSON), PrusaSlicer
stocke la config dans `Metadata/Slic3r_PE.config` au format `; clé = valeur`, plus
`Metadata/Slic3r_PE_model.config` (XML par objet). La géométrie est un 3MF standard
avec le namespace slic3rpe.

On part de la config par défaut complète de PrusaSlicer (data/prusa_base_config.json,
341 clés → 3MF toujours valide) et on override les clés pilotées par neoSlice +
l'identité machine issue du catalogue Prusa (data/prusa_printers.json).
"""
from __future__ import annotations
import json
import zipfile
from datetime import date
from pathlib import Path

import trimesh
from loguru import logger

from core.parameters.print_config import PrintConfig

_DATA = Path(__file__).resolve().parent.parent.parent / "data"


def _load_json(name: str) -> dict:
    try:
        return json.loads((_DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Tables de correspondance neoSlice → PrusaSlicer ────────────────────────────
_FILL_PATTERN = {
    "grid": "grid", "gyroid": "gyroid", "honeycomb": "honeycomb",
    "cubic": "cubic", "adaptivecubic": "adaptivecubic", "lightning": "lightning",
}
_TOP_PATTERN = {
    "monotonicline": "monotoniclines", "monotonic": "monotonic",
    "rectilinear": "rectilinear", "concentric": "concentric",
}
_SEAM = {"aligned": "aligned", "nearest": "nearest", "random": "random", "back": "rear"}
_BRIM = {"no_brim": "no_brim", "outer_only": "outer_only",
         "inner_only": "inner_only", "outer_and_inner": "outer_and_inner"}


def _config_to_prusa(config: PrintConfig, printer: dict, nozzle_mm: float,
                     filament_name: str = "") -> dict:
    """Construit les overrides PrusaSlicer depuis un PrintConfig + l'imprimante cible."""
    o: dict[str, str] = {}

    # Couches / structure
    o["layer_height"] = f"{config.layer_height}"
    o["first_layer_height"] = f"{config.first_layer_height}"
    o["perimeters"] = f"{config.wall_loops}"
    o["top_solid_layers"] = f"{config.top_shell_layers}"
    o["bottom_solid_layers"] = f"{config.bottom_shell_layers}"

    # Remplissage
    o["fill_density"] = f"{config.infill_density}%"
    o["fill_pattern"] = _FILL_PATTERN.get(config.infill_pattern, "grid")
    _top = _TOP_PATTERN.get(config.top_surface_pattern, "monotonic")
    o["top_fill_pattern"] = _top
    o["bottom_fill_pattern"] = "monotonic" if _top == "monotonic" else "rectilinear"

    # Vitesses (mm/s)
    o["perimeter_speed"] = f"{config.inner_wall_speed}"
    o["external_perimeter_speed"] = f"{config.outer_wall_speed}"
    o["infill_speed"] = f"{config.infill_speed}"
    o["solid_infill_speed"] = f"{config.top_surface_speed}"
    o["top_solid_infill_speed"] = f"{config.top_surface_speed}"
    o["bridge_speed"] = f"{config.bridge_speed}"
    o["first_layer_speed"] = f"{config.first_layer_speed}"

    # Températures (côté "filament")
    o["temperature"] = f"{config.nozzle_temperature}"
    o["first_layer_temperature"] = f"{config.nozzle_temperature}"
    o["bed_temperature"] = f"{config.bed_temperature}"
    o["first_layer_bed_temperature"] = f"{config.bed_temperature}"

    # Ventilation — suit le MATÉRIAU (avant : celle du preset PLA du slicer ;
    # un PA/ABS refroidi plein ventilateur délamine entre couches)
    try:
        from data.filaments import FILAMENTS
        fil = FILAMENTS.get(filament_name, {})
    except Exception:
        fil = {}
    if fil:
        o["min_fan_speed"] = f"{int(fil.get('ventilateur_seuil_mini', 35))}"
        o["max_fan_speed"] = f"{int(fil.get('ventilateur_max', 100))}"
        o["bridge_fan_speed"] = f"{int(fil.get('ventilateur_surplombs', 100))}"
        o["disable_fan_first_layers"] = (
            "1" if int(fil.get("ventilateur_1ere_couche", 0)) == 0 else "0")
        o["fan_always_on"] = "1" if fil.get("ventilation_active", True) else "0"

    # Supports
    has_support = config.support_type != "none"
    o["support_material"] = "1" if has_support else "0"
    o["support_material_auto"] = "1" if has_support else "0"
    o["support_material_threshold"] = f"{int(config.support_threshold_angle)}"
    o["support_material_buildplate_only"] = "1" if config.support_on_build_plate_only else "0"
    o["support_material_style"] = "organic" if config.support_type.startswith("tree") else "snug"

    # Ponts / qualité
    o["bridge_flow_ratio"] = f"{config.bridge_flow}"
    o["seam_position"] = _SEAM.get(config.seam_position, "aligned")

    # Adhérence
    o["brim_type"] = _BRIM.get(config.brim_type, "no_brim")
    o["brim_width"] = f"{config.brim_width}"

    # Repassage (ironing)
    o["ironing"] = "1" if config.ironing_type not in ("no ironing", "", None) else "0"

    # ── Identité machine (catalogue Prusa) ───────────────────────────────────
    if printer:
        o["bed_shape"] = printer.get("bed_shape", o.get("bed_shape", ""))
        o["max_print_height"] = printer.get("max_print_height", o.get("max_print_height", ""))
        o["printer_model"] = printer.get("printer_model", "")
        o["printer_variant"] = printer.get("printer_variant", str(nozzle_mm))
        gf = printer.get("gcode_flavor")
        if gf:
            o["gcode_flavor"] = gf
    o["nozzle_diameter"] = f"{nozzle_mm}"

    return o


class PrusaThreeMFBuilder:
    """Génère un .3MF PrusaSlicer valide (projet avec réglages neoSlice)."""

    def build(
        self,
        mesh: trimesh.Trimesh,
        config: PrintConfig,
        output_path: Path,
        object_name: str = "neoSlice_Object",
        printer_ui_name: str = "Original Prusa MK4S 0.4 nozzle",
        filament_ui_name: str = "PLA",
        nozzle_diameter_mm: float = 0.4,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        prusa_cat = _load_json("prusa_printers.json")
        # printer_ui_name peut être un nom de preset exact OU un model_key (ex. 'MK4S')
        printer = prusa_cat.get(printer_ui_name, {})
        if not printer:
            from data.printers import prusa_preset_for
            resolved = prusa_preset_for(printer_ui_name, nozzle_diameter_mm)
            if resolved:
                printer = prusa_cat.get(resolved, {})
                printer_ui_name = resolved

        # Config = base complète (341 clés) + overrides neoSlice
        settings = _load_json("prusa_base_config.json")
        settings.update(_config_to_prusa(config, printer, nozzle_diameter_mm,
                                         filament_name=filament_ui_name))

        # Identité presets (PrusaSlicer fait correspondre à l'installé)
        settings["printer_settings_id"] = printer_ui_name
        _lh = f"{config.layer_height:.2f}"
        settings["print_settings_id"] = f"neoSlice {_lh}mm"
        deffil = printer.get("default_filament_profile") or "Generic PLA"
        settings["filament_settings_id"] = deffil

        # Centrage sur le plateau réel
        cx, cy = self._bed_center(printer)
        bb = mesh.bounds
        zc = -bb[0][2]                      # poser la base sur Z=0
        tx = cx - (bb[0][0] + bb[1][0]) / 2
        ty = cy - (bb[0][1] + bb[1][1]) / 2

        tmp = output_path.with_suffix(".3mf.tmp")
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", self._content_types())
                zf.writestr("_rels/.rels", self._rels())
                zf.writestr("3D/3dmodel.model",
                            self._model_xml(mesh, tx, ty, zc, object_name))
                zf.writestr("Metadata/Slic3r_PE_model.config",
                            self._model_config(len(mesh.faces), object_name))
                zf.writestr("Metadata/Slic3r_PE.config", self._print_config(settings))
            tmp.replace(output_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        logger.info(f"3MF PrusaSlicer généré → {output_path} "
                    f"({output_path.stat().st_size // 1024} KB, printer={printer_ui_name})")
        return output_path

    # ── Pièces ────────────────────────────────────────────────────────────────
    @staticmethod
    def _bed_center(printer: dict) -> tuple[float, float]:
        try:
            xs, ys = [], []
            for pt in printer.get("bed_shape", "").split(","):
                x, y = pt.split("x")
                xs.append(float(x)); ys.append(float(y))
            return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
        except Exception:
            return (125.0, 105.0)

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
            ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>'
        )

    @staticmethod
    def _model_xml(mesh: trimesh.Trimesh, tx: float, ty: float, tz: float,
                   title: str) -> str:
        today = date.today().isoformat()
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">',
            ' <metadata name="slic3rpe:Version3mf">1</metadata>',
            f' <metadata name="Title">{title}</metadata>',
            f' <metadata name="CreationDate">{today}</metadata>',
            f' <metadata name="ModificationDate">{today}</metadata>',
            ' <metadata name="Application">neoSlice</metadata>',
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

    @staticmethod
    def _model_config(face_count: int, name: str) -> str:
        last = max(0, face_count - 1)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<config>\n'
            ' <object id="1" instances_count="1">\n'
            f'  <metadata type="object" key="name" value="{name}"/>\n'
            f'  <volume firstid="0" lastid="{last}">\n'
            f'   <metadata type="volume" key="name" value="{name}"/>\n'
            '   <metadata type="volume" key="volume_type" value="ModelPart"/>\n'
            '   <metadata type="volume" key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            '  </volume>\n'
            ' </object>\n'
            '</config>'
        )

    @staticmethod
    def _print_config(settings: dict) -> str:
        """`Metadata/Slic3r_PE.config` : une ligne `; clé = valeur` par option (triées)."""
        lines = ["; generated by neoSlice"]
        for k in sorted(settings):
            v = settings[k]
            lines.append(f"; {k} = {v}")
        return "\n".join(lines) + "\n"
