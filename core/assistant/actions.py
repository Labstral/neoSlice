"""Actions atelier exécutables par Oen (l'assistant IA) — CRÉER dans l'Espace Pro.

Oen ne fait pas qu'observer l'Espace Pro : il peut AGIR dessus. Il émet, en fin de
réponse, UN marqueur d'action au format :

    [[ACTION: <verbe> <json>]]

Ex. : [[ACTION: add_client {"nom": "Jean Dupont", "email": "j@ex.com", "ville": "Genève"}]]
      [[ACTION: add_quote {"client": "Jean Dupont", "items": [{"designation": "Figurine", "qty": 2, "unit_price": 15}]}]]

Ce module extrait ces marqueurs, exécute l'action réelle contre `core.business.store`
(écriture disque), et renvoie (texte_sans_marqueurs, confirmations). Le marqueur est
masqué de l'affichage (comme [[OPTIONS: …]]). AUCUNE exception ne remonte à l'UI :
chaque handler renvoie une chaîne de confirmation OU un message d'erreur clair (préfixe
« ⚠ ») qu'Oen relaie à l'utilisateur.

Données SENSIBLES (gestion d'entreprise) : on ne devine JAMAIS un montant, on résout les
références (client par nom) et on refuse proprement si une info requise manque.
"""
from __future__ import annotations
import json
import re

# Marqueur : [[ACTION: verbe {json}]] ou (rétro-compat) [[ACTION: verbe | k=v | k=v]]
_ACTION_RE = re.compile(r"\[\[\s*ACTION\s*:\s*(.+?)\]\]", re.IGNORECASE | re.DOTALL)
_VERB_RE = re.compile(r"^\s*([a-zA-Z_]+)\s*(.*)$", re.DOTALL)

# Noms de couleur courants (FR/EN) → hex, pour une pastille cohérente dans l'atelier.
_COLOR_HEX = {
    "noir": "#000000", "black": "#000000", "blanc": "#FFFFFF", "white": "#FFFFFF",
    "rouge": "#E23636", "red": "#E23636", "vert": "#2FA84A", "green": "#2FA84A",
    "bleu": "#2850E0", "blue": "#2850E0", "jaune": "#F1C40F", "yellow": "#F1C40F",
    "orange": "#E67E22", "gris": "#8A8A8A", "grey": "#8A8A8A", "gray": "#8A8A8A",
    "violet": "#8E44AD", "purple": "#8E44AD", "rose": "#FF6FA3", "pink": "#FF6FA3",
    "marron": "#8B5A2B", "brown": "#8B5A2B", "naturel": "#EDE6D6", "natural": "#EDE6D6",
    "transparent": "#DDDDDD", "or": "#D4AF37", "gold": "#D4AF37", "argent": "#C0C0C0",
    "silver": "#C0C0C0", "turquoise": "#1ABC9C", "cyan": "#17BEBB",
}


# ── Utilitaires ───────────────────────────────────────────────────────────────
def _num(x, default: float = 0.0) -> float:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).lower()
        for junk in ("chf", "eur", "€", "usd", "$", "kg", "g", "%"):
            s = s.replace(junk, "")
        return float(s.replace(",", ".").strip())
    except Exception:
        return default


def _first(p: dict, *keys, default=None):
    for k in keys:
        v = p.get(k)
        if v not in (None, ""):
            return v
    return default


def _hex_for(name: str, given) -> str:
    if given:
        g = str(given).strip()
        if not g.startswith("#"):
            g = "#" + g
        if len(g) in (4, 7):
            return g
    return _COLOR_HEX.get((name or "").strip().lower(), "#1E90FF")


def _currency() -> str:
    try:
        from core.business import store, invoicing
        return invoicing.currency(store.get_company().get("pays", "") or "")
    except Exception:
        return ""


def _money(v) -> str:
    cur = _currency()
    return f"{float(v):.2f} {cur}".strip()


def _norm_items(raw) -> list[dict]:
    """Normalise une liste de lignes -> [{designation, qty, unit_price_ht}]."""
    out = []
    for it in (raw or []):
        if not isinstance(it, dict):
            continue
        desig = str(_first(it, "designation", "name", "nom", "libelle", default="")).strip()
        qty = int(_num(_first(it, "qty", "quantity", "quantite", "nombre", default=1), 1)) or 1
        pu = _num(_first(it, "unit_price_ht", "unit_price", "prix", "price", "pu", default=0), 0)
        if not desig and pu <= 0:
            continue
        out.append({"designation": desig, "qty": qty, "unit_price_ht": pu})
    return out


