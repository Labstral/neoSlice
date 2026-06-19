"""Taxonomie des défauts d'impression 3D + règles de remédiation.

Chaque défaut mappe vers des correctifs PrintConfig applicables directement
par le ParameterEngine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DefectClass(str, Enum):
    GOOD              = "good"
    STRINGING         = "stringing"
    WARPING           = "warping"
    UNDER_EXTRUSION   = "under_extrusion"
    OVER_EXTRUSION    = "over_extrusion"
    LAYER_SHIFT       = "layer_shift"
    SPAGHETTI         = "spaghetti"
    PILLOWING         = "pillowing"
    ELEPHANTS_FOOT    = "elephants_foot"
    Z_WOBBLE          = "z_wobble"


class Severity(str, Enum):
    NONE     = "none"       # bonne impression
    LOW      = "low"        # cosmétique
    MEDIUM   = "medium"     # fonctionnel affecté
    HIGH     = "high"       # pièce inutilisable
    CRITICAL = "critical"   # arrêt recommandé


@dataclass
class DiagnosticResult:
    defect: DefectClass
    confidence: float                   # 0.0 → 1.0
    severity: Severity
    all_probs: dict[str, float]         # {DefectClass.value: prob}
    remediation: dict[str, Any]         # champs PrintConfig à patcher
    message_fr: str                     # message UI
    stop_print: bool = False            # spaghetti / layer_shift critique
    uncertain: bool = False             # confiance trop faible → abstention
    embedding: list[float] = field(default_factory=list, repr=False)


# ──────────────────────────────────────────────────────────────────────────────
# Descriptions lisibles (UI)
# ──────────────────────────────────────────────────────────────────────────────

DEFECT_LABELS_FR: dict[DefectClass, str] = {
    DefectClass.GOOD:            "Bonne impression",
    DefectClass.STRINGING:       "Filaments parasites (stringing)",
    DefectClass.WARPING:         "Décollement du plateau (warping)",
    DefectClass.UNDER_EXTRUSION: "Sous-extrusion",
    DefectClass.OVER_EXTRUSION:  "Sur-extrusion",
    DefectClass.LAYER_SHIFT:     "Décalage de couche",
    DefectClass.SPAGHETTI:       "Spaghetti (échec complet)",
    DefectClass.PILLOWING:       "Peluchage couche du dessus (pillowing)",
    DefectClass.ELEPHANTS_FOOT:  "Pied d'éléphant (première couche évasée)",
    DefectClass.Z_WOBBLE:        "Surface ondulée (Z-wobble)",
}

DEFECT_DESCRIPTIONS_FR: dict[DefectClass, str] = {
    DefectClass.GOOD:
        "L'impression se déroule correctement. Aucune correction nécessaire.",
    DefectClass.STRINGING:
        "Des fils de plastique se forment entre les parties. Causé par une température "
        "trop élevée ou une rétractation insuffisante.",
    DefectClass.WARPING:
        "La pièce se décolle du plateau en refroidissant. Plus fréquent avec ABS/ASA "
        "ou les grandes surfaces. Pensez à bien nettoyer votre plateau (eau chaude + "
        "liquide vaisselle, sans gras ni traces de doigts) : une mauvaise adhérence en "
        "est souvent la cause. Un brim et une température plateau plus haute aident également.",
    DefectClass.UNDER_EXTRUSION:
        "Pas assez de matière extrudée : couches faibles, trous, lignes manquantes. "
        "Causé par une température trop basse, une vitesse trop élevée ou un engrenage usé.",
    DefectClass.OVER_EXTRUSION:
        "Trop de matière extrudée : bourrelets, surface irrégulière, dimensions incorrectes. "
        "Ajuster le flux ou baisser légèrement la température.",
    DefectClass.LAYER_SHIFT:
        "Les couches sont décalées horizontalement. Causé par une mécanique trop sollicitée "
        "ou une vitesse d'impression trop élevée.",
    DefectClass.SPAGHETTI:
        "ÉCHEC CRITIQUE — le filament s'imprime dans le vide. La pièce s'est décollée "
        "ou a bougé. Arrêt immédiat recommandé pour protéger l'imprimante.",
    DefectClass.PILLOWING:
        "La couche supérieure présente des boursouflures ou ondulations. "
        "Manque de couches top, ventilation insuffisante, ou vitesse trop élevée.",
    DefectClass.ELEPHANTS_FOOT:
        "La première couche est évasée vers l'extérieur. "
        "Plateau trop proche de la buse ou température première couche trop élevée.",
    DefectClass.Z_WOBBLE:
        "Stries horizontales ondulées sur les parois. Souvent un problème mécanique "
        "(vis Z, courroie) mais peut être amélioré en réduisant les vitesses.",
}

DEFECT_LABELS_EN: dict[DefectClass, str] = {
    DefectClass.GOOD:            "Good print",
    DefectClass.STRINGING:       "Stringing",
    DefectClass.WARPING:         "Warping (bed detachment)",
    DefectClass.UNDER_EXTRUSION: "Under-extrusion",
    DefectClass.OVER_EXTRUSION:  "Over-extrusion",
    DefectClass.LAYER_SHIFT:     "Layer shift",
    DefectClass.SPAGHETTI:       "Spaghetti (complete failure)",
    DefectClass.PILLOWING:       "Top-layer pillowing",
    DefectClass.ELEPHANTS_FOOT:  "Elephant's foot (flared first layer)",
    DefectClass.Z_WOBBLE:        "Wavy surface (Z-wobble)",
}

DEFECT_DESCRIPTIONS_EN: dict[DefectClass, str] = {
    DefectClass.GOOD:
        "The print looks fine. No correction needed.",
    DefectClass.STRINGING:
        "Thin plastic threads form between parts. Caused by a temperature that is too "
        "high or insufficient retraction.",
    DefectClass.WARPING:
        "The part lifts off the bed as it cools. More common with ABS/ASA or large "
        "surfaces. Be sure to clean your build plate (warm water + dish soap, free of "
        "grease and fingerprints): poor adhesion is often the cause. A brim and a higher "
        "bed temperature also help.",
    DefectClass.UNDER_EXTRUSION:
        "Not enough material extruded: weak layers, gaps, missing lines. Caused by a "
        "temperature too low, a speed too high, or a worn extruder gear.",
    DefectClass.OVER_EXTRUSION:
        "Too much material extruded: blobs, uneven surface, incorrect dimensions. "
        "Adjust the flow or slightly lower the temperature.",
    DefectClass.LAYER_SHIFT:
        "Layers are shifted horizontally. Caused by overstressed mechanics or a print "
        "speed that is too high.",
    DefectClass.SPAGHETTI:
        "CRITICAL FAILURE — filament is printing into the air. The part detached or "
        "moved. Immediate stop recommended to protect the printer.",
    DefectClass.PILLOWING:
        "The top layer shows bumps or waves. Not enough top layers, insufficient "
        "cooling, or a speed too high.",
    DefectClass.ELEPHANTS_FOOT:
        "The first layer flares outward. Bed too close to the nozzle or first-layer "
        "temperature too high.",
    DefectClass.Z_WOBBLE:
        "Wavy horizontal lines on the walls. Often a mechanical issue (Z screw, belt) "
        "but can be improved by reducing speeds.",
}


def defect_label(defect: DefectClass) -> str:
    """Libellé du défaut dans la langue active."""
    from core.i18n import lang
    table = DEFECT_LABELS_EN if lang() == "en" else DEFECT_LABELS_FR
    return table.get(defect, DEFECT_LABELS_FR.get(defect, defect.value))


def defect_description(defect: DefectClass) -> str:
    """Description du défaut dans la langue active."""
    from core.i18n import lang
    table = DEFECT_DESCRIPTIONS_EN if lang() == "en" else DEFECT_DESCRIPTIONS_FR
    return table.get(defect, DEFECT_DESCRIPTIONS_FR.get(defect, ""))


# Traduction française des noms de champs de correction (termes Bambu Studio en
# anglais → français lisible). Affichée entre parenthèses en mode FR uniquement.
# Clé = nom du champ nettoyé (sans préfixe "delta_", underscores → espaces).
FIELD_LABELS_FR: dict[str, str] = {
    "nozzle temperature":         "température buse",
    "bed temperature":            "température plateau",
    "outer wall speed":           "vitesse paroi externe",
    "inner wall speed":           "vitesse paroi interne",
    "infill speed":               "vitesse remplissage",
    "first layer speed":          "vitesse 1re couche",
    "top surface speed":          "vitesse surface du dessus",
    "top shell layers":           "couches du dessus",
    "brim type":                  "type de bordure",
    "brim width":                 "largeur bordure",
    "elefant foot compensation":  "compensation pied d'éléphant",
}


def field_translation_fr(field: str) -> str | None:
    """Traduction française d'un nom de champ de correction (None si inconnu)."""
    return FIELD_LABELS_FR.get(field)


