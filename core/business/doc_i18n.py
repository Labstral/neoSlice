"""Langue des DOCUMENTS (factures, devis, bons) — indépendante de la langue de
l'interface. Une facture destinée à un client allemand doit être en allemand,
quelle que soit la langue de l'app.

`doc_lang(country, company)` choisit la langue (override possible via la fiche
société), et `t(key, lang)` traduit les ~40 termes structurels des PDF.

Langues couvertes : fr · en · de · nl · it · es. Repli : en.
"""
from __future__ import annotations

# Langue de document par défaut selon le pays de facturation.
DEFAULT_DOC_LANG: dict[str, str] = {
    "France": "fr", "Suisse": "fr", "Belgique": "fr", "Luxembourg": "fr", "Canada": "fr",
    "Allemagne": "de", "Autriche": "de",
    "Royaume-Uni": "en", "États-Unis": "en", "Irlande": "en",
    "Pays-Bas": "nl",
    "Italie": "it",
    "Espagne": "es",
}

DOC_LANGS = ["fr", "en", "de", "nl", "it", "es"]
DOC_LANG_LABELS = {
    "fr": "Français", "en": "English", "de": "Deutsch",
    "nl": "Nederlands", "it": "Italiano", "es": "Español",
}


def doc_lang(country: str, company: dict | None = None) -> str:
    """Langue du document : override explicite de la société, sinon défaut pays."""
    if company:
        ov = str(company.get("doc_lang", "")).strip().lower()
        if ov in DOC_LANGS:
            return ov
    return DEFAULT_DOC_LANG.get(country, "en")


