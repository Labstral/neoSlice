"""Génère une facture PDF professionnelle (QPdfWriter natif, sans dépendance).

render_invoice(path, invoice, company) — mise en page A4 : bloc émetteur, bloc
client, tableau des lignes, totaux HT/TVA/TTC, conditions de paiement, IBAN et
mentions légales du pays.
"""
from __future__ import annotations

from core.business import invoicing
from core.i18n import _
from ui.styles.theme import FONT_MAIN, FONT_MONO


def _fmt(v: float, cur: str) -> str:
    return f"{v:,.2f} {cur}".replace(",", " ")


def render_invoice(path: str, invoice: dict, company: dict) -> str:
    from PySide6.QtGui import QPdfWriter, QPainter, QPageSize, QColor, QFont
    from PySide6.QtCore import QMarginsF, Qt

    cur = invoice.get("currency") or invoicing.currency(invoice.get("country", ""))
    items = invoice.get("items", [])
    vat_rate = float(invoice.get("vat_rate", 0) or 0)
    disc = float(invoice.get("discount_pct", 0) or 0)
    tot = invoicing.compute(items, vat_rate, disc)

    # Langue du document (selon le pays de facturation, override société possible)
    from core.business.doc_i18n import doc_lang, t as _docterm, country_name
    from core.export.pdf_util import fit_font, elided
    lang = doc_lang(invoice.get("country", ""), company)
    def T(k):
        return _docterm(k, lang)

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(150)
    writer.setPageMargins(QMarginsF(16, 16, 16, 16))
    try:
        writer.setTitle(f"{T('invoice')} {invoice.get('number','')}")
    except Exception:
        pass

    p = QPainter(writer)
    try:
        W = writer.width()
        ink = QColor("#0B0F14")
        grey = QColor("#5A6B7A")
        light = QColor("#9AA7B2")
        accent = QColor("#1E88E5")
        line_c = QColor("#C8D2DC")

        f_big = QFont(FONT_MAIN, 24, QFont.Bold)
        f_h = QFont(FONT_MAIN, 11, QFont.Bold)
        f_n = QFont(FONT_MAIN, 9)
        f_sm = QFont(FONT_MAIN, 8)
        f_mono = QFont(FONT_MAIN, 9)

        def txt(x, y, w, s, font, color=ink, align=Qt.AlignLeft):
            p.setFont(font); p.setPen(color)
            # Hauteur de zone large (à 150 DPI un 24 pt fait ~50 px) → jamais rogné
            p.drawText(int(x), int(y), int(w), 70, int(align | Qt.AlignTop), str(s))

        y = 0
        # ── En-tête : émetteur (gauche) / FACTURE (droite) ──────────────────
        col_r = int(W * 0.58)
        p.setFont(f_h); p.setPen(ink)
        p.drawText(0, int(y), col_r, 40, Qt.AlignLeft | Qt.AlignTop,
                   elided(f_h, company.get("nom") or T("your_company"), col_r - 8))
        yy = y + 30
        for line in (company.get("forme"), company.get("adresse"),
                     f"{company.get('cp','')} {company.get('ville','')}".strip(),
                     country_name(company.get("pays", ""), lang),
                     company.get("email"), company.get("tel"),
                     company.get("id_fiscal")):
            if line and str(line).strip():
                txt(0, yy, col_r, line, f_sm, grey); yy += 22

        # FACTURE (droite) — police réduite si le titre traduit est trop long
        f_title = fit_font(f_big, T("invoice"), W - col_r - 4, min_pt=14)
        txt(col_r, y, W - col_r, T("invoice"), f_title, accent, Qt.AlignRight)
        ry = y + 64
        for label, val in ((T("number"), invoice.get("number", "")),
                           (T("date"), invoice.get("date", "")),
                           (T("due"), invoice.get("due_date", ""))):
            if val:
                p.setFont(f_sm); p.setPen(grey)
                p.drawText(col_r, int(ry), W - col_r - 240, 30, Qt.AlignRight | Qt.AlignTop, label)
                p.setFont(f_n); p.setPen(ink)
                p.drawText(W - 230, int(ry), 230, 30, Qt.AlignRight | Qt.AlignTop, str(val))
                ry += 24

        y = max(yy, ry) + 18
        p.setPen(line_c); p.drawLine(0, int(y), W, int(y)); y += 22

        # ── Client ──────────────────────────────────────────────────────────
        cli = invoice.get("client", {})
        txt(0, y, col_r, T("billto"), f_sm, grey); y += 24
        txt(0, y, col_r, elided(f_h, cli.get("nom") or "—", col_r - 8), f_h, ink); y += 28
        for line in (cli.get("adresse"),
                     f"{cli.get('cp','')} {cli.get('ville','')}".strip(),
                     cli.get("email"), cli.get("id_fiscal")):
            if line and str(line).strip():
                txt(0, y, col_r, line, f_sm, grey); y += 20
        y += 16

        # ── Tableau des lignes ──────────────────────────────────────────────
        cx_des, cx_qty, cx_pu, cx_tot = 0, int(W * 0.58), int(W * 0.72), int(W * 0.86)
        p.setFont(f_sm); p.setPen(QColor("#FFFFFF"))
        p.fillRect(0, int(y), W, 30, accent)
        p.drawText(cx_des + 8, int(y), cx_qty - 8, 30, Qt.AlignLeft | Qt.AlignVCenter, T("desig"))
        p.drawText(cx_qty, int(y), cx_pu - cx_qty - 6, 30, Qt.AlignRight | Qt.AlignVCenter, T("qty"))
        p.drawText(cx_pu, int(y), cx_tot - cx_pu - 6, 30, Qt.AlignRight | Qt.AlignVCenter, T("unit_price"))
        p.drawText(cx_tot, int(y), W - cx_tot - 6, 30, Qt.AlignRight | Qt.AlignVCenter, T("line_total"))
        y += 34

        p.setFont(f_n); p.setPen(ink)
        for it in items:
            des = str(it.get("designation", ""))
            q = float(it.get("qty") or 0)
            pu = float(it.get("unit_price_ht") or 0)
            lt = q * pu
            p.setPen(ink); p.setFont(f_n)
            p.drawText(cx_des + 8, int(y), cx_qty - 16, 30, Qt.AlignLeft | Qt.AlignVCenter,
                       elided(f_n, des, cx_qty - 16))
            p.setFont(f_mono)
            p.drawText(cx_qty, int(y), cx_pu - cx_qty - 6, 30, Qt.AlignRight | Qt.AlignVCenter, f"{q:g}")
            p.drawText(cx_pu, int(y), cx_tot - cx_pu - 6, 30, Qt.AlignRight | Qt.AlignVCenter, _fmt(pu, cur))
            p.drawText(cx_tot, int(y), W - cx_tot - 6, 30, Qt.AlignRight | Qt.AlignVCenter, _fmt(lt, cur))
            y += 28
            p.setPen(QColor("#E4EAF0")); p.drawLine(0, int(y), W, int(y)); y += 6

        # ── Totaux (bloc à droite) ──────────────────────────────────────────
        y += 10
        bx = int(W * 0.55)
        def total_row(label, value, bold=False, big=False):
            nonlocal y
            lbl_font = QFont(FONT_MAIN, 12, QFont.Bold) if big else (f_h if bold else f_n)
            lbl_w = int(W * 0.30)   # large + police réduite si label long (GESAMTBETRAG…)
            p.setFont(fit_font(lbl_font, label, lbl_w - 4, min_pt=9))
            p.setPen(ink if (bold or big) else grey)
            p.drawText(bx, int(y), lbl_w, 28, Qt.AlignLeft | Qt.AlignVCenter, label)
            p.setFont(QFont(FONT_MAIN, 12, QFont.Bold) if big else f_mono)
            p.drawText(int(W * 0.74), int(y), W - int(W * 0.74), 28,
                       Qt.AlignRight | Qt.AlignVCenter, _fmt(value, cur))
            y += 30

        total_row(T("subtotal"), tot["total_ht"])
        if tot["discount"] > 0:
            total_row(f"{T('discount')} ({disc:g} %)", -tot["discount"])
            total_row(T("net"), tot["net_ht"])
        total_row(f"{invoicing.vat_label(invoice.get('country',''))} ({vat_rate:g} %)", tot["tva"])
        p.setPen(accent); p.drawLine(bx, int(y), W, int(y)); y += 8
        total_row(T("total"), tot["ttc"], big=True)

        # ── Conditions / IBAN / mentions ────────────────────────────────────
        y += 18
        p.setPen(line_c); p.drawLine(0, int(y), W, int(y)); y += 16
        cond = company.get("conditions")
        if cond:
            txt(0, y, W, f"{T('terms')} : {cond}", f_sm, grey); y += 22
        if company.get("iban"):
            txt(0, y, W, f"IBAN : {company.get('iban')}", f_sm, grey); y += 22
        if invoice.get("notes"):
            txt(0, y, W, invoice.get("notes"), f_sm, grey); y += 22
        # Mentions légales propres au pays (identité société + obligations),
        # construites depuis la fiche société. Rédigées dans la langue du pays.
        ment = invoicing.legal_block(company, invoice.get("country", ""))
        if ment:
            p.setFont(f_sm); p.setPen(grey)
            p.drawText(0, int(y), W, 130, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, ment)

        # Pied = coordonnées de l'émetteur (et non « neoSlice »). Police réduite +
        # retour à la ligne pour ne jamais rogner une fiche société longue.
        p.setFont(QFont(FONT_MAIN, 7)); p.setPen(grey)
        _foot = invoicing.company_footer(company, lang) or (company.get("nom") or "")
        p.drawText(0, writer.height() - 50, W, 44,
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, _foot)
    finally:
        p.end()
    return path
