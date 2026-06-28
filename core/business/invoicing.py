"""Facturation — données fiscales par pays + calcul des totaux.

Taux de TVA / devises / mentions légales (2025-2026). INDICATIF : les taux et
obligations évoluent ; l'utilisateur peut ajuster le taux à la main. Sources :
administrations fiscales (AFC Suisse, service-public.fr, SPF Finances BE, etc.).
"""
from __future__ import annotations


# Par pays : devise, taux de TVA disponibles (taux normal en premier), mention
# légale type figurant sur la facture, et libellé de la taxe.
VAT_BY_COUNTRY: dict[str, dict] = {
    "Suisse": {
        "devise": "CHF", "vat_label": "TVA", "default": 8.1,
        "rates": [8.1, 3.8, 2.6, 0.0],
        "id_label": "N° TVA (CHE-xxx.xxx.xxx TVA)",
        "mentions": "TVA suisse — taux normal 8.1 %, réduit 2.6 %, hébergement 3.8 %.",
    },
    "France": {
        "devise": "EUR", "vat_label": "TVA", "default": 20.0,
        "rates": [20.0, 10.0, 5.5, 2.1, 0.0],
        "id_label": "N° TVA intracom. / SIRET",
        "mentions": ("En cas de retard de paiement : pénalités au taux légal + "
                     "indemnité forfaitaire de 40 € pour frais de recouvrement. "
                     "Pas d'escompte pour paiement anticipé.\n"
                     "Si non assujetti : « TVA non applicable, art. 293 B du CGI »."),
    },
    "Belgique": {
        "devise": "EUR", "vat_label": "TVA", "default": 21.0,
        "rates": [21.0, 12.0, 6.0, 0.0],
        "id_label": "N° TVA (BE 0xxx.xxx.xxx)",
        "mentions": "TVA belge — taux normal 21 %, intermédiaire 12 %, réduit 6 %.",
    },
    "Luxembourg": {
        "devise": "EUR", "vat_label": "TVA", "default": 17.0,
        "rates": [17.0, 14.0, 8.0, 3.0, 0.0],
        "id_label": "N° TVA (LU xxxxxxxx)",
        "mentions": "TVA luxembourgeoise — taux normal 17 %.",
    },
    "Allemagne": {
        "devise": "EUR", "vat_label": "USt.", "default": 19.0,
        "rates": [19.0, 7.0, 0.0],
        "id_label": "USt-IdNr. (DE xxxxxxxxx)",
        "mentions": "Umsatzsteuer — Regelsatz 19 %, ermäßigt 7 %.",
    },
    "Royaume-Uni": {
        "devise": "GBP", "vat_label": "VAT", "default": 20.0,
        "rates": [20.0, 5.0, 0.0],
        "id_label": "VAT No. (GB xxxxxxxxx)",
        "mentions": "UK VAT — standard 20 %, reduced 5 %.",
    },
    "Pays-Bas": {
        "devise": "EUR", "vat_label": "BTW", "default": 21.0,
        "rates": [21.0, 9.0, 0.0],
        "id_label": "BTW-nummer (NL…B01)",
        "mentions": "BTW Nederland — standaardtarief 21 %, verlaagd 9 %.",
    },
    "Italie": {
        "devise": "EUR", "vat_label": "IVA", "default": 22.0,
        "rates": [22.0, 10.0, 5.0, 4.0, 0.0],
        "id_label": "Partita IVA (IT…)",
        "mentions": "IVA italiana — aliquota ordinaria 22 %.",
    },
    "Espagne": {
        "devise": "EUR", "vat_label": "IVA", "default": 21.0,
        "rates": [21.0, 10.0, 4.0, 0.0],
        "id_label": "NIF / CIF",
        "mentions": "IVA España — tipo general 21 %, reducido 10 %.",
    },
    "Autriche": {
        "devise": "EUR", "vat_label": "USt.", "default": 20.0,
        "rates": [20.0, 13.0, 10.0, 0.0],
        "id_label": "UID (ATU…)",
        "mentions": "Umsatzsteuer Österreich — Normalsatz 20 %, ermäßigt 10/13 %.",
    },
    "Canada": {
        "devise": "CAD", "vat_label": "TPS/TVH", "default": 5.0,
        "rates": [5.0, 0.0],
        "id_label": "N° TPS/TVQ",
        "mentions": ("TPS fédérale 5 % indiquée. Ajoutez la taxe provinciale "
                     "(TVQ, TVH…) selon votre province."),
    },
    "États-Unis": {
        "devise": "USD", "vat_label": "Sales Tax", "default": 0.0,
        "rates": [0.0],
        "id_label": "EIN / Tax ID",
        "mentions": ("Pas de TVA fédérale aux États-Unis. Appliquez la sales tax "
                     "de votre état/comté si applicable (taux à saisir)."),
    },
    "Autre / manuel": {
        "devise": "EUR", "vat_label": "TVA", "default": 0.0,
        "rates": [0.0],
        "id_label": "N° fiscal",
        "mentions": "Renseignez le taux de taxe applicable à votre pays.",
    },
}