# Termes structurels des PDF, par langue. Clé → {lang: texte}.
TERMS: dict[str, dict[str, str]] = {
    # ── Titres ──
    "invoice":   {"fr": "FACTURE", "en": "INVOICE", "de": "RECHNUNG", "nl": "FACTUUR", "it": "FATTURA", "es": "FACTURA"},
    "quote":     {"fr": "DEVIS", "en": "QUOTE", "de": "ANGEBOT", "nl": "OFFERTE", "it": "PREVENTIVO", "es": "PRESUPUESTO"},
    "workorder": {"fr": "BON DE PRODUCTION", "en": "WORK ORDER", "de": "FERTIGUNGSAUFTRAG", "nl": "WERKORDER", "it": "ORDINE DI PRODUZIONE", "es": "ORDEN DE PRODUCCIÓN"},
    # ── Méta ──
    "number": {"fr": "N°", "en": "No.", "de": "Nr.", "nl": "Nr.", "it": "N.", "es": "N.º"},
    "date":   {"fr": "Date", "en": "Date", "de": "Datum", "nl": "Datum", "it": "Data", "es": "Fecha"},
    "due":    {"fr": "Échéance", "en": "Due date", "de": "Fällig am", "nl": "Vervaldatum", "it": "Scadenza", "es": "Vencimiento"},
    "status": {"fr": "Statut", "en": "Status", "de": "Status", "nl": "Status", "it": "Stato", "es": "Estado"},
    # ── Parties ──
    "billto": {"fr": "Facturé à", "en": "Bill to", "de": "Rechnung an", "nl": "Factuur aan", "it": "Destinatario", "es": "Facturar a"},
    "client": {"fr": "Client", "en": "Client", "de": "Kunde", "nl": "Klant", "it": "Cliente", "es": "Cliente"},
    "your_company": {"fr": "Votre société", "en": "Your company", "de": "Ihr Unternehmen", "nl": "Uw bedrijf", "it": "La tua azienda", "es": "Su empresa"},
    # ── Tableau ──
    "desig":      {"fr": "Désignation", "en": "Description", "de": "Beschreibung", "nl": "Omschrijving", "it": "Descrizione", "es": "Descripción"},
    "qty":        {"fr": "Qté", "en": "Qty", "de": "Menge", "nl": "Aantal", "it": "Q.tà", "es": "Cant."},
    "unit_price": {"fr": "PU HT", "en": "Unit price", "de": "Einzelpreis", "nl": "Stukprijs", "it": "Prezzo unit.", "es": "Precio unit."},
    "line_total": {"fr": "Total HT", "en": "Total", "de": "Gesamt", "nl": "Totaal", "it": "Totale", "es": "Total"},
    # ── Totaux ──
    "subtotal": {"fr": "Total HT", "en": "Subtotal", "de": "Nettobetrag", "nl": "Subtotaal", "it": "Imponibile", "es": "Base imponible"},
    "discount": {"fr": "Remise", "en": "Discount", "de": "Rabatt", "nl": "Korting", "it": "Sconto", "es": "Descuento"},
    "net":      {"fr": "Net HT", "en": "Net", "de": "Netto", "nl": "Netto", "it": "Netto", "es": "Neto"},
    "total":    {"fr": "TOTAL TTC", "en": "TOTAL", "de": "GESAMTBETRAG", "nl": "TOTAAL", "it": "TOTALE", "es": "TOTAL"},
    "total_simple": {"fr": "TOTAL", "en": "TOTAL", "de": "GESAMT", "nl": "TOTAAL", "it": "TOTALE", "es": "TOTAL"},
    # ── Paiement ──
    "terms": {"fr": "Conditions de paiement", "en": "Payment terms", "de": "Zahlungsbedingungen", "nl": "Betalingsvoorwaarden", "it": "Condizioni di pagamento", "es": "Condiciones de pago"},
    # ── Bon de production ──
    "consumptions": {"fr": "Consommation filament", "en": "Filament usage", "de": "Filamentverbrauch", "nl": "Filamentverbruik", "it": "Consumo di filamento", "es": "Consumo de filamento"},
    "unassigned":   {"fr": "(bobine non assignée)", "en": "(spool unassigned)", "de": "(Spule nicht zugewiesen)", "nl": "(spoel niet toegewezen)", "it": "(bobina non assegnata)", "es": "(bobina no asignada)"},
    "notes":        {"fr": "Notes", "en": "Notes", "de": "Anmerkungen", "nl": "Opmerkingen", "it": "Note", "es": "Notas"},
    "wo_footer":    {"fr": "Document de production interne", "en": "Internal production document", "de": "Internes Produktionsdokument", "nl": "Intern productiedocument", "it": "Documento di produzione interno", "es": "Documento de producción interno"},
    # ── Lettre de relance (facture impayée) ──
    "reminder_title": {"fr": "RELANCE", "en": "PAYMENT REMINDER", "de": "ZAHLUNGSERINNERUNG", "nl": "BETALINGSHERINNERING", "it": "SOLLECITO DI PAGAMENTO", "es": "RECORDATORIO DE PAGO"},
    "reminder_obj":   {"fr": "Objet : relance de la facture {number}", "en": "Re: reminder for invoice {number}", "de": "Betreff: Zahlungserinnerung zur Rechnung {number}", "nl": "Betreft: herinnering factuur {number}", "it": "Oggetto: sollecito fattura {number}", "es": "Asunto: recordatorio de la factura {number}"},
    "reminder_greeting": {"fr": "Madame, Monsieur,", "en": "Dear Sir or Madam,", "de": "Sehr geehrte Damen und Herren,", "nl": "Geachte heer, mevrouw,", "it": "Gentile Cliente,", "es": "Estimado cliente:"},
    "reminder_body": {
        "fr": "Sauf erreur ou omission de notre part, la facture {number} du {date}, d'un montant de {amount}, arrivée à échéance le {due}, demeure impayée à ce jour ({days} jours de retard). Nous vous remercions de bien vouloir procéder à son règlement dans les meilleurs délais.",
        "en": "Unless we are mistaken, invoice {number} dated {date}, for the amount of {amount} and due on {due}, remains unpaid to date ({days} days overdue). We kindly ask you to settle it at your earliest convenience.",
        "de": "Sofern uns kein Fehler unterlaufen ist, ist die Rechnung {number} vom {date} über {amount}, fällig am {due}, bis heute unbezahlt ({days} Tage überfällig). Wir bitten Sie, den Betrag baldmöglichst zu begleichen.",
        "nl": "Tenzij wij ons vergissen, is factuur {number} van {date}, ten bedrage van {amount} en vervallen op {due}, tot op heden onbetaald ({days} dagen te laat). Wij verzoeken u vriendelijk deze zo spoedig mogelijk te voldoen.",
        "it": "Salvo errori od omissioni da parte nostra, la fattura {number} del {date}, per un importo di {amount}, scaduta il {due}, risulta a oggi non pagata ({days} giorni di ritardo). La preghiamo di provvedere al saldo quanto prima.",
        "es": "Salvo error u omisión por nuestra parte, la factura {number} de fecha {date}, por un importe de {amount} y vencida el {due}, sigue pendiente de pago a día de hoy ({days} días de retraso). Le rogamos proceda a su liquidación a la mayor brevedad.",
    },
    "reminder_body2": {
        "fr": "Si votre règlement a été effectué entre-temps, nous vous prions de ne pas tenir compte de ce courrier. Nous restons à votre disposition pour toute question.",
        "en": "If your payment has been made in the meantime, please disregard this letter. We remain at your disposal for any questions.",
        "de": "Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben, betrachten Sie es bitte als gegenstandslos. Für Rückfragen stehen wir gerne zur Verfügung.",
        "nl": "Indien uw betaling inmiddels is verricht, kunt u deze brief als niet verzonden beschouwen. Wij staan tot uw beschikking voor vragen.",
        "it": "Qualora il pagamento fosse già stato effettuato, La preghiamo di non tenere conto della presente. Restiamo a disposizione per qualsiasi chiarimento.",
        "es": "Si el pago ya se ha efectuado, le rogamos que no tenga en cuenta esta carta. Quedamos a su disposición para cualquier consulta.",
    },
    "reminder_sign": {"fr": "Cordialement,", "en": "Kind regards,", "de": "Mit freundlichen Grüßen", "nl": "Met vriendelijke groet,", "it": "Cordiali saluti,", "es": "Atentamente,"},
    # ── Statuts de commande ──
    "st_todo":      {"fr": "À faire", "en": "To do", "de": "Offen", "nl": "Te doen", "it": "Da fare", "es": "Pendiente"},
    "st_printing":  {"fr": "En impression", "en": "Printing", "de": "Im Druck", "nl": "Aan het printen", "it": "In stampa", "es": "Imprimiendo"},
    "st_done":      {"fr": "Terminé", "en": "Done", "de": "Fertig", "nl": "Klaar", "it": "Completato", "es": "Terminado"},
    "st_delivered": {"fr": "Livré", "en": "Delivered", "de": "Geliefert", "nl": "Geleverd", "it": "Consegnato", "es": "Entregado"},
    "st_paid":      {"fr": "Payé", "en": "Paid", "de": "Bezahlt", "nl": "Betaald", "it": "Pagato", "es": "Pagado"},
    "st_cancelled": {"fr": "Annulé", "en": "Cancelled", "de": "Storniert", "nl": "Geannuleerd", "it": "Annullato", "es": "Cancelado"},
    # ── Devis (calculateur) ──
    "part":         {"fr": "Pièce", "en": "Part", "de": "Teil", "nl": "Onderdeel", "it": "Pezzo", "es": "Pieza"},
    "r_material":   {"fr": "Matière", "en": "Material", "de": "Material", "nl": "Materiaal", "it": "Materiale", "es": "Material"},
    "r_electricity":{"fr": "Électricité", "en": "Electricity", "de": "Strom", "nl": "Elektriciteit", "it": "Elettricità", "es": "Electricidad"},
    "r_wear":       {"fr": "Usure machine", "en": "Machine wear", "de": "Maschinenverschleiß", "nl": "Machineslijtage", "it": "Usura macchina", "es": "Desgaste de máquina"},
    "r_labor":      {"fr": "Main d'œuvre", "en": "Labor", "de": "Arbeitszeit", "nl": "Arbeid", "it": "Manodopera", "es": "Mano de obra"},
    "r_packaging":  {"fr": "Emballage", "en": "Packaging", "de": "Verpackung", "nl": "Verpakking", "it": "Imballaggio", "es": "Embalaje"},
    "r_failure":    {"fr": "Marge échec", "en": "Failure margin", "de": "Ausschussmarge", "nl": "Faalmarge", "it": "Margine scarti", "es": "Margen de fallos"},
    "r_costprice":  {"fr": "Coût de revient", "en": "Cost price", "de": "Selbstkosten", "nl": "Kostprijs", "it": "Costo di produzione", "es": "Coste de producción"},
    "r_margin":     {"fr": "Marge", "en": "Margin", "de": "Marge", "nl": "Marge", "it": "Margine", "es": "Margen"},
    "r_saleprice":  {"fr": "Prix de vente conseillé", "en": "Recommended price", "de": "Empf. Verkaufspreis", "nl": "Adviesprijs", "it": "Prezzo consigliato", "es": "Precio recomendado"},
    "r_total_qty":  {"fr": "Total ({n})", "en": "Total ({n})", "de": "Gesamt ({n})", "nl": "Totaal ({n})", "it": "Totale ({n})", "es": "Total ({n})"},
    "quote_disclaimer": {
        "fr": "Estimation établie à titre indicatif, sous réserve de modification. Valable 30 jours à compter de la date d'émission.",
        "en": "Estimate provided for information, subject to change. Valid for 30 days from the date of issue.",
        "de": "Unverbindlicher Kostenvoranschlag, Änderungen vorbehalten. Gültig 30 Tage ab Ausstellungsdatum.",
        "nl": "Vrijblijvende schatting, onder voorbehoud van wijzigingen. Geldig gedurende 30 dagen na uitgiftedatum.",
        "it": "Stima indicativa, soggetta a modifiche. Valida 30 giorni dalla data di emissione.",
        "es": "Estimación a título indicativo, sujeta a cambios. Válida 30 días desde la fecha de emisión.",
    },
}


