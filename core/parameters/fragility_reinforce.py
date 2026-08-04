"""Renforcement automatique des pièces fragiles (édition multi-objets).

À partir de la thermomap de fragilité (sévérité par pièce, 0 = solide → 1 =
très fragile), neoSlice renforce PAR DÉFAUT les pièces oranges/rouges d'un
plateau (plus de parois + remplissage plus dense) et laisse les vertes/jaunes
en réglages normaux. Le résultat est mémorisé comme réglage PAR OBJET puis
ressort dans l'export d'ensemble (un seul 3MF, surcharges par objet).

Module PUR (aucune dépendance UI) → testable sans Qt ni OpenGL.

Seuils calés sur la colormap de la thermomap (viewer_3d) :
  vert 0.0 → jaune 0.35 → orange 0.62 → rouge 1.0
« orange ou rouge » (choix Emmanuel) = sévérité ≥ 0.60 ; les pièces vertes et
jaunes restent en réglages normaux.
"""
from __future__ import annotations

# Seuils de sévérité (thermomap normalisée 0..1)
FRAG_ORANGE = 0.60   # ≥ → pièce fragile (orange) : renfort modéré
FRAG_RED = 0.82      # ≥ → pièce très fragile (rouge) : renfort fort

# Paramètres de renfort par niveau (jamais EN-DESSOUS de la config de base).
_RENFORT = {
    "orange": {"wall_loops": 4, "infill_density": 30},
    "red":    {"wall_loops": 5, "infill_density": 40},
}


def niveau_fragilite(severity: float) -> str:
    """Renvoie 'green' (normal), 'orange' ou 'red' selon la sévérité."""
    try:
        s = float(severity)
    except (TypeError, ValueError):
        return "green"
    if s >= FRAG_RED:
        return "red"
    if s >= FRAG_ORANGE:
        return "orange"
    return "green"


def doit_renforcer(severity: float) -> bool:
    """Vrai si la pièce est orange/rouge → à renforcer."""
    return niveau_fragilite(severity) != "green"


def renforcer_config(base_config, severity: float):
    """Retourne une COPIE renforcée de `base_config` pour une pièce fragile,
    ou None si la pièce est verte/jaune (pas de renfort → suit les réglages
    communs). Ne réduit JAMAIS un paramètre sous sa valeur de base (max()).

    Renfort = plus de parois + remplissage plus dense (choix Emmanuel).
    """
    niveau = niveau_fragilite(severity)
    if niveau == "green":
        return None
    cible = _RENFORT[niveau]

    cfg = base_config.model_copy(deep=True)

    base_walls = int(getattr(base_config, "wall_loops", 2) or 2)
    base_infill = int(getattr(base_config, "infill_density", 15) or 15)
    cfg.wall_loops = max(base_walls, cible["wall_loops"])
    cfg.infill_density = max(base_infill, cible["infill_density"])

    # S'assurer que ces clés sont EXPORTÉES (model_fields_set → _config_to_bambu_
    # overrides les émet, donc la surcharge par objet est bien calculée).
    try:
        cfg.__pydantic_fields_set__.update({"wall_loops", "infill_density"})
    except Exception:
        pass
    return cfg


def appliquer_renfort_auto(severities: dict, base_config,
                           per_object_state: dict, actif: bool = True):
    """Applique le renforcement automatique à l'état par objet (fonction PURE,
    sans UI → testable). Retourne `(nouvel_etat, nb_renforcees, ids_retires)`.

    - `severities` : {object_id: sévérité 0..1} (thermomap).
    - `base_config` : config commune de la scène (PrintConfig) ou None.
    - `per_object_state` : dict {object_id: {config, auto_reinforced, ...}}.
    - `actif` : préférence utilisateur (case Réglages).

    Règles : les pièces oranges/rouges reçoivent une config renforcée (drapeau
    `auto_reinforced`) ; les éditions MANUELLES (config sans ce drapeau) ne sont
    jamais touchées ; une pièce redevenue verte/jaune perd son renfort AUTO ; si
    `actif` est False, tous les renforts AUTO sont retirés (manuels conservés).
    """
    state = dict(per_object_state or {})

    if not actif:
        removed = [oid for oid, st in state.items()
                   if st and st.get("auto_reinforced")]
        for oid in removed:
            state.pop(oid, None)
        return state, 0, removed

    if not severities or base_config is None:
        return state, 0, []

    count = 0
    removed: list = []
    for oid, sev in severities.items():
        st = state.get(oid)
        # Édition MANUELLE (config posée sans le drapeau auto) → intouchée.
        if st is not None and st.get("config") is not None \
                and not st.get("auto_reinforced"):
            continue
        if doit_renforcer(sev):
            cfg = renforcer_config(base_config, sev)
            if cfg is None:
                continue
            new_st = dict(st or {})
            new_st["config"] = cfg
            new_st["auto_reinforced"] = True
            new_st.setdefault("selection", None)
            new_st.setdefault("explanations", None)
            new_st.setdefault("intent_ids", None)
            state[oid] = new_st
            count += 1
        elif st is not None and st.get("auto_reinforced"):
            state.pop(oid, None)
            removed.append(oid)
    return state, count, removed