PAYS_ORDRE = list(VAT_BY_COUNTRY.keys())


def country_info(country: str) -> dict:
    return VAT_BY_COUNTRY.get(country, VAT_BY_COUNTRY["Autre / manuel"])


def currency(country: str) -> str:
    return country_info(country)["devise"]


def default_vat(country: str) -> float:
    return country_info(country)["default"]


def vat_rates(country: str) -> list[float]:
    return country_info(country)["rates"]


def vat_label(country: str) -> str:
    return country_info(country)["vat_label"]


def legal_mentions(country: str) -> str:
    return country_info(country)["mentions"]


# ──────────────────────────────────────────────────────────────────────────────
# Champs société additionnels exigés selon le pays (au-delà des champs universels
# nom/adresse/email/tél/n° fiscal/IBAN). Affichés dynamiquement dans le formulaire.
# (clé, clé i18n du libellé, placeholder, type)  type : "text" | "regime"
# ──────────────────────────────────────────────────────────────────────────────
COUNTRY_FIELDS: dict[str, list[tuple]] = {
    "France": [
        ("reg_number",   "fact.f_siret",     "123 456 789 00012",        "text"),
        ("reg_office",   "fact.f_rcs",       "RCS Paris 123 456 789",    "text"),
        ("capital",      "fact.f_capital",   "1 000",                    "text"),
        ("regime",       "fact.f_regime",    "",                          "regime"),
        ("recovery_fee", "fact.f_recovery",  "40",                        "text"),
    ],
    "Allemagne": [
        ("reg_number", "fact.f_steuernr",  "12/345/67890",             "text"),
        ("reg_office", "fact.f_handelsreg","HRB 12345, Amtsgericht …",  "text"),
    ],
    "Belgique":    [("reg_number",   "fact.f_bce",      "0123.456.789", "text"),
                    ("recovery_fee", "fact.f_recovery", "40",           "text")],
    "Luxembourg":  [("reg_number", "fact.f_rcsl",     "B123456",      "text"),
                    ("capital",    "fact.f_capital",  "12 000",        "text")],
    "Royaume-Uni": [("reg_number", "fact.f_companyno","12345678",     "text")],
    "Canada":      [("reg_number", "fact.f_busno",    "123456789 RT0001", "text")],
    "Pays-Bas":    [("reg_number",   "fact.f_kvk",      "12345678",   "text"),
                    ("recovery_fee", "fact.f_recovery", "40",         "text")],
    "Italie":      [("reg_number", "fact.f_rea",      "MI-1234567",   "text")],
    "Espagne":     [("reg_number", "fact.f_nif",      "B12345678",    "text")],
    "Autriche":    [("reg_number", "fact.f_firmenbuch","FN 123456a",  "text")],
}


