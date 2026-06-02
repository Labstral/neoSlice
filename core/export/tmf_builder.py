"""Génère des fichiers .3MF 100% compatibles Bambu Studio.

Stratégie :
  Bambu Studio valide 3 choses avant de charger les paramètres :
    1. metadata Application = "BambuStudio-XX.XX.XX.XX"
    2. Présence de Metadata/project_settings.config (~561 clés)
    3. Structure ZIP exacte (3D/Objects/, _rels/, slice_info.config…)

  On extrait project_settings.config d'un vrai .3mf Bambu Studio présent
  sur la machine (auto-détection), on override nos paramètres dedans,
  puis on reconstruit un ZIP avec la structure exacte attendue.
"""
from __future__ import annotations
import json
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import tempfile

import numpy as np
import trimesh
from loguru import logger

from ..parameters.print_config import PrintConfig

BAMBU_VERSION = "02.07.01.57"
_NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_NS_BBL = "http://schemas.bambulab.com/package/2021"
_NS_PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"

_TEMPLATE_CACHE: dict | None = None
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_CACHE_FILE = _DATA_DIR / "bambu_config_template.json"
_CLEAN_DEFAULTS_FILE = _DATA_DIR / "bambu_defaults_clean.json"


def _find_bambu_template() -> dict | None:
    """Retourne le config Bambu Studio complet (~560 clés).

    Priorité :
      1. Cache mémoire (session courante)
      2. Defaults hardcodés neoSlice (data/bambu_defaults_clean.json — source de vérité)
      3. Profils système Bambu Studio (fallback si fichier defaults absent)
      4. None → mode fallback minimal
    """
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE

    # 1. Defaults hardcodés — extraits d'un .3mf Bambu Studio 100% standard.
    #    Ces valeurs correspondent exactement aux defaults "0.20mm Standard @BBL X1C".
    #    Standard mode = ces valeurs + zéro override → Bambu Studio ne voit aucun changement.
    if _CLEAN_DEFAULTS_FILE.exists():
        try:
            _TEMPLATE_CACHE = json.loads(_CLEAN_DEFAULTS_FILE.read_text(encoding="utf-8"))
            logger.info(f"Template defaults neoSlice chargé ({len(_TEMPLATE_CACHE)} clés).")
            return _TEMPLATE_CACHE
        except Exception as e:
            logger.warning(f"Lecture defaults échouée : {e}")

    # 2. Profils système Bambu Studio (fallback si bambu_defaults_clean.json manquant)
    try:
        from .bambu_config_resolver import resolve_from_system_profiles
        resolved = resolve_from_system_profiles()
        if resolved and len(resolved) >= 50:
            _TEMPLATE_CACHE = resolved
            logger.info(f"Template résolu depuis profils système Bambu ({len(resolved)} clés).")
            return _TEMPLATE_CACHE
    except Exception as e:
        logger.warning(f"Résolution système échouée : {e}")

    logger.warning("Aucun template Bambu Studio disponible — export en mode simplifié.")
    return None