# ──────────────────────────────────────────────────────────────────────────────
# Sévérité par défaut
# ──────────────────────────────────────────────────────────────────────────────

DEFECT_DEFAULT_SEVERITY: dict[DefectClass, Severity] = {
    DefectClass.GOOD:            Severity.NONE,
    DefectClass.STRINGING:       Severity.LOW,
    DefectClass.WARPING:         Severity.MEDIUM,
    DefectClass.UNDER_EXTRUSION: Severity.MEDIUM,
    DefectClass.OVER_EXTRUSION:  Severity.LOW,
    DefectClass.LAYER_SHIFT:     Severity.HIGH,
    DefectClass.SPAGHETTI:       Severity.CRITICAL,
    DefectClass.PILLOWING:       Severity.LOW,
    DefectClass.ELEPHANTS_FOOT:  Severity.LOW,
    DefectClass.Z_WOBBLE:        Severity.MEDIUM,
}


# ──────────────────────────────────────────────────────────────────────────────
# Règles de remédiation → champs PrintConfig
# ──────────────────────────────────────────────────────────────────────────────
# Valeurs : deltas (prefixe "delta_") ou valeurs absolues.
# L'engine de remédiation applique les deltas sur le PrintConfig courant,
# avec clamping aux valeurs minimales Bambu Studio.

