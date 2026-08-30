"""Résout le config Bambu Studio complet depuis les fichiers système locaux.

Bambu Studio installe ses profils système sur chaque machine dans :
  %APPDATA%/BambuStudio/system/BBL/

La hiérarchie pour un profil process standard 0.20mm X1C est :
  fdm_process_common
    └── fdm_process_single_common
          └── fdm_process_single_0.20
                └── 0.20mm Standard @BBL X1C

On fusionne ces couches pour obtenir un config plat complet, puis on
ajoute les clés filament et machine du printer détecté.
Fonctionne sur toute machine avec Bambu Studio installé — aucun .3mf requis.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import sys
from loguru import logger

def _bbl_root() -> Path:
    """Retourne le dossier racine BambuStudio selon la plateforme."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "BambuStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BambuStudio"
    return Path.home() / ".config" / "BambuStudio"

_BBL_ROOT     = _bbl_root()
_BBL_PROCESS  = _BBL_ROOT / "system" / "BBL" / "process"
_BBL_MACHINE  = _BBL_ROOT / "system" / "BBL" / "machine"
_BBL_FILAMENT = _BBL_ROOT / "system" / "BBL" / "filament"
_BBL_USER     = _BBL_ROOT / "user"

# Profils process à fusionner dans l'ordre (du plus général au plus spécifique)
_PROCESS_CHAIN_0_20 = [
    "fdm_process_common.json",
    "fdm_process_single_common.json",
    "fdm_process_single_0.20.json",
]

# Profil process final par printer (le plus courant en premier)
_PRINTER_PROCESS_PROFILES = {
    "X1C":  "0.20mm Standard @BBL X1C.json",
    "X1":   "0.20mm Standard @BBL X1C.json",
    "P1S":  "0.20mm Standard @BBL P1S.json",
    "P1P":  "0.20mm Standard @BBL P1P.json",
    "A1":   "0.20mm Standard @BBL A1.json",
    "A1M":  "0.20mm Standard @BBL A1M.json",
    "A2L":  "0.20mm Standard @BBL A2L.json",
    "H2D":  "0.20mm Standard @BBL H2D.json",
}

# Profil filament PLA générique de base
_GENERIC_PLA_CHAIN = [
    "fdm_filament_common.json",
    "Generic PLA.json",
]


def detect_printer_model() -> str | None:
    """Détecte le modèle d'imprimante depuis les profils utilisateur existants.
    Retourne None si aucun profil n'est trouvé (l'appelant doit gérer le cas).
    """
    if not _BBL_USER.exists():
        return None

    # Chercher printer_settings_id dans les profils utilisateur
    for user_dir in _BBL_USER.iterdir():
        process_dir = user_dir / "process"
        if not process_dir.exists():
            continue
        for f in process_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                printer_id = data.get("printer_settings_id", "")
                for model in _PRINTER_PROCESS_PROFILES:
                    if model in printer_id:
                        logger.info(f"Imprimante détectée : {model} ({printer_id})")
                        return model
            except Exception:
                continue

    # Chercher dans les profils user .info
    for user_dir in _BBL_USER.iterdir():
        process_dir = user_dir / "process"
        if not process_dir.exists():
            continue
        for f in process_dir.glob("*.json"):
            fname = f.stem  # ex: "0.20mm Standard @BBL X1C - Optimal"
            for model in _PRINTER_PROCESS_PROFILES:
                if model in fname:
                    logger.info(f"Imprimante détectée depuis nom de profil : {model}")
                    return model

    return None  # aucune imprimante détectée


def _profil_standard(bbl_id: str, nozzle_mm: float):
    """Fichier « … Standard @BBL <id> [<D> nozzle].json » de la BONNE buse.

    Bambu nomme ses process par hauteur de couche + buse : « 0.20mm Standard
    @BBL X1C.json » (0,4, sans suffixe) mais « 0.10mm Standard @BBL X1C 0.2
    nozzle.json ». On scanne le dossier (robuste aux nouveaux modèles — la X2D
    n'était dans aucun dict) et on prend la hauteur la plus proche de D/2, le
    défaut Bambu par buse. None si rien (vieux BS, modèle absent)."""
    import re
    if not _BBL_PROCESS.exists():
        return None
    suffixe = "" if abs(nozzle_mm - 0.4) < 1e-6 else f" {nozzle_mm:g} nozzle"
    motif = re.compile(
        rf"^(\d+\.\d+)mm Standard @BBL {re.escape(bbl_id)}{re.escape(suffixe)}\.json$")
    cands = []
    for f in _BBL_PROCESS.iterdir():
        m = motif.match(f.name)
        if m:
            cands.append((abs(float(m.group(1)) - nozzle_mm / 2), f.name))
    return min(cands)[1] if cands else None


def _resolve_par_inherits(nom_profil: str) -> dict:
    """Fusion de la VRAIE chaîne d'héritage Bambu (champ « inherits »), racine
    vers feuille — c'est elle qui porte les largeurs de ligne par buse. La
    chaîne figée historique ignorait les variantes de buse : un export en 0,2
    gardait les largeurs 0,42–0,50 du fdm_process_common (bug remonté par un
    utilisateur X2D 0,2 — largeurs doublées, 30 h d'impression évitées)."""
    chaine, nom, vus = [], nom_profil, set()
    while nom and nom not in vus and len(chaine) < 10:
        vus.add(nom)
        path = _BBL_PROCESS / f"{nom}.json"
        if not path.exists():
            logger.warning(f"Chaînon inherits manquant : {nom}")
            break
        chaine.append(_load_json_flat(path))
        try:
            nom = json.loads(path.read_text(encoding="utf-8")).get("inherits") or ""
        except Exception:
            break
    merged: dict = {}
    for d in reversed(chaine):        # racine d'abord, la feuille surcharge
        merged.update(d)
    return merged


