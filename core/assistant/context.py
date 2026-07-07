"""Contexte en direct de neoSlice fourni a l'assistant IA.

A chaque question, on construit un instantane lisible de :
  - l'Espace Pro (stock filament, stock par couleur, devis / factures / clients /
    commandes, rentabilite) lu directement dans core.business.store ;
  - les parametres de generation du fichier en cours (imprimante, filament, buse,
    hauteur de couche, parois, remplissage, supports, temperatures...) ;
  - l'analyse geometrique de l'objet charge dans le viewer (dimensions, volume,
    surplombs, fragilite, stabilite, besoin de supports).

La fenetre principale enregistre un fournisseur d'etat via register_app_state().
Tout est tolerant aux erreurs : aucune exception ici ne doit casser une reponse.
"""
from __future__ import annotations
from typing import Callable, Optional

# Fournisseur d'etat applicatif (defini par la fenetre principale au demarrage).
_app_state_provider: Optional[Callable[[], dict]] = None


def register_app_state(fn: Callable[[], dict]) -> None:
    """Enregistre une fonction sans argument renvoyant l'etat courant de l'appli
    (imprimante/filament/config/analyse). Voir MainWindow._assistant_snapshot."""
    global _app_state_provider
    _app_state_provider = fn


def configured_printer() -> str:
    """Nom de l'imprimante actuellement configuree dans neoSlice (ou '' si aucune).
    Sert a cibler les FAITS IMPRIMANTE injectes a l'assistant (voir printer_kb)."""
    app = _safe(_app_state_provider, {}) if _app_state_provider else {}
    app = app or {}
    return (_get(app, "printer") or "").strip()


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _get(obj, name, default=None):
    """Lit un attribut (objet pydantic) ou une cle (dict) de facon defensive."""
    try:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
    except Exception:
        return default


def _money(v, cur: str) -> str:
    try:
        return f"{float(v):.2f} {cur}".strip()
    except Exception:
        return f"{v} {cur}".strip()


# ── Espace Pro ────────────────────────────────────────────────────────────────
def _pro_section() -> str:
    from core.business import store
    st = _safe(store.dashboard_stats, {}) or {}
    if not st:
        return ""
    cur = st.get("currency", "")
    L = ["ESPACE PRO (atelier, donnees en direct) :"]
    L.append(f"- Chiffre d'affaires : facture {_money(st.get('billed', 0), cur)}, "
             f"encaisse {_money(st.get('paid', 0), cur)}, reste du {_money(st.get('due', 0), cur)} "
             f"(ce mois : facture {_money(st.get('month_billed', 0), cur)}).")
    L.append(f"- Factures : {st.get('n_invoices', 0)} au total, {st.get('n_unpaid', 0)} impayees, "
             f"{st.get('n_overdue', 0)} en retard ({_money(st.get('overdue_amount', 0), cur)}).")
    L.append(f"- Devis : {st.get('n_quotes', 0)}. Clients : {st.get('n_clients', 0)}. "
             f"Articles au catalogue : {st.get('n_products', 0)}.")
    L.append(f"- Commandes actives : {st.get('n_orders_active', 0)} "
             f"(a faire {st.get('n_orders_todo', 0)}, en impression {st.get('n_orders_printing', 0)}).")
    if st.get("is_profitable"):
        rent = f"benefice net {_money(st.get('net_result', 0), cur)}"
    else:
        rent = (f"reste {_money(st.get('to_recover', 0), cur)} a rentabiliser "
                f"({st.get('recover_pct', 0)}% couvert)")
    L.append(f"- Rentabilite : investi {_money(st.get('invested', 0), cur)}, consommables "
             f"{_money(st.get('consumables_bought', 0), cur)} -> {rent}.")
    L.append(f"- Stock filament : {st.get('n_spools', 0)} bobines, {st.get('stock_g', 0):.0f} g, "
             f"valeur {_money(st.get('stock_value', 0), cur)}.")

    colors = _safe(store.stock_by_color, []) or []
    if colors:
        parts = []
        for c in colors[:14]:
            nom = c.get("couleur_nom") or c.get("couleur_hex") or "?"
            fin = c.get("finition")
            label = f"{c.get('materiau', '?')} {nom}" + (f" {fin}" if fin else "")
            parts.append(f"{label} : {c.get('restant_g', 0):.0f}g ({c.get('n_bobines', 0)} bob.)")
        L.append("- Stock par couleur : " + " ; ".join(parts) + ".")
    low = _safe(store.low_stock_by_color, []) or []
    if low:
        names = ", ".join(f"{c.get('materiau', '?')} {c.get('couleur_nom') or c.get('couleur_hex') or '?'}"
                          for c in low[:14])
        L.append(f"- ALERTE stock bas (a racheter) : {names}.")
    return "\n".join(L)


# ── Parametres de generation du fichier ──────────────────────────────────────
_SUPPORT_LABEL = {"none": "aucun", "normal(auto)": "normaux (auto)", "tree(auto)": "arborescents (auto)"}


