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

# ─────────────────────────────────────────────────────────────────────────────
# LECTURE SEULE (decision produit, 2026-07-09) : Oen RENSEIGNE sur tout l'Espace
# Pro mais ne MODIFIE plus rien. Les handlers d'ecriture ci-dessous restent en
# dormance (re-activables en basculant ce flag) ; `parse_and_execute` n'execute
# AUCUNE ecriture tant que WRITE_ENABLED est False. Motif : donnees d'atelier trop
# sensibles pour les confier a un petit modele local (doublons, faux succes...).
WRITE_ENABLED = False

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


# ── Modifications (update) ────────────────────────────────────────────────────
def _update_product(p: dict) -> str:
    from core.business import store
    name = _clean_ref(_first(p, "nom", "name", "designation", "target", "article", default=""))
    if not name:
        return "⚠ Précise quel article modifier."
    ql = name.lower()
    prods = store.list_products()
    matches = [x for x in prods if ql == str(x.get("nom", "")).lower()] \
        or [x for x in prods if ql in str(x.get("nom", "")).lower()]
    if not matches:
        return f"⚠ Article « {name} » introuvable."
    if len(matches) > 1:
        return f"⚠ Plusieurs articles « {name} ». Précise le nom exact."
    pr = matches[0]
    changes = {}
    if _first(p, "prix", "price", "new_price") not in (None, ""):
        changes["prix"] = _num(_first(p, "prix", "price", "new_price"))
    if _first(p, "grams", "poids_g", "poids") not in (None, ""):
        changes["grams"] = _num(_first(p, "grams", "poids_g", "poids"))
    if _first(p, "duree_h", "duree", "hours") not in (None, ""):
        changes["duree_h"] = _num(_first(p, "duree_h", "duree", "hours"))
    if _first(p, "notes", "note") not in (None, ""):
        changes["notes"] = str(_first(p, "notes", "note"))
    nn = _clean_ref(_first(p, "new_name", "nouveau_nom", default=""))
    if nn:
        changes["nom"] = nn
    if not changes:
        return "⚠ Rien à modifier : précise ce qui change (prix, poids…)."
    store.update_product(pr["id"], changes)
    what = ", ".join(f"{k}={v}" for k, v in changes.items())
    return f"✓ Article « {pr.get('nom')} » modifié ({what})"


def _update_client(p: dict) -> str:
    from core.business import store
    c = _resolve_client(_first(p, "nom", "name", "client", "target", "societe", default=""))
    if c is None:
        return f"⚠ Client introuvable. Précise le nom exact."
    _FIELDS = {"email": ("email", "mail"), "tel": ("tel", "telephone", "phone"),
               "adresse": ("adresse", "address"), "cp": ("cp", "code_postal", "zip"),
               "ville": ("ville", "city"), "pays": ("pays", "country"),
               "societe": ("societe", "company"), "id_fiscal": ("id_fiscal", "tva", "vat"),
               "notes": ("notes", "note")}
    changes = {}
    for field, aliases in _FIELDS.items():
        v = _first(p, *aliases)
        if v not in (None, ""):
            changes[field] = str(v).strip()
    nn = _clean_ref(_first(p, "new_name", "nouveau_nom", default=""))
    if nn:
        changes["nom"] = nn
    if not changes:
        return "⚠ Rien à modifier : précise ce qui change (email, téléphone…)."
    store.update_client(c["id"], changes)
    return f"✓ Client « {store.client_label(c)} » modifié ({', '.join(changes)})"


def _find_one_spool(p, action="modifier"):
    """Resout UNE bobine par materiau+couleur. Renvoie (spool, None) ou (None, message)."""
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
        return None, f"⚠ Aucune bobine {quoi} à {action}."
    if len(cands) > 1:
        cols = ", ".join(sorted({str(s.get("couleur_nom") or s.get("couleur_hex")) for s in cands}))
        return None, f"⚠ Plusieurs bobines {material} ({cols}). Précise laquelle {action}."
    return cands[0], None


def _update_spool(p: dict) -> str:
    from core.business import store
    s, err = _find_one_spool(p, "modifier")
    if err:
        return err
    changes = {}
    rem = _first(p, "remaining_g", "poids_restant_g", "reste_g", "weight_g", "grams")
    if rem not in (None, ""):
        changes["poids_restant_g"] = _num(rem)
    if _first(p, "price", "prix", "cout_total") not in (None, ""):
        changes["cout_total"] = _num(_first(p, "price", "prix", "cout_total"))
    if _first(p, "brand", "marque") not in (None, ""):
        changes["marque"] = str(_first(p, "brand", "marque")).strip()
    nc = _clean_ref(_first(p, "new_color", "nouvelle_couleur", default=""))
    if nc:
        changes["couleur_nom"] = nc
        changes["couleur_hex"] = _hex_for(nc, None)
    if not changes:
        return "⚠ Rien à modifier : précise ce qui change (restant, prix, marque…)."
    store.update_spool(s["id"], changes)
    lbl = f"{s.get('materiau', '')} {s.get('couleur_nom') or s.get('couleur_hex') or ''}".strip()
    return f"✓ Bobine {lbl} modifiée ({', '.join(changes)})"


