"""Actions atelier exécutables par Oen (l'assistant IA).

Oen ne fait pas qu'observer l'Espace Pro : il peut AGIR dessus. Pour ça il émet, à la
fin de sa réponse, un marqueur d'action au format :

    [[ACTION: add_spool | material=PLA | color=noir | weight_g=1000 | brand=Creality | price=20]]

Ce module extrait ces marqueurs du texte, exécute l'action réelle contre `core.business.store`
(écriture disque), et renvoie (texte_sans_marqueurs, confirmations). Le marqueur est masqué
de l'affichage (comme [[OPTIONS: …]]). Aucune exception ne doit remonter à l'UI.
"""
from __future__ import annotations
import re

# Marqueur : [[ACTION: verbe | clé=valeur | clé=valeur ]]
_ACTION_RE = re.compile(r"\[\[\s*ACTION\s*:\s*(.+?)\]\]", re.IGNORECASE | re.DOTALL)

# Noms de couleur courants (FR/EN) → hex, pour une pastille cohérente dans l'atelier.
_COLOR_HEX = {
    "noir": "#000000", "black": "#000000",
    "blanc": "#FFFFFF", "white": "#FFFFFF",
    "rouge": "#E23636", "red": "#E23636",
    "vert": "#2FA84A", "green": "#2FA84A",
    "bleu": "#2850E0", "blue": "#2850E0",
    "jaune": "#F1C40F", "yellow": "#F1C40F",
    "orange": "#E67E22",
    "gris": "#8A8A8A", "grey": "#8A8A8A", "gray": "#8A8A8A",
    "violet": "#8E44AD", "purple": "#8E44AD",
    "rose": "#FF6FA3", "pink": "#FF6FA3",
    "marron": "#8B5A2B", "brown": "#8B5A2B",
    "naturel": "#EDE6D6", "natural": "#EDE6D6", "transparent": "#DDDDDD",
    "or": "#D4AF37", "gold": "#D4AF37", "argent": "#C0C0C0", "silver": "#C0C0C0",
    "turquoise": "#1ABC9C", "cyan": "#17BEBB",
}


def _num(x, default: float = 0.0) -> float:
    try:
        s = str(x).lower().replace(",", ".").replace("chf", "").replace("€", "").replace("$", "")
        s = s.replace("kg", "").replace("g", "").strip()
        return float(s)
    except Exception:
        return default


def _hex_for(name: str, given: str | None) -> str:
    if given:
        g = given.strip()
        if not g.startswith("#"):
            g = "#" + g
        if len(g) in (4, 7):
            return g
    return _COLOR_HEX.get((name or "").strip().lower(), "#1E90FF")


def _parse_kv(body: str) -> tuple[str, dict]:
    """« verbe | k=v | k=v » → (verbe, {k: v})."""
    parts = [p.strip() for p in body.split("|")]
    verb = parts[0].split("=")[0].strip().lower() if parts else ""
    kv: dict[str, str] = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.strip().lower()] = v.strip()
    return verb, kv


def _do_add_spool(p: dict) -> str:
    from core.business import store
    material = (p.get("material") or p.get("materiau") or "PLA").upper()
    color = (p.get("color") or p.get("couleur") or p.get("color_name")
             or p.get("couleur_nom") or "").strip()
    hexc = _hex_for(color, p.get("hex") or p.get("couleur_hex"))
    weight = _num(p.get("weight_g") or p.get("poids_g") or p.get("weight")
                  or p.get("poids") or 1000, 1000.0)
    # Tolérance : si l'utilisateur/Oen a donné des kg (valeur < 20), convertir.
    raw_w = str(p.get("weight_g") or p.get("weight") or p.get("poids") or "")
    if "kg" in raw_w.lower() or (0 < weight < 20):
        weight *= 1000.0
    brand = (p.get("brand") or p.get("marque") or "").strip()
    price = _num(p.get("price") or p.get("prix") or p.get("cout") or p.get("cout_total") or 0, 0.0)

    store.add_spool({
        "materiau": material, "marque": brand,
        "couleur_nom": color, "couleur_hex": hexc,
        "poids_total_g": weight, "poids_restant_g": weight,
        "cout_total": price,
    })
    lbl = f"{material} {color}".strip()
    extra = []
    if brand:
        extra.append(brand)
    if price:
        extra.append(f"{price:.2f}")
    tail = (" — " + ", ".join(extra)) if extra else ""
    return f"✓ Bobine ajoutée à l'atelier : {lbl} · {weight / 1000:.2f} kg{tail}"


# Verbe → handler. Extensible (futur : consume_spool, update_spool…).
_HANDLERS = {
    "add_spool": _do_add_spool,
    "ajouter_bobine": _do_add_spool,
}


def parse_and_execute(text: str) -> tuple[str, list[str]]:
    """Extrait et EXÉCUTE les [[ACTION: …]] du texte. Renvoie
    (texte sans les marqueurs, liste de confirmations à afficher)."""
    confirmations: list[str] = []

    def _run(m: "re.Match") -> str:
        verb, params = _parse_kv(m.group(1))
        handler = _HANDLERS.get(verb)
        if not handler:
            return ""  # verbe inconnu → on retire juste le marqueur
        try:
            confirmations.append(handler(params))
        except Exception as exc:  # jamais casser l'UI
            confirmations.append(f"⚠ Action « {verb} » impossible : {exc}")
        return ""

    clean = _ACTION_RE.sub(_run, text).strip()
    return clean, confirmations