def _save_cache(cfg: dict) -> None:
    try:
        _DATA_DIR.mkdir(exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Impossible de sauvegarder le cache : {e}")


def _config_to_bambu_overrides(config: PrintConfig) -> dict:
    """Convertit un PrintConfig en dict de paramètres au format project_settings.config.

    Seuls les paramètres présents dans model_fields_set (chargés depuis le YAML de profil)
    sont appliqués. Cela évite d'écraser les valeurs par défaut du template Bambu quand
    le profil "standard" ne définit pas un paramètre donné.

    Les vitesses sont stockées comme tableaux JSON ["val_standard", "val_high_flow"].
    """
    s = str
    fields = config.model_fields_set

    def spd(v: int) -> list[str]:
        return [str(v), str(v)]

    overrides: dict = {}

    # Couches
    if "layer_height" in fields:
        overrides["layer_height"] = s(config.layer_height)
    if "first_layer_height" in fields:
        overrides["initial_layer_print_height"] = s(config.first_layer_height)

    # Structure
    if "wall_loops" in fields:
        overrides["wall_loops"] = s(config.wall_loops)
    if "wall_generator" in fields:
        overrides["wall_generator"] = config.wall_generator
    if "wall_sequence" in fields:
        overrides["wall_sequence"] = config.wall_sequence
    if "top_shell_layers" in fields:
        overrides["top_shell_layers"] = s(config.top_shell_layers)
    if "bottom_shell_layers" in fields:
        overrides["bottom_shell_layers"] = s(config.bottom_shell_layers)
    if "top_one_wall_type" in fields:
        overrides["top_one_wall_type"] = config.top_one_wall_type

    # Remplissage
    if "infill_density" in fields:
        overrides["sparse_infill_density"] = f"{config.infill_density}%"
    if "infill_pattern" in fields:
        overrides["sparse_infill_pattern"] = config.infill_pattern

    # Surfaces
    if "top_surface_pattern" in fields:
        _TSP_LEGACY = {"rectilinear": "zig-zag", "alignedrectilinear": "zig-zag"}
        overrides["top_surface_pattern"] = _TSP_LEGACY.get(
            config.top_surface_pattern, config.top_surface_pattern
        )

    # Repassage
    if "ironing_type" in fields:
        overrides["ironing_type"] = config.ironing_type
    if "ironing_speed" in fields:
        overrides["ironing_speed"] = s(config.ironing_speed)
    if "ironing_flow" in fields:
        overrides["ironing_flow"] = f"{config.ironing_flow}%"
    if "ironing_spacing" in fields:
        overrides["ironing_spacing"] = s(config.ironing_spacing)

    # Adhérence — seulement si déclenché par un géo-modifier ou une sélection explicite
    if "brim_type" in fields or "brim_width" in fields:
        overrides["brim_type"] = config.brim_type if config.brim_width > 0 else "no_brim"
        overrides["brim_width"] = s(config.brim_width)
        overrides["brim_object_gap"] = s(config.brim_object_gap)

    # Vitesses — format tableau JSON ["val", "val"] (nozzle standard + high flow)
    if "outer_wall_speed" in fields:
        overrides["outer_wall_speed"] = spd(config.outer_wall_speed)
    if "inner_wall_speed" in fields:
        overrides["inner_wall_speed"] = spd(config.inner_wall_speed)
    if "infill_speed" in fields:
        overrides["sparse_infill_speed"] = spd(config.infill_speed)
    if "top_surface_speed" in fields:
        overrides["top_surface_speed"] = spd(config.top_surface_speed)
    if "bridge_speed" in fields:
        overrides["bridge_speed"] = spd(config.bridge_speed)
    if "first_layer_speed" in fields:
        overrides["initial_layer_speed"] = spd(config.first_layer_speed)

    # Qualité / Précision
    if "seam_position" in fields:
        overrides["seam_position"] = config.seam_position
    if "xy_contour_compensation" in fields:
        overrides["xy_contour_compensation"] = s(config.xy_contour_compensation)
    if "elefant_foot_compensation" in fields:
        overrides["elefant_foot_compensation"] = s(config.elefant_foot_compensation)

    # AMS / Purge
    if "flush_into_infill" in fields:
        overrides["flush_into_infill"] = "1" if config.flush_into_infill else "0"
    if "flush_into_support" in fields:
        overrides["flush_into_support"] = "1" if config.flush_into_support else "0"
    if "enable_prime_tower" in fields:
        overrides["enable_prime_tower"] = "1" if config.enable_prime_tower else "0"

    # Support — toujours explicite (indépendant de model_fields_set)
    # support_type est assigné après __init__ par le moteur de paramètres → jamais
    # dans fields. On écrit toujours cette section pour garantir que BS respecte le choix.
    if config.support_type == "none":
        overrides["enable_support"] = "0"
    else:
        overrides["enable_support"] = "1"
        overrides["support_type"] = config.support_type
        overrides["support_style"] = "tree_slim" if "tree" in config.support_type else "default"
        overrides["support_threshold_angle"] = s(int(config.support_threshold_angle))
        overrides["support_on_build_plate_only"] = "1" if config.support_on_build_plate_only else "0"
        overrides["support_angle"] = "0"

    return overrides


# Correspondance nom UI → suffixe BBL dans les noms de profils système
# (ex: "0.20mm Standard @BBL X1C", "Generic PLA @BBL P1S"…)
# Les modèles récents sans profils dédiés héritent du modèle parent le plus proche.
_UI_TO_BBL: dict[str, str] = {
    # Série H2
    "H2D":           "H2D",
    "H2C":           "H2D",    # pas de profils H2C distincts dans BS
    "H2S":           "H2D",
    "H2D Pro":       "H2D",
    # Série X
    "X1 Carbon":     "X1C",
    "X1E":           "X1C",    # X1E partage les profils process X1C
    "X2D":           "X1C",    # X2D trop récent, pas encore dans profils système BS
    # Série P
    "P2S":           "P1S",    # P2S trop récent, fallback P1S
    "P1S":           "P1S",
    "P1":            "P1P",
    # Série A
    "A1 Mini":       "A1M",
    "A1":            "A1",
    "A2L":           "A2L",
}

# printer_settings_id exact attendu par Bambu Studio pour chaque modèle
_UI_TO_PRINTER_ID: dict[str, str] = {
    "H2D":           "Bambu Lab H2D 0.4 nozzle",
    "H2C":           "Bambu Lab H2D 0.4 nozzle",
    "H2S":           "Bambu Lab H2D 0.4 nozzle",
    "H2D Pro":       "Bambu Lab H2D 0.4 nozzle",
    "X1 Carbon":     "Bambu Lab X1 Carbon 0.4 nozzle",
    "X1E":           "Bambu Lab X1E 0.4 nozzle",
    "X2D":           "Bambu Lab X2D 0.4 nozzle",
    "P2S":           "Bambu Lab P2S 0.4 nozzle",
    "P1S":           "Bambu Lab P1S 0.4 nozzle",
    "P1":            "Bambu Lab P1P 0.4 nozzle",
    "A1 Mini":       "Bambu Lab A1 mini 0.4 nozzle",
    "A1":            "Bambu Lab A1 0.4 nozzle",
    "A2L":           "Bambu Lab A2L 0.4 nozzle",
}

# Noms filaments UI → label Bambu Studio (Generic <X> @BBL <printer>)
_FILAMENT_BBL_NAMES: dict[str, str] = {
    "PLA":        "Generic PLA",
    "PETG":       "Generic PETG",
    "ABS":        "Generic ABS",
    "ASA":        "Generic ASA",
    "TPU":        "Generic TPU",
    "PC":         "Generic PC",
    "PA":         "Generic PA",
    "PLA-CF":     "Generic PLA-CF",
    "PETG-CF":    "Generic PETG-CF",
    "ABS-GF":     "Generic ABS-GF",
    "Support PLA": "Generic Support W",
}


class ThreeMFBuilder:
    """Génère un .3MF Bambu Studio valide avec paramètres intégrés."""

    def __init__(self):
        self._template: dict | None = None

    def build(
        self,
        mesh: trimesh.Trimesh,
        config: PrintConfig,
        output_path: Path,
        object_name: str = "neoSlice_Object",
        printer_ui_name: str = "X1 Carbon",
        filament_ui_name: str = "PLA",
        nozzle_diameter_mm: float = 0.4,
    ) -> Path:
        self._template = _find_bambu_template()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self._template:
            return self._build_native(
                mesh, config, output_path, object_name,
                printer_ui_name, filament_ui_name, nozzle_diameter_mm,
            )
        else:
            return self._build_fallback(mesh, config, output_path, object_name)

    # ------------------------------------------------------------------
    # Build natif Bambu Studio (avec template)
    # ------------------------------------------------------------------

    def _build_native(
        self, mesh: trimesh.Trimesh, config: PrintConfig,
        output_path: Path, object_name: str,
        printer_ui_name: str = "X1 Carbon",
        filament_ui_name: str = "PLA",
        nozzle_diameter_mm: float = 0.4,
    ) -> Path:
        obj_uuid = str(uuid.uuid4())
        comp_uuid = str(uuid.uuid4())
        item_uuid = str(uuid.uuid4())
        build_uuid = str(uuid.uuid4())

        bbl_id = _UI_TO_BBL.get(printer_ui_name, "X1C")

        # Paramètres : template + overrides neoSlice
        project_settings = dict(self._template)
        project_settings.update(_config_to_bambu_overrides(config))

        # ── Overrides nozzle — valeurs exactes mesurées sur fichiers Bambu Studio réels ──
        # Données extraites de 4 fichiers BS (0.2/0.4/0.6/0.8 mm).
        _D = nozzle_diameter_mm
        _lw = round(_D + 0.02, 2)
        _ilw = round(_D * 1.25 if _D <= 0.4 else _D + 0.02, 2)
        _iww = {0.2: 0.22, 0.4: 0.45, 0.6: 0.62, 0.8: 0.82}.get(_D, _lw)
        project_settings["nozzle_diameter"]                    = [str(_D)]
        project_settings["line_width"]                         = str(_lw)
        project_settings["outer_wall_line_width"]              = str(_lw)
        project_settings["inner_wall_line_width"]              = str(_iww)
        project_settings["initial_layer_line_width"]           = str(_ilw)
        project_settings["internal_solid_infill_line_width"]   = str(_lw)

        # ID machine — on inclut la taille de buse réelle dans le printer_settings_id.
        _base_id = _UI_TO_PRINTER_ID.get(printer_ui_name, "Bambu Lab X1 Carbon 0.4 nozzle")
        project_settings["printer_settings_id"] = _base_id.replace("0.4 nozzle", f"{_D} nozzle")

        # different_settings_to_system : si présent avec slot 1 = '' (vide), BS recharge
        # le preset système Generic PLA par-dessus project_settings.config → supprimé.
        project_settings.pop("different_settings_to_system", None)

        # Profil procédé : NE PAS utiliser un preset BS connu.
        # Si print_settings_id correspond à un preset installé dans BS, BS recharge
        # ce preset PAR-DESSUS project_settings.config → écrase enable_support='1'.
        # Avec un ID inconnu de BS, il utilise project_settings.config directement.
        project_settings["print_settings_id"] = f"neoSlice 0.20mm @BBL {bbl_id}"

        # Remplacer tous les réglages filament par un slot "Generic PLA" neutre.
        # Bambu Studio exige la présence de ces clés pour charger le fichier sans crasher.
        # Les valeurs correspondent exactement au profil built-in "Generic PLA" de BS
        # → pas de dialog "Préréglage Personnalisé", pas de crash.
        # L'utilisateur configure le filament lui-même dans BS (guidé par la fiche PDF).
        _filament_strip = [k for k in project_settings
                           if k.startswith("filament_") or k.startswith("default_filament_")]
        _filament_strip += [
            "nozzle_temperature", "nozzle_temperature_initial_layer",
            "nozzle_temperature_range_high", "nozzle_temperature_range_low",
            "required_nozzle_HRC",
        ]
        for _k in _filament_strip:
            project_settings.pop(_k, None)
        project_settings.update({
            "filament_settings_id":              [f"Generic PLA @BBL {bbl_id}"],
            "filament_colour":                   ["#FFFFFF"],
            "filament_type":                     ["PLA"],
            "filament_diameter":                 ["1.75"],
            "filament_density":                  ["1.24"],
            "filament_flow_ratio":               ["0.98"],
            "filament_is_support":               ["0"],
            "filament_soluble":                  ["0"],
            "nozzle_temperature":                ["220"],
            "nozzle_temperature_initial_layer":  ["220"],
            "nozzle_temperature_range_high":     ["240"],
            "nozzle_temperature_range_low":      ["190"],
            "required_nozzle_HRC":               ["3"],
        })

        # Remplacer tous les réglages filament par un slot "Generic PLA" neutre.
        # Bambu Studio exige la présence de ces clés pour charger le fichier sans crasher.
        # Les valeurs correspondent exactement au profil built-in "Generic PLA" de BS
        # → pas de dialog "Préréglage Personnalisé", pas de crash.
        # L'utilisateur configure le filament lui-même dans BS (guidé par la fiche PDF).
        _filament_strip = [k for k in project_settings
                           if k.startswith("filament_") or k.startswith("default_filament_")]
        _filament_strip += [
            "nozzle_temperature", "nozzle_temperature_initial_layer",
            "nozzle_temperature_range_high", "nozzle_temperature_range_low",
            "required_nozzle_HRC",
        ]
        for _k in _filament_strip:
            project_settings.pop(_k, None)
        project_settings.update({
            "filament_settings_id":              [f"Generic PLA @BBL {bbl_id}"],
            "filament_colour":                   ["#FFFFFF"],
            "filament_type":                     ["PLA"],
            "filament_diameter":                 ["1.75"],
            "filament_density":                  ["1.24"],
            "filament_flow_ratio":               ["0.98"],
            "filament_is_support":               ["0"],
            "filament_soluble":                  ["0"],
            "nozzle_temperature":                ["220"],
            "nozzle_temperature_initial_layer":  ["220"],
            "nozzle_temperature_range_high":     ["240"],
            "nozzle_temperature_range_low":      ["190"],
            "required_nozzle_HRC":               ["3"],
        })

        # Remplacer tous les réglages filament par un slot "Generic PLA" neutre.
        # Bambu Studio exige la présence de ces clés pour charger le fichier sans crasher.
        # Les valeurs correspondent exactement au profil built-in "Generic PLA" de BS
        # → pas de dialog "Préréglage Personnalisé", pas de crash.
        # L'utilisateur configure le filament lui-même dans BS (guidé par la fiche PDF).
        _filament_strip = [k for k in project_settings
                           if k.startswith("filament_") or k.startswith("default_filament_")]
        _filament_strip += [
            "nozzle_temperature", "nozzle_temperature_initial_layer",
            "nozzle_temperature_range_high", "nozzle_temperature_range_low",
            "required_nozzle_HRC",
        ]
        for _k in _filament_strip:
            project_settings.pop(_k, None)
        project_settings.update({
            "filament_settings_id":              [f"Generic PLA @BBL {bbl_id}"],
            "filament_colour":                   ["#FFFFFF"],
            "filament_type":                     ["PLA"],
            "filament_diameter":                 ["1.75"],
            "filament_density":                  ["1.24"],
            "filament_flow_ratio":               ["0.98"],
            "filament_is_support":               ["0"],
            "filament_soluble":                  ["0"],
            "nozzle_temperature":                ["220"],
            "nozzle_temperature_initial_layer":  ["220"],
            "nozzle_temperature_range_high":     ["240"],
            "nozzle_temperature_range_low":      ["190"],
            "required_nozzle_HRC":               ["3"],
        })

        # Positionner la pièce au centre du plateau (256×256 mm pour X1C)
        bb = mesh.bounding_box.extents
        cx = 128.0 - bb[0] / 2
        cy = 128.0 - bb[1] / 2
        transform = f"1 0 0 0 1 0 0 0 1 {cx:.4f} {cy:.4f} 0"

        tmp_path = output_path.with_suffix(".3mf.tmp")
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", self._content_types())
                zf.writestr("_rels/.rels", self._rels(has_thumbnail=False))
                zf.writestr(
                    "3D/3dmodel.model",
                    self._main_model(obj_uuid, comp_uuid, item_uuid, build_uuid, transform, object_name),
                )
                zf.writestr(
                    "3D/_rels/3dmodel.model.rels",
                    self._model_rels(),
                )
                zf.writestr(
                    "3D/Objects/object_1.model",
                    self._object_model(mesh),
                )
                zf.writestr(
                    "Metadata/model_settings.config",
                    self._model_settings(len(mesh.faces), object_name),
                )
                zf.writestr(
                    "Metadata/project_settings.config",
                    json.dumps(project_settings, indent=4, ensure_ascii=False),
                )
                zf.writestr("Metadata/slice_info.config", self._slice_info())
                zf.writestr("Metadata/cut_information.xml", self._cut_info())
                zf.writestr("Metadata/filament_sequence.json",
                           '{"plate_1":{"nozzle_sequence":[],"optimal_assignment":[],"sequence":[]}}')
                zf.writestr("Metadata/filament_sequence.json",
                           '{"plate_1":{"nozzle_sequence":[],"optimal_assignment":[],"sequence":[]}}')
            tmp_path.replace(output_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        logger.info(f"3MF natif Bambu généré → {output_path} ({output_path.stat().st_size // 1024} KB)")
        return output_path

    # ------------------------------------------------------------------
    # Fichiers structurels
    # ------------------------------------------------------------------

    def _content_types(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
            ' <Default Extension="config" ContentType="application/xml"/>\n'
            ' <Default Extension="json" ContentType="application/json"/>\n'
            '</Types>'
        )

    def _rels(self, has_thumbnail: bool = False) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>',
        ]
        lines.append('</Relationships>')
        return "\n".join(lines)

    def _model_rels(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/Objects/object_1.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>'
        )

    def _main_model(
        self,
        obj_uuid: str, comp_uuid: str, item_uuid: str, build_uuid: str,
        transform: str, object_name: str,
    ) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="{_NS_3MF}" xmlns:BambuStudio="{_NS_BBL}" xmlns:p="{_NS_PROD}" requiredextensions="p">
 <metadata name="Application">BambuStudio-{BAMBU_VERSION}</metadata>
 <metadata name="BambuStudio:3mfVersion">1.9.0</metadata>
 <metadata name="CreationDate">{today}</metadata>
 <metadata name="ModificationDate">{today}</metadata>
 <metadata name="Title">{object_name}</metadata>
 <resources>
  <object id="2" p:UUID="{obj_uuid}" type="model">
   <components>
    <component p:path="/3D/Objects/object_1.model" objectid="1" p:UUID="{comp_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>
   </components>
  </object>
 </resources>
 <build p:UUID="{build_uuid}">
  <item objectid="2" p:UUID="{item_uuid}" transform="{transform}" printable="1"/>
 </build>
</model>"""

    def _object_model(self, mesh: trimesh.Trimesh) -> str:
        """Géométrie dans 3D/Objects/object_1.model."""
        verts_lines = "\n".join(
            f'    <vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>'
            for v in mesh.vertices
        )
        tris_lines = "\n".join(
            f'    <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>'
            for f in mesh.faces
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="{_NS_3MF}" xmlns:BambuStudio="{_NS_BBL}">
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
{verts_lines}
    </vertices>
    <triangles>
{tris_lines}
    </triangles>
   </mesh>
  </object>
 </resources>
</model>"""

    def _model_settings(self, face_count: int, object_name: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="2">
    <metadata key="name" value="{object_name}"/>
    <metadata key="extruder" value="1"/>
    <metadata face_count="{face_count}"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="{object_name}"/>
      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
      <metadata key="source_file" value="{object_name}.stl"/>
      <metadata key="source_object_id" value="0"/>
      <metadata key="source_volume_id" value="0"/>
      <metadata key="source_offset_x" value="0"/>
      <metadata key="source_offset_y" value="0"/>
      <metadata key="source_offset_z" value="0"/>
      <mesh_stat face_count="{face_count}" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
    </part>
  </object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <metadata key="thumbnail_file" value=""/>
    <model_instance>
      <metadata key="object_id" value="2"/>
      <metadata key="instance_id" value="0"/>
      <metadata key="identify_id" value="1"/>
    </model_instance>
  </plate>
</config>"""

    def _plate_json(self, object_name: str) -> str:
        data = {
            "objects": [{"id": "2", "name": object_name}],
            "bed_type": "textured_plate",
            "print_sequence": "by_layer",
            "first_layer_print_sequence": [0],
            "spiral_mode": False,
            "timelapse_type": 0,
            "gcode_file": "",
        }
        return json.dumps(data, ensure_ascii=False)

    def _plate_json(self, object_name: str) -> str:
        data = {
            "objects": [{"id": "2", "name": object_name}],
            "bed_type": "textured_plate",
            "print_sequence": "by_layer",
            "first_layer_print_sequence": [0],
            "spiral_mode": False,
            "timelapse_type": 0,
            "gcode_file": "",
        }
        return json.dumps(data, ensure_ascii=False)

    def _slice_info(self) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="{BAMBU_VERSION}"/>
  </header>
</config>"""

    def _cut_info(self) -> str:
        return """<?xml version="1.0" encoding="utf-8"?>
<objects>
 <object id="1">
  <cut_id id="0" check_sum="1" connectors_cnt="0"/>
 </object>
</objects>"""

    # ------------------------------------------------------------------
    # Fallback sans template (si aucun .3mf Bambu trouvé)
    # ------------------------------------------------------------------

    def _build_fallback(
        self, mesh: trimesh.Trimesh, config: PrintConfig,
        output_path: Path, object_name: str
    ) -> Path:
        """Export simplifié si aucun template Bambu Studio n'est disponible."""
        logger.warning("Export fallback — aucun template Bambu trouvé. Les paramètres ne seront pas intégrés.")
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types())
            zf.writestr("_rels/.rels", self._rels())
            zf.writestr("3D/_rels/3dmodel.model.rels", self._model_rels())
            obj_uuid = str(uuid.uuid4())
            comp_uuid = str(uuid.uuid4())
            item_uuid = str(uuid.uuid4())
            build_uuid = str(uuid.uuid4())
            bb = mesh.bounding_box.extents
            cx = 128.0 - bb[0] / 2
            cy = 128.0 - bb[1] / 2
            transform = f"1 0 0 0 1 0 0 0 1 {cx:.4f} {cy:.4f} 0"
            zf.writestr("3D/3dmodel.model", self._main_model(
                obj_uuid, comp_uuid, item_uuid, build_uuid, transform, object_name
            ))
            zf.writestr("3D/Objects/object_1.model", self._object_model(mesh))
            zf.writestr("Metadata/model_settings.config", self._model_settings(len(mesh.faces), object_name))
            zf.writestr("Metadata/slice_info.config", self._slice_info())
            zf.writestr("Metadata/cut_information.xml", self._cut_info())
        return output_path

    def set_template_from_file(self, path: Path) -> bool:
        """Charge manuellement un .3mf Bambu Studio comme template."""
        global _TEMPLATE_CACHE
        try:
            with zipfile.ZipFile(path) as z:
                cfg = json.loads(z.read("Metadata/project_settings.config"))
            saved = Path(__file__).parent.parent.parent / "data" / "bambu_config_template.json"
            saved.parent.mkdir(exist_ok=True)
            saved.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            _TEMPLATE_CACHE = cfg
            self._template = cfg
            logger.info(f"Template défini depuis : {path}")
            return True
        except Exception as e:
            logger.error(f"Impossible de charger le template : {e}")
            return False
