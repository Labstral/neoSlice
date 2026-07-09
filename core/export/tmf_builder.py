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
_PRINTER_TEMPLATE_CACHE: dict[str, dict] = {}  # cache par printer_id
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

    # Couches — TOUJOURS écrites (paramètres cœur maîtrisés par neoSlice). Ne PAS
    # conditionner à model_fields_set : les profils process Bambu héritent souvent
    # layer_height d'un parent, or _load_json_flat NE résout PAS l'héritage → le 3MF
    # sortirait SANS layer_height et Bambu Studio appliquerait SON défaut (ex. A1 →
    # 0.16 Optimal alors que neoSlice affiche 0.20). Cf. bug A1 0.2→0.16.
    overrides["layer_height"] = s(config.layer_height)
    # first_layer >= layer (sinon Bambu Studio refuse le profil).
    overrides["initial_layer_print_height"] = s(
        max(config.first_layer_height, config.layer_height))

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
    if "seam_gap" in fields:
        overrides["seam_gap"] = f"{config.seam_gap}%"

    # Surplombs / Ponts — détecter + ralentir les porte-à-faux raides, débit pont calibré.
    if "detect_overhang_wall" in fields:
        overrides["detect_overhang_wall"] = "1" if config.detect_overhang_wall else "0"
    if "bridge_flow" in fields:
        overrides["bridge_flow"] = s(config.bridge_flow)
    if "slow_down_overhangs" in fields:
        # enable_overhang_speed + vitesses par tranche (arrays per-extrudeur, format Bambu)
        overrides["enable_overhang_speed"] = ["1" if config.slow_down_overhangs else "0"]
        if config.slow_down_overhangs:
            overrides["overhang_1_4_speed"] = [s(config.overhang_1_4_speed)]
            overrides["overhang_2_4_speed"] = [s(config.overhang_2_4_speed)]
            overrides["overhang_3_4_speed"] = [s(config.overhang_3_4_speed)]
            overrides["overhang_4_4_speed"] = [s(config.overhang_4_4_speed)]

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
        # "snug" = supports normaux ajustés (ne débordent pas) ; "default" pour l'arborescent
        overrides["support_style"] = "snug" if config.support_type.startswith("normal") else "default"
        overrides["support_threshold_angle"] = s(int(config.support_threshold_angle))
        overrides["support_on_build_plate_only"] = "1" if config.support_on_build_plate_only else "0"
        overrides["support_angle"] = "0"
        overrides["support_top_z_distance"] = s(config.support_top_z_distance)
        overrides["support_bottom_z_distance"] = s(config.support_bottom_z_distance)
        # Interface de supports — contact propre + retrait facile (dessous lisse).
        # NB : on GARDE le gap Z ; le réduire fuserait support et pièce en mono-matériau.
        overrides["support_interface_top_layers"] = s(int(config.support_interface_top_layers))
        overrides["support_interface_bottom_layers"] = s(int(config.support_interface_bottom_layers))
        overrides["support_interface_spacing"] = s(config.support_interface_spacing)
        overrides["support_interface_pattern"] = config.support_interface_pattern
        overrides["support_object_xy_distance"] = s(config.support_object_xy_distance)

    # Sortie OrcaSlicer : l'ancienne valeur Bambu "enabled" de
    # ensure_vertical_shell_thickness a été renommée en "ensure_all" dans Orca.
    # Écrire la valeur moderne évite le popup de migration d'Orca (« a été remplacé
    # par ensure_all »). Sans effet pour la sortie Bambu.
    from core.prefs import PREFS
    if PREFS.get("slicer_output", "bambu") == "orca":
        overrides["ensure_vertical_shell_thickness"] = "ensure_all"

    return overrides


import re as _re
_BBL_REF_RE = _re.compile(r"@BBL\s+[A-Za-z0-9]+")


