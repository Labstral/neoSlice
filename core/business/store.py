"""Stockage local de l'Espace Pro (100 % hors-ligne, JSON).

Données dans ~/.neoslice/business/ :
  - spools.json   : inventaire des bobines de filament

Écriture atomique (fichier temporaire + remplacement) pour ne jamais corrompre
les données d'un professionnel. Sauvegarde/restauration via export_backup().

Phase 1 = bobines. Les clients/devis/factures viendront s'ajouter ici (même
patron : un fichier JSON par collection + un accès typé).
"""
from __future__ import annotations

import json
import os
import uuid
import zipfile
from datetime import datetime, date
from pathlib import Path

_DIR = Path.home() / ".neoslice" / "business"
_SPOOLS = _DIR / "spools.json"
_COMPANY = _DIR / "company.json"
_INVOICES = _DIR / "invoices.json"
_QUOTES = _DIR / "devis.json"
_CLIENTS = _DIR / "clients.json"
_ORDERS = _DIR / "orders.json"
_PRODUCTS = _DIR / "products.json"


# ──────────────────────────────────────────────────────────────────────────────
# Bas niveau : lecture / écriture atomique
# ──────────────────────────────────────────────────────────────────────────────
def _load(path: Path) -> list:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save(path: Path, items: list) -> None:
    """Sauvegarde atomique + copie de secours (.bak) : on n'écrase le fichier
    qu'après écriture complète d'un temporaire, et on conserve la version
    précédente en .bak → aucune perte même en cas de coupure/corruption."""
    _DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    if path.exists():
        try:
            import shutil
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except Exception:
            pass
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_dict(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_dict(path: Path, data: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if path.exists():
        try:
            import shutil
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except Exception:
            pass
    os.replace(tmp, path)


# ──────────────────────────────────────────────────────────────────────────────
# Modèle Bobine
# ──────────────────────────────────────────────────────────────────────────────
# Champs d'une bobine (dict) :
#   id, cree_le, modifie_le
#   materiau          : clé du catalogue de types (PLA, PETG, …)
#   marque, couleur_hex, couleur_nom, finition
#   poids_total_g     : neuf (hors bobine vide)
#   poids_restant_g   : restant estimé
#   tare_g            : poids de la bobine vide
#   cout_total        : prix payé (devise atelier)
#   fournisseur, date_achat, emplacement, lot, notes
#   sechage_log       : [{date, temp, duree}]
#   archivee          : bool

def _spool_defaults() -> dict:
    return {
        "materiau": "PLA", "marque": "", "couleur_hex": "#1E90FF", "couleur_nom": "",
        "finition": "", "poids_total_g": 1000.0, "poids_restant_g": 1000.0,
        "tare_g": 200.0, "cout_total": 0.0, "fournisseur": "", "date_achat": "",
        "emplacement": "", "lot": "", "notes": "", "sechage_log": [], "archivee": False,
        # Seuil de réapprovisionnement : sous ce restant, la bobine passe en
        # « à racheter » (alerte stock + liste de courses).
        "seuil_reappro_g": 150.0,
    }


def cout_par_kg(spool: dict) -> float:
    """Coût au kg déduit du prix total et du poids neuf."""
    g = float(spool.get("poids_total_g") or 0)
    c = float(spool.get("cout_total") or 0)
    return round(c / (g / 1000.0), 2) if g > 0 else 0.0


def pct_restant(spool: dict) -> float:
    """Pourcentage de filament restant (0–100)."""
    tot = float(spool.get("poids_total_g") or 0)
    rem = float(spool.get("poids_restant_g") or 0)
    if tot <= 0:
        return 0.0
    return max(0.0, min(100.0, rem / tot * 100.0))


# ──────────────────────────────────────────────────────────────────────────────
# API Bobines
# ──────────────────────────────────────────────────────────────────────────────
def list_spools(include_archived: bool = False) -> list[dict]:
    items = _load(_SPOOLS)
    if not include_archived:
        items = [s for s in items if not s.get("archivee")]
    return items


def get_spool(spool_id: str) -> dict | None:
    return next((s for s in _load(_SPOOLS) if s.get("id") == spool_id), None)


def add_spool(data: dict) -> dict:
    items = _load(_SPOOLS)
    spool = _spool_defaults()
    spool.update({k: v for k, v in data.items() if k in spool})
    spool["id"] = uuid.uuid4().hex
    spool["cree_le"] = spool["modifie_le"] = _now()
    items.append(spool)
    _save(_SPOOLS, items)
    return spool


def update_spool(spool_id: str, data: dict) -> dict | None:
    items = _load(_SPOOLS)
    for s in items:
        if s.get("id") == spool_id:
            for k, v in data.items():
                if k not in ("id", "cree_le"):
                    s[k] = v
            s["modifie_le"] = _now()
            _save(_SPOOLS, items)
            return s
    return None


def delete_spool(spool_id: str) -> bool:
    items = _load(_SPOOLS)
    new = [s for s in items if s.get("id") != spool_id]
    if len(new) != len(items):
        _save(_SPOOLS, new)
        return True
    return False


def consume(spool_id: str, grams: float) -> dict | None:
    """Décrémente le poids restant d'une bobine (jamais sous 0)."""
    s = get_spool(spool_id)
    if not s:
        return None
    reste = max(0.0, float(s.get("poids_restant_g") or 0) - max(0.0, float(grams)))
    return update_spool(spool_id, {"poids_restant_g": round(reste, 1)})


def add_drying(spool_id: str, temp: float, duree_h: float) -> dict | None:
    s = get_spool(spool_id)
    if not s:
        return None
    log = list(s.get("sechage_log") or [])
    log.append({"date": date.today().isoformat(), "temp": temp, "duree_h": duree_h})
    return update_spool(spool_id, {"sechage_log": log})


# ── Requêtes utiles ────────────────────────────────────────────────────────────
def spools_for_material(materiau: str) -> list[dict]:
    """Bobines (non archivées, non vides) d'un matériau donné — pour le devis/export."""
    return [s for s in list_spools()
            if s.get("materiau") == materiau and float(s.get("poids_restant_g") or 0) > 0]


def _spool_threshold(s: dict) -> float:
    """Seuil de réappro effectif d'une bobine (valeur par bobine, repli 150 g)."""
    try:
        v = float(s.get("seuil_reappro_g"))
        return v if v > 0 else 150.0
    except (TypeError, ValueError):
        return 150.0


def low_stock(seuil_g: float | None = None) -> list[dict]:
    """Bobines à réapprovisionner : restant ≤ seuil. Si seuil_g est fourni, il
    s'applique à toutes ; sinon on utilise le seuil propre à chaque bobine.
    Inclut les bobines vides (restant = 0)."""
    out = []
    for s in list_spools():
        rem = float(s.get("poids_restant_g") or 0)
        seuil = seuil_g if seuil_g is not None else _spool_threshold(s)
        if rem <= seuil:
            out.append(s)
    return out


def shopping_list() -> list[dict]:
    """Liste de courses : pour chaque bobine sous le seuil, ce qu'il faut racheter.
    On ne rachète pas le « manque » exact (on n'achète pas 880 g de filament) mais
    une bobine pleine → `racheter_g` = poids initial renseigné à la création."""
    out = []
    for s in low_stock():
        rem = float(s.get("poids_restant_g") or 0)
        tot = float(s.get("poids_total_g") or 0)
        out.append({
            "id": s.get("id"),
            "materiau": s.get("materiau", ""),
            "marque": s.get("marque", ""),
            "couleur_nom": s.get("couleur_nom", ""),
            "couleur_hex": s.get("couleur_hex", "#888"),
            "fournisseur": s.get("fournisseur", ""),
            "restant_g": round(rem, 0),
            "racheter_g": round(tot, 0),   # bobine pleine (valeur initiale)
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Société (émetteur des factures)
# ──────────────────────────────────────────────────────────────────────────────
def company_defaults() -> dict:
    return {
        "nom": "", "forme": "", "adresse": "", "cp": "", "ville": "",
        "pays": "Suisse", "email": "", "tel": "", "id_fiscal": "", "iban": "",
        "conditions": "Paiement à 30 jours.",
        # Champs légaux spécifiques au pays (affichés dynamiquement) :
        #   reg_number : SIRET / Steuernr. / BCE / Company No. / BN…
        #   reg_office : RCS, Handelsregister…
        #   capital    : capital social (France, Luxembourg…)
        #   regime     : "normal" | "franchise" (auto-entrepreneur FR → 293 B)
        "reg_number": "", "reg_office": "", "capital": "", "regime": "normal",
        # Frais forfaitaires de recouvrement facturés en cas de retard de paiement
        # (montant, devise du pays de facturation). "" = défaut légal du pays
        # (ex. 40 en France). Repris dans les mentions légales du devis/facture.
        "recovery_fee": "",
        # Langue des documents (facture/devis/bon) : "" = auto selon le pays,
        # sinon code langue ("fr","en","de","nl","it","es").
        "doc_lang": "",
    }


def get_company() -> dict:
    d = company_defaults()
    d.update(_load_dict(_COMPANY))
    return d


def save_company(data: dict) -> dict:
    d = company_defaults()
    d.update({k: v for k, v in data.items() if k in d})
    _save_dict(_COMPANY, d)
    return d


# ──────────────────────────────────────────────────────────────────────────────
# Factures
# ──────────────────────────────────────────────────────────────────────────────
def list_invoices() -> list[dict]:
    return sorted(_load(_INVOICES), key=lambda i: i.get("number", ""), reverse=True)


def get_invoice(inv_id: str) -> dict | None:
    return next((i for i in _load(_INVOICES) if i.get("id") == inv_id), None)


def next_invoice_number() -> str:
    """Numéro séquentiel par année : AAAA-0001, AAAA-0002…"""
    year = datetime.now().strftime("%Y")
    seq = 0
    for inv in _load(_INVOICES):
        num = str(inv.get("number", ""))
        if num.startswith(year + "-"):
            try:
                seq = max(seq, int(num.split("-")[1]))
            except (IndexError, ValueError):
                pass
    return f"{year}-{seq + 1:04d}"


def add_invoice(data: dict) -> dict:
    items = _load(_INVOICES)
    inv = dict(data)
    inv["id"] = uuid.uuid4().hex
    inv.setdefault("number", next_invoice_number())
    inv["cree_le"] = inv["modifie_le"] = _now()
    inv.setdefault("status", "draft")
    # Échéance de paiement (par défaut +30 jours) → base des relances pour retard.
    inv.setdefault("echeance", _add_days(inv.get("date") or datetime.now().strftime("%Y-%m-%d"), 30))
    inv.setdefault("relance_le", "")   # date de dernière relance envoyée
    items.append(inv)
    _save(_INVOICES, items)
    return inv


def _add_days(iso_date: str, days: int) -> str:
    """Ajoute des jours à une date 'YYYY-MM-DD' (repli : aujourd'hui + days)."""
    from datetime import timedelta
    try:
        d = datetime.strptime(iso_date[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        d = date.today()
    return (d + timedelta(days=days)).isoformat()


def invoice_ttc(inv: dict) -> float:
    """Total TTC d'une facture (recalculé via le moteur TVA/remise)."""
    from core.business import invoicing
    return invoicing.compute(inv.get("items", []),
                             float(inv.get("vat_rate", 0) or 0),
                             float(inv.get("discount_pct", 0) or 0))["ttc"]


def invoices_overdue(ref: str | None = None) -> list[dict]:
    """Factures non payées dont l'échéance est dépassée (relances). Triées de la
    plus en retard à la moins en retard."""
    today = ref or date.today().isoformat()
    out = []
    for i in list_invoices():
        if i.get("status") == "paid":
            continue
        ech = str(i.get("echeance") or "")
        if ech and ech < today:
            out.append(i)
    return sorted(out, key=lambda i: str(i.get("echeance") or ""))


def days_overdue(inv: dict, ref: str | None = None) -> int:
    """Nombre de jours de retard d'une facture (0 si pas en retard)."""
    today = ref or date.today().isoformat()
    ech = str(inv.get("echeance") or "")
    if not ech or inv.get("status") == "paid" or ech >= today:
        return 0
    try:
        d1 = datetime.strptime(ech[:10], "%Y-%m-%d").date()
        d2 = datetime.strptime(today[:10], "%Y-%m-%d").date()
        return max(0, (d2 - d1).days)
    except (ValueError, TypeError):
        return 0


def mark_relance(inv_id: str) -> dict | None:
    """Enregistre qu'une relance a été envoyée aujourd'hui."""
    return update_invoice(inv_id, {"relance_le": date.today().isoformat()})


def update_invoice(inv_id: str, data: dict) -> dict | None:
    items = _load(_INVOICES)
    for i in items:
        if i.get("id") == inv_id:
            for k, v in data.items():
                if k not in ("id", "cree_le", "number"):
                    i[k] = v
            i["modifie_le"] = _now()
            _save(_INVOICES, items)
            return i
    return None


def set_invoice_status(inv_id: str, status: str) -> dict | None:
    return update_invoice(inv_id, {"status": status})


def delete_invoice(inv_id: str) -> bool:
    items = _load(_INVOICES)
    new = [i for i in items if i.get("id") != inv_id]
    if len(new) != len(items):
        _save(_INVOICES, new)
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Devis enregistrés
# ──────────────────────────────────────────────────────────────────────────────
def list_quotes() -> list[dict]:
    return sorted(_load(_QUOTES), key=lambda q: q.get("number", ""), reverse=True)


def get_quote(qid: str) -> dict | None:
    return next((q for q in _load(_QUOTES) if q.get("id") == qid), None)


def next_quote_number() -> str:
    year = datetime.now().strftime("%Y")
    seq = 0
    for q in _load(_QUOTES):
        num = str(q.get("number", ""))
        if num.startswith(f"D-{year}-"):
            try:
                seq = max(seq, int(num.split("-")[2]))
            except (IndexError, ValueError):
                pass
    return f"D-{year}-{seq + 1:04d}"


def add_quote(data: dict) -> dict:
    items = _load(_QUOTES)
    q = dict(data)
    q["id"] = uuid.uuid4().hex
    q.setdefault("number", next_quote_number())
    q.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    q["cree_le"] = _now()
    q.setdefault("status", "open")
    items.append(q)
    _save(_QUOTES, items)
    return q


def delete_quote(qid: str) -> bool:
    items = _load(_QUOTES)
    new = [q for q in items if q.get("id") != qid]
    if len(new) != len(items):
        _save(_QUOTES, new)
        return True
    return False


def mark_quote_converted(qid: str, invoice_number: str) -> dict | None:
    items = _load(_QUOTES)
    for q in items:
        if q.get("id") == qid:
            q["status"] = "converted"
            q["invoice_number"] = invoice_number
            _save(_QUOTES, items)
            return q
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Clients (mini-CRM) — reliés aux devis et factures via client_id
# ──────────────────────────────────────────────────────────────────────────────
def _client_defaults() -> dict:
    return {"nom": "", "societe": "", "adresse": "", "cp": "", "ville": "",
            "pays": "Suisse", "email": "", "tel": "", "id_fiscal": "", "notes": ""}


def list_clients() -> list[dict]:
    return sorted(_load(_CLIENTS), key=lambda c: (c.get("nom") or c.get("societe") or "").lower())


def get_client(cid: str) -> dict | None:
    return next((c for c in _load(_CLIENTS) if c.get("id") == cid), None)


def add_client(data: dict) -> dict:
    items = _load(_CLIENTS)
    c = _client_defaults()
    c.update({k: v for k, v in data.items() if k in c})
    c["id"] = uuid.uuid4().hex
    c["cree_le"] = c["modifie_le"] = _now()
    items.append(c)
    _save(_CLIENTS, items)
    return c


def update_client(cid: str, data: dict) -> dict | None:
    items = _load(_CLIENTS)
    for c in items:
        if c.get("id") == cid:
            for k, v in data.items():
                if k not in ("id", "cree_le"):
                    c[k] = v
            c["modifie_le"] = _now()
            _save(_CLIENTS, items)
            return c
    return None


def delete_client(cid: str) -> bool:
    items = _load(_CLIENTS)
    new = [c for c in items if c.get("id") != cid]
    if len(new) != len(items):
        _save(_CLIENTS, new)
        return True
    return False


def client_label(c: dict) -> str:
    nom = c.get("nom", "").strip()
    soc = c.get("societe", "").strip()
    if nom and soc:
        return f"{nom} ({soc})"
    return nom or soc or "—"


def invoices_for_client(cid: str) -> list[dict]:
    return [i for i in list_invoices() if i.get("client_id") == cid]


def quotes_for_client(cid: str) -> list[dict]:
    return [q for q in list_quotes() if q.get("client_id") == cid]


def client_stats(cid: str) -> dict:
    """Agrège devis + factures d'un client : nb, CA facturé, CA payé, CA dû."""
    from core.business import invoicing
    invs = invoices_for_client(cid)
    quos = quotes_for_client(cid)
    billed = paid = 0.0
    for inv in invs:
        ttc = invoicing.compute(inv.get("items", []),
                                float(inv.get("vat_rate", 0) or 0),
                                float(inv.get("discount_pct", 0) or 0))["ttc"]
        billed += ttc
        if inv.get("status") == "paid":
            paid += ttc
    return {
        "n_quotes": len(quos),
        "n_invoices": len(invs),
        "billed": round(billed, 2),
        "paid": round(paid, 2),
        "due": round(billed - paid, 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Commandes — file de production (lien devis → commande → facture)
# ──────────────────────────────────────────────────────────────────────────────
# Cycle de vie d'une commande :
#   todo (à faire) → printing (en impression) → done (terminé) → delivered
#   (livré) → paid (payé). Plus « cancelled » (annulé).
ORDER_STATUSES = ["todo", "printing", "done", "delivered", "paid", "cancelled"]
# Statuts qui « consomment » le filament (impression lancée/faite) → décrément
# automatique du stock une seule fois.
_ORDER_CONSUMED_AT = "printing"


def _order_defaults() -> dict:
    return {
        "client_id": "", "client_label": "", "items": [], "total_ttc": 0.0,
        "currency": "", "status": "todo", "echeance": "", "notes": "",
        "quote_id": "", "quote_number": "", "invoice_id": "", "invoice_number": "",
        # Consommation filament : une ligne (bobine, grammes) PAR couleur utilisée.
        # Mono-couleur = 1 ligne (estimable) ; multi-couleur = plusieurs lignes,
        # saisies par l'utilisateur (l'estimation serait fausse). « grams » = total.
        "consumptions": [], "grams": 0.0, "stock_deducted": False,
    }


def _order_total_grams(o: dict) -> float:
    return round(sum(float(c.get("grams") or 0)
                     for c in (o.get("consumptions") or [])), 1)


def list_orders(include_cancelled: bool = True) -> list[dict]:
    items = sorted(_load(_ORDERS), key=lambda o: o.get("number", ""), reverse=True)
    if not include_cancelled:
        items = [o for o in items if o.get("status") != "cancelled"]
    return items


def get_order(oid: str) -> dict | None:
    return next((o for o in _load(_ORDERS) if o.get("id") == oid), None)


def next_order_number() -> str:
    """Numéro séquentiel par année : CMD-AAAA-0001…"""
    year = datetime.now().strftime("%Y")
    seq = 0
    for o in _load(_ORDERS):
        num = str(o.get("number", ""))
        if num.startswith(f"CMD-{year}-"):
            try:
                seq = max(seq, int(num.split("-")[2]))
            except (IndexError, ValueError):
                pass
    return f"CMD-{year}-{seq + 1:04d}"


def add_order(data: dict) -> dict:
    items = _load(_ORDERS)
    o = _order_defaults()
    o.update({k: v for k, v in data.items() if k in o})
    o["id"] = uuid.uuid4().hex
    o["number"] = next_order_number()
    o["cree_le"] = o["modifie_le"] = _now()
    o["grams"] = _order_total_grams(o)
    if not o.get("currency"):
        from core.business import invoicing
        o["currency"] = invoicing.currency(get_company().get("pays", ""))
    items.append(o)
    _save(_ORDERS, items)
    # Si la commande démarre déjà en impression/terminée, on déduit le stock.
    _maybe_consume_stock(o["id"])
    return get_order(o["id"]) or o


def update_order(oid: str, data: dict) -> dict | None:
    items = _load(_ORDERS)
    for o in items:
        if o.get("id") == oid:
            for k, v in data.items():
                if k not in ("id", "cree_le", "number"):
                    o[k] = v
            o["grams"] = _order_total_grams(o)
            o["modifie_le"] = _now()
            _save(_ORDERS, items)
            _maybe_consume_stock(oid)
            return get_order(oid)
    return None


def set_order_status(oid: str, status: str) -> dict | None:
    if status not in ORDER_STATUSES:
        return None
    return update_order(oid, {"status": status})


def delete_order(oid: str) -> bool:
    items = _load(_ORDERS)
    new = [o for o in items if o.get("id") != oid]
    if len(new) != len(items):
        _save(_ORDERS, new)
        return True
    return False


def _maybe_consume_stock(oid: str) -> None:
    """Déduit le filament de la bobine choisie quand la commande atteint l'état
    « en impression » (ou au-delà). Idempotent : ne déduit qu'une seule fois
    grâce au drapeau stock_deducted."""
    o = get_order(oid)
    if not o or o.get("stock_deducted"):
        return
    if o.get("status") == "cancelled":
        return
    consuming = o.get("status") in ("printing", "done", "delivered", "paid")
    if not consuming:
        return
    # Déduit chaque ligne de consommation (une par couleur) de sa bobine.
    consumed_any = False
    for c in (o.get("consumptions") or []):
        sid = c.get("spool_id")
        g = float(c.get("grams") or 0)
        if sid and g > 0 and get_spool(sid):
            consume(sid, g)
            consumed_any = True
    # On marque « déduit » dès qu'on est en consommation (même sans bobine liée,
    # pour ne pas re-tenter à chaque changement de statut).
    items = _load(_ORDERS)
    for it in items:
        if it.get("id") == oid:
            it["stock_deducted"] = True
            it["modifie_le"] = _now()
            break
    _save(_ORDERS, items)


def order_for_invoice(invoice_id: str) -> dict | None:
    """Commande reliée à une facture (via invoice_id), si elle existe."""
    if not invoice_id:
        return None
    return next((o for o in _load(_ORDERS) if o.get("invoice_id") == invoice_id), None)


def order_from_quote(quote: dict) -> dict:
    """Crée une commande « à faire » à partir d'un devis enregistré."""
    cid = quote.get("client_id", "")
    label = quote.get("client_label", "")
    if cid and not label:
        c = get_client(cid)
        label = client_label(c) if c else ""
    # Un devis = une estimation mono-couleur → 1 ligne de consommation pré-remplie
    # (bobine à choisir, grammes estimés à corriger si besoin). Pour du multi-
    # couleur, l'utilisateur ajoutera des lignes et saisira chaque conso.
    est = float(quote.get("grams") or quote.get("poids_g") or 0)
    cons = [{"spool_id": "", "grams": round(est, 0)}] if est > 0 else []
    # items de facturation : reconstruits depuis le devis (désignation + PU)
    items = quote.get("items") or [{
        "designation": quote.get("part_name", ""),
        "qty": int(quote.get("qty", 1) or 1),
        "unit_price_ht": float(quote.get("unit_price", 0) or 0),
    }]
    data = {
        "client_id": cid, "client_label": label,
        "items": items,
        "total_ttc": float(quote.get("total_price") or quote.get("total_ttc") or 0),
        "currency": quote.get("currency", ""),
        "consumptions": cons,
        "quote_id": quote.get("id", ""), "quote_number": quote.get("number", ""),
        "echeance": _add_days(datetime.now().strftime("%Y-%m-%d"), 7),
        "status": "todo",
    }
    return add_order(data)


# ──────────────────────────────────────────────────────────────────────────────
# Articles — catalogue de produits récurrents (insertion rapide en devis/facture)
# ──────────────────────────────────────────────────────────────────────────────
def _product_defaults() -> dict:
    return {"nom": "", "prix": 0.0, "grams": 0.0, "duree_h": 0.0, "notes": ""}


def order_from_product(product: dict) -> dict:
    """Crée une commande « à faire » à partir d'un article du catalogue. L'article
    porte une estimation de grammes → 1 ligne de consommation (mono-couleur)."""
    est = float(product.get("grams") or 0)
    cons = [{"spool_id": "", "grams": round(est, 0)}] if est > 0 else []
    data = {
        "items": [{"designation": product.get("nom", ""), "qty": 1,
                   "unit_price_ht": float(product.get("prix", 0) or 0)}],
        "total_ttc": float(product.get("prix", 0) or 0),
        "consumptions": cons,
        "echeance": _add_days(datetime.now().strftime("%Y-%m-%d"), 7),
        "status": "todo",
    }
    return add_order(data)


def list_products() -> list[dict]:
    return sorted(_load(_PRODUCTS), key=lambda p: (p.get("nom") or "").lower())


def get_product(pid: str) -> dict | None:
    return next((p for p in _load(_PRODUCTS) if p.get("id") == pid), None)


def add_product(data: dict) -> dict:
    items = _load(_PRODUCTS)
    p = _product_defaults()
    p.update({k: v for k, v in data.items() if k in p})
    p["id"] = uuid.uuid4().hex
    p["cree_le"] = p["modifie_le"] = _now()
    items.append(p)
    _save(_PRODUCTS, items)
    return p


def update_product(pid: str, data: dict) -> dict | None:
    items = _load(_PRODUCTS)
    for p in items:
        if p.get("id") == pid:
            for k, v in data.items():
                if k not in ("id", "cree_le"):
                    p[k] = v
            p["modifie_le"] = _now()
            _save(_PRODUCTS, items)
            return p
    return None


def delete_product(pid: str) -> bool:
    items = _load(_PRODUCTS)
    new = [p for p in items if p.get("id") != pid]
    if len(new) != len(items):
        _save(_PRODUCTS, new)
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Rapport mensuel + export comptable
# ──────────────────────────────────────────────────────────────────────────────
def monthly_revenue(months: int = 6) -> list[dict]:
    """CA facturé et encaissé par mois (N derniers mois, du plus ancien au plus
    récent) → [{'mois':'AAAA-MM', 'billed':…, 'paid':…}]."""
    from datetime import timedelta
    today = date.today().replace(day=1)
    buckets: list[str] = []
    d = today
    for _ in range(months):
        buckets.append(d.strftime("%Y-%m"))
        # mois précédent
        d = (d - timedelta(days=1)).replace(day=1)
    buckets = list(reversed(buckets))
    agg = {m: {"billed": 0.0, "paid": 0.0} for m in buckets}
    for inv in list_invoices():
        m = str(inv.get("date") or inv.get("cree_le") or "")[:7]
        if m in agg:
            ttc = invoice_ttc(inv)
            agg[m]["billed"] += ttc
            if inv.get("status") == "paid":
                agg[m]["paid"] += ttc
    return [{"mois": m, "billed": round(agg[m]["billed"], 2),
             "paid": round(agg[m]["paid"], 2)} for m in buckets]


def export_accounting_csv(dest: Path) -> Path:
    """Export comptable des factures (CSV ; séparateur ';' pour Excel FR/CH)."""
    import csv
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    from core.business import invoicing
    rows = []
    for inv in sorted(list_invoices(), key=lambda i: str(i.get("date") or "")):
        comp = invoicing.compute(inv.get("items", []),
                                 float(inv.get("vat_rate", 0) or 0),
                                 float(inv.get("discount_pct", 0) or 0))
        rows.append({
            "Numéro": inv.get("number", ""),
            "Date": inv.get("date", ""),
            "Échéance": inv.get("echeance", ""),
            "Client": inv.get("client_label", ""),
            "Statut": inv.get("status", ""),
            "Devise": inv.get("currency", ""),
            "Total HT": f"{comp['net_ht']:.2f}",
            "TVA": f"{comp['tva']:.2f}",
            "Total TTC": f"{comp['ttc']:.2f}",
        })
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["Numéro", "Date", "Échéance", "Client", "Statut",
                            "Devise", "Total HT", "TVA", "Total TTC"], delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return dest


# ──────────────────────────────────────────────────────────────────────────────
# Tableau de bord — indicateurs agrégés
# ──────────────────────────────────────────────────────────────────────────────
def dashboard_stats() -> dict:
    """Indicateurs synthétiques : chiffre d'affaires, documents, stock filament."""
    from core.business import invoicing
    invs = list_invoices()
    quos = list_quotes()
    clients = list_clients()
    spools = list_spools()

    # Devise dominante (la plus fréquente parmi les factures, sinon société)
    cur_count: dict[str, int] = {}
    for inv in invs:
        cur_count[inv.get("currency", "")] = cur_count.get(inv.get("currency", ""), 0) + 1
    currency = (max(cur_count, key=cur_count.get) if cur_count
                else invoicing.currency(get_company().get("pays", "")))

    billed = paid = 0.0
    for inv in invs:
        ttc = invoicing.compute(inv.get("items", []),
                                float(inv.get("vat_rate", 0) or 0),
                                float(inv.get("discount_pct", 0) or 0))["ttc"]
        billed += ttc
        if inv.get("status") == "paid":
            paid += ttc
    n_unpaid = sum(1 for i in invs if i.get("status") != "paid")

    # Retards (relances) : nb + montant total dû en retard
    overdue = invoices_overdue()
    overdue_amount = sum(invoice_ttc(i) for i in overdue)

    # CA du mois en cours (facturé / encaissé)
    this_month = date.today().strftime("%Y-%m")
    month_billed = month_paid = 0.0
    for inv in invs:
        if str(inv.get("date") or inv.get("cree_le") or "")[:7] == this_month:
            ttc = invoice_ttc(inv)
            month_billed += ttc
            if inv.get("status") == "paid":
                month_paid += ttc

    # Commandes en cours (non livrées / non payées / non annulées)
    orders = list_orders(include_cancelled=False)
    active_orders = [o for o in orders if o.get("status") in ("todo", "printing", "done")]
    n_todo = sum(1 for o in orders if o.get("status") == "todo")
    n_printing = sum(1 for o in orders if o.get("status") == "printing")

    stock_g = 0.0
    stock_value = 0.0
    for s in spools:
        rem = float(s.get("poids_restant_g") or 0)
        stock_g += rem
        stock_value += (rem / 1000.0) * cout_par_kg(s)

    return {
        "currency": currency,
        "billed": round(billed, 2),
        "paid": round(paid, 2),
        "due": round(billed - paid, 2),
        "n_invoices": len(invs),
        "n_unpaid": n_unpaid,
        "n_overdue": len(overdue),
        "overdue_amount": round(overdue_amount, 2),
        "month_billed": round(month_billed, 2),
        "month_paid": round(month_paid, 2),
        "n_quotes": len(quos),
        "n_clients": len(clients),
        "n_orders_active": len(active_orders),
        "n_orders_todo": n_todo,
        "n_orders_printing": n_printing,
        "n_products": len(list_products()),
        "n_spools": len(spools),
        "stock_g": round(stock_g, 0),
        "stock_value": round(stock_value, 2),
        "n_low_stock": len(low_stock()),
    }


# ── Sauvegarde / restauration ───────────────────────────────────────────────────
def export_backup(dest_zip: Path) -> Path:
    """Exporte toutes les données métier dans un .zip (sécurité pour le pro)."""
    _DIR.mkdir(parents=True, exist_ok=True)
    dest_zip = Path(dest_zip)
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in _DIR.glob("*.json"):
            zf.write(f, f.name)
    return dest_zip


def import_backup(src_zip: Path) -> int:
    """Restaure les données depuis un .zip exporté. Remplace les fichiers JSON
    actuels (une copie .bak de chaque est conservée). Retourne le nb de fichiers."""
    src = Path(src_zip)
    with zipfile.ZipFile(src, "r") as zf:
        names = [n for n in zf.namelist() if n.endswith(".json") and "/" not in n]
        if not names:
            raise ValueError("Ce fichier ne contient pas de données neoSlice.")
        _DIR.mkdir(parents=True, exist_ok=True)
        for n in names:
            data = zf.read(n)
            dest = _DIR / Path(n).name
            if dest.exists():
                try:
                    import shutil
                    shutil.copy2(dest, dest.with_suffix(dest.suffix + ".bak"))
                except Exception:
                    pass
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
    return len(names)