# Valeurs "bidon" que le modele met parfois faute d'info -> a traiter comme VIDE.
_PLACEHOLDERS = {"", "non renseigne", "non renseigné", "inconnu", "unknown", "n/a",
                 "na", "aucun", "-", "?", "client", "nom", "tbd", "a definir", "à définir"}


def _clean_ref(name) -> str:
    s = str(name or "").strip()
    return "" if s.lower() in _PLACEHOLDERS else s


def _resolve_client(name: str):
    """Trouve un client par nom/société (exact puis contient). None si absent."""
    from core.business import store
    q = _clean_ref(name).lower()
    if not q:
        return None
    clients = store.list_clients()
    for c in clients:  # exact
        if q in (str(c.get("nom", "")).strip().lower(), str(c.get("societe", "")).strip().lower()):
            return c
    for c in clients:  # contient
        hay = (str(c.get("nom", "")) + " " + str(c.get("societe", ""))).lower()
        if q in hay:
            return c
    return None


# ── Handlers ──────────────────────────────────────────────────────────────────
def _add_spool(p: dict) -> str:
    from core.business import store
    material = str(_first(p, "material", "materiau", "matiere", default="PLA")).upper()
    color = str(_first(p, "color", "couleur", "color_name", "couleur_nom", default="")).strip()
    hexc = _hex_for(color, _first(p, "hex", "couleur_hex"))
    weight = _num(_first(p, "weight_g", "poids_g", "weight", "poids", default=1000), 1000.0)
    raw_w = str(_first(p, "weight_g", "weight", "poids", default=""))
    if "kg" in raw_w.lower() or (0 < weight < 20):
        weight *= 1000.0
    brand = str(_first(p, "brand", "marque", default="")).strip()
    price = _num(_first(p, "price", "prix", "cout", "cout_total", default=0), 0.0)
    store.add_spool({
        "materiau": material, "marque": brand, "couleur_nom": color, "couleur_hex": hexc,
        "poids_total_g": weight, "poids_restant_g": weight, "cout_total": price,
    })
    tail = " · ".join(x for x in [brand, _money(price) if price else ""] if x)
    return f"✓ Bobine ajoutée : {material} {color}".rstrip() + f" · {weight/1000:.2f} kg" + (f" · {tail}" if tail else "")


def _consume_spool(p: dict) -> str:
    from core.business import store
    material = str(_first(p, "material", "materiau", default="")).upper()
    color = str(_first(p, "color", "couleur", "couleur_nom", default="")).strip().lower()
    grams = _num(_first(p, "grams", "grammes", "poids_g", "g", default=0), 0)
    if grams <= 0:
        return "⚠ Décompte impossible : indique la quantité en grammes à déduire."
    cands = [s for s in store.list_spools() if float(s.get("poids_restant_g") or 0) > 0
             and (not material or str(s.get("materiau", "")).upper() == material)]
    if color:
        cands = [s for s in cands
                 if color in str(s.get("couleur_nom", "")).lower()
                 or color == str(s.get("couleur_hex", "")).lower()]
    if not cands:
        quoi = " ".join(x for x in [material, color] if x) or "correspondante"
        return f"⚠ Aucune bobine {quoi} avec du stock. Vérifie le matériau/la couleur."
    # Plusieurs couleurs et aucune précisée -> demander (on n'agit pas au hasard).
    colors = {str(s.get("couleur_nom") or s.get("couleur_hex")) for s in cands}
    if not color and len(colors) > 1:
        return ("⚠ Plusieurs bobines " + (material or "") + f" en stock ({', '.join(sorted(colors))}). "
                "Précise la couleur à décompter.").replace("  ", " ")
    # Choisir la bobine avec le PLUS de restant (la plus à même de couvrir).
    spool = max(cands, key=lambda s: float(s.get("poids_restant_g") or 0))
    before = float(spool.get("poids_restant_g") or 0)
    store.consume(spool["id"], grams)
    after = max(0.0, before - grams)
    lbl = f"{spool.get('materiau', '')} {spool.get('couleur_nom') or spool.get('couleur_hex') or ''}".strip()
    warn = "  (dépassait le restant → mis à 0)" if grams > before else ""
    return f"✓ {grams:.0f} g déduits de {lbl} : reste {after:.0f} g{warn}"