# Montant légal/usuel par défaut des frais forfaitaires de recouvrement en cas de
# retard de paiement, dans la devise du pays. Utilisé si l'utilisateur ne renseigne
# pas son propre montant. (France : 40 € fixés par la loi LME / art. D441-5.)
_DEFAULT_RECOVERY_FEE: dict[str, str] = {
    "France": "40",
}


def default_recovery_fee(country: str) -> str:
    """Montant par défaut des frais de recouvrement pour ce pays ('' si aucun)."""
    return _DEFAULT_RECOVERY_FEE.get(country, "")


def company_legal_fields(country: str) -> list[tuple]:
    """Champs société spécifiques à afficher dans le formulaire pour ce pays."""
    return COUNTRY_FIELDS.get(country, [])


def _join_dot(parts) -> str:
    return "  ·  ".join(p for p in parts if p and str(p).strip())


def legal_block(company: dict, country: str) -> str:
    """Bloc de mentions légales obligatoires pour un devis/facture, RÉDIGÉ DANS LA
    LANGUE DU PAYS de facturation (les mentions légales ne se traduisent pas).
    Construit à partir de la fiche société (forme, capital, immatriculation,
    n° fiscal) + des obligations propres au pays.

    ⚠️ Indicatif : à faire valider par un comptable du pays concerné."""
    c = company or {}
    info = country_info(country)
    forme = str(c.get("forme", "")).strip()
    cap   = str(c.get("capital", "")).strip()
    reg   = str(c.get("reg_number", "")).strip()
    off   = str(c.get("reg_office", "")).strip()
    vat   = str(c.get("id_fiscal", "")).strip()
    dev   = info["devise"]
    # Frais forfaitaires de recouvrement (retard de paiement) — montant choisi par
    # l'utilisateur ; à défaut, valeur légale par pays (France : 40 €).
    fee   = str(c.get("recovery_fee", "")).strip() or _DEFAULT_RECOVERY_FEE.get(country, "")
    lines: list[str] = []

    if country == "France":
        lines.append(_join_dot([forme,
                                f"capital {cap} {dev}" if cap else "",
                                f"SIRET {reg}" if reg else "", off,
                                f"TVA {vat}" if vat else ""]))
        if c.get("regime") == "franchise":
            lines.append("TVA non applicable, art. 293 B du CGI.")
        lines.append("En cas de retard de paiement : pénalités au taux légal et "
                     f"indemnité forfaitaire de {fee} {dev} pour frais de recouvrement. "
                     "Pas d'escompte pour paiement anticipé.")
    elif country == "Allemagne":
        lines.append(_join_dot([forme,
                                f"Steuernr. {reg}" if reg else "",
                                f"USt-IdNr. {vat}" if vat else "", off]))
        lines.append("Rechnung gemäß § 14 UStG. Bei Kleinunternehmern wird gemäß "
                     "§ 19 UStG keine Umsatzsteuer ausgewiesen.")
    elif country == "Belgique":
        lines.append(_join_dot([forme, f"BCE {reg}" if reg else "",
                                f"TVA/BTW {vat}" if vat else ""]))
        indem = (f"indemnité forfaitaire de {fee} {dev}" if fee
                 else "indemnité forfaitaire")
        lines.append("Intérêts de retard et " + indem + " applicables en "
                     "cas de non-paiement à l'échéance.")
    elif country == "Luxembourg":
        lines.append(_join_dot([forme, f"capital {cap} {dev}" if cap else "",
                                f"RCS {reg}" if reg else "",
                                f"TVA {vat}" if vat else ""]))
        lines.append("TVA luxembourgeoise — taux normal 17 %.")
    elif country == "Royaume-Uni":
        lines.append(_join_dot([forme, f"Company No. {reg}" if reg else "",
                                f"VAT No. {vat}" if vat else ""]))
        lines.append("Late payment may incur statutory interest and compensation "
                     "(Late Payment of Commercial Debts Act).")
    elif country == "Suisse":
        lines.append(_join_dot([forme, f"IDE/TVA {vat}" if vat else ""]))
        lines.append("TVA suisse — taux normal 8.1 %, réduit 2.6 %, hébergement 3.8 %.")
    elif country == "Canada":
        lines.append(_join_dot([forme, f"BN {reg}" if reg else "",
                                f"TPS/TVH {vat}" if vat else ""]))
        lines.append("TPS/TVH fédérale indiquée. Ajoutez la taxe provinciale "
                     "(TVQ, TVH…) selon la province.")
    elif country == "Pays-Bas":
        lines.append(_join_dot([forme, f"KvK {reg}" if reg else "",
                                f"BTW {vat}" if vat else ""]))
        kosten = (f"incassokosten ({fee} {dev})" if fee else "incassokosten")
        lines.append("Bij niet-tijdige betaling zijn wettelijke rente en "
                     + kosten + " verschuldigd.")
    elif country == "Italie":
        lines.append(_join_dot([forme, f"REA {reg}" if reg else "",
                                f"P. IVA {vat}" if vat else ""]))
        lines.append("In caso di ritardato pagamento si applicano interessi di "
                     "mora ai sensi del D.lgs. 231/2002.")
    elif country == "Espagne":
        lines.append(_join_dot([forme, f"NIF {reg or vat}" if (reg or vat) else ""]))
        lines.append("En caso de impago se aplicarán intereses de demora "
                     "conforme a la Ley 3/2004.")
    elif country == "Autriche":
        lines.append(_join_dot([forme, f"FN {reg}" if reg else "",
                                f"UID {vat}" if vat else ""]))
        lines.append("Rechnung gemäß § 11 UStG. Bei Kleinunternehmern keine "
                     "USt nach § 6 Abs. 1 Z 27 UStG.")
    elif country == "États-Unis":
        lines.append(_join_dot([forme, f"EIN {vat}" if vat else ""]))
        lines.append("No federal VAT. Applicable state/county sales tax to be added.")
    else:
        lines.append(_join_dot([forme, vat]))
        if info.get("mentions"):
            lines.append(info["mentions"])
    return "\n".join(l for l in lines if l and l.strip())


