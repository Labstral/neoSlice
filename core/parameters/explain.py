# -*- coding: utf-8 -*-
"""Explications « ce que neoSlice a CHANGÉ » — diff réel vs le profil par défaut.

Compare la config finale au profil PAR DÉFAUT (standard.yaml, réglages Bambu
bruts) et liste, champ par champ, TOUT ce qui a réellement changé — avec une
raison claire pour un débutant (pourquoi → bénéfice).

N'affiche QUE les vrais changements (pas de carte « méta ») : parois, coques,
remplissage, vitesses, températures, finition, plus brim / supports ajoutés.

Chaque entrée = {cat, titre, raison} :
  - cat    : catégorie courte en capitales (ex. « PAROIS »)
  - titre  : le changement, valeur avant → après (ex. « Parois : 3 → 5 »)
  - raison : pourquoi ce changement → bénéfice, en langage simple

Aucune dépendance UI (testable seul). Textes via l'i18n (FR + EN symétriques).
"""
from __future__ import annotations

from core.i18n import _

# Champs comparés (ordre d'affichage) : (attribut, catégorie, libellé, type)
_CHAMPS = [
    ("layer_height",              "explain.cat_quality", "explain.f_layer_h",   "mm"),
    ("wall_loops",                "explain.cat_walls",   "explain.f_walls",     "int"),
    ("wall_generator",            "explain.cat_walls",   "explain.f_wallgen",   "enum"),
    ("top_shell_layers",          "explain.cat_shells",  "explain.f_topshell",  "int"),
    ("bottom_shell_layers",       "explain.cat_shells",  "explain.f_botshell",  "int"),
    ("infill_density",            "explain.cat_infill",  "explain.f_density",   "pct"),
    ("infill_pattern",            "explain.cat_infill",  "explain.f_pattern",   "enum"),
    ("outer_wall_speed",          "explain.cat_speed",   "explain.f_outer",     "speed"),
    ("inner_wall_speed",          "explain.cat_speed",   "explain.f_inner",     "speed"),
    ("infill_speed",              "explain.cat_speed",   "explain.f_infillspd", "speed"),
    ("bridge_speed",              "explain.cat_speed",   "explain.f_bridge",    "speed"),
    ("first_layer_speed",         "explain.cat_speed",   "explain.f_first",     "speed"),
    # NB : températures buse/plateau volontairement ABSENTES — elles ne partent
    # pas dans le g-code du 3MF (slot filament neutre), seulement dans le PDF.
    # Les afficher ici comme « changé » serait trompeur.
    ("seam_position",             "explain.cat_finish",  "explain.f_seam",      "enum"),
    ("ironing_type",              "explain.cat_finish",  "explain.f_ironing",   "enum"),
    ("elefant_foot_compensation", "explain.cat_finish",  "explain.f_eleph",     "mm"),
    ("xy_contour_compensation",   "explain.cat_finish",  "explain.f_xy",        "mm"),
]


def _fmt(val, kind: str) -> str:
    if kind == "speed":
        return f"{val} mm/s"
    if kind == "temp":
        return f"{val} °C"
    if kind == "pct":
        return f"{val} %"
    if kind == "mm":
        return f"{val} mm"
    if kind == "enum":
        return str(val).replace("_", " ")
    return str(val)


