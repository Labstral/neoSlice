"""Génère un « bon de production » PDF pour une commande (QPdfWriter natif).

render_order(path, order, company) — A4 : émetteur, n° commande + statut +
échéance, client, lignes (désignation/qté/PU/total), consommation filament par
couleur (bobine + grammes), total et notes. Document interne d'atelier.
"""
from __future__ import annotations

from core.business import store, invoicing
from core.i18n import _
from ui.styles.theme import FONT_MAIN


def _fmt(v: float, cur: str) -> str:
    return f"{v:,.2f} {cur}".replace(",", " ")


def render_order(path: str, order: dict, company: dict) -> str:
    from PySide6.QtGui import QPdfWriter, QPainter, QPageSize, QColor, QFont
    from PySide6.QtCore import QMarginsF, Qt

    cur = order.get("currency") or invoicing.currency(company.get("pays", ""))
    items = order.get("items", [])
    total = float(order.get("total_ttc", 0) or 0)
    status = order.get("status", "todo")

    from core.business.doc_i18n import doc_lang, t as _docterm, country_name
    from core.export.pdf_util import fit_font, elided
    lang = doc_lang(company.get("pays", ""), company)
    def T(k):
        return _docterm(k, lang)

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(150)
    writer.setPageMargins(QMarginsF(16, 16, 16, 16))
    try:
        writer.setTitle(f"{T('workorder')} {order.get('number','')}")
    except Exception:
        pass

    p = QPainter(writer)
    try:
        W = writer.width()
        ink = QColor("#0B0F14"); grey = QColor("#5A6B7A"); light = QColor("#9AA7B2")
        accent = QColor("#1E88E5"); line_c = QColor("#C8D2DC")
        f_big = QFont(FONT_MAIN, 17, QFont.Bold)   # « BON DE PRODUCTION » est long
        f_h = QFont(FONT_MAIN, 11, QFont.Bold)
        f_n = QFont(FONT_MAIN, 9); f_sm = QFont(FONT_MAIN, 8); f_mono = QFont(FONT_MAIN, 9)

        def txt(x, y, w, s, font, color=ink, align=Qt.AlignLeft):
            p.setFont(font); p.setPen(color)
            p.drawText(int(x), int(y), int(w), 70, int(align | Qt.AlignTop), str(s))

        y = 0
        col_r = int(W * 0.58)
        p.setFont(f_h); p.setPen(ink)
        p.drawText(0, int(y), col_r, 40, Qt.AlignLeft | Qt.AlignTop,
                   elided(f_h, company.get("nom") or T("your_company"), col_r - 8))
        yy = y + 30
        for line in (company.get("adresse"),
                     f"{company.get('cp','')} {company.get('ville','')}".strip(),
                     country_name(company.get("pays", ""), lang),
                     company.get("email"), company.get("tel")):
            if line and str(line).strip():
                txt(0, yy, col_r, line, f_sm, grey); yy += 22

        # Titre (boîte large + police réduite si traduit long, ex. FERTIGUNGSAUFTRAG)
        _wo_w = W - int(W * 0.38)
        f_title = fit_font(f_big, T("workorder"), _wo_w - 4, min_pt=11)
        txt(int(W * 0.38), y, _wo_w, T("workorder"), f_title, accent, Qt.AlignRight)
        ry = y + 52
        for label, val in ((T("number"), order.get("number", "")),
                           (T("date"), str(order.get("cree_le", ""))[:10]),
                           (T("due"), order.get("echeance", "")),
                           (T("status"), _docterm(f"st_{status}", lang))):
            if val:
                p.setFont(f_sm); p.setPen(grey)
                p.drawText(col_r, int(ry), W - col_r - 240, 30, Qt.AlignRight | Qt.AlignTop, label)
                p.setFont(f_n); p.setPen(ink)
                p.drawText(W - 230, int(ry), 230, 30, Qt.AlignRight | Qt.AlignTop, str(val))
                ry += 24

        y = max(yy, ry) + 18
        p.setPen(line_c); p.drawLine(0, int(y), W, int(y)); y += 22

        # Client
        cli_label = order.get("client_label", "")
        if cli_label:
            txt(0, y, col_r, T("client"), f_sm, grey); y += 24
            txt(0, y, col_r, elided(f_h, cli_label, col_r - 8), f_h, ink); y += 30

        # Lignes
        cx_des, cx_qty, cx_pu, cx_tot = 0, int(W * 0.58), int(W * 0.72), int(W * 0.86)
        p.setFont(f_sm); p.setPen(QColor("#FFFFFF")); p.fillRect(0, int(y), W, 30, accent)
        p.drawText(cx_des + 8, int(y), cx_qty - 8, 30, Qt.AlignLeft | Qt.AlignVCenter, T("desig"))
        p.drawText(cx_qty, int(y), cx_pu - cx_qty - 6, 30, Qt.AlignRight | Qt.AlignVCenter, T("qty"))
        p.drawText(cx_pu, int(y), cx_tot - cx_pu - 6, 30, Qt.AlignRight | Qt.AlignVCenter, T("unit_price"))
        p.drawText(cx_tot, int(y), W - cx_tot - 6, 30, Qt.AlignRight | Qt.AlignVCenter, T("line_total"))
        y += 34
        p.setFont(f_n); p.setPen(ink)
        for it in items:
            q = float(it.get("qty") or 0); pu = float(it.get("unit_price_ht") or 0)
            p.setPen(ink); p.setFont(f_n)
            p.drawText(cx_des + 8, int(y), cx_qty - 16, 30, Qt.AlignLeft | Qt.AlignVCenter,
                       elided(f_n, it.get("designation", ""), cx_qty - 16))
            p.setFont(f_mono)
            p.drawText(cx_qty, int(y), cx_pu - cx_qty - 6, 30, Qt.AlignRight | Qt.AlignVCenter, f"{q:g}")
            p.drawText(cx_pu, int(y), cx_tot - cx_pu - 6, 30, Qt.AlignRight | Qt.AlignVCenter, _fmt(pu, cur))
            p.drawText(cx_tot, int(y), W - cx_tot - 6, 30, Qt.AlignRight | Qt.AlignVCenter, _fmt(q * pu, cur))
            y += 28
            p.setPen(QColor("#E4EAF0")); p.drawLine(0, int(y), W, int(y)); y += 6

        # Total
        y += 8
        _tl = T("total_simple")
        p.setFont(fit_font(QFont(FONT_MAIN, 12, QFont.Bold), _tl, int(W * 0.30) - 4, 9)); p.setPen(ink)
        p.drawText(int(W * 0.55), int(y), int(W * 0.30), 28, Qt.AlignLeft | Qt.AlignVCenter, _tl)
        p.drawText(int(W * 0.74), int(y), W - int(W * 0.74), 28, Qt.AlignRight | Qt.AlignVCenter, _fmt(total, cur))
        y += 40

        # Consommation filament (par couleur)
        cons = order.get("consumptions") or []
        txt(0, y, W, T("consumptions"), f_h, ink); y += 30
        if cons:
            for c in cons:
                sp = store.get_spool(c.get("spool_id", "")) if c.get("spool_id") else None
                if sp:
                    name = " ".join(x for x in (sp.get("materiau", ""), sp.get("marque", ""),
                                                sp.get("couleur_nom", "")) if x)
                else:
                    name = T("unassigned")
                g = float(c.get("grams") or 0)
                p.setFont(f_n); p.setPen(ink)
                p.drawText(8, int(y), int(W * 0.7), 26, Qt.AlignLeft | Qt.AlignVCenter, "• " + (name or "—"))
                p.setFont(f_mono)
                p.drawText(int(W * 0.7), int(y), W - int(W * 0.7) - 6, 26,
                           Qt.AlignRight | Qt.AlignVCenter, f"{g:.0f} g")
                y += 26
            p.setFont(f_h); p.setPen(grey)
            p.drawText(8, int(y), int(W * 0.7), 26, Qt.AlignLeft | Qt.AlignVCenter, T("total_simple"))
            p.setFont(f_mono); p.setPen(ink)
            p.drawText(int(W * 0.7), int(y), W - int(W * 0.7) - 6, 26,
                       Qt.AlignRight | Qt.AlignVCenter, f"{float(order.get('grams', 0) or 0):.0f} g")
            y += 30
        else:
            txt(8, y, W, "—", f_n, grey); y += 26

        if order.get("notes"):
            y += 10
            p.setPen(line_c); p.drawLine(0, int(y), W, int(y)); y += 14
            txt(0, y, W, f"{T('notes')} : {order.get('notes')}", f_sm, grey)

        p.setFont(f_sm); p.setPen(light)
        p.drawText(0, writer.height() - 30, W, 30, Qt.AlignHCenter | Qt.AlignBottom, T("wo_footer"))
    finally:
        p.end()
    return path