def _add_client(p: dict) -> str:
    from core.business import store
    nom = str(_first(p, "nom", "name", "client", default="")).strip()
    societe = str(_first(p, "societe", "company", "entreprise", default="")).strip()
    if not nom and not societe:
        return "⚠ Client non créé : il faut au moins un nom ou une société."
    data = {
        "nom": nom, "societe": societe,
        "email": str(_first(p, "email", "mail", default="")).strip(),
        "tel": str(_first(p, "tel", "telephone", "phone", default="")).strip(),
        "adresse": str(_first(p, "adresse", "address", default="")).strip(),
        "cp": str(_first(p, "cp", "code_postal", "zip", default="")).strip(),
        "ville": str(_first(p, "ville", "city", default="")).strip(),
        "pays": str(_first(p, "pays", "country", default="Suisse")).strip() or "Suisse",
        "id_fiscal": str(_first(p, "id_fiscal", "tva", "vat", default="")).strip(),
        "notes": str(_first(p, "notes", "note", default="")).strip(),
    }
    store.add_client(data)
    who = nom or societe
    extra = ", ".join(x for x in [societe if nom else "", data["ville"], data["email"]] if x)
    return f"✓ Client ajouté : {who}" + (f" ({extra})" if extra else "")


def _add_product(p: dict) -> str:
    from core.business import store
    nom = str(_first(p, "nom", "name", "designation", default="")).strip()
    if not nom:
        return "⚠ Article non créé : il faut un nom."
    prix = _num(_first(p, "prix", "price", "unit_price", default=0), 0)
    store.add_product({
        "nom": nom, "prix": prix,
        "grams": _num(_first(p, "grams", "poids_g", "poids", default=0), 0),
        "duree_h": _num(_first(p, "duree_h", "duree", "hours", "temps_h", default=0), 0),
        "notes": str(_first(p, "notes", "note", default="")).strip(),
    })
    return f"✓ Article ajouté au catalogue : {nom}" + (f" · {_money(prix)}" if prix else "")


def _add_order(p: dict) -> str:
    from core.business import store
    items = _norm_items(_first(p, "items", "lignes", "articles", default=[]))
    if not items:
        return "⚠ Commande non créée : il faut au moins une ligne (désignation + prix)."
    cname = _clean_ref(_first(p, "client", "client_name", "client_label", default=""))
    cid, clabel = "", cname
    if cname:
        c = _resolve_client(cname)
        if c:
            cid = c.get("id", "")
            clabel = store.client_label(c)
    total = _num(_first(p, "total_ttc", "total", default=0), 0) or round(
        sum(it["qty"] * it["unit_price_ht"] for it in items), 2)
    data = {
        "client_id": cid, "client_label": clabel, "items": items, "total_ttc": total,
        "status": str(_first(p, "status", "statut", default="todo")).strip() or "todo",
        "echeance": str(_first(p, "echeance", "due", "deadline", default="")).strip(),
        "notes": str(_first(p, "notes", "note", default="")).strip(),
    }
    o = store.add_order(data)
    parts = [f"✓ Commande {o.get('number', '')} créée"]
    if clabel:
        parts.append(f"pour {clabel}")
    if items:
        parts.append(f"({len(items)} ligne(s), {_money(total)})")
    return " ".join(parts)