def company_footer(company: dict, lang: str | None = None) -> str:
    """Ligne de pied de page = coordonnées de l'émetteur (devis & factures),
    à la place d'une mention « neoSlice ». Si `lang` est fourni, le nom du pays
    est traduit dans la langue du document. Les mentions légales propres au pays
    restent fournies par legal_block()."""
    if not isinstance(company, dict):
        return ""
    nom = (company.get("nom") or "").strip()
    forme = (company.get("forme") or "").strip()
    head = f"{nom} ({forme})" if nom and forme else (nom or forme)
    pays = (company.get("pays", "") or "").strip()
    if lang:
        from core.business.doc_i18n import country_name
        pays = country_name(pays, lang)
    addr = " ".join(p for p in (company.get("adresse", "").strip(),
                                f"{company.get('cp','')} {company.get('ville','')}".strip(),
                                pays) if p)
    parts = [head, addr,
             (company.get("email") or "").strip(),
             (company.get("tel") or "").strip(),
             (company.get("id_fiscal") or "").strip()]
    return "  ·  ".join(p for p in parts if p)


def compute(items: list[dict], vat_rate: float, discount_pct: float = 0.0) -> dict:
    """items = [{designation, qty, unit_price_ht}]. Retourne HT/remise/TVA/TTC."""
    total_ht = 0.0
    for it in items:
        try:
            total_ht += float(it.get("qty") or 0) * float(it.get("unit_price_ht") or 0)
        except (TypeError, ValueError):
            continue
    discount = total_ht * max(0.0, min(100.0, discount_pct)) / 100.0
    net_ht = max(0.0, total_ht - discount)
    tva = net_ht * max(0.0, vat_rate) / 100.0
    return {
        "total_ht": round(total_ht, 2),
        "discount": round(discount, 2),
        "net_ht": round(net_ht, 2),
        "tva": round(tva, 2),
        "ttc": round(net_ht + tva, 2),
    }
