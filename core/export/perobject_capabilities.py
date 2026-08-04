"""Capacités « réglages par objet » selon le slicer de sortie.

Édition par objet (neoSlice) — deux modes d'export voulus :
  (a) objet ISOLÉ  → 3MF de cet objet seul (universel, tous slicers) ;
  (b) VUE D'ENSEMBLE → UN seul 3MF avec TOUS les objets, chacun ses réglages.

Le mode (b) « plusieurs réglages dans un seul fichier » n'est PAS supporté par
tous les slicers. Ce module centralise la table de capacités + la liste blanche
des clés réellement surchargeables par objet, pour que l'UI n'offre l'option que
là où elle fonctionne (sinon → repli : un objet = un 3MF, ou réglages communs).

Base factuelle : 82 fichiers 3MF Bambu Studio RÉELS analysés (D:/Impression 3D).
Bambu Studio / OrcaSlicer stockent les réglages par objet comme
`<metadata key="…" value="…"/>` directement sous `<object …>` dans
`Metadata/model_settings.config`, avec les MÊMES clés que
`project_settings.config` et des valeurs en CHAÎNES SIMPLES (pas de tableaux).
"""
from __future__ import annotations

# ── Table de capacités : per-object dans UN seul 3MF ──────────────────────────
# Implémenté + testé pour Bambu/Orca (injection de metadata <object> dans le
# 3MF source Bambu — géométrie jamais reconstruite, donc sûr).
#
# Prusa : le format le permet (metadata <volume>) mais exige de reconstruire un
#   3MF Slic3r multi-volumes → non implémenté ici (repli batch), à activer après
#   validation réelle.
# Cura : pile de conteneurs quality_changes GLOBALE, aucun concept par-objet.
# FlashPrint : profil .cfg unique par machine, aucun réglage par-objet.
_PER_OBJECT_ONE_FILE: frozenset[str] = frozenset({"bambu", "orca"})

# Slicers dont le format 3MF DÉRIVE de Bambu (lisent la metadata <object>).
# Utile pour un éventuel élargissement ; l'implémentation actuelle ne route en
# passthrough (injection) que bambu/orca sur imprimante Bambu Lab.
_BAMBU_FAMILY: frozenset[str] = frozenset(
    {"bambu", "orca", "creality", "elegoo", "anycubic", "snapmaker"}
)


def supports_per_object_one_file(slicer: str | None) -> bool:
    """Le slicer sait-il lire plusieurs réglages par objet dans UN seul 3MF ?

    (Capacité THÉORIQUE du format ; l'export vérifie en plus que la source est un
    vrai 3MF Bambu et l'imprimante une Bambu Lab — voir main_window.)
    """
    return (slicer or "bambu").lower() in _PER_OBJECT_ONE_FILE


def is_bambu_family(slicer: str | None) -> bool:
    return (slicer or "bambu").lower() in _BAMBU_FAMILY


# ── Liste blanche des clés surchargeables PAR OBJET (Bambu/Orca) ──────────────
# Union des clés observées au niveau <object> dans les 82 fichiers Bambu réels,
# restreinte à ce que neoSlice sait produire via _config_to_bambu_overrides.
# (Les clés absentes d'ici restent GLOBALES dans project_settings.config.)
BAMBU_PER_OBJECT_KEYS: frozenset[str] = frozenset({
    # Couches / coques
    "layer_height",
    "wall_loops",
    "top_shell_layers",
    "bottom_shell_layers",
    # Remplissage
    "sparse_infill_density",
    "sparse_infill_pattern",
    # Surfaces
    "top_surface_pattern",
    "bottom_surface_pattern",
    "internal_solid_infill_pattern",
    # Vitesses (valeur SIMPLE au niveau objet, pas de tableau)
    "outer_wall_speed",
    "inner_wall_speed",
    "sparse_infill_speed",
    "internal_solid_infill_speed",
    "top_surface_speed",
    "gap_infill_speed",
    # Qualité / couture
    "seam_position",
    "seam_slope_entire_loop",
    "xy_contour_compensation",
    "xy_hole_compensation",
    # Repassage
    "ironing_type",
    # Adhérence
    "brim_type",
    "brim_width",
    # Peau floue
    "fuzzy_skin",
    "fuzzy_skin_point_distance",
    "fuzzy_skin_thickness",
    # Supports
    "enable_support",
    "support_type",
    "support_threshold_angle",
    "support_on_build_plate_only",
    "support_top_z_distance",
    "support_object_xy_distance",
    "support_interface_pattern",
    "support_interface_spacing",
    "support_filament",
    "support_interface_filament",
    "flush_into_support",
})


def _flatten(value):
    """Valeur per-objet Bambu = CHAÎNE SIMPLE. Aplati les tableaux JSON
    (`["100","100"]` → `"100"`) produits par _config_to_bambu_overrides pour
    les vitesses ; garde les autres valeurs telles quelles (en chaîne)."""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value)


def diff_per_object_overrides(base_overrides: dict, obj_overrides: dict) -> dict:
    """Réglages à écrire AU NIVEAU OBJET = ce qui diffère de la base commune.

    `base_overrides` / `obj_overrides` : sorties de _config_to_bambu_overrides
    (dict clé Bambu → valeur). Retourne `{clé: chaîne_simple}` restreint à
    BAMBU_PER_OBJECT_KEYS, uniquement pour les clés dont la valeur (aplatie)
    diffère de la base.
    """
    out: dict[str, str] = {}
    for key in BAMBU_PER_OBJECT_KEYS:
        if key not in obj_overrides:
            continue
        obj_v = _flatten(obj_overrides[key])
        base_v = _flatten(base_overrides[key]) if key in base_overrides else None
        if obj_v != base_v:
            out[key] = obj_v
    return out