def _add_quote(p: dict) -> str:
    from core.business import store, invoicing
    items = _norm_items(_first(p, "items", "lignes", "articles", default=[]))
    if not items:
        return "⚠ Devis non créé : il faut au moins une ligne (désignation + prix)."
    cname = _clean_ref(_first(p, "client", "client_name", default=""))
    client_block, cid = {}, ""
    if cname:
        c = _resolve_client(cname)
        if c:
            cid = c.get("id", "")
            client_block = {k: c.get(k, "") for k in
                            ("nom", "societe", "adresse", "cp", "ville", "pays", "email", "tel", "id_fiscal")}
        else:
            client_block = {"nom": cname}
    country = str(_first(p, "country", "pays", default="")).strip() or store.get_company().get("pays", "")
    vat = _num(_first(p, "vat_rate", "tva", default=None), invoicing.default_vat(country) if country else 0.0)
    disc = _num(_first(p, "discount_pct", "remise", default=0), 0)
    totals = invoicing.compute(items, vat, disc)
    if totals["ttc"] <= 0:
        return ("⚠ Devis non créé : indique au moins un article AVEC son prix "
                "(le total est à 0).")
    store.add_quote({
        "client": client_block, "client_id": cid,
        "client_label": client_block.get("nom") or client_block.get("societe") or cname,
        "country": country, "currency": invoicing.currency(country) if country else _currency(),
        "vat_rate": vat, "discount_pct": disc, "items": items,
        "total_ttc": totals["ttc"], "grams": _num(_first(p, "grams", "poids_g", default=0), 0),
        "notes": str(_first(p, "notes", "note", default="")).strip(),
    })
    who = f" pour {client_block.get('nom') or client_block.get('societe') or cname}" if cname else ""
    return f"✓ Devis créé{who} · {len(items)} ligne(s) · total {_money(totals['ttc'])} (dont TVA {_money(totals['tva'])})"


# ── Suppressions (destructif → resolution stricte, refus si ambigu) ───────────
def _delete_spool(p: dict) -> str:
    from core.business import store
    material = str(_first(p, "material", "materiau", default="")).upper()
    color = _clean_ref(_first(p, "color", "couleur", "couleur_nom", default="")).lower()
    cands = store.list_spools()
    if material:
        cands = [s for s in cands if str(s.get("materiau", "")).upper() == material]
    if color:
        cands = [s for s in cands if color in str(s.get("couleur_nom", "")).lower()
                 or color == str(s.get("couleur_hex", "")).lower()]
    if not cands:
        quoi = " ".join(x for x in [material, color] if x) or "correspondante"
        return f"⚠ Aucune bobine {quoi} à supprimer."
    if len(cands) > 1:
        # Cas courant : supprimer la bobine VIDE (0 g) laissée après usage.
        empties = [s for s in cands if float(s.get("poids_restant_g") or 0) <= 0]
        if len(empties) == 1:
            cands = empties
        else:
            cols = ", ".join(sorted({str(s.get("couleur_nom") or s.get("couleur_hex")) for s in cands}))
            return f"⚠ Plusieurs bobines {material} en stock ({cols}). Précise laquelle supprimer."
    s = cands[0]
    store.delete_spool(s["id"])
    lbl = f"{s.get('materiau', '')} {s.get('couleur_nom') or s.get('couleur_hex') or ''}".strip()
    return f"✓ Bobine supprimée : {lbl}"


def _delete_client(p: dict) -> str:
    from core.business import store
    name = _clean_ref(_first(p, "name", "nom", "client", "societe", default=""))
    if not name:
        return "⚠ Précise le nom du client à supprimer."
    ql = name.lower()
    clients = store.list_clients()
    exact = [c for c in clients if ql in (str(c.get("nom", "")).lower(), str(c.get("societe", "")).lower())]
    matches = exact or [c for c in clients
                        if ql in (str(c.get("nom", "")) + " " + str(c.get("societe", ""))).lower()]
    if not matches:
        return f"⚠ Client « {name} » introuvable."
    if len(matches) > 1:
        return f"⚠ Plusieurs clients correspondent à « {name} ». Précise le nom complet."
    c = matches[0]
    store.delete_client(c["id"])
    return f"✓ Client supprimé : {store.client_label(c)}"


def _delete_product(p: dict) -> str:
    from core.business import store
    name = _clean_ref(_first(p, "name", "nom", "designation", default=""))
    if not name:
        return "⚠ Précise le nom de l'article à supprimer."
    ql = name.lower()
    prods = store.list_products()
    exact = [p2 for p2 in prods if ql == str(p2.get("nom", "")).lower()]
    matches = exact or [p2 for p2 in prods if ql in str(p2.get("nom", "")).lower()]
    if not matches:
        return f"⚠ Article « {name} » introuvable."
    if len(matches) > 1:
        return f"⚠ Plusieurs articles correspondent à « {name} ». Précise le nom exact."
    pr = matches[0]
    store.delete_product(pr["id"])
    return f"✓ Article supprimé : {pr.get('nom', '')}"