_STATUS_MAP = {
    "todo": "todo", "a faire": "todo", "à faire": "todo", "en attente": "todo",
    "printing": "printing", "en impression": "printing", "en cours": "printing", "impression": "printing",
    "done": "done", "termine": "done", "terminé": "done", "terminee": "done", "terminée": "done",
    "fini": "done", "finie": "done", "fait": "done", "prete": "done", "prête": "done",
    "delivered": "delivered", "livre": "delivered", "livré": "delivered", "livree": "delivered",
    "livrée": "delivered", "facture": "delivered", "facturé": "delivered",
    "cancelled": "cancelled", "annule": "cancelled", "annulé": "cancelled", "annulee": "cancelled",
    "annulée": "cancelled",
}


def _set_order_status(p: dict) -> str:
    from core.business import store
    ref = str(_first(p, "number", "numero", "ref", "id", default="")).strip().lower()
    if not ref:
        return "⚠ Précise le numéro de la commande (ex. CMD-2026-0001)."
    matches = [o for o in store.list_orders() if ref in str(o.get("number", "")).lower() or ref == o.get("id")]
    if not matches:
        return f"⚠ Commande « {ref} » introuvable."
    if len(matches) > 1:
        return f"⚠ Plusieurs commandes correspondent à « {ref} ». Donne le numéro complet."
    o = matches[0]
    raw = str(_first(p, "status", "statut", "state", default="")).strip().lower()
    status = _STATUS_MAP.get(raw)
    if not status:
        return ("⚠ Statut inconnu. Valeurs possibles : à faire, en impression, terminé, "
                "livré, annulé.")
    store.set_order_status(o["id"], status)
    return f"✓ Commande {o.get('number', '')} → statut « {status} »"


# ── Factures & fournitures ────────────────────────────────────────────────────
def _add_invoice(p: dict) -> str:
    from core.business import store, invoicing
    items = _norm_items(_first(p, "items", "lignes", "articles", default=[]))
    if not items:
        return "⚠ Facture non créée : il faut au moins une ligne (désignation + prix)."
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
        return "⚠ Facture non créée : indique au moins un article AVEC son prix."
    inv = store.add_invoice({
        "client": client_block, "client_id": cid,
        "client_label": client_block.get("nom") or client_block.get("societe") or cname,
        "country": country, "currency": invoicing.currency(country) if country else _currency(),
        "vat_rate": vat, "discount_pct": disc, "items": items,
        "notes": str(_first(p, "notes", default="")).strip(),
    })
    who = f" pour {inv.get('client_label')}" if inv.get("client_label") else ""
    return f"✓ Facture {inv.get('number', '')} créée{who} · total {_money(totals['ttc'])} (dont TVA {_money(totals['tva'])})"


def _find_invoice(p):
    from core.business import store
    ref = str(_first(p, "number", "numero", "ref", "facture", "id", default="")).strip().lower()
    if not ref:
        return None, "⚠ Précise le numéro de la facture (ex. 2026-0001)."
    matches = [i for i in store.list_invoices() if ref in str(i.get("number", "")).lower() or ref == i.get("id")]
    if not matches:
        return None, f"⚠ Facture « {ref} » introuvable."
    if len(matches) > 1:
        return None, f"⚠ Plusieurs factures « {ref} ». Donne le numéro complet."
    return matches[0], None


def _mark_invoice_paid(p: dict) -> str:
    from core.business import store
    inv, err = _find_invoice(p)
    if err:
        return err
    store.set_invoice_status(inv["id"], "paid")
    return f"✓ Facture {inv.get('number', '')} marquée PAYÉE"


def _relance_invoice(p: dict) -> str:
    from core.business import store
    inv, err = _find_invoice(p)
    if err:
        return err
    store.mark_relance(inv["id"])
    return f"✓ Relance enregistrée pour la facture {inv.get('number', '')}"


def _delete_invoice(p: dict) -> str:
    from core.business import store
    return _delete_by_number(p, store.list_invoices, store.delete_invoice,
                             "de la facture", "2026-0001", "Facture supprimée")


def _add_supply(p: dict) -> str:
    from core.business import store
    nom = str(_first(p, "nom", "name", "designation", default="")).strip()
    if not nom:
        return "⚠ Fourniture non créée : il faut un nom."
    store.add_supply({
        "nom": nom,
        "quantite": _num(_first(p, "quantite", "quantity", "qty", "nombre", default=0), 0),
        "unite": str(_first(p, "unite", "unit", default="u")).strip() or "u",
        "seuil": _num(_first(p, "seuil", "threshold", "reappro", default=0), 0),
        "cout_unitaire": _num(_first(p, "cout_unitaire", "cout", "prix", "price", default=0), 0),
        "fournisseur": str(_first(p, "fournisseur", "supplier", default="")).strip(),
    })
    return f"✓ Fourniture ajoutée : {nom}"