def _force_printer_identity(project_settings: dict, bbl_id: str,
                            target_machine: str | None = None) -> None:
    """PROCÉDURE FORCÉE : garantit que le profil neoSlice/cible PRIME, quel que soit
    le profil d'origine enregistré dans le 3MF importé (ex. « 0.16mm Optimal @BBL P1P »).

    Sans ça, un 3MF créé pour un AUTRE printer laisse des références (inherits_group,
    filament/print_settings_id, compatible_printers…) qui font recharger SON preset par
    Bambu Studio PAR-DESSUS nos réglages → couche/supports faux. Ici on :
      1. supprime tout héritage de preset système (BS utiliserait ce preset) ;
      2. retargete TOUTE référence de preset « @BBL <autre modèle> » vers le cible ;
      3. force les clés d'identité machine (« Bambu Lab <modèle>… ») vers la machine cible.
    Idempotent, sûr à appeler plusieurs fois. `target_machine` = ex. "Bambu Lab A1 0.4 nozzle"."""
    # 1) Ne jamais hériter d'un preset système / delta système figé.
    for _k in ("inherits", "inherits_group", "different_settings_to_system"):
        project_settings.pop(_k, None)
    # 2) Retargeter toute référence de preset « @BBL <modèle> » vers le printer cible.
    repl = f"@BBL {bbl_id}"

    def _fix(v):
        if isinstance(v, str):
            return _BBL_REF_RE.sub(repl, v)
        if isinstance(v, list):
            return [_fix(x) for x in v]
        return v

    for _k in list(project_settings.keys()):
        project_settings[_k] = _fix(project_settings[_k])
    # 3) Clés d'identité MACHINE (format « Bambu Lab <modèle> <buse> nozzle », sans @BBL) :
    #    forcer explicitement vers la machine cible, sinon un « Bambu Lab P1P… » résiduel
    #    rend le profil incompatible avec la machine cible → BS le remplace.
    if target_machine:
        if project_settings.get("printer_settings_id"):
            project_settings["printer_settings_id"] = target_machine
        for _k in ("print_compatible_printers", "compatible_printers"):
            if project_settings.get(_k):
                project_settings[_k] = [target_machine]


def _bed_center(machine: dict) -> tuple[float, float]:
    """Centre du plateau (mm) depuis printable_area, repli 128×128."""
    try:
        xs, ys = [], []
        for pt in machine.get("printable_area", []):
            x, y = pt.split("x")
            xs.append(float(x)); ys.append(float(y))
        return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    except Exception:
        return (128.0, 128.0)


def _apply_non_bambu_machine(project_settings: dict, printer_ui_name: str,
                             nozzle_mm: float) -> dict | None:
    """Pour une imprimante du catalogue (Creality, Prusa, Anycubic, Flashforge,
    Elegoo, Qidi), remplace le bloc machine du 3MF par celui de l'imprimante cible
    (géométrie, g-code start/end, rétraction, identité) afin qu'OrcaSlicer / Bambu
    Studio charge la BONNE machine à l'ouverture.

    Retourne la config machine appliquée, ou None si l'imprimante est une Bambu Lab
    (auquel cas le chemin Bambu existant garde la main)."""
    from data.printers import (
        is_catalogue_model, profile_name_for, machine_config_for, brand_of,
    )
    if not is_catalogue_model(printer_ui_name):
        return None
    pname = profile_name_for(printer_ui_name, nozzle_mm)
    machine = machine_config_for(pname) if pname else {}
    if not machine:
        return None

    brand = brand_of(printer_ui_name)
    # Bloc machine complet de l'imprimante cible (écrase la géométrie Bambu du template)
    project_settings.update(machine)
    # Identité : le slicer fait correspondre printer_settings_id à un profil installé
    project_settings["printer_settings_id"] = pname
    project_settings["printer_model"] = machine.get("printer_model", printer_ui_name)
    project_settings["nozzle_diameter"] = [str(nozzle_mm)]
    # Filament générique de la marque (présent dans Orca/BS pour ce vendor)
    deffil = machine.get("default_filament_profile")
    if deffil:
        project_settings["filament_settings_id"] = (
            [deffil] if isinstance(deffil, str) else deffil
        )
    # print_settings_id reste INCONNU du slicer (préfixe neoSlice) → pas d'écrasement
    _lh = project_settings.get("layer_height", "0.20")
    try:
        _lhd = f"{float(_lh):.2f}"
    except (ValueError, TypeError):
        _lhd = "0.20"
    project_settings["print_settings_id"] = f"neoSlice {_lhd}mm @{brand}"
    # Aligner imprimante + filament sur de VRAIS préréglages système du fork strict
    # (évite « préréglage personnalisé / confirmez le G-code » sur CrealityPrint/Elegoo).
    _align_strict_preset_names(project_settings, pname, brand)
    return machine