def _delete_by_number(p: dict, lister, deleter, kind: str, example: str, done: str) -> str:
    ref = str(_first(p, "number", "numero", "ref", "id", default="")).strip().lower()
    if not ref:
        return f"⚠ Précise le numéro {kind} à supprimer (ex. {example})."
    matches = [x for x in lister() if ref in str(x.get("number", "")).lower() or ref == x.get("id")]
    if not matches:
        return f"⚠ {kind.capitalize()} « {ref} » introuvable."
    if len(matches) > 1:
        return f"⚠ Plusieurs correspondent à « {ref} ». Donne le numéro complet ({example})."
    x = matches[0]
    deleter(x["id"])
    return f"✓ {done} : {x.get('number', '')}"


def _delete_quote(p: dict) -> str:
    from core.business import store
    return _delete_by_number(p, store.list_quotes, store.delete_quote,
                             "du devis", "D-2026-0001", "Devis supprimé")


def _delete_order(p: dict) -> str:
    from core.business import store
    return _delete_by_number(p, store.list_orders, store.delete_order,
                             "de la commande", "CMD-2026-0001", "Commande supprimée")


# Verbe → handler. Extensible (futur : update_*, add_invoice…).
_HANDLERS = {
    "add_spool": _add_spool, "ajouter_bobine": _add_spool,
    "consume_spool": _consume_spool, "deduct_stock": _consume_spool, "deduire_stock": _consume_spool,
    "add_client": _add_client, "ajouter_client": _add_client,
    "add_product": _add_product, "add_article": _add_product, "ajouter_article": _add_product,
    "add_order": _add_order, "ajouter_commande": _add_order,
    "add_quote": _add_quote, "ajouter_devis": _add_quote, "create_quote": _add_quote,
    # Suppressions
    "delete_spool": _delete_spool, "supprimer_bobine": _delete_spool, "remove_spool": _delete_spool,
    "delete_client": _delete_client, "supprimer_client": _delete_client, "remove_client": _delete_client,
    "delete_product": _delete_product, "delete_article": _delete_product, "supprimer_article": _delete_product,
    "delete_quote": _delete_quote, "supprimer_devis": _delete_quote, "remove_quote": _delete_quote,
    "delete_order": _delete_order, "supprimer_commande": _delete_order, "remove_order": _delete_order,
}


# ── Parsing marqueur ──────────────────────────────────────────────────────────
def _kv_fallback(body: str) -> dict:
    """Ancien format « k=v | k=v » (rétro-compat add_spool)."""
    kv = {}
    for part in body.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip().lower()] = v.strip()
    return kv


_PLACEHOLDER_RE = re.compile(r"^\s*<.+>\s*$")


def _has_placeholder(obj) -> bool:
    """True si une valeur ressemble a un placeholder de format « <nom> » non rempli."""
    if isinstance(obj, str):
        return bool(_PLACEHOLDER_RE.match(obj))
    if isinstance(obj, dict):
        return any(_has_placeholder(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_placeholder(v) for v in obj)
    return False


def _parse_marker(body: str) -> tuple[str, dict]:
    m = _VERB_RE.match(body.strip())
    if not m:
        return "", {}
    verb = m.group(1).lower()
    rest = m.group(2).strip()
    if rest.startswith("{"):
        try:
            params = json.loads(rest)
            if isinstance(params, dict):
                return verb, params
        except Exception:
            pass
    return verb, _kv_fallback(body)


def parse_and_execute(text: str) -> tuple[str, list[str]]:
    """Extrait et EXÉCUTE les [[ACTION: …]] du texte. Renvoie
    (texte sans les marqueurs, liste de confirmations/erreurs à afficher)."""
    confirmations: list[str] = []

    def _run(m: "re.Match") -> str:
        verb, params = _parse_marker(m.group(1))
        handler = _HANDLERS.get(verb)
        if not handler:
            return ""  # verbe inconnu → on retire juste le marqueur
        # DEFENSE : le modele a parfois laisse des placeholders « <nom> », « <prix> »
        # (format non rempli) -> on N'EXECUTE PAS et on signale l'info manquante.
        if _has_placeholder(params):
            confirmations.append("⚠ Action annulée : il manque des informations "
                                 "(le champ n'a pas été renseigné).")
            return ""
        try:
            confirmations.append(handler(params))
        except Exception as exc:  # jamais casser l'UI
            confirmations.append(f"⚠ Action « {verb} » impossible : {exc}")
        return ""

    clean = _ACTION_RE.sub(_run, text).strip()
    return clean, confirmations
