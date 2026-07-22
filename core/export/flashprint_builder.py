# -*- coding: utf-8 -*-
"""Export **FlashPrint 5** (FlashForge) : 3MF géométrie + profil de tranchage.

FlashPrint n'est PAS un fork Slic3r/Orca : son projet natif (.fpp) ne transporte
pas les réglages. En revanche :
  1. il ouvre les 3MF (géométrie, via lib3mf) ;
  2. ses profils de tranchage utilisateur vivent dans un fichier plat
     `~/.FlashPrint5/slice_profile/<machineId>_<buse>_<nom>.cfg`. Format RELEVÉ et
     VALIDÉ en pilotant FlashPrint 5.8.7 (2026-07-20) :
       [Custom]  machineId (entier), nozzleSize/materialDensity* (flottants QVariant),
                 profileName/materialName* (texte)
       [General] ~200 clés : flottants encodés QVariant `@Variant(\\0\\0\\0\\x87<BE f32>)`,
                 booléens/tableaux/petits enums en texte.
     Les `machineId` (Adventurer 5M=33, Inventor II Series=8, …) ne sont NI dans
     profile.dat NI dans le binaire : relevés machine par machine (config écrit le
     machineId courant) → table dans tools/extract_flashprint_printers.py.
  3. il sait aussi IMPORTER un `.fcfg` (même format) via son dialogue de tranchage.

Stratégie neoSlice (validée par Emmanuel + vérifiée en GUI) : à l'export on écrit
  - `<piece>.3mf`  : la géométrie (FlashPrint l'ouvre directement, centrée) ;
  - le profil « neoSlice <piece> » DÉPOSÉ dans ~/.FlashPrint5/slice_profile/ ;
  - `<piece>.fcfg` à côté du 3MF, en SECOURS (autre poste / dossier absent) :
    importable via « Importer » dans le dialogue de tranchage.

Côté utilisateur, pour retrouver le profil (vérifié à l'écran) : ouvrir le 3MF →
Commencer le tranchage → mode expert → **Type Matériau = « Materiau personnalisé »**
→ **Profil de tranche = « neoSlice <piece> »** → Tranche. (FlashPrint range TOUS les
profils utilisateur sous le matériau personnalisé, quel que soit leur matériau.)

Le profil part du préréglage CONSTRUCTEUR exact (couple machine×matériau de
profile.dat), complété par le schéma canonique (data/flashprint_profile_schema.json,
les ~200 clés attendues), et n'est surchargé que par les paramètres neoSlice.
Règles de prudence :
  - les VITESSES ne dépassent jamais le préréglage constructeur (on ralentit
    seulement) ; un plateau non chauffant (platformTemp=0) le RESTE ;
  - `raftEnable` du constructeur est conservé (Dreamer/Creator Pro… impriment AVEC
    raft) ; le brim n'est ajouté que si le raft n'est pas déjà actif ;
  - `fillPattern` (enum propriétaire) n'est PAS surchargé (correspondance des
    entiers non documentée) — motif constructeur conservé, densité appliquée.

Les supports FlashPrint sont une opération de SCÈNE (générés dans l'app) : un
profil ne peut pas les activer → le dialogue de succès indique le clic
« Supports → Auto » quand l'intent en demande.
"""
from __future__ import annotations

import functools
import json
import re
import struct
from pathlib import Path

import trimesh
from loguru import logger

from core.parameters.print_config import PrintConfig

_DATA = Path(__file__).resolve().parent.parent.parent / "data"

#: dossier des profils utilisateur de FlashPrint 5 (Windows ET macOS : ~/.FlashPrint5)
FLASHPRINT_USER_DIR = Path.home() / ".FlashPrint5"


def _load_catalog() -> dict:
    try:
        return json.loads((_DATA / "flashprint_printers.json").read_text(encoding="utf-8"))
    except Exception as e:                              # catalogue absent du build = bug
        logger.error(f"[FlashPrint] catalogue illisible: {e}")
        return {"machines": {}, "profiles": {}}


@functools.lru_cache(maxsize=1)
def _load_schema() -> dict:
    """Schéma canonique du profil utilisateur (ordre + type des ~200 clés)."""
    try:
        return json.loads((_DATA / "flashprint_profile_schema.json").read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"[FlashPrint] schéma de profil illisible: {e}")
        return {"general_order": [], "general": {}, "custom_order": [], "custom": {}}


# ── Encodage QVariant (flottant) tel que lu par FlashPrint ────────────────────
def _qv(value: float) -> str:
    """Flottant → `@Variant(\\x..\\x..)` : préfixe de type FlashPrint (4 octets)
    + le float IEEE-754 32 bits big-endian, chaque octet échappé `\\xNN`. Cette
    forme « tout \\xNN » est acceptée telle quelle par l'analyseur INI de Qt
    (vérifié en GUI : température 199 °C et couche 0.33 mm relues correctement)."""
    b = b"\x00\x00\x00\x87" + struct.pack(">f", float(value))
    return "@Variant(" + "".join("\\x{:02x}".format(x) for x in b) + ")"