def _sanitize_strict(project_settings: dict) -> None:
    """Corrige des valeurs TOLÉRÉES par OrcaSlicer/Bambu mais REFUSÉES par
    CrealityPrint (validation stricte), sans rien changer pour les autres :
      • index de filament (clés `*_filament`) 1-based → 0 devient 1 ;
      • `tree_support_wall_count` = -1 (« auto » Orca) → 0 (plage CrealityPrint [0,2]).
    Ces valeurs « 1 » et « 0 » sont aussi correctes pour Bambu/Orca → sûr partout."""
    # support_filament / support_interface_filament : 0 n'est PAS un index mais la
    # valeur spéciale « Défaut = même filament que l'objet ». La convertir en 1
    # forcerait les supports sur le filament 1 → couleur différente de l'objet +
    # tour d'amorçage + purge énorme sur les pièces mono-couleur. On les EXCLUT.
    _FILAMENT_ZERO_MEANS_DEFAULT = {"support_filament", "support_interface_filament"}
    for k, v in list(project_settings.items()):
        if k.endswith("_filament") and k not in _FILAMENT_ZERO_MEANS_DEFAULT:
            val = v[0] if isinstance(v, list) and v else v
            if str(val).strip() in ("0", "0.0"):
                project_settings[k] = ["1"] if isinstance(v, list) else "1"
    tsw = project_settings.get("tree_support_wall_count")
    val = tsw[0] if isinstance(tsw, list) and tsw else tsw
    try:
        if val is not None and int(float(val)) < 0:
            project_settings["tree_support_wall_count"] = ["0"] if isinstance(tsw, list) else "0"
    except (ValueError, TypeError):
        pass
    # nozzle_type dédoublé pour mono-extrudeur (["hardened_steel","hardened_steel"]
    # ou "x,x") → valeur unique, sinon CrealityPrint le met « Non défini ».
    nt = project_settings.get("nozzle_type")
    if isinstance(nt, list) and len(set(map(str, nt))) == 1 and nt:
        project_settings["nozzle_type"] = nt[0]
    elif isinstance(nt, str) and "," in nt:
        parts = [s.strip() for s in nt.split(",") if s.strip()]
        if parts and len(set(parts)) == 1:
            project_settings["nozzle_type"] = parts[0]


# Vocabulaire de clés réellement comprises par chaque slicer-fork strict (généré
# depuis TOUS leurs profils : data/<slicer>_keys.json). Sert à retirer les clés
# Bambu-only (ex. locked_skeleton_infill_pattern) que CrealityPrint refuse.
_SLICER_VOCAB_CACHE: dict[str, set | None] = {}
# Clés d'identité / méta 3MF toujours conservées même si absentes du vocabulaire.
_KEEP_ALWAYS = {"printer_settings_id", "print_settings_id", "filament_settings_id",
                "printer_model", "printer_variant", "nozzle_diameter", "version", "from", "name"}


