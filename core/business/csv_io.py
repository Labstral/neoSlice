# -*- coding: utf-8 -*-
"""Import / export CSV de l'Espace Pro : clients, devis, commandes.

Demande d'un client Pro (Nord Impression 3D) : ses prospects arrivent d'un
outil commercial (Limova) et il ressaisissait chaque client à la main dans
neoSlice. Pas d'API (neoSlice reste 100 % local) : un échange de FICHIERS,
générique, qui marche avec Limova comme avec n'importe quel CRM ou tableur.

Import : lecture tolérante (séparateur et encodage détectés, Excel français
compris), colonnes reconnues par leur nom (FR/EN), doublons repérés par
référence externe puis adresse mail : on complète la fiche, on ne duplique
pas, et une case vide du fichier n'efface jamais une donnée existante.
Export : clients, devis, commandes (statut en code stable ET en clair), au
format de l'export comptable (« ; », UTF-8 avec BOM : Excel l'ouvre juste).

Module PUR (aucune dépendance Qt) → testable.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

from core.i18n import _


# ── Champs importables ───────────────────────────────────────────────────────
# (clé de la fiche client, synonymes d'en-tête NORMALISÉS : minuscules, sans
#  accents, ponctuation → espaces). « prenom » est un pseudo-champ fusionné
#  dans « nom » (les CRM séparent souvent prénom et nom).
CHAMPS_CLIENT: list[tuple[str, tuple[str, ...]]] = [
    ("societe", ("societe", "entreprise", "company", "company name", "raison sociale",
                 "organisation", "organization", "nom entreprise",
                 "nom de l entreprise", "nom de la societe", "structure",
                 "account", "account name")),
    ("prenom", ("prenom", "first name", "firstname", "given name",
                "prenom du dirigeant", "prenom du contact", "prenom contact",
                "prenom du gerant")),
    ("nom", ("nom", "contact", "nom du contact", "nom contact", "name", "full name",
             "nom complet", "last name", "lastname", "nom de famille",
             "interlocuteur", "decideur", "contact name",
             # prospection B2B : l'interlocuteur est le dirigeant ou le gérant
             "nom du dirigeant", "nom dirigeant", "dirigeant", "dirigeant complet",
             "gerant", "nom du gerant", "responsable",
             "nom et prenom", "prenom et nom", "nom prenom", "prenom nom")),
    ("email", ("email", "e mail", "mail", "courriel", "adresse mail",
               "adresse email", "adresse e mail", "email address",
               "e mail address")),
    ("tel", ("tel", "telephone", "phone", "phone number", "mobile", "portable",
             "numero de telephone", "tel portable", "telephone mobile")),
    ("adresse", ("adresse", "address", "rue", "street", "adresse postale",
                 "address line 1", "street address")),
    ("cp", ("cp", "code postal", "postal code", "zip", "zip code", "postcode")),
    ("ville", ("ville", "city", "commune", "localite", "town")),
    ("pays", ("pays", "country")),
    ("id_fiscal", ("id fiscal", "siret", "siren", "tva", "numero tva", "n tva",
                   "tva intracommunautaire", "vat", "vat number", "tax id",
                   "ide", "uid")),
    ("notes", ("notes", "note", "commentaire", "commentaires", "comment",
               "comments", "remarques", "description")),
    ("ref_externe", ("reference externe", "ref externe", "id externe",
                     "external id", "external ref", "external reference",
                     "reference", "ref", "id", "crm id", "lead id",
                     "id prospect", "id contact", "id client")),
]
CLES_CLIENT = [c for c, _s in CHAMPS_CLIENT]

# En-têtes à ne JAMAIS deviner par « contient » : ils décrivent autre chose
# (« Fonction du dirigeant » n'est pas un nom, « Code NAF » pas un code postal).
_MOTS_NEUTRES = {"fonction", "poste", "titre", "role", "job", "title", "site",
                 "web", "url", "linkedin", "naf", "ape", "activite", "secteur"}

# Libellé (clé i18n) de chaque champ dans la boîte d'import.
LIBELLES_CHAMPS = {
    "societe": "client.company", "prenom": "csvio.firstname", "nom": "client.name",
    "email": "client.email", "tel": "client.phone", "adresse": "client.address",
    "cp": "client.zip", "ville": "client.city", "pays": "client.country",
    "id_fiscal": "client.taxid", "notes": "client.notes",
    "ref_externe": "client.ref_ext",
}

# Codes pays usuels → nom du sélecteur de pays.
_CODES_PAYS = {
    "fr": "France", "ch": "Suisse", "be": "Belgique", "lu": "Luxembourg",
    "de": "Allemagne", "at": "Autriche", "it": "Italie", "es": "Espagne",
    "nl": "Pays-Bas", "gb": "Royaume-Uni", "uk": "Royaume-Uni",
    "us": "États-Unis", "usa": "États-Unis", "ca": "Canada",
}


def _norm(txt) -> str:
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return " ".join(t.split())


# ── Lecture ──────────────────────────────────────────────────────────────────
def lire_csv(chemin) -> tuple[list[str], list[list[str]]]:
    """(en-têtes, lignes) d'un CSV quelconque.

    Encodage : UTF-8 (avec ou sans BOM), sinon Windows-1252 (Excel français).
    Séparateur : celui qui apparaît le plus dans la ligne d'en-tête parmi
    « ; », « , », tabulation et « | ». Les lignes vides sont ignorées, les
    lignes courtes complétées. ValueError si le fichier est vide."""
    brut = Path(chemin).read_bytes()
    texte = ""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = brut.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    if not texte.strip():
        raise ValueError("fichier vide")

    premiere = texte.lstrip("\n").split("\n", 1)[0]
    sep = max((";", ",", "\t", "|"), key=premiere.count)
    if premiere.count(sep) == 0:
        sep = ";"                     # une seule colonne : peu importe

    tout = [r for r in csv.reader(io.StringIO(texte), delimiter=sep)
            if any((c or "").strip() for c in r)]
    if not tout:
        raise ValueError("fichier vide")
    entetes = [(c or "").strip() for c in tout[0]]
    lignes = []
    for r in tout[1:]:
        r = [(c or "").strip() for c in r]
        r += [""] * (len(entetes) - len(r))
        lignes.append(r[:len(entetes)])
    return entetes, lignes


def deviner_colonnes(entetes: list[str]) -> list[str]:
    """Pour chaque colonne du fichier, le champ client deviné ("" = ignorée).

    Correspondance exacte d'abord, puis « l'en-tête contient un synonyme »
    (synonymes d'au moins 4 lettres, pour ne pas prendre « id » partout).
    Un champ n'est attribué qu'à UNE colonne : la première qui y correspond."""
    normes = [_norm(e) for e in entetes]
    resultat = [""] * len(entetes)
    pris: set[str] = set()
    for i, n in enumerate(normes):                       # 1. exacte
        for cle, syn in CHAMPS_CLIENT:
            if cle not in pris and n in syn:
                resultat[i] = cle
                pris.add(cle)
                break
    for i, n in enumerate(normes):                       # 2. contient
        if resultat[i] or not n or set(n.split()) & _MOTS_NEUTRES:
            continue
        # Plusieurs champs peuvent correspondre (« Email de contact » contient
        # « email » ET « contact ») : le mot qui arrive EN PREMIER dans l'en-tête
        # l'emporte (c'est le nom de la colonne, la suite le précise), puis le
        # synonyme le plus long. Vécu sur un vrai export Limova : les adresses
        # mail partaient dans le nom du contact.
        meilleur = None
        for cle, syn in CHAMPS_CLIENT:
            if cle in pris:
                continue
            for s in syn:
                if len(s) < 4:
                    continue
                m = re.search(rf"\b{re.escape(s)}\b", n)
                if m and (meilleur is None or (m.start(), -len(s)) < meilleur[0]):
                    meilleur = ((m.start(), -len(s)), cle)
        if meilleur:
            resultat[i] = meilleur[1]
            pris.add(meilleur[1])
    return resultat


def _pays_connu(valeur: str) -> str:
    """Nom du sélecteur de pays (« Suisse »…) depuis un nom dans n'importe
    quelle langue (« Switzerland », « Schweiz ») ou un code (« CH ») ;
    "" si inconnu (on garde alors le pays par défaut plutôt qu'une valeur
    que la facturation ne saurait pas traiter)."""
    from core.business.doc_i18n import COUNTRY_NAMES
    n = _norm(valeur)
    if not n:
        return ""
    if n in _CODES_PAYS:
        return _CODES_PAYS[n]
    for cle, traductions in COUNTRY_NAMES.items():
        if n == _norm(cle) or any(n == _norm(v) for v in traductions.values()):
            return cle
    return ""


def preparer_clients(lignes: list[list[str]], colonnes: list[str]) -> list[dict]:
    """Fiches clients prêtes à importer. Plusieurs colonnes associées au même
    champ sont mises bout à bout (ex. « Adresse 1 » + « Adresse 2 »). Une
    ligne sans contact, société ni adresse mail est écartée."""
    out = []
    for r in lignes:
        d: dict[str, str] = {}
        for i, cle in enumerate(colonnes):
            if not cle or i >= len(r) or not r[i]:
                continue
            d[cle] = f"{d[cle]} {r[i]}" if cle in d else r[i]
        prenom = d.pop("prenom", "")
        nom = d.get("nom", "")
        # Fusion prénom + nom, sauf si le nom contient DÉJÀ le prénom (colonne
        # « nom complet » choisie) : jamais de « Hamid Hamid Gaoua ».
        if prenom and prenom.lower() not in nom.lower():
            d["nom"] = f"{prenom} {nom}".strip()
        if "pays" in d:
            p = _pays_connu(d["pays"])
            if p:
                d["pays"] = p
            else:
                d.pop("pays")
        if d.get("nom") or d.get("societe") or d.get("email"):
            out.append(d)
    return out


# ── Import ───────────────────────────────────────────────────────────────────
def importer_clients(clients: list[dict]) -> dict:
    """Crée ou complète les fiches. Retourne {crees, maj, inchanges}.

    Un client existant est retrouvé par sa RÉFÉRENCE EXTERNE, sinon par son
    ADRESSE MAIL (sans tenir compte des majuscules). Il est complété avec les
    seules valeurs NON vides du fichier : réimporter une liste plus pauvre
    n'efface rien. Les doublons à l'intérieur du fichier sont fusionnés."""
    from core.business import store

    # Clés d'identité, de la plus sûre à la moins sûre : référence externe,
    # identifiant fiscal (SIREN, SIRET, TVA : unique par entreprise), mail.
    index: dict[str, dict[str, dict]] = {"ref": {}, "fisc": {}, "mail": {}}

    def cles(c: dict) -> dict:
        return {"ref": (c.get("ref_externe") or "").strip().lower(),
                "fisc": re.sub(r"[^0-9a-z]", "", (c.get("id_fiscal") or "").lower()),
                "mail": (c.get("email") or "").strip().lower()}

    def indexer(c: dict) -> None:
        for k, v in cles(c).items():
            if v:
                index[k][v] = c

    for c in store.list_clients():
        indexer(c)

    # Pays d'une NOUVELLE fiche sans colonne pays : celui de l'atelier (vécu :
    # 60 garages du Nord importés en « Suisse », le défaut d'une fiche vierge,
    # donc TVA et devise fausses sur leurs futures factures).
    pays_atelier = _pays_connu(store.get_company().get("pays", ""))

    crees = maj = inchanges = 0
    for d in clients:
        k = cles(d)
        cible = None
        for cle_id in ("ref", "fisc", "mail"):
            if cible is None and k[cle_id]:
                cible = index[cle_id].get(k[cle_id])
        if cible is None:
            nouveau = dict(d)
            if "pays" not in nouveau and pays_atelier:
                nouveau["pays"] = pays_atelier
            indexer(store.add_client(nouveau))
            crees += 1
            continue
        modif = {k: v for k, v in d.items() if v and str(cible.get(k) or "") != v}
        if modif:
            cible = store.update_client(cible["id"], modif) or cible
            indexer(cible)
            maj += 1
        else:
            inchanges += 1
    return {"crees": crees, "maj": maj, "inchanges": inchanges}


# ── Export ───────────────────────────────────────────────────────────────────
def _ecrire(dest, entetes: list[str], lignes: list[list]) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(entetes)
        w.writerows(lignes)
    return dest


# Ces en-têtes sont RECONNUS par deviner_colonnes : un export se réimporte tel
# quel (aller-retour avec un outil externe sans rien remapper).
ENTETES_CLIENTS = ["Référence externe", "Société", "Contact", "Email", "Téléphone",
                   "Adresse", "Code postal", "Ville", "Pays", "ID fiscal", "Notes",
                   "Créé le", "ID neoSlice"]


def export_clients_csv(dest) -> Path:
    from core.business import store
    lignes = [[c.get("ref_externe", ""), c.get("societe", ""), c.get("nom", ""),
               c.get("email", ""), c.get("tel", ""), c.get("adresse", ""),
               c.get("cp", ""), c.get("ville", ""), c.get("pays", ""),
               c.get("id_fiscal", ""), c.get("notes", ""),
               str(c.get("cree_le", ""))[:10], c.get("id", "")]
              for c in store.list_clients()]
    return _ecrire(dest, ENTETES_CLIENTS, lignes)


def _client_de(doc: dict) -> tuple[str, str, str]:
    """(libellé, référence externe, adresse mail) du client lié à un document."""
    from core.business import store
    c = store.get_client(doc.get("client_id") or "") or {}
    libelle = doc.get("client_label") or (store.client_label(c) if c else "")
    return libelle, c.get("ref_externe", ""), c.get("email", "")


def export_devis_csv(dest) -> Path:
    from core.business import store
    entetes = ["Numéro", "Date", "Client", "Référence externe client", "Email client",
               "Pièce", "Quantité", "Total", "Devise", "Statut", "Code statut",
               "Facture", "ID neoSlice"]
    lignes = []
    for q in sorted(store.list_quotes(), key=lambda q: str(q.get("number", ""))):
        libelle, ref, mail = _client_de(q)
        code = q.get("status", "open") or "open"
        cle = f"csvio.q_{code}"
        statut = _(cle) if _(cle) != cle else code
        lignes.append([q.get("number", ""), q.get("date", ""), libelle, ref, mail,
                       q.get("part_name", ""), q.get("qty", 1),
                       f"{float(q.get('total_price') or 0):.2f}", q.get("currency", ""),
                       statut, code, q.get("invoice_number", ""), q.get("id", "")])
    return _ecrire(dest, entetes, lignes)


def export_commandes_csv(dest) -> Path:
    from core.business import store
    entetes = ["Numéro", "Créée le", "Client", "Référence externe client", "Statut",
               "Code statut", "Échéance", "Total TTC", "Devise", "Devis", "Facture",
               "Filament (g)", "Désignation", "ID neoSlice"]
    lignes = []
    for o in sorted(store.list_orders(), key=lambda o: str(o.get("number", ""))):
        libelle, ref, _mail = _client_de(o)
        code = o.get("status", "todo") or "todo"
        cle = f"ord.status_{code}"
        statut = _(cle) if _(cle) != cle else code
        designation = ", ".join(str(it.get("designation") or "").strip()
                                for it in (o.get("items") or [])
                                if str(it.get("designation") or "").strip())
        lignes.append([o.get("number", ""), str(o.get("cree_le", ""))[:10], libelle,
                       ref, statut, code, o.get("echeance", ""),
                       f"{float(o.get('total_ttc') or 0):.2f}", o.get("currency", ""),
                       o.get("quote_number", ""), o.get("invoice_number", ""),
                       f"{float(o.get('grams') or 0):g}", designation, o.get("id", "")])
    return _ecrire(dest, entetes, lignes)