# Matériau de base neoSlice → répertoires FlashPrint, par ordre de préférence.
_MATERIAL_PREF: dict[str, list[str]] = {
    "PLA":     ["PLA", "HS PLA", "PLA-Multicolor"],
    "PETG":    ["PETG", "HS PETG"],
    "ABS":     ["ABS"],
    "ASA":     ["ASA"],
    "TPU":     ["TPU 95A", "TPU", "TPU 90A"],
    "PC":      ["PC"],
    "PA":      ["PA", "PA6_66", "PA12-CF10"],
    "PLA-CF":  ["PLA-CF10", "PLA"],
    "PETG-CF": ["PETG-CF10", "PETG"],
    "PVA":     ["PVA"],
    "HIPS":    ["HIPS"],
    "Wood":    ["Wood", "PLA"],
}


def _mat_name(mat_dir: str) -> str:
    """« PLA-1.75 » → « PLA » (nom du matériau, sans le diamètre)."""
    return mat_dir.rpartition("-")[0] or mat_dir


def _pick_material_dir(available: list[str], filament_ui_name: str) -> str:
    """Choisit le répertoire matériau FlashPrint pour le filament neoSlice."""
    base = "PLA"
    try:
        from data.filaments import base_materiau
        base = (base_materiau(filament_ui_name) or "PLA").strip() or "PLA"
    except Exception:
        pass
    by_name = {_mat_name(d): d for d in available}
    prefs = _MATERIAL_PREF.get(base)
    if prefs is None:
        for known in sorted(_MATERIAL_PREF, key=len, reverse=True):
            if base.upper().startswith(known.upper()):
                prefs = _MATERIAL_PREF[known]
                break
    for want in (prefs or [base, "PLA"]):
        if want in by_name:
            return by_name[want]
    return by_name.get("PLA", available[0] if available else "PLA-1.75")