def _slicer_vocab(slicer: str) -> set | None:
    if slicer not in _SLICER_VOCAB_CACHE:
        vocab = None
        f = _DATA_DIR / f"{slicer}_keys.json"
        if f.exists():
            try:
                vocab = set(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                vocab = None
        _SLICER_VOCAB_CACHE[slicer] = vocab
    return _SLICER_VOCAB_CACHE[slicer]


# Noms EXACTS des préréglages système installés de chaque fork strict
# (data/<slicer>_presets.json : {"machines":[…],"filaments":[…]}). Sert à aligner
# printer_settings_id / filament_settings_id sur de VRAIS préréglages → le fork les
# reconnaît comme « système » et n'affiche plus « préréglage personnalisé / G-code ».
_SLICER_PRESETS_CACHE: dict[str, dict | None] = {}


def _slicer_presets(slicer: str) -> dict | None:
    if slicer not in _SLICER_PRESETS_CACHE:
        data = None
        f = _DATA_DIR / f"{slicer}_presets.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                data = None
        _SLICER_PRESETS_CACHE[slicer] = data
    return _SLICER_PRESETS_CACHE[slicer]


def _align_strict_preset_names(project_settings: dict, pname: str, brand: str) -> None:
    """Pour un fork strict (CrealityPrint/ElegooSlicer), remplace les noms de
    préréglages imprimante/filament par les VRAIS noms système installés. Sans ça,
    un nom inexistant (ex. filament « @K2-all », imprimante « … (0.4 nozzle) »
    communautaire) est traité comme « personnalisé » → avertissement G-code.
    Aucun effet pour bambu/orca/prusa (pas de fichier presets → on ne touche à rien)."""
    from core.prefs import PREFS
    presets = _slicer_presets(PREFS.get("slicer_output", "bambu"))
    if not presets:
        return
    machines = set(presets.get("machines", []))
    filaments = set(presets.get("filaments", []))

    # 1) Imprimante : si le nom n'est pas un préréglage réel, tenter la variante
    #    sans parenthèses (« Elegoo Neptune 4 Pro (0.4 nozzle) » → « … 0.4 nozzle »).
    real_machine = pname
    if machines and pname not in machines:
        alt = pname.replace(" (", " ").replace(")", "")
        if alt in machines:
            real_machine = alt
        else:
            cand = [m for m in machines
                    if m.replace(" (", " ").replace(")", "") == alt]
            if cand:
                real_machine = cand[0]
    if real_machine != pname and real_machine in machines:
        project_settings["printer_settings_id"] = real_machine

    # 2) Filament : choisir un vrai « Generic PLA @… » (préréglage installé).
    if filaments:
        for cand in (f"Generic PLA @{real_machine}", f"Generic PLA @{brand}"):
            if cand in filaments:
                project_settings["filament_settings_id"] = [cand]
                return
        brand_fils = [x for x in filaments
                      if x.startswith("Generic PLA @") and brand and brand in x]
        any_fils = [x for x in filaments if x.startswith("Generic PLA @")]
        pick = brand_fils or any_fils
        if pick:
            project_settings["filament_settings_id"] = [min(pick, key=len)]


def _filter_for_strict_slicer(project_settings: dict) -> None:
    """Pour un slicer-fork strict (CrealityPrint/ElegooSlicer) : ne garde que les
    clés que CE slicer connaît → supprime les clés Bambu-only inconnues (qui
    déclenchent « Non défini » à l'ouverture). Aucun effet si pas de vocabulaire
    (bambu/orca/prusa → fichier absent → on ne touche à rien)."""
    from core.prefs import PREFS
    vocab = _slicer_vocab(PREFS.get("slicer_output", "bambu"))
    if not vocab:
        return
    for k in list(project_settings.keys()):
        if k not in vocab and k not in _KEEP_ALWAYS:
            project_settings.pop(k, None)

    # Clamp des accélérations absolues au plafond machine (sinon CrealityPrint
    # avertit qu'il auto-limite). Les valeurs en « % » sont relatives → ignorées.
    mx = project_settings.get("machine_max_acceleration_extruding")
    mxv = mx[0] if isinstance(mx, list) and mx else mx
    try:
        cap = float(mxv)
    except (TypeError, ValueError):
        cap = 0.0
    if cap > 0:
        for ak in [k for k in project_settings if k.endswith("_acceleration")]:
            v = project_settings[ak]
            vv = v[0] if isinstance(v, list) and v else v
            s = str(vv).strip()
            if s.endswith("%") or not s:
                continue
            try:
                if float(s) > cap:
                    project_settings[ak] = [str(int(cap))] if isinstance(v, list) else str(int(cap))
            except (ValueError, TypeError):
                pass


# ── « Déguisement » du 3MF en projet natif du slicer-fork de sortie ──────────
# Sans ça, CrealityPrint affiche « Ce fichier de projet n'est pas de Creality Print,
# sélectionnez l'imprimante » ET ignore l'imprimante embarquée (retombe sur l'Ender-3
# V2 par défaut). Un vrai projet CrealityPrint se reconnaît à 3 marqueurs (relevés sur
# resources/calib/.../CrealityToleranceTest.3mf) : Application="Creality_Print V…",
# header slice_info X-CX-Client-Type="creality_print", et un fichier Metadata/creality.config.
# ElegooSlicer/OrcaSlicer acceptent les marqueurs Bambu par défaut → rien à changer.
_CREALITY_APP_VERSION = "7.2.0"
# ElegooSlicer reconnaît le producteur « ElegooSlicer-<version> » (littéral présent
# dans ElegooSlicer.dll, à côté de BambuStudio-/OrcaSlicer-). Avec ce producteur il
# ouvre le 3MF comme SON projet → plus de « may be incompatible / Load Whole File ».
# Il garde les headers X-BBL et n'a pas de fichier config dédié.
_ELEGOO_APP_VERSION = "1.5.2.2"
# OrcaSlicer reconnaît le producteur « OrcaSlicer-<version> » (comme ElegooSlicer,
# tous deux forks de BambuStudio). Avec ce producteur, Orca ouvre le 3MF comme SON
# projet → plus de popup « Le fichier 3MF a été créé par BambuStudio ». Il garde les
# clés/headers Bambu (qu'il lit nativement) → slice_info=None, pas de fichier dédié.
_ORCA_APP_VERSION = "02.03.00.58"


def _creality_config_xml() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        '    <metadata key="Company" value="Creality"/>\n'
        '    <metadata key="Application" value="Creality_Print"/>\n'
        f'    <metadata key="AppVersion" value="{_CREALITY_APP_VERSION}"/>\n'
        '    <metadata key="AppStage" value="Release"/>\n'
        '    <metadata key="FileVersion" value="1.0"/>\n'
        '    <metadata key="FileType" value="Undefined"/>\n'
        f'    <metadata key="CreationDate" value="{today}"/>\n'
        '</config>'
    )