def _generation_section(app: dict) -> str:
    cfg = _get(app, "config")
    printer = (_get(app, "printer") or "").strip()
    filament = (_get(app, "filament") or "").strip()
    nozzle = _get(app, "nozzle_mm")
    L = ["PARAMETRES DE GENERATION (fichier en preparation) :"]
    L.append(f"- Imprimante cible : {printer or 'non definie'}.")
    fil = filament or "non defini"
    if nozzle:
        fil += f" | buse {nozzle} mm"
    L.append(f"- Filament : {fil}.")
    if cfg is None:
        L.append("- Aucun profil genere pour l'instant (l'utilisateur n'a pas encore lance la generation).")
        return "\n".join(L)

    intent = (_get(cfg, "neoslice_intent_text") or "").strip()
    if intent:
        L.append(f"- Intention demandee : \"{intent}\".")
    L.append(f"- Couche : {_get(cfg, 'layer_height')} mm "
             f"(1re couche {_get(cfg, 'first_layer_height')} mm).")
    L.append(f"- Parois : {_get(cfg, 'wall_loops')} "
             f"({_get(cfg, 'wall_generator')}), dessus {_get(cfg, 'top_shell_layers')} / "
             f"dessous {_get(cfg, 'bottom_shell_layers')} couches.")
    L.append(f"- Remplissage : {_get(cfg, 'infill_density')}% ({_get(cfg, 'infill_pattern')}).")
    sup = _SUPPORT_LABEL.get(_get(cfg, "support_type", "none"), _get(cfg, "support_type", "none"))
    mode = _get(cfg, "neoslice_support_mode", "auto")
    L.append(f"- Supports : {sup} (mode neoSlice : {mode}, "
             f"seuil {_get(cfg, 'support_threshold_angle')} deg).")
    brim = _get(cfg, "brim_type", "no_brim")
    if brim and brim != "no_brim":
        L.append(f"- Bordure (brim) : {brim}, {_get(cfg, 'brim_width')} mm.")
    L.append(f"- Temperatures : buse {_get(cfg, 'nozzle_temperature')} deg, "
             f"plateau {_get(cfg, 'bed_temperature')} deg.")
    L.append(f"- Vitesses : paroi ext. {_get(cfg, 'outer_wall_speed')}, paroi int. "
             f"{_get(cfg, 'inner_wall_speed')}, remplissage {_get(cfg, 'infill_speed')} mm/s.")
    return "\n".join(L)


# ── Analyse de l'objet dans le viewer ────────────────────────────────────────
def _viewer_section(app: dict) -> str:
    if not _get(app, "has_mesh"):
        return "OBJET DANS LE VIEWER : aucun objet charge actuellement."
    rep = _get(app, "analysis")
    name = _get(app, "filename") or "objet charge"
    L = [f"OBJET DANS LE VIEWER : {name}."]
    if rep is None:
        L.append("- Analyse geometrique pas encore disponible (en cours ou non lancee).")
        return "\n".join(L)
    bb = _get(rep, "bounding_box_mm") or [0, 0, 0]
    try:
        L.append(f"- Dimensions : {bb[0]:.1f} x {bb[1]:.1f} x {bb[2]:.1f} mm.")
    except Exception:
        pass
    L.append(f"- Volume : {_get(rep, 'volume_cm3', 0):.1f} cm3, "
             f"surface {_get(rep, 'surface_area_cm2', 0):.1f} cm2.")
    sev = _get(rep, "overhang_severity", 0.0)
    L.append(f"- Surplombs : severite {sev:.2f} (0=aucun, 1=critique), "
             f"angle max {_get(rep, 'max_overhang_angle', 0):.0f} deg.")
    if _get(rep, "support_needed"):
        L.append(f"- Supports NECESSAIRES (ratio estime {_get(rep, 'estimated_support_ratio', 0):.2f}"
                 + (", regions flottantes detectees" if _get(rep, "has_floating_regions") else "") + ").")
    else:
        L.append("- Supports non necessaires selon l'analyse.")
    L.append(f"- Stabilite : {_get(rep, 'stability_score', 1.0):.2f} (0=instable, 1=tres stable).")
    if _get(rep, "has_fragile_zones"):
        L.append(f"- Zones fragiles detectees (paroi mini {_get(rep, 'min_wall_thickness_mm', 0):.2f} mm).")
    summ = _get(rep, "summary_text")
    if summ:
        L.append(f"- Resume : {summ}.")
    warns = _get(rep, "warnings") or []
    if warns:
        L.append("- Avertissements : " + " ; ".join(str(w) for w in warns[:5]) + ".")
    return "\n".join(L)


# ── Assemblage ────────────────────────────────────────────────────────────────
def build_context_block(max_chars: int = 7000) -> str:
    """Bloc de contexte injecte dans le prompt avant chaque reponse. Chaine vide
    si rien d'utile (l'assistant repond alors avec ses seules connaissances)."""
    app = _safe(_app_state_provider, {}) if _app_state_provider else {}
    app = app or {}
    sections = [
        _safe(_pro_section, "") or "",
        _safe(lambda: _generation_section(app), "") or "",
        _safe(lambda: _viewer_section(app), "") or "",
    ]
    text = "\n\n".join(s for s in sections if s).strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[...]"
    return ("ETAT ACTUEL DE neoSlice (utilise ces donnees reelles pour repondre "
            "precisement ; ne les invente pas, ne les recite pas telles quelles sauf "
            "si on te le demande) :\n\n" + text)