def _num(profile: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(profile.get(key, default))
    except (TypeError, ValueError):
        return default


def _apply_overrides(profile: dict[str, str], config: PrintConfig) -> dict[str, str]:
    """Préréglage constructeur (plain) + paramètres neoSlice → dict plat de valeurs
    (voir règles de prudence dans l'en-tête). Renvoie des chaînes ; l'encodage
    QVariant/texte final est fait par `_emit_user_cfg` selon le schéma."""
    p = dict(profile)

    p["layerHeight"] = f"{config.layer_height:g}"
    p["firstLayerHeight"] = f"{config.first_layer_height:g}"
    p["shellCnt"] = str(int(config.wall_loops))
    p["fillTopSolidCnt"] = str(int(config.top_shell_layers))
    p["fillBottomSolidCnt"] = str(int(config.bottom_shell_layers))
    p["fillDensity"] = f"{max(0, min(100, config.infill_density)) / 100.0:g}"

    def _cap(key: str, wanted: float) -> None:
        base = _num(p, key)
        if base > 0 and wanted > 0:
            p[key] = f"{min(wanted, base):g}"
    _cap("baseSpeed", config.infill_speed)
    _cap("shellOuterMaxSpeed", config.outer_wall_speed)
    _cap("shellVisibleInnerMaxSpeed", config.inner_wall_speed)
    _cap("shellInvisibleInnerMaxSpeed", config.inner_wall_speed)
    _cap("firstLayerMaxSpeed", config.first_layer_speed)

    if config.slow_down_overhangs:
        p["overhangSpeedEnable"] = "true"
    if "ironingEnable" in p:
        p["ironingEnable"] = "true" if config.ironing_type != "no ironing" else "false"

    p["extruderTemp0"] = str(int(config.nozzle_temperature))
    if _num(p, "platformTemp") > 0:
        p["platformTemp"] = str(int(config.bed_temperature))

    raft_on = str(p.get("raftEnable", "false")).lower() == "true"
    if not raft_on and config.brim_type != "no_brim" and "brimMode" in p:
        p["brimMode"] = "1"
        if config.brim_width > 0:
            p["brimMargin"] = f"{config.brim_width:g}"
        p["brimSpaceToModel"] = f"{max(0.0, config.brim_object_gap):g}"
        if "brimGenInner" in p:
            p["brimGenInner"] = ("true" if config.brim_type in ("inner_only", "outer_and_inner")
                                 else "false")
    return p


def _emit_user_cfg(profile: dict[str, str], machine_id: int, nozzle_mm: float,
                   name: str, mat_name: str, density: float) -> str:
    """Sérialise le profil au format FlashPrint utilisateur (.cfg), selon le schéma
    canonique. Clés « variant » (flottant) → QVariant ; « plain » → texte brut.
    Les clés surchargées prennent la valeur neoSlice/constructeur ; les autres
    gardent la valeur par défaut canonique."""
    schema = _load_schema()
    lines = ["[Custom]",
             f"machineId={machine_id}",
             f"nozzleSize={_qv(nozzle_mm)}",
             f"profileName={name}",
             f"materialName0=Flashforge-{mat_name}-1",
             "materialName1=",
             f"materialDensity0={_qv(density)}",
             f"materialDensity1={_qv(0)}",
             "",
             "[General]"]
    gen = schema.get("general", {})
    for k in schema.get("general_order", []):
        meta = gen.get(k, {"type": "plain", "raw": ""})
        if meta["type"] == "variant":
            if k in profile:
                try:
                    lines.append(f"{k}={_qv(float(profile[k]))}")
                    continue
                except (TypeError, ValueError):
                    pass
            lines.append(f"{k}={meta['raw']}")          # défaut canonique verbatim
        else:                                            # plain (bool / [] / enum)
            lines.append(f"{k}={profile.get(k, meta['raw'])}")
    return "\n".join(lines) + "\n"


def _safe_name(stem: str) -> str:
    """Nom de profil affiché dans FlashPrint, sans caractères interdits en fichier."""
    clean = re.sub(r'[\\/:*?"<>|]+', " ", stem).strip() or "piece"
    return f"neoSlice {clean}"[:60]


class FlashPrintBuilder:
    """Construit la sortie FlashPrint : 3MF + profil déposé + .fcfg de secours."""

    def __init__(self) -> None:
        self._catalog = _load_catalog()
        self.last_profile_name: str = ""
        self.last_profile_installed: bool = False
        self.last_fcfg_path: Path | None = None

    # ── API publique ─────────────────────────────────────────────────────────
    def build(self, mesh: trimesh.Trimesh, config: PrintConfig, output_path: Path,
              printer_ui_name: str, filament_ui_name: str,
              nozzle_diameter_mm: float = 0.4) -> Path:
        output_path = Path(output_path).with_suffix(".3mf")

        machine = self._catalog.get("machines", {}).get(printer_ui_name, {})
        machine_id = int(machine.get("machine_id", -1))
        machine_key = self._machine_key(printer_ui_name, nozzle_diameter_mm)
        mats = self._catalog.get("profiles", {}).get(machine_key, {})
        mat_dir = _pick_material_dir(sorted(mats), filament_ui_name)
        base = mats.get(mat_dir) or self._fallback_profile()
        mat_name = _mat_name(mat_dir)

        profile = _apply_overrides(base, config)
        density = 0.0
        try:
            density = float(getattr(config, "filament_density_g_cm3", 1.24)) or 1.24
        except (TypeError, ValueError):
            density = 1.24
        name = _safe_name(output_path.stem)
        cfg_text = _emit_user_cfg(profile, machine_id, nozzle_diameter_mm, name,
                                  mat_name, density)

        # 1) géométrie : 3MF standard (FlashPrint lit la géométrie via lib3mf)
        mesh.export(str(output_path), file_type="3mf")

        # 2) profil déposé chez FlashPrint (si installé et machineId connu)
        self.last_profile_name = name
        self.last_profile_installed = self._install_profile(
            machine_id, nozzle_diameter_mm, name, cfg_text)

        # 3) .fcfg de secours à côté du 3MF (même format, importable à la main)
        fcfg = output_path.with_suffix(".fcfg")
        fcfg.write_text(cfg_text, encoding="utf-8")
        self.last_fcfg_path = fcfg

        logger.info(f"[FlashPrint] export : {output_path.name} + profil « {name} » "
                    f"({'déposé' if self.last_profile_installed else 'fcfg seul'}) "
                    f"[{printer_ui_name} id={machine_id} / {mat_dir}]")
        return output_path

    # ── Interne ──────────────────────────────────────────────────────────────
    def _machine_key(self, printer_ui_name: str, nozzle_mm: float) -> str:
        """« FlashForge Adventurer 5M » + 0.4 → clé profile.dat « …-0.4 »."""
        return f"{printer_ui_name}-{nozzle_mm:g}"

    def _fallback_profile(self) -> dict[str, str]:
        """Préréglage de secours : PLA de l'Adventurer 5M-0.4, sinon premier trouvé."""
        profs = self._catalog.get("profiles", {})
        for key in ("FlashForge Adventurer 5M-0.4", "FlashForge Adventurer 3 Series-0.4"):
            for d, prof in profs.get(key, {}).items():
                if _mat_name(d) == "PLA":
                    return prof
        for mats in profs.values():
            for prof in mats.values():
                return prof
        return {}

    def _install_profile(self, machine_id: int, nozzle_mm: float, name: str,
                         cfg_text: str) -> bool:
        """Dépose `<machineId>_<buse>_<nom>.cfg` dans ~/.FlashPrint5/slice_profile/.
        (Aucun fichier d'index nécessaire : vérifié en GUI, un .cfg déposé apparaît
        sous « Materiau personnalisé ».) False si FlashPrint absent ou machineId
        inconnu → le .fcfg de secours prend le relais."""
        if machine_id < 0 or not FLASHPRINT_USER_DIR.exists():
            return False
        try:
            dest = FLASHPRINT_USER_DIR / "slice_profile"
            dest.mkdir(parents=True, exist_ok=True)
            fname = f"{machine_id}_{nozzle_mm:g}_{name}.cfg"
            (dest / fname).write_text(cfg_text, encoding="utf-8")
            return True
        except Exception as e:
            logger.warning(f"[FlashPrint] dépôt du profil impossible : {e}")
            return False