def _slicer_branding() -> dict:
    """Marqueurs d'identité à écrire pour que le slicer-fork de sortie ouvre le 3MF
    comme SON projet. Renvoie {application, slice_info(xml|None), extra_files{path:xml}}.
    Par défaut (bambu/orca/elegoo/prusa) → identité Bambu Studio (comportement inchangé)."""
    from core.prefs import PREFS
    slicer = PREFS.get("slicer_output", "bambu")
    if slicer == "creality":
        return {
            "application": f"Creality_Print V{_CREALITY_APP_VERSION}",
            "slice_info": (
                '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
                '    <header_item key="X-CX-Client-Type" value="creality_print"/>\n'
                f'    <header_item key="X-CX-Client-Version" value="{_CREALITY_APP_VERSION}"/>\n'
                '  </header>\n</config>'
            ),
            "extra_files": {"Metadata/creality.config": _creality_config_xml()},
        }
    if slicer == "elegoo":
        # Producteur natif ElegooSlicer ; headers X-BBL conservés (slice_info=None).
        return {
            "application": f"ElegooSlicer-{_ELEGOO_APP_VERSION}",
            "slice_info": None,
            "extra_files": {},
        }
    if slicer == "orca":
        # Producteur natif OrcaSlicer → ouvre le 3MF comme son projet (pas de popup
        # « créé par BambuStudio »). Clés Bambu conservées (Orca les lit).
        return {
            "application": f"OrcaSlicer-{_ORCA_APP_VERSION}",
            "slice_info": None,
            "extra_files": {},
        }
    return {"application": f"BambuStudio-{BAMBU_VERSION}", "slice_info": None, "extra_files": {}}