REMEDIATION_RULES: dict[DefectClass, dict[str, Any]] = {
    DefectClass.GOOD: {},

    DefectClass.STRINGING: {
        # Baisser temp + activer rétractation agressive
        "delta_nozzle_temperature":  -5,      # °C
        "delta_outer_wall_speed":    +10,     # mm/s (déplacements plus rapides)
        # Note : retraction_distance et retraction_speed sont dans les profils filament BS,
        # non dans PrintConfig — on documente le conseil mais sans clé directe.
        "_hint": (
            "Vérifiez aussi : Rétractation +0.5 mm, Vitesse rétractation +10 mm/s "
            "dans le profil filament Bambu Studio."
        ),
        "_hint_en": (
            "Also check: Retraction +0.5 mm, Retraction speed +10 mm/s "
            "in the Bambu Studio filament profile."
        ),
    },

    DefectClass.WARPING: {
        "brim_type":                 "outer_only",
        "delta_brim_width":          +8.0,    # mm
        "delta_bed_temperature":     +5,      # °C
        "delta_first_layer_speed":   -10,     # mm/s
        "delta_nozzle_temperature":  +5,      # °C (meilleure adhérence PLA/ABS)
    },

    DefectClass.UNDER_EXTRUSION: {
        "delta_nozzle_temperature":  +5,      # °C
        "delta_outer_wall_speed":    -15,     # mm/s (% relatif appliqué en code)
        "delta_infill_speed":        -20,     # mm/s
        "_hint": (
            "Vérifiez aussi : Flux (flow ratio) +3 à 5% dans le profil filament. "
            "Nettoyez la buse si le problème persiste."
        ),
        "_hint_en": (
            "Also check: Flow ratio +3 to 5% in the filament profile. "
            "Clean the nozzle if the problem persists."
        ),
    },

    DefectClass.OVER_EXTRUSION: {
        "delta_nozzle_temperature":  -5,      # °C
        "_hint": (
            "Vérifiez aussi : Flux (flow ratio) -3 à 5% dans le profil filament."
        ),
        "_hint_en": (
            "Also check: Flow ratio -3 to 5% in the filament profile."
        ),
    },

    DefectClass.LAYER_SHIFT: {
        "delta_outer_wall_speed":    -20,     # mm/s
        "delta_inner_wall_speed":    -20,     # mm/s
        "delta_infill_speed":        -30,     # mm/s
        "delta_first_layer_speed":   -5,      # mm/s
        "_hint": (
            "Vérifiez les courroies et l'état mécanique de l'imprimante. "
            "Un décalage mécanique ne peut pas être résolu uniquement par les paramètres."
        ),
        "_hint_en": (
            "Check the belts and the printer's mechanical condition. "
            "A mechanical shift cannot be fixed by settings alone."
        ),
    },

    DefectClass.SPAGHETTI: {
        "_stop_print": True,
        "_hint": (
            "Pour éviter ce problème à l'avenir : nettoyez le plateau à l'eau chaude "
            "et au liquide vaisselle (le plus efficace pour dégraisser), ou à défaut à "
            "l'alcool isopropylique ; ajoutez un brim généreux (10 mm minimum), vérifiez "
            "la calibration de la première couche et réduisez sa vitesse."
        ),
        "_hint_en": (
            "To avoid this in the future: clean the bed with warm water and dish soap "
            "(most effective for degreasing), or failing that with isopropyl alcohol; "
            "add a generous brim (10 mm minimum), check the first-layer calibration and "
            "reduce its speed."
        ),
    },

    DefectClass.PILLOWING: {
        "delta_top_shell_layers":    +2,
        "delta_top_surface_speed":   -15,     # mm/s
        "_hint": (
            "Augmentez la ventilation (refroidissement) si votre imprimante le permet."
        ),
        "_hint_en": (
            "Increase cooling (fan) if your printer allows it."
        ),
    },

    DefectClass.ELEPHANTS_FOOT: {
        "delta_elefant_foot_compensation": +0.1,  # mm
        "delta_first_layer_speed":         -5,    # mm/s
        "delta_bed_temperature":           -3,    # °C (plateau trop chaud = plastique mou)
    },

    DefectClass.Z_WOBBLE: {
        "delta_outer_wall_speed":    -20,     # mm/s
        "delta_inner_wall_speed":    -20,     # mm/s
        "_hint": (
            "Z-wobble est souvent mécanique (vis Z mal lubrifiée, jeu). "
            "Inspectez et lubrifiez la vis Z."
        ),
        "_hint_en": (
            "Z-wobble is often mechanical (poorly lubricated Z screw, play). "
            "Inspect and lubricate the Z screw."
        ),
    },
}


def build_diagnostic_message(defect: DefectClass, confidence: float, severity: Severity) -> str:
    """Message UI court pour l'affichage dans neoSlice (langue active)."""
    from core.i18n import lang
    en = lang() == "en"
    label = defect_label(defect)
    pct = int(confidence * 100)
    if severity == Severity.NONE:
        suffix = "confidence" if en else "de confiance"
        return f"✅ {label} ({pct}% {suffix})"
    elif severity == Severity.CRITICAL:
        return f"🚨 {label} ({pct}%) — " + ("Stop recommended!" if en else "Arrêt recommandé !")
    elif severity == Severity.HIGH:
        return f"⚠️ {label} ({pct}%) — " + ("Part may be unusable" if en else "Pièce potentiellement inutilisable")
    elif severity == Severity.MEDIUM:
        return f"⚠️ {label} ({pct}%) — " + ("Correction recommended" if en else "Correction recommandée")
    else:
        return f"ℹ️ {label} ({pct}%) — " + ("Cosmetic defect" if en else "Défaut cosmétique")