def t(key: str, lang: str = "en") -> str:
    """Terme structurel d'un document dans la langue voulue (repli en/clé)."""
    entry = TERMS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


# Nom du pays (clé = nom français du sélecteur) traduit par langue de document.
COUNTRY_NAMES: dict[str, dict[str, str]] = {
    "Suisse":       {"fr": "Suisse", "en": "Switzerland", "de": "Schweiz", "nl": "Zwitserland", "it": "Svizzera", "es": "Suiza"},
    "France":       {"fr": "France", "en": "France", "de": "Frankreich", "nl": "Frankrijk", "it": "Francia", "es": "Francia"},
    "Belgique":     {"fr": "Belgique", "en": "Belgium", "de": "Belgien", "nl": "België", "it": "Belgio", "es": "Bélgica"},
    "Luxembourg":   {"fr": "Luxembourg", "en": "Luxembourg", "de": "Luxemburg", "nl": "Luxemburg", "it": "Lussemburgo", "es": "Luxemburgo"},
    "Allemagne":    {"fr": "Allemagne", "en": "Germany", "de": "Deutschland", "nl": "Duitsland", "it": "Germania", "es": "Alemania"},
    "Royaume-Uni":  {"fr": "Royaume-Uni", "en": "United Kingdom", "de": "Vereinigtes Königreich", "nl": "Verenigd Koninkrijk", "it": "Regno Unito", "es": "Reino Unido"},
    "Pays-Bas":     {"fr": "Pays-Bas", "en": "Netherlands", "de": "Niederlande", "nl": "Nederland", "it": "Paesi Bassi", "es": "Países Bajos"},
    "Italie":       {"fr": "Italie", "en": "Italy", "de": "Italien", "nl": "Italië", "it": "Italia", "es": "Italia"},
    "Espagne":      {"fr": "Espagne", "en": "Spain", "de": "Spanien", "nl": "Spanje", "it": "Spagna", "es": "España"},
    "Autriche":     {"fr": "Autriche", "en": "Austria", "de": "Österreich", "nl": "Oostenrijk", "it": "Austria", "es": "Austria"},
    "Canada":       {"fr": "Canada", "en": "Canada", "de": "Kanada", "nl": "Canada", "it": "Canada", "es": "Canadá"},
    "États-Unis":   {"fr": "États-Unis", "en": "United States", "de": "Vereinigte Staaten", "nl": "Verenigde Staten", "it": "Stati Uniti", "es": "Estados Unidos"},
}


def country_name(country: str, lang: str = "en") -> str:
    """Nom du pays dans la langue du document (repli : nom d'origine)."""
    entry = COUNTRY_NAMES.get(country)
    if not entry:
        return country or ""
    return entry.get(lang) or entry.get("en") or country
