# -*- coding: utf-8 -*-
"""Lettre de relance PDF pour une facture impayée (QPdfWriter natif).

render_relance(path, invoice, company) — courrier A4 prêt à envoyer : bloc
émetteur, bloc client, objet, corps poli (montant, échéance, jours de retard),
IBAN, signature. Rédigé dans la LANGUE DU DOCUMENT (pays de la facture,
override société possible) — même mécanique que la facture elle-même.
"""
from __future__ import annotations

from datetime import date

from core.business import invoicing
from ui.styles.theme import FONT_MAIN


def render_relance(path: str, invoice: dict, company: dict) -> str:
    from PySide6.QtGui import QPdfWriter, QPainter, QPageSize, QColor, QFont
    from PySide6.QtCore import QMarginsF, Qt, QRect

    from core.business.doc_i18n import doc_lang, t as _docterm, country_name
    from core.business.store import invoice_ttc, days_overdue
    from core.export.pdf_util import elided

    lang = doc_lang(invoice.get("country", ""), company)

    def T(k):
        return _docterm(k, lang)

    cur = invoice.get("currency") or invoicing.currency(invoice.get("country", ""))
    ttc = invoice_ttc(invoice)
    montant = f"{ttc:,.2f} {cur}".replace(",", " ")
    echeance = str(invoice.get("echeance") or invoice.get("due_date") or "")
    retard = days_overdue(invoice)

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(150)
    writer.setPageMargins(QMarginsF(20, 18, 20, 18))
    try:
        writer.setTitle(f"{T('reminder_title')} {invoice.get('number', '')}")
    except Exception:
        pass

    p = QPainter(writer)
    try:
        W = writer.width()
        ink = QColor("#0B0F14")
        grey = QColor("#5A6B7A")
        accent = QColor("#1E88E5")
        line_c = QColor("#C8D2DC")

        f_big = QFont(FONT_MAIN, 20, QFont.Bold)
        f_h = QFont(FONT_MAIN, 11, QFont.Bold)
        f_n = QFont(FONT_MAIN, 10)
        f_sm = QFont(FONT_MAIN, 8)

        def txt(x, y, w, s, font, color=ink, align=Qt.AlignLeft):
            p.setFont(font)
            p.setPen(color)
            p.drawText(int(x), int(y), int(w), 70, int(align | Qt.AlignTop), str(s))

        def para(y, s, font=f_n, color=ink) -> int:
            """Paragraphe multi-lignes (word wrap) ; retourne le y suivant."""
            p.setFont(font)
            p.setPen(color)
            flags = int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
            rect = p.boundingRect(QRect(0, int(y), W, 3000), flags, str(s))
            p.drawText(rect, flags, str(s))
            return y + rect.height()

        y = 0
        # ── Émetteur (gauche) / RELANCE (droite) ────────────────────────────
        col_r = int(W * 0.58)
        p.setFont(f_h)
        p.setPen(ink)
        p.drawText(0, int(y), col_r, 40, Qt.AlignLeft | Qt.AlignTop,
                   elided(f_h, company.get("nom") or "", col_r - 8))
        yy = y + 30
        for line in (company.get("forme"), company.get("adresse"),
                     f"{company.get('cp', '')} {company.get('ville', '')}".strip(),
                     country_name(company.get("pays", ""), lang),
                     company.get("email"), company.get("tel"),
                     company.get("id_fiscal")):
            if line and str(line).strip():
                txt(0, yy, col_r, line, f_sm, grey)
                yy += 22

        from core.export.pdf_util import fit_font
        f_title = fit_font(f_big, T("reminder_title"), W - col_r - 4, min_pt=12)
        txt(col_r, y, W - col_r, T("reminder_title"), f_title, accent, Qt.AlignRight)
        ry = y + 56
        for label, val in ((T("number"), invoice.get("number", "")),
                           (T("date"), date.today().isoformat()),
                           (T("due"), echeance)):
            if val:
                p.setFont(f_sm)
                p.setPen(grey)
                p.drawText(col_r, int(ry), W - col_r - 240, 30,
                           Qt.AlignRight | Qt.AlignTop, label)
                p.setFont(f_n)
                p.setPen(ink)
                p.drawText(W - 230, int(ry), 230, 30,
                           Qt.AlignRight | Qt.AlignTop, str(val))
                ry += 24

        y = max(yy, ry) + 18
        p.setPen(line_c)
        p.drawLine(0, int(y), W, int(y))
        y += 26

        # ── Destinataire ────────────────────────────────────────────────────
        cli = invoice.get("client", {}) or {}
        txt(0, y, col_r, elided(f_h, cli.get("nom") or invoice.get("client_label")
                                or "—", col_r - 8), f_h, ink)
        y += 28
        for line in (cli.get("adresse"),
                     f"{cli.get('cp', '')} {cli.get('ville', '')}".strip(),
                     cli.get("email")):
            if line and str(line).strip():
                txt(0, y, col_r, line, f_sm, grey)
                y += 20
        y += 30

        # ── Objet + corps ───────────────────────────────────────────────────
        y = para(y, T("reminder_obj").format(number=invoice.get("number", "")),
                 f_h, ink) + 22
        y = para(y, T("reminder_greeting")) + 16
        y = para(y, T("reminder_body").format(
            number=invoice.get("number", ""),
            date=invoice.get("date", ""),
            amount=montant, due=echeance, days=retard)) + 16
        y = para(y, T("reminder_body2")) + 26

        if company.get("iban"):
            y = para(y, f"IBAN : {company.get('iban')}", f_sm, grey) + 16

        y = para(y, T("reminder_sign")) + 10
        y = para(y, company.get("nom") or "", f_h, ink)

        # ── Pied de page ────────────────────────────────────────────────────
        foot = invoicing.company_footer(company, lang)
        if foot:
            p.setFont(f_sm)
            p.setPen(grey)
            p.drawText(0, writer.height() - 30, W, 30,
                       int(Qt.AlignHCenter | Qt.AlignTop), elided(f_sm, foot, W - 8))
    finally:
        p.end()
    return path