def _raison(attr: str, old, new, a, intent) -> str:
    """Raison contextuelle d'un changement (analyse + objectif)."""
    strength = getattr(intent, "strength", 0.0) or 0.0
    outdoor = getattr(intent, "outdoor_resistance", 0.0) or 0.0
    frag = bool(getattr(a, "has_fragile_zones", False))
    num = isinstance(old, (int, float)) and isinstance(new, (int, float))
    down = num and new < old

    if attr == "layer_height":
        return _("explain.r_layer_fine") if down else _("explain.r_layer_thick")
    if attr == "wall_loops":
        if frag:
            mt = getattr(a, "min_wall_thickness_mm", 0.0) or 0.0
            return _("explain.r_walls_frag", min_t=f"{mt:.1f}")
        if strength > 0.6 or outdoor > 0.5:
            return _("explain.r_walls_strong")
        return _("explain.r_walls_generic")
    if attr == "wall_generator":
        return _("explain.r_wallgen")
    if attr in ("top_shell_layers", "bottom_shell_layers"):
        return _("explain.r_shells")
    if attr == "infill_density":
        return _("explain.r_density_down") if down else _("explain.r_density_up")
    if attr == "infill_pattern":
        return _("explain.r_pattern_gyroid") if new == "gyroid" else _("explain.r_pattern")
    if attr == "outer_wall_speed":
        return _("explain.r_outer_slow") if down else _("explain.r_speed_fast")
    if attr in ("inner_wall_speed", "infill_speed"):
        return _("explain.r_speed_slow_mat") if down else _("explain.r_speed_fast")
    if attr == "bridge_speed":
        return _("explain.r_bridge_slow") if down else _("explain.r_speed_fast")
    if attr == "first_layer_speed":
        return _("explain.r_first_slow") if down else _("explain.r_speed_fast")
    if attr in ("nozzle_temperature", "bed_temperature"):
        return _("explain.r_temp")
    if attr == "seam_position":
        return _("explain.r_seam")
    if attr == "ironing_type":
        return _("explain.r_ironing")
    if attr in ("elefant_foot_compensation", "xy_contour_compensation"):
        return _("explain.r_comp")
    return ""


def expliquer_config(
    intent,
    analysis,
    config,
    filament_name: str = "",
    printer_name: str = "",
    nozzle_mm: float = 0.4,
    is_litho: bool = False,
) -> list[dict]:
    """Retourne la liste des changements (voir module docstring)."""
    from core.parameters.parameter_engine import profil_par_defaut

    base = profil_par_defaut()
    a = analysis
    c = config
    exps: list[dict] = []

    def add(cat_key: str, titre: str, raison: str) -> None:
        exps.append({"cat": _(cat_key), "titre": titre, "raison": raison})

    # ── Diff champ par champ vs le profil par défaut ─────────────────────
    for attr, cat_key, lbl_key, kind in _CHAMPS:
        old = getattr(base, attr, None)
        new = getattr(c, attr, None)
        if old is None or new is None or old == new:
            continue
        titre = f"{_(lbl_key)} : {_fmt(old, kind)} → {_fmt(new, kind)}"
        add(cat_key, titre, _raison(attr, old, new, a, intent))

    # ── Brim ajouté (adhérence) ──────────────────────────────────────────
    if getattr(c, "brim_type", "no_brim") != "no_brim" and getattr(c, "brim_width", 0.0) > 0:
        w = f"{c.brim_width:.0f}"
        if getattr(a, "stability_score", 1.0) < 0.65:
            raison = _("explain.brim_reason_stab")
        elif getattr(a, "is_large_flat_part", False):
            raison = _("explain.brim_reason_flat")
        else:
            raison = _("explain.brim_reason_generic")
        add("explain.cat_brim", _("explain.brim_title", w=w), raison)

    # ── Supports ajoutés ─────────────────────────────────────────────────
    if getattr(c, "support_type", "none") not in ("none", "", None):
        kind_supp = (_("explain.supp_tree") if "tree" in c.support_type
                     else _("explain.supp_normal"))
        add("explain.cat_support",
            _("explain.support_title", kind=kind_supp), _("explain.r_support"))

    # ── Multicolore : tour de purge ──────────────────────────────────────
    if getattr(c, "enable_prime_tower", False):
        add("explain.cat_finish", _("explain.prime_title"), _("explain.r_prime"))

    # ── Lithophanie (profil imposé) ──────────────────────────────────────
    if is_litho:
        add("explain.cat_litho", _("explain.litho_title"), _("explain.litho_reason"))

    return exps
