"""Base de données des imprimantes Bambu Lab supportées, organisée par série."""
from __future__ import annotations

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
        "volume": "325×320×325 mm",
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
        "volume": "325×320×325 mm",
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
        "volume": "325×320×325 mm (simple) / 300×320×325 mm (double)",
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
        "volume": "325×320×325 mm",
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
        "plateau_max_temp": 60, "buse_max_temp": 300,
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
        "plateau_max_temp": 60, "buse_max_temp": 300,
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
    nozzle_max_temp, bed_max_temp. Tolérant : retombe sur les défauts de série
    puis sur un défaut CoreXY si le modèle est inconnu."""
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
    serie = p.get("serie", "")
    base = dict(_SPECS_PAR_SERIE.get(serie, _SPECS_DEFAUT))
    base.update(_SPECS_OVERRIDE.get(matched, {}))
    base["nozzle_max_temp"] = p.get("buse_max_temp", 300)
    base["bed_max_temp"] = p.get("plateau_max_temp", 100)
    return base
