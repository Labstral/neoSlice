"""Base de données des imprimantes supportées.

- Bambu Lab : catalogue enrichi à la main (PRINTERS), groupé par série.
- Autres marques (Creality, Prusa, Anycubic, Flashforge, Elegoo, Qidi) : catalogue
  généré depuis les profils officiels Bambu Studio + OrcaSlicer
  (data/printers_catalog.json pour l'UI, data/printer_machines.json pour le 3MF).
  Voir tools/extract_printers.py.
"""
from __future__ import annotations
import functools
import json
from pathlib import Path

# Ordre d'affichage des séries dans les sélecteurs
SERIES_ORDRE = ["Série H2", "Série X", "Série P", "Série A"]

PRINTERS: dict[str, dict] = {

    # ── Série H2 — ordre croissant : H2S → H2C → H2D → H2D Pro ──────────
    "H2S": {
        "serie": "Série H2",
        "nom_complet": "Bambu Lab H2S",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": True,
        "plateau_max_temp": 120, "buse_max_temp": 350,
        "volume": "340×320×340 mm",
        "couleurs_max": 16,
        "particularites": ["Variante simplifiée du H2D", "Double extrusion"],
        "filaments_incompatibles": [],
    },
    "H2C": {
        "serie": "Série H2",
        "nom_complet": "Bambu Lab H2C",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": True,
        "plateau_max_temp": 120, "buse_max_temp": 350,
        "volume": "330×320×325 mm",
        "couleurs_max": 7,
        "particularites": ["Changement automatique de buses sans purge", "7 couleurs simultanées", "Réduction waste filament"],
        "filaments_incompatibles": [],
    },
    "H2D": {
        "serie": "Série H2",
        "nom_complet": "Bambu Lab H2D",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": True,
        "plateau_max_temp": 120, "buse_max_temp": 350,
        "volume": "350×320×325 mm (simple) / 300×320×325 mm (double)",
        "couleurs_max": 25,
        "particularites": ["Double extrudeur", "Compatible laser/cutter", "Chambre chauffée"],
        "filaments_incompatibles": [],
    },
    "H2D Pro": {
        "serie": "Série H2",
        "nom_complet": "Bambu Lab H2D Pro",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": True,
        "plateau_max_temp": 120, "buse_max_temp": 350,
        "volume": "350×320×325 mm",
        "couleurs_max": 25,
        "particularites": ["Laser avancé", "Air assist intégré", "Fonctions professionnelles"],
        "filaments_incompatibles": [],
    },

    # ── Série X — ordre croissant : X1 Carbon → X1E → X2D ────────────────
    "X1 Carbon": {
        "serie": "Série X",
        "nom_complet": "Bambu Lab X1 Carbon",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 120, "buse_max_temp": 300,
        "volume": "256×256×256 mm",
        "couleurs_max": 16,
        "particularites": ["CoreXY haute vitesse", "LiDAR intégré", "Caméra IA"],
        "filaments_incompatibles": [],
    },
    "X1E": {
        "serie": "Série X",
        "nom_complet": "Bambu Lab X1E",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 120, "buse_max_temp": 320,
        "volume": "256×256×256 mm",
        "couleurs_max": 16,
        "particularites": ["Variante industrielle X1C", "Buse 320°C", "Wi-Fi et Ethernet"],
        "filaments_incompatibles": [],
    },
    "X2D": {
        "serie": "Série X",
        "nom_complet": "Bambu Lab X2D",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": True,
        "plateau_max_temp": 120, "buse_max_temp": 300,
        "volume": "256×256×260 mm",
        "couleurs_max": 16,
        "particularites": ["Double extrudeur ultra-léger", "Chambre chauffée active 60-65°C", "IA avancée", "Supports solubles"],
        "filaments_incompatibles": [],
    },

    # ── Série P — ordre croissant : P1 → P1S → P2S ───────────────────────
    "P1": {
        "serie": "Série P",
        "nom_complet": "Bambu Lab P1",
        "enceinte": False, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 100, "buse_max_temp": 300,
        "volume": "256×256×256 mm",
        "couleurs_max": 16,
        "particularites": ["Open frame", "Entrée de gamme série P"],
        "filaments_incompatibles": ["ABS", "ASA", "PC", "PA-CF"],
    },
    "P1S": {
        "serie": "Série P",
        "nom_complet": "Bambu Lab P1S",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 120, "buse_max_temp": 300,
        "volume": "256×256×256 mm",
        "couleurs_max": 16,
        "particularites": ["CoreXY rapide", "Excellent rapport qualité/prix"],
        "filaments_incompatibles": [],
    },
    "P2S": {
        "serie": "Série P",
        "nom_complet": "Bambu Lab P2S",
        "enceinte": True, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 120, "buse_max_temp": 300,
        "volume": "256×256×256 mm",
        "couleurs_max": 16,
        "particularites": ["Successeur P1S", "Très rapide", "Caméra IA intégrée", "Extrusion renforcée"],
        "filaments_incompatibles": [],
    },

    # ── Série A — ordre croissant : A1 Mini → A1 → A2L ───────────────────
    "A1 Mini": {
        "serie": "Série A",
        "nom_complet": "Bambu Lab A1 Mini",
        "enceinte": False, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 80, "buse_max_temp": 300,
        "volume": "180×180×180 mm",
        "couleurs_max": 4,
        "particularites": ["Bed slinger compact", "AMS Lite compatible"],
        "filaments_incompatibles": ["ABS", "ASA", "PC", "Nylon", "PA-CF", "PETG-CF", "TPE"],
    },
    "A1": {
        "serie": "Série A",
        "nom_complet": "Bambu Lab A1",
        "enceinte": False, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 100, "buse_max_temp": 300,
        "volume": "256×256×256 mm",
        "couleurs_max": 4,
        "particularites": ["Bed slinger", "AMS Lite inclus"],
        "filaments_incompatibles": ["ABS", "ASA", "PC", "Nylon", "PA-CF", "PETG-CF", "TPE"],
    },
    "A2L": {
        "serie": "Série A",
        "nom_complet": "Bambu Lab A2L",
        "enceinte": False, "ams": True, "multi_couleur": True,
        "double_extrudeur": False,
        "plateau_max_temp": 80, "buse_max_temp": 300,
        "volume": "330×320×325 mm",
        "couleurs_max": 19,
        "particularites": ["Bed slinger grand format", "AMS Lite (jusqu'à 19 couleurs)", "Servo PMSM boucle fermée", "Module découpe/dessin modulaire"],
        "filaments_incompatibles": ["ABS", "ASA", "PC", "Nylon", "PA-CF", "PETG-CF"],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Specs de MOUVEMENT (specs officielles Bambu Lab 2024-2025).
# Sources : pages tech-specs Bambu Lab, comparatifs, forum.
# Sert à générer des paramètres cohérents avec les limites réelles de la machine.
#
# Réalité importante : la plupart des Bambu partagent 500 mm/s max. Les vrais
# différenciateurs sont l'ACCÉLÉRATION (bed slinger série A = 10 000 vs CoreXY
# 20 000) et le DÉBIT VOLUMÉTRIQUE max du hotend (le vrai facteur limitant).
# Valeurs par série, avec surcharges par modèle connu.
# ──────────────────────────────────────────────────────────────────────────────

_SPECS_PAR_SERIE: dict[str, dict] = {
    # max_speed_mms : vitesse linéaire max | max_accel_mms2 : accélération max
    # max_flow_mm3s : débit volumétrique max du hotend standard (0.4 mm)
    "Série A":  {"max_speed_mms": 500,  "max_accel_mms2": 10000, "max_flow_mm3s": 28, "bed_slinger": True},
    "Série P":  {"max_speed_mms": 500,  "max_accel_mms2": 20000, "max_flow_mm3s": 32, "bed_slinger": False},
    "Série X":  {"max_speed_mms": 500,  "max_accel_mms2": 20000, "max_flow_mm3s": 32, "bed_slinger": False},
    "Série H2": {"max_speed_mms": 600,  "max_accel_mms2": 20000, "max_flow_mm3s": 40, "bed_slinger": False},
}

# Surcharges par modèle (specs spécifiques connues).
_SPECS_OVERRIDE: dict[str, dict] = {
    "A1 Mini":  {"max_flow_mm3s": 24},                       # hotend plus petit
    "H2D":      {"max_speed_mms": 600, "max_flow_mm3s": 40}, # 1000 mm/s toolhead, ~600 en impression
    "H2D Pro":  {"max_speed_mms": 600, "max_flow_mm3s": 65}, # hotend haut débit
    "P1":       {"max_flow_mm3s": 28},                       # hotend standard d'entrée de gamme
}

_SPECS_DEFAUT = {"max_speed_mms": 500, "max_accel_mms2": 20000, "max_flow_mm3s": 32, "bed_slinger": False}


def printer_specs(name: str) -> dict:
    """Specs de mouvement + limites thermiques d'une imprimante.

    Renvoie : max_speed_mms, max_accel_mms2, max_flow_mm3s, bed_slinger,
    nozzle_max_temp, bed_max_temp. Gère les Bambu Lab (PRINTERS) ET les marques
    tierces (catalogue). Tolérant : retombe sur les défauts de série puis sur un
    défaut CoreXY si le modèle est inconnu."""
    p = PRINTERS.get(name, {})
    matched = name
    if not p and name:
        # Tolérant : casse / sous-chaîne (ex. "x1 carbon", "X1C" → "X1 Carbon")
        low = name.lower()
        for k in PRINTERS:
            kl = k.lower()
            if kl == low or kl in low or low in kl:
                p, matched = PRINTERS[k], k
                break
    if p:   # Bambu Lab
        serie = p.get("serie", "")
        base = dict(_SPECS_PAR_SERIE.get(serie, _SPECS_DEFAUT))
        base.update(_SPECS_OVERRIDE.get(matched, {}))
        base["nozzle_max_temp"] = p.get("buse_max_temp", 300)
        base["bed_max_temp"] = p.get("plateau_max_temp", 100)
        return base

    # Marque tierce : specs depuis le catalogue (par printer_model)
    m = _by_model().get(name)
    if m:
        gc = (m.get("gcode") or "").lower()
        klipper = "klipper" in gc
        marlin2 = "marlin2" in gc
        # Débit volumétrique absent des profils machine → estimation prudente par
        # firmware (proxy de génération) : klipper haute vitesse > marlin2 moderne
        # (Prusa MK4/Core One) > marlin i3 legacy. Volontairement conservateur pour
        # ne JAMAIS sur-vitesser ; l'utilisateur peut imprimer plus vite à la main.
        flow = 22 if klipper else (16 if marlin2 else 10)
        return {
            "max_speed_mms": int(m.get("max_speed", 500)),
            "max_accel_mms2": int(m.get("max_accel", 10000)),
            "max_flow_mm3s": flow,
            "bed_slinger": not klipper,
            # Hotends modernes klipper/marlin2 souvent tout-métal (≈300°C) ; marlin
            # legacy ≈260°C. La couche filament plafonne ensuite selon le matériau.
            "nozzle_max_temp": 300 if (klipper or marlin2) else 260,
            "bed_max_temp": 110 if klipper else 100,
        }

    # Inconnu → défaut CoreXY prudent
    base = dict(_SPECS_DEFAUT)
    base["nozzle_max_temp"] = 300
    base["bed_max_temp"] = 100
    return base


# ──────────────────────────────────────────────────────────────────────────────
# Catalogue multi-marques (Creality, Prusa, Anycubic, Flashforge, Elegoo, Qidi)
# Généré depuis les profils officiels — voir tools/extract_printers.py.
# ──────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parent

# Ordre d'affichage des marques dans le sélecteur (Bambu Lab géré via SERIES_ORDRE)
MARQUES_ORDRE = ["Bambu Lab", "Creality", "Prusa", "Anycubic",
                 "Flashforge", "Elegoo", "Qidi"]

# Marques grand public affichées DIRECTEMENT dans le menu ; les autres sont
# regroupées sous « Autres marques » pour raccourcir le menu (beaucoup de marques).
POPULAR_BRANDS = [
    "Creality", "Prusa", "Anycubic", "Elegoo", "Sovol", "Voron", "Snapmaker",
    "Artillery", "Qidi", "Flashforge", "Anker", "FLSun", "Geeetech", "Raise3D",
    "UltiMaker", "Tronxy", "TwoTrees",
]


def split_popular(brands: list[str]) -> tuple[list[str], list[str]]:
    """Sépare une liste de marques en (courantes présentes, autres) en préservant
    l'ordre : les courantes dans l'ordre de POPULAR_BRANDS, le reste tel quel."""
    popular = [b for b in POPULAR_BRANDS if b in brands]
    others = [b for b in brands if b not in popular]
    return popular, others


def split_popular_souple(brands: list[str]) -> tuple[list[str], list[str]]:
    """Comme split_popular, mais comparaison SOUPLE (préfixe, insensible casse) —
    les fabricants Cura sont suffixés différemment du nom usuel ('Creality3D',
    'Ultimaker B.V.' au lieu de 'Creality'/'UltiMaker'), l'égalité stricte les
    ratait tous et les reléguait dans « Autres marques »."""
    def _norm(s: str) -> str:
        return s.lower().split(" ")[0].rstrip("3d.").strip()
    by_norm = {_norm(b): b for b in brands}
    popular = [by_norm[_norm(p)] for p in POPULAR_BRANDS if _norm(p) in by_norm]
    others = [b for b in brands if b not in popular]
    return popular, others


@functools.lru_cache(maxsize=1)
def _catalogue() -> dict:
    try:
        return json.loads((_DATA_DIR / "printers_catalog.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _machines() -> dict:
    try:
        return json.loads((_DATA_DIR / "printer_machines.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _display_model(model_key: str, marque: str) -> str:
    """Retire le préfixe marque pour un affichage propre sous l'en-tête de marque."""
    first_brand_word = marque.split(" ")[0].lower()
    parts = model_key.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == first_brand_word:
        return parts[1]
    return model_key


@functools.lru_cache(maxsize=1)
def _by_model() -> dict:
    """Index : printer_model → {marque, display, nozzles:{nz_str: profile_name}, slicers, specs}."""
    out: dict[str, dict] = {}
    for name, e in _catalogue().items():
        mk = e.get("printer_model") or name
        slot = out.setdefault(mk, {
            "marque": e.get("marque", ""),
            "display": _display_model(mk, e.get("marque", "")),
            "nozzles": {},
            "slicers": set(),
            "bed_size": e.get("bed_size", ""),
            "height": e.get("printable_height", ""),
            "max_speed": e.get("max_speed_mms", 500),
            "max_accel": e.get("max_accel_mms2", 10000),
            "gcode": e.get("gcode_flavor", ""),
        })
        slot["nozzles"][str(e.get("nozzle_diameter", "0.4"))] = name
        slot["slicers"].update(e.get("slicers", ["bambu", "orca"]))
    return out


def _fmt_nozzle(mm: float) -> str:
    return f"{float(mm):g}"


def _brand_sort_key(b: str):
    """Marques prioritaires en tête, puis ordre alphabétique."""
    prio = [m for m in MARQUES_ORDRE if m != "Bambu Lab"]
    return (prio.index(b) if b in prio else len(prio), b.lower())


def _slicer_supported(slicer: str, entry_slicers, marque: str) -> bool:
    """Un modèle est-il proposé pour ce slicer de sortie ?

    Anycubic Slicer (Next) et Snapmaker Orca sont des forks d'OrcaSlicer :
      • snapmaker embarque TOUTE la bibliothèque OrcaSlicer → disponibilité « orca » ;
      • anycubic n'embarque que le vendor Anycubic → marque Anycubic uniquement,
        + les modèles tagués « anycubic » absents d'OrcaSlicer (ex. Kobra 3 V2)."""
    es = entry_slicers or []
    if slicer == "snapmaker":
        return "orca" in es or "snapmaker" in es
    if slicer == "anycubic":
        return marque == "Anycubic" and ("orca" in es or "anycubic" in es)
    return slicer in es


def catalogue_brands(slicer: str = "orca") -> list[str]:
    """Marques tierces ayant ≥1 modèle supporté par ce slicer (bambu/orca/…)."""
    present = {v["marque"] for v in _by_model().values()
               if _slicer_supported(slicer, v["slicers"], v["marque"])}
    return sorted(present, key=_brand_sort_key)


def models_for_brand(brand: str, slicer: str = "orca") -> list[tuple[str, str]]:
    """[(libellé affiché, model_key)] triés, pour une marque et un slicer donnés."""
    items = [(v["display"], mk) for mk, v in _by_model().items()
             if v["marque"] == brand and _slicer_supported(slicer, v["slicers"], v["marque"])]
    return sorted(items, key=lambda t: t[0].lower())


def nozzles_for_model(model_key: str) -> list[float]:
    """Diamètres de buse réellement disponibles pour ce modèle (triés)."""
    nz = _by_model().get(model_key, {}).get("nozzles", {})
    return sorted(float(x) for x in nz)


def profile_name_for(model_key: str, nozzle_mm: float) -> str | None:
    """Nom exact du profil (ex. 'Creality Ender-3 V3 0.4 nozzle') pour le 3MF."""
    nz = _by_model().get(model_key, {}).get("nozzles", {})
    if not nz:
        return None
    target = _fmt_nozzle(nozzle_mm)
    if target in nz:
        return nz[target]
    # Repli : buse la plus proche
    closest = min(nz, key=lambda k: abs(float(k) - float(nozzle_mm)))
    return nz[closest]


def machine_config_for(profile_name: str) -> dict:
    """Config machine COMPLÈTE (résolue) pour injection dans project_settings.config."""
    return dict(_machines().get(profile_name, {}))


def is_catalogue_model(model_key: str) -> bool:
    """True si l'identifiant correspond à une imprimante du catalogue (non-Bambu)."""
    return model_key in _by_model()


def brand_of(model_key: str) -> str:
    """Marque d'un model_key catalogue ('' si Bambu/inconnu)."""
    return _by_model().get(model_key, {}).get("marque", "")


# ──────────────────────────────────────────────────────────────────────────────
# Catalogue PrusaSlicer (sortie « PrusaSlicer ») — data/prusa_printers.json
# ──────────────────────────────────────────────────────────────────────────────
import re as _re


@functools.lru_cache(maxsize=1)
def _prusa_catalogue() -> dict:
    try:
        return json.loads((_DATA_DIR / "prusa_printers.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _prusa_display(preset_name: str) -> str:
    """Retire les infos de buse du nom de preset PrusaSlicer (formats variés) :
    'Original Prusa MK4S 0.4 nozzle', 'Creality CR-10 (0.3 mm nozzle)',
    'Switchwire - 0.4mm Nozzle (High Flow)' → libellé propre."""
    s = preset_name
    s = _re.sub(r"\s*\([^)]*\)", "", s)                       # parenthèses (… nozzle), (High Flow)
    s = _re.sub(r"\s*[-–]?\s*(HF)?\d(\.\d+)?\s*(mm)?\s*nozzle", "", s, flags=_re.I)  # 0.4 nozzle / 0.4mm Nozzle
    s = _re.sub(r"\s*[-–]\s*$", "", s)                        # tiret traînant
    return _re.sub(r"\s+", " ", s).strip()


def _prusa_display_brand(preset: str, brand: str) -> str:
    """Libellé d'un modèle Prusa sans la buse, et sans le préfixe marque si présent."""
    disp = _prusa_display(preset)
    bw = brand.split(" ")[0].lower()
    parts = disp.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == bw:
        return parts[1]
    return disp


@functools.lru_cache(maxsize=1)
def _prusa_by_model() -> dict:
    """Index : printer_model → {marque, display, nozzles:{nz_str: preset_name}}."""
    out: dict[str, dict] = {}
    for preset, e in _prusa_catalogue().items():
        mk = e.get("printer_model") or preset
        brand = e.get("marque", "Prusa")
        slot = out.setdefault(mk, {
            "marque": brand,
            "display": _prusa_display_brand(preset, brand),
            "nozzles": {},
        })
        slot["nozzles"][str(e.get("nozzle_diameter", "0.4"))] = preset
    return out


# Ordre d'affichage des marques en mode PrusaSlicer (Prusa en tête, reste alpha)
def prusa_brands() -> list[str]:
    """Marques présentes dans le catalogue PrusaSlicer (Prusa en premier)."""
    present = sorted({v["marque"] for v in _prusa_by_model().values()},
                     key=lambda b: (b != "Prusa", b.lower()))
    return present


def prusa_models_for_brand(brand: str) -> list[tuple[str, str]]:
    """[(libellé affiché, model_key)] triés, pour une marque en mode PrusaSlicer."""
    items = [(v["display"], mk) for mk, v in _prusa_by_model().items()
             if v["marque"] == brand]
    return sorted(items, key=lambda t: t[0].lower())


def prusa_models() -> list[tuple[str, str]]:
    """[(libellé affiché, model_key)] triés (toutes marques) — compat."""
    items = [(v["display"], mk) for mk, v in _prusa_by_model().items()]
    return sorted(items, key=lambda t: t[0].lower())


def prusa_nozzles_for_model(model_key: str) -> list[float]:
    nz = _prusa_by_model().get(model_key, {}).get("nozzles", {})
    return sorted(float(x) for x in nz)


def prusa_preset_for(model_key: str, nozzle_mm: float) -> str | None:
    """Nom de preset PrusaSlicer exact (ex. 'Original Prusa MK4S 0.4 nozzle')."""
    nz = _prusa_by_model().get(model_key, {}).get("nozzles", {})
    if not nz:
        return None
    target = _fmt_nozzle(nozzle_mm)
    if target in nz:
        return nz[target]
    closest = min(nz, key=lambda k: abs(float(k) - float(nozzle_mm)))
    return nz[closest]


def is_prusa_model(model_key: str) -> bool:
    return model_key in _prusa_by_model()


# ──────────────────────────────────────────────────────────────────────────────
# Catalogue Cura (sortie « Cura ») — data/cura_printers.json
# Voir tools/extract_cura_printers.py (définitions officielles UltiMaker Cura,
# résolues via leur chaîne `inherits` ; buses via l'index des fichiers variant).
# ──────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _cura_catalogue() -> dict:
    try:
        return json.loads((_DATA_DIR / "cura_printers.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cura_display(machine_id: str, name: str, brand: str) -> str:
    """Nom affiché sans le préfixe marque (déjà affiché comme en-tête du menu).
    Comparaison souple (prefix) : marque officielle Cura souvent suffixée
    ('Creality3D', 'Ultimaker B.V.') alors que le nom du modèle utilise la forme
    courte ('Creality Ender-3')."""
    bw = brand.split(" ")[0].split(".")[0].lower()
    parts = name.split(" ", 1)
    if len(parts) == 2:
        fw = parts[0].lower()
        if fw == bw or bw.startswith(fw) or fw.startswith(bw):
            return parts[1]
    return name


@functools.lru_cache(maxsize=1)
def _cura_by_model() -> dict:
    """Index : machine_id -> {marque, display, nozzles, ...specs}."""
    out: dict[str, dict] = {}
    for machine_id, e in _cura_catalogue().items():
        brand = e.get("manufacturer") or "Autre"
        out[machine_id] = {
            "marque": brand,
            "display": _cura_display(machine_id, e.get("name", machine_id), brand),
            "nozzles": e.get("nozzles", [0.4]),
            "width": e.get("width", 200.0),
            "depth": e.get("depth", 200.0),
            "height": e.get("height", 200.0),
            "center_is_zero": e.get("center_is_zero", False),
            "extruder_count": e.get("extruder_count", 1),
            "heated_bed": e.get("heated_bed", False),
            "gcode_flavor": e.get("gcode_flavor", ""),
            "quality_definition": e.get("quality_definition", machine_id),
            "extruder_defs": e.get("extruder_defs", [f"{machine_id}_extruder_0"]),
        }
    return out


def cura_brands() -> list[str]:
    """Marques présentes dans le catalogue Cura (Ultimaker en tête, reste alpha)."""
    present = sorted({v["marque"] for v in _cura_by_model().values()},
                     key=lambda b: (not b.lower().startswith("ultimaker"), b.lower()))
    return present


def cura_models_for_brand(brand: str) -> list[tuple[str, str]]:
    """[(libellé affiché, machine_id)] triés, pour une marque en mode Cura."""
    items = [(v["display"], mk) for mk, v in _cura_by_model().items()
             if v["marque"] == brand]
    return sorted(items, key=lambda t: t[0].lower())


def cura_models() -> list[tuple[str, str]]:
    """[(libellé affiché, machine_id)] triés (toutes marques) — compat."""
    items = [(v["display"], mk) for mk, v in _cura_by_model().items()]
    return sorted(items, key=lambda t: t[0].lower())


def cura_nozzles_for_model(machine_id: str) -> list[float]:
    return sorted(float(x) for x in _cura_by_model().get(machine_id, {}).get("nozzles", [0.4]))


def cura_machine_for(machine_id: str) -> dict:
    """Specs COMPLÈTES résolues (dimensions, extrudeurs, g-code…) pour le 3MF projet."""
    return dict(_cura_by_model().get(machine_id, {}))


def is_cura_model(machine_id: str) -> bool:
    return machine_id in _cura_by_model()