def resolve_from_system_profiles(printer_model: str | None = None,
                                 nozzle_mm: float = 0.4) -> dict | None:
    """Construit un config Bambu Studio complet depuis les fichiers système,
    pour LE couple (imprimante, buse) — plus jamais le process 0,4 pour tous.

    Fonctionne sur toute installation Bambu Studio sans nécessiter de .3mf.
    Retourne None si Bambu Studio n'est pas installé.
    """
    if not _BBL_PROCESS.exists():
        logger.warning("Profils système Bambu Studio introuvables.")
        return None

    if printer_model is None:
        printer_model = detect_printer_model()
    if printer_model is None:
        logger.warning("Aucune imprimante détectée — résolution impossible.")
        return None

    merged: dict = {}

    # 1+2. Process : le profil « Standard » du couple (printer, buse), résolu par
    # sa vraie chaîne inherits. Repli : l'ancienne chaîne figée 0,20 mm / 0,4.
    std = _profil_standard(printer_model, nozzle_mm)
    if std:
        merged.update(_resolve_par_inherits(Path(std).stem))
        logger.info(f"Profil process résolu par inherits : {std}")
    else:
        for filename in _PROCESS_CHAIN_0_20:
            path = _BBL_PROCESS / filename
            if path.exists():
                merged.update(_load_json_flat(path))
            else:
                logger.warning(f"Profil système manquant : {filename}")
        printer_profile = _PRINTER_PROCESS_PROFILES.get(printer_model)
        if printer_profile and (_BBL_PROCESS / printer_profile).exists():
            merged.update(_load_json_flat(_BBL_PROCESS / printer_profile))
            logger.info(f"Profil process chargé (chaîne figée) : {printer_profile}")
        else:
            logger.warning(f"Aucun profil process buse/printer pour {printer_model} "
                           f"(buse {nozzle_mm:g}) — chaîne de base seule.")

    # 3. Ajouter les clés filament (PLA générique)
    for filename in _GENERIC_PLA_CHAIN:
        path = _BBL_FILAMENT / filename
        if path.exists():
            merged.update(_load_json_flat(path))

    # 4. Ajouter les clés machine (printer)
    machine_name = _find_machine_profile(printer_model)
    if machine_name:
        machine_path = _BBL_MACHINE / machine_name
        if machine_path.exists():
            merged.update(_load_json_flat(machine_path))

    # 5. Nettoyer les clés non-pertinentes pour project_settings.config
    merged.pop("inherits", None)
    merged.pop("from", None)
    merged.pop("setting_id", None)
    merged.pop("instantiation", None)
    merged.pop("compatible_printers", None)
    merged.pop("compatible_printers_condition", None)

    # 6. Champs critiques — forcer les valeurs correctes même si les profils système
    #    contiennent des chaînes vides (setdefault ne surcharge pas les chaînes vides)
    merged["printer_settings_id"] = (
        merged.get("printer_settings_id") or _printer_settings_id(printer_model)
    )
    merged["print_settings_id"] = (
        merged.get("print_settings_id") or f"0.20mm Standard @BBL {printer_model}"
    )
    filament_id = merged.get("filament_settings_id")
    if not filament_id or filament_id == [""] or filament_id == "":
        merged["filament_settings_id"] = [f"Generic PLA @BBL {printer_model}"]
    merged.setdefault("version", "02.07.00.55")

    logger.info(f"Config résolu depuis fichiers système : {len(merged)} paramètres (printer={printer_model})")
    return merged


def _load_json_flat(path: Path) -> dict:
    """Charge un profil JSON et retourne ses clés sans les métadonnées de hiérarchie."""
    skip = {"type", "name", "inherits", "from", "setting_id", "instantiation",
            "compatible_printers", "compatible_printers_condition", "description"}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if k not in skip}
    except Exception as e:
        logger.error(f"Erreur lecture profil {path.name}: {e}")
        return {}


def _find_machine_profile(printer_model: str) -> str | None:
    """Trouve le fichier JSON du profil machine pour un modèle donné."""
    if not _BBL_MACHINE.exists():
        return None
    candidates = {
        "X1C": "Bambu Lab X1 Carbon 0.4 nozzle.json",
        "X1":  "Bambu Lab X1 0.4 nozzle.json",
        "P1S": "Bambu Lab P1S 0.4 nozzle.json",
        "P1P": "Bambu Lab P1P 0.4 nozzle.json",
        "A1":  "Bambu Lab A1 0.4 nozzle.json",
        "A1M": "Bambu Lab A1 mini 0.4 nozzle.json",
        "A2L": "Bambu Lab A2L 0.4 nozzle.json",
        "H2D": "Bambu Lab H2D 0.4 nozzle.json",
    }
    return candidates.get(printer_model)


def _printer_settings_id(printer_model: str) -> str:
    names = {
        "X1C": "Bambu Lab X1 Carbon 0.4 nozzle",
        "X1":  "Bambu Lab X1 0.4 nozzle",
        "P1S": "Bambu Lab P1S 0.4 nozzle",
        "P1P": "Bambu Lab P1P 0.4 nozzle",
        "A1":  "Bambu Lab A1 0.4 nozzle",
        "A1M": "Bambu Lab A1 mini 0.4 nozzle",
        "A2L": "Bambu Lab A2L 0.4 nozzle",
        "H2D": "Bambu Lab H2D 0.4 nozzle",
    }
    return names.get(printer_model, f"Bambu Lab {printer_model} 0.4 nozzle")
