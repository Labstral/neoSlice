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
        "ou les grandes surfaces. Un brim et une température plateau plus haute aident.",
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
    },

    DefectClass.OVER_EXTRUSION: {
        "delta_nozzle_temperature":  -5,      # °C
        "_hint": (
            "Vérifiez aussi : Flux (flow ratio) -3 à 5% dans le profil filament."
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
    },

    DefectClass.SPAGHETTI: {
        "_stop_print": True,
        "_hint": (
            "Pour éviter ce problème à l'avenir : nettoyez le plateau à l'alcool isopropylique, "
            "ajoutez un brim généreux (10 mm minimum), vérifiez la calibration de la première couche "
            "et réduisez la vitesse de la première couche."
        ),
    },

    DefectClass.PILLOWING: {
        "delta_top_shell_layers":    +2,
        "delta_top_surface_speed":   -15,     # mm/s
        "_hint": (
            "Augmentez la ventilation (refroidissement) si votre imprimante le permet."
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
    },
}


def build_diagnostic_message(defect: DefectClass, confidence: float, severity: Severity) -> str:
    """Message UI court pour l'affichage dans neoSlice."""
    label = DEFECT_LABELS_FR[defect]
    pct = int(confidence * 100)
    if severity == Severity.NONE:
        return f"✅ {label} ({pct}% de confiance)"
    elif severity == Severity.CRITICAL:
        return f"🚨 {label} ({pct}%) — Arrêt recommandé !"
    elif severity == Severity.HIGH:
        return f"⚠️ {label} ({pct}%) — Pièce potentiellement inutilisable"
    elif severity == Severity.MEDIUM:
        return f"⚠️ {label} ({pct}%) — Correction recommandée"
    else:
        return f"ℹ️ {label} ({pct}%) — Défaut cosmétique"