# Correspondance nom UI → suffixe BBL dans les noms de profils système
# (ex: "0.20mm Standard @BBL X1C", "Generic PLA @BBL P1S"…)
# Les modèles récents sans profils dédiés héritent du modèle parent le plus proche.
_UI_TO_BBL: dict[str, str] = {
    # Série H2
    "H2D":           "H2D",
    "H2C":           "H2C",    # BS a ses propres profils H2C (machine/Bambu Lab H2C 0.4 nozzle.json)
    "H2S":           "H2S",
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
    "H2C":           "Bambu Lab H2C 0.4 nozzle",
    "H2S":           "Bambu Lab H2S 0.4 nozzle",
    "H2D Pro":       "Bambu Lab H2D Pro 0.4 nozzle",
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

    def inject_settings_into_3mf(
        self,
        source_path: Path,
        config: PrintConfig,
        output_path: Path,
        printer_ui_name: str = "X1 Carbon",
        filament_ui_name: str = "PLA",
        nozzle_diameter_mm: float = 0.4,
    ) -> Path:
        """Injecte les paramètres neoSlice dans un 3MF existant sans toucher à la géométrie.

        Copie le 3MF source tel quel (préserve modifier_part, components, toute la structure
        originale) et remplace uniquement project_settings.config avec les paramètres générés.
        Évite la reconstruction depuis zéro qui perd les modifier_part → Generic-Cubes solides.
        """
        import shutil, json
        self._template = _find_bambu_template()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Copier le 3MF source → output
        shutil.copy2(source_path, output_path)

        # Lire le project_settings.config ORIGINAL du 3MF source comme base.
        # On MERGE nos overrides dessus — ça préserve max_volumetric_speed,
        # filament_settings_id et les autres clés que neoSlice ne touche pas.
        # Évite les warnings BS "Vitesse volumétrique max trop faible".
        _original_ps = {}
        try:
            with zipfile.ZipFile(source_path, "r") as _zsrc:
                if "Metadata/project_settings.config" in _zsrc.namelist():
                    _original_ps = json.loads(_zsrc.read("Metadata/project_settings.config"))
        except Exception:
            pass

        # Partir des settings originaux + overrides neoSlice (pas depuis le template BS)
        bbl_id = _UI_TO_BBL.get(printer_ui_name, printer_ui_name)
        project_settings = dict(_original_ps)  # base = settings originaux du fichier
        project_settings.update(_config_to_bambu_overrides(config))

        _D = nozzle_diameter_mm
        _lw = round(_D + 0.02, 2)
        project_settings["nozzle_diameter"] = [str(_D)]
        project_settings["line_width"] = str(_lw)

        _base_id = _UI_TO_PRINTER_ID.get(printer_ui_name,
                                          f"Bambu Lab {printer_ui_name} 0.4 nozzle")
        project_settings["printer_settings_id"] = _base_id.replace("0.4 nozzle",
                                                                      f"{_D} nozzle")
        project_settings.pop("different_settings_to_system", None)

        _lh_val = project_settings.get("layer_height", "0.20")
        try:
            _lh_display = f"{float(_lh_val):.2f}"
        except (ValueError, TypeError):
            _lh_display = "0.20"
        project_settings["print_settings_id"] = f"neoSlice {_lh_display}mm @BBL {bbl_id}"

        # Profil process par défaut adapté au printer CIBLE. Sinon un 3MF importé
        # d'un AUTRE printer (ex. projet P1P retargeté A1) garde son
        # default_print_profile "@BBL P1P" → BS le juge incompatible avec la machine
        # A1 et recharge un preset système (0.16mm Optimal) PAR-DESSUS nos réglages
        # (couche 0.16, supports off). Cf. bug Darth Vader A1/P1P.
        project_settings["default_print_profile"] = f"0.20mm Standard @BBL {bbl_id}"

        # Filament — multi-couleurs : on reconstruit N slots « Generic PLA » PROPRES
        # (valeurs génériques, AUCUN G-code personnalisé), en PRÉSERVANT le nombre de
        # slots ET les couleurs d'origine. Deux pièges évités :
        #   • forcer 1 seul slot rendait le projet incohérent (objets sur extruder 2
        #     sans filament 2) → BS supprimait les couleurs + réinitialisait le process ;
        #   • préserver le filament source (ex. "Generic PLA @BBL X1C" avec G-code custom)
        #     déclenchait l'alerte BS « préréglage personnalisé — G-codes modifiés ».
        _src_col = _original_ps.get("filament_colour")
        if isinstance(_src_col, list) and _src_col:
            _colours = [str(c) for c in _src_col]
        else:
            _fid = _original_ps.get("filament_settings_id")
            _n0 = len(_fid) if isinstance(_fid, list) and _fid else 1
            _colours = ["#FFFFFF"] * _n0
        _n = max(1, len(_colours))
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
            "filament_settings_id":              ["Generic PLA"] * _n,
            "filament_colour":                   _colours,
            "filament_type":                     ["PLA"] * _n,
            "filament_diameter":                 ["1.75"] * _n,
            "filament_density":                  ["1.24"] * _n,
            "filament_flow_ratio":               ["0.98"] * _n,
            "filament_is_support":               ["0"] * _n,
            "filament_soluble":                  ["0"] * _n,
            "nozzle_temperature":                ["220"] * _n,
            "nozzle_temperature_initial_layer":  ["220"] * _n,
            "nozzle_temperature_range_high":     ["240"] * _n,
            "nozzle_temperature_range_low":      ["190"] * _n,
            "required_nozzle_HRC":               ["3"] * _n,
        })

        # Ne PAS hériter d'un preset système hérité du fichier importé : inherits_group
        # garde souvent "0.16mm Optimal @BBL P1P" → BS charge CE preset (0.16, supports
        # off) par-dessus nos réglages. On le retire pour que BS utilise les valeurs à
        # plat de project_settings.config (cohérent avec print_settings_id "neoSlice…").
        project_settings.pop("inherits_group", None)

        # La compatibilité doit viser le printer CIBLE : un print_compatible_printers
        # resté sur "Bambu Lab P1P…" fait juger le profil incompatible avec la machine
        # A1 → BS le remplace par son défaut. On aligne sur la machine cible.
        _target_machine = _base_id.replace("0.4 nozzle", f"{_D} nozzle")
        if "print_compatible_printers" in project_settings:
            project_settings["print_compatible_printers"] = [_target_machine]
        if project_settings.get("compatible_printers"):
            project_settings["compatible_printers"] = [_target_machine]

        # PROCÉDURE FORCÉE (bulletproof) : purge tout héritage/référence à l'imprimante
        # d'origine du 3MF importé → le profil neoSlice/cible PRIME toujours, quel que
        # soit le profil initial (ex. P1P 0.16mm). Filet de sécurité générique en plus
        # des retargetages explicites ci-dessus.
        _force_printer_identity(project_settings, bbl_id, _target_machine)

        # Imprimante non-Bambu (catalogue) → remplacer le bloc machine + identité
        _apply_non_bambu_machine(project_settings, printer_ui_name, _D)
        _sanitize_strict(project_settings)   # valeurs refusées par CrealityPrint
        _filter_for_strict_slicer(project_settings)   # retire les clés Bambu-only

        # Injecter dans le ZIP en remplaçant uniquement project_settings.config
        tmp = output_path.with_suffix(".tmp")
        try:
            with zipfile.ZipFile(output_path, "r") as zin, \
                 zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "Metadata/project_settings.config":
                        zout.writestr(item, json.dumps(project_settings,
                                                       indent=4, ensure_ascii=False))
                    else:
                        zout.writestr(item, zin.read(item.filename))
            tmp.replace(output_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        logger.info(f"3MF injecté (structure originale préservée) → {output_path}")
        return output_path

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

        # bbl_id : si le printer n'est pas dans le dict c'est un bug de code à corriger,
        # pas à masquer avec un fallback silencieux. On log l'erreur et on tente quand même.
        # Exception : les imprimantes du catalogue (non-Bambu) sont gérées plus bas par
        # _apply_non_bambu_machine — pas de bbl_id attendu, donc pas d'erreur.
        from data.printers import is_catalogue_model as _is_cat
        bbl_id = _UI_TO_BBL.get(printer_ui_name)
        if bbl_id is None:
            if not _is_cat(printer_ui_name):
                logger.error(
                    f"Printer '{printer_ui_name}' absent de _UI_TO_BBL — "
                    "ajouter ce modèle dans tmf_builder.py. "
                    "Export tenté avec le nom UI comme bbl_id."
                )
            bbl_id = printer_ui_name  # utiliser le nom tel quel ; écrasé si catalogue

        # Paramètres : charger le template du bon printer (mis en cache par printer_id)
        if bbl_id not in _PRINTER_TEMPLATE_CACHE:
            try:
                from .bambu_config_resolver import resolve_from_system_profiles
                resolved = resolve_from_system_profiles(bbl_id)
                _PRINTER_TEMPLATE_CACHE[bbl_id] = resolved or self._template
            except Exception:
                _PRINTER_TEMPLATE_CACHE[bbl_id] = self._template
        project_settings = dict(_PRINTER_TEMPLATE_CACHE[bbl_id])
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

        # ID machine — jamais de fallback X1C. Si inconnu, construire depuis le nom UI.
        _base_id = _UI_TO_PRINTER_ID.get(printer_ui_name)
        if _base_id is None:
            _base_id = f"Bambu Lab {printer_ui_name} 0.4 nozzle"
            if not _is_cat(printer_ui_name):
                logger.warning(f"printer_settings_id inconnu pour '{printer_ui_name}' — construit: {_base_id}")
        project_settings["printer_settings_id"] = _base_id.replace("0.4 nozzle", f"{_D} nozzle")

        # Profil process par défaut — adapté au printer sélectionné (template peut être X1C)
        project_settings["default_print_profile"] = f"0.20mm Standard @BBL {bbl_id}"

        # different_settings_to_system : si présent avec slot 1 = '' (vide), BS recharge
        # le preset système Generic PLA par-dessus project_settings.config → supprimé.
        project_settings.pop("different_settings_to_system", None)

        # Profil procédé : NE PAS utiliser un preset BS connu.
        # Si print_settings_id correspond à un preset installé dans BS, BS recharge
        # ce preset PAR-DESSUS project_settings.config → écrase enable_support='1'.
        # Avec un ID inconnu de BS, il utilise project_settings.config directement.
        # Utiliser la vraie hauteur de couche dans l'ID pour que BS affiche la bonne résolution.
        # L'ID doit rester INCONNU de BS (préfixe "neoSlice") pour éviter l'écrasement du preset.
        _lh_val = project_settings.get("layer_height", "0.20")  # déjà mis à jour par _config_to_bambu_overrides
        try:
            _lh_display = f"{float(_lh_val):.2f}"
        except (ValueError, TypeError):
            _lh_display = "0.20"
        project_settings["print_settings_id"] = f"neoSlice {_lh_display}mm @BBL {bbl_id}"

        # Slot filament Generic PLA neutre — BS exige ces clés pour charger sans crash.
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
            "filament_settings_id":              ["Generic PLA"],
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

        # Imprimante non-Bambu (catalogue) → remplacer le bloc machine + identité
        _machine = _apply_non_bambu_machine(project_settings, printer_ui_name, _D)
        _sanitize_strict(project_settings)   # valeurs refusées par CrealityPrint
        _filter_for_strict_slicer(project_settings)   # retire les clés Bambu-only

        # Centrer la pièce sur le plateau d'après ses bornes RÉELLES.
        # Un STL conserve ses coordonnées d'origine (souvent centré sur son
        # centroïde, pas coin mini à 0,0) → l'ancien calcul `centre - taille/2`
        # supposait min=(0,0) et décalait la pièce vers l'avant-gauche.
        # On translate le CENTRE de la bbox sur le centre du plateau, et on pose
        # la base (z min) sur le plateau (z=0).
        lo, hi = mesh.bounds
        _bx, _by = _bed_center(_machine) if _machine else (128.0, 128.0)
        cx = _bx - (lo[0] + hi[0]) / 2
        cy = _by - (lo[1] + hi[1]) / 2
        cz = -lo[2]
        transform = f"1 0 0 0 1 0 0 0 1 {cx:.4f} {cy:.4f} {cz:.4f}"

        tmp_path = output_path.with_suffix(".3mf.tmp")
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", self._content_types())
                zf.writestr("_rels/.rels", self._rels(has_thumbnail=False))
                # Géométrie INLINE dans 3dmodel.model (pas de fichier séparé object_1.model).
                # Un fichier séparé + _rels pointant dessus causait un double-chargement par BS :
                # le mesh apparaissait 2× (une fois à Z=0 + une fois placé), créant un intérieur
                # ouvert avec des supports partout dedans.
                zf.writestr(
                    "3D/3dmodel.model",
                    self._inline_model(mesh, obj_uuid, item_uuid, build_uuid, transform, object_name),
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
                # Marqueurs propres au slicer-fork de sortie (ex. Metadata/creality.config)
                # → le fork ouvre le 3MF comme SON projet et honore l'imprimante embarquée.
                for _path, _xml in _slicer_branding()["extra_files"].items():
                    zf.writestr(_path, _xml)
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
 <metadata name="Application">{_slicer_branding()["application"]}</metadata>
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

    def _inline_model(
        self, mesh: trimesh.Trimesh,
        obj_uuid: str, item_uuid: str, build_uuid: str,
        transform: str, object_name: str,
    ) -> str:
        """Modèle 3MF complet avec géométrie inline — évite le double-chargement BS."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Merger les vertices AVANT export — critique pour les meshes chargés avec process=False.
        # Sans merge, chaque triangle a 3 vertices uniques → aucune arête partagée → BS
        # voit le mesh comme totalement ouvert → supports générés à l'intérieur du modèle.
        export_mesh = mesh
        n_before = len(mesh.vertices)
        if len(mesh.vertices) > len(mesh.faces):
            # Ratio verts/faces > 1 = vertices non-mergés (3 par face) → merger nécessaire
            try:
                export_mesh = mesh.copy()
                export_mesh.merge_vertices(merge_tex=False)
                logger.info(f"Export: merge_vertices {n_before} → {len(export_mesh.vertices)} vertices")
            except Exception as _me:
                logger.warning(f"merge_vertices export échoué ({_me}) — utilisation mesh brut")
                export_mesh = mesh

        verts_lines = "\n".join(
            f'      <vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>'
            for v in export_mesh.vertices
        )
        tris_lines = "\n".join(
            f'      <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>'
            for f in export_mesh.faces
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="{_NS_3MF}" xmlns:BambuStudio="{_NS_BBL}" xmlns:p="{_NS_PROD}" requiredextensions="p">
 <metadata name="Application">{_slicer_branding()["application"]}</metadata>
 <metadata name="BambuStudio:3mfVersion">1.9.0</metadata>
 <metadata name="CreationDate">{today}</metadata>
 <metadata name="ModificationDate">{today}</metadata>
 <metadata name="Title">{object_name}</metadata>
 <resources>
  <object id="1" p:UUID="{obj_uuid}" type="model" name="{object_name}">
   <mesh>
    <vertices>
{verts_lines}
    </vertices>
    <triangles>
{tris_lines}
    </triangles>
   </mesh>
   <BambuStudio:Stats edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0"/>
  </object>
 </resources>
 <build p:UUID="{build_uuid}">
  <item objectid="1" p:UUID="{item_uuid}" transform="{transform}" printable="1"/>
 </build>
</model>"""

    def _object_model(self, mesh: trimesh.Trimesh) -> str:
        """Géométrie dans 3D/Objects/object_1.model (gardé pour compatibilité fallback)."""
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
        # object id="1" : cohérent avec la géométrie inline dans _inline_model.
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1">
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
  <plate index="0">
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <metadata key="thumbnail_file" value=""/>
    <model_instance objectid="1" instance_id="0" identify_id="0" plater_id="0" printable="true"/>
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
        custom = _slicer_branding()["slice_info"]
        if custom:
            return custom
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
            lo, hi = mesh.bounds
            cx = 128.0 - (lo[0] + hi[0]) / 2
            cy = 128.0 - (lo[1] + hi[1]) / 2
            cz = -lo[2]
            transform = f"1 0 0 0 1 0 0 0 1 {cx:.4f} {cy:.4f} {cz:.4f}"
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