# Verbe → handler.
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
    # Modifications
    "update_product": _update_product, "modifier_article": _update_product, "update_article": _update_product,
    "update_client": _update_client, "modifier_client": _update_client,
    "update_spool": _update_spool, "modifier_bobine": _update_spool,
    "set_order_status": _set_order_status, "update_order": _set_order_status,
    "statut_commande": _set_order_status, "order_status": _set_order_status,
    # Factures & fournitures
    "add_invoice": _add_invoice, "creer_facture": _add_invoice, "create_invoice": _add_invoice,
    "mark_invoice_paid": _mark_invoice_paid, "facture_payee": _mark_invoice_paid,
    "set_invoice_paid": _mark_invoice_paid, "marquer_payee": _mark_invoice_paid,
    "relance_invoice": _relance_invoice, "relancer_facture": _relance_invoice,
    "delete_invoice": _delete_invoice, "supprimer_facture": _delete_invoice,
    "add_supply": _add_supply, "ajouter_fourniture": _add_supply, "add_fourniture": _add_supply,
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


# Detecteur de FAUSSE confirmation : le modele affirme parfois avoir cree/supprime/
# modifie un element SANS emettre de marqueur (donc rien n'a ete fait). On le detecte
# pour ne pas laisser l'utilisateur croire qu'une action a eu lieu.
_CLAIM_RE = re.compile(
    r"(avec succ[eè]s"
    r"|a\s+[eé]t[eé]\s+(cr[eé]{2}|ajout|supprim|enregistr|modifi|effac|mis[e]?\s+[aà]\s+jour)"
    r"|ont\s+[eé]t[eé]\s+(cr[eé]{2}|ajout|supprim|enregistr|modifi|effac)"
    r"|j['e ]\s*(?:ai|viens de)\s+(bien\s+)?(cr[eé]{2}|ajout|supprim|enregistr|modifi|effac|mis))",
    re.IGNORECASE,
)


def claims_action_done(text: str) -> bool:
    """True si le texte AFFIRME avoir realise une action (create/delete/update)."""
    return bool(_CLAIM_RE.search(text or ""))


# Intention de suppression EN MASSE dans le message utilisateur (garde-fou independant
# du modele : meme si Oen n'emet qu'UN marqueur delete quand il y a peu d'elements).
_BULK_RE = re.compile(
    r"\b(tout|tous|toutes|l'ensemble|int[eé]gralit[eé]|tous mes|toutes mes)\b"
    r"|\bvide[rz]?\b|\befface[rz]?\s+tout", re.IGNORECASE)


def parse_and_execute(text: str, user_text: str = "") -> tuple[str, list[str]]:
    """Extrait et EXÉCUTE le [[ACTION: …]] du texte. Renvoie
    (texte sans les marqueurs, liste de confirmations/erreurs à afficher).

    SÉCURITÉ : au plus UNE action par reponse ; si le modele en emet plusieurs d'un coup
    (typique de « tout supprimer / vider le stock »), on N'EN EXECUTE AUCUNE. De plus, si
    le MESSAGE de l'utilisateur exprime une suppression EN MASSE (tout/tous/vide…), on
    refuse toute suppression meme sur un seul marqueur.

    LECTURE SEULE (WRITE_ENABLED=False) : Oen ne modifie PLUS l'Espace Pro. On retire les
    marqueurs eventuels et on N'EXECUTE AUCUNE ecriture — la saisie reste a l'utilisateur
    (decision produit : donnees d'atelier trop sensibles pour un modele local)."""
    clean = _ACTION_RE.sub("", text).strip()
    if not WRITE_ENABLED:
        return clean, []
    matches = list(_ACTION_RE.finditer(text))
    if not matches:
        return clean, []
    if len(matches) > 1:
        return clean, ["⚠ Plusieurs actions demandées d'un coup : par sécurité je n'en "
                       "exécute AUCUNE. Demande-les une par une, précisément."]
    verb, params = _parse_marker(matches[0].group(1))
    handler = _HANDLERS.get(verb)
    if not handler:
        return clean, []  # verbe inconnu → marqueur retiré, aucun effet
    # Suppression EN MASSE demandee par l'utilisateur -> refus (donnees sensibles).
    if verb.startswith("delete_") and _BULK_RE.search(user_text or ""):
        return clean, ["⚠ Suppression en masse refusée par sécurité. Supprime un élément "
                       "précis à la fois (ou fais-le dans l'Espace Pro)."]
    # Placeholders « <nom> » non remplis -> on n'execute pas.
    if _has_placeholder(params):
        return clean, ["⚠ Action annulée : il manque des informations "
                       "(un champ n'a pas été renseigné)."]
    try:
        return clean, [handler(params)]
    except Exception as exc:  # jamais casser l'UI
        return clean, [f"⚠ Action « {verb} » impossible : {exc}"]
