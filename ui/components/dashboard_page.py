"""Onglet Tableau de bord de l'Espace Pro — vue d'ensemble de l'atelier.

Indicateurs synthétiques (chiffre d'affaires, documents, stock filament) agrégés
depuis les bobines, devis, factures et clients. Lecture seule, rafraîchi à
l'ouverture de l'onglet.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QFileDialog,
)

from core.i18n import _, lang as _lang
from core.business import store
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO

# Abréviations de mois localisées (index 1..12)
_MONTHS_FR = ["", "janv.", "févr.", "mars", "avr.", "mai", "juin",
              "juil.", "août", "sept.", "oct.", "nov.", "déc."]
_MONTHS_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_label(ym: str) -> str:
    """'AAAA-MM' → abréviation du mois dans la langue active (ex. 'juin', 'Jun')."""
    try:
        mi = int(str(ym)[-2:])
    except (ValueError, TypeError):
        return str(ym)[-2:]
    table = _MONTHS_EN if _lang() == "en" else _MONTHS_FR
    return table[mi] if 1 <= mi <= 12 else str(ym)[-2:]


class _RevenueChart(QWidget):
    """Mini histogramme du CA mensuel (facturé = barre, payé = portion verte)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self.setMinimumHeight(132)

    def set_data(self, data: list[dict]):
        self._data = data or []
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        pal = _T.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pad_b, pad_t = 22, 16          # marges bas (labels) / haut (valeurs)
        n = len(self._data)
        maxv = max((d["billed"] for d in self._data), default=0) or 1.0
        gap = 14
        bw = max(8.0, (W - gap * (n + 1)) / n)
        base = H - pad_b
        f = QFont(FONT_MAIN, 7); p.setFont(f)
        for i, d in enumerate(self._data):
            x = gap + i * (bw + gap)
            bh = (d["billed"] / maxv) * (H - pad_b - pad_t)
            ph = (d["paid"] / maxv) * (H - pad_b - pad_t)
            # barre facturée (fond)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["INACTIVE"]))
            p.drawRoundedRect(QRectF(x, base - bh, bw, bh), 2, 2)
            # portion payée (verte)
            if ph > 0:
                p.setBrush(QColor(pal["TELE_GREEN"]))
                p.drawRoundedRect(QRectF(x, base - ph, bw, ph), 2, 2)
            # label mois (nom abrégé localisé : juin / Jun)
            p.setPen(QColor(pal["TEXT_LABEL"]))
            mm = _month_label(d["mois"])
            p.drawText(QRectF(x - gap / 2, base + 3, bw + gap, 16),
                       Qt.AlignHCenter | Qt.AlignTop, mm)
            # valeur facturée si non nulle
            if d["billed"] > 0:
                p.setPen(QColor(pal["TEXT_SECONDARY"]))
                p.drawText(QRectF(x - gap / 2, base - bh - pad_t, bw + gap, pad_t),
                           Qt.AlignHCenter | Qt.AlignBottom, f"{d['billed']:.0f}")
        p.end()


class _Card(QFrame):
    """Carte indicateur : grande valeur + libellé + sous-texte optionnel."""

    def __init__(self, key: str, color_role: str, parent=None):
        super().__init__(parent)
        self.setObjectName("kpi")
        self._color_role = color_role
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        self.value = QLabel("—")
        self.value.setFont(QFont(FONT_MAIN, 17, QFont.Bold))
        self.title = QLabel("")
        self.title.setFont(QFont(FONT_MAIN, 8))
        self.title.setObjectName("kpititle")
        self.sub = QLabel("")
        self.sub.setFont(QFont(FONT_MAIN, 8))
        self.sub.setObjectName("kpisub")
        self.sub.hide()
        lay.addWidget(self.value)
        lay.addWidget(self.title)
        lay.addWidget(self.sub)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, _Card] = {}
        self._build()
        self.refresh()
        self.apply_theme()
        _T.register(self.apply_theme)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        self._scroll = scroll
        host = QWidget(); self._host = host
        lay = QVBoxLayout(host); lay.setContentsMargins(24, 18, 24, 20); lay.setSpacing(8)

        self._welcome = QLabel(_("dash.welcome"))
        self._welcome.setFont(QFont(FONT_MAIN, 16, QFont.Bold))
        lay.addWidget(self._welcome)
        self._welcome_sub = QLabel(_("dash.welcome_sub"))
        self._welcome_sub.setFont(QFont(FONT_MAIN, 9)); self._welcome_sub.setWordWrap(True)
        lay.addWidget(self._welcome_sub)

        # Bandeau d'alerte « factures en retard » (masqué si aucun retard)
        self._overdue_banner = QLabel("")
        self._overdue_banner.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._overdue_banner.setWordWrap(True)
        self._overdue_banner.hide()
        lay.addWidget(self._overdue_banner)
        lay.addSpacing(10)

        # ── Activité (CA) ────────────────────────────────────────────────────
        lay.addWidget(self._section(_("dash.sec_activity")))
        lay.addLayout(self._row([
            ("billed", "TEXT_PRIMARY", _("dash.billed")),
            ("paid", "TELE_GREEN", _("dash.paid")),
            ("due", "AMBER", _("dash.due")),
            ("month_billed", "ACCENT_BRIGHT", _("dash.month_billed")),
        ]))
        lay.addSpacing(8)

        # ── Rentabilité (encaissé vs investi + consommables) ─────────────────
        lay.addWidget(self._section(_("dash.sec_profit")))
        lay.addLayout(self._row([
            ("invested", "AMBER", _("dash.invested")),
            ("consumables_bought", "AMBER", _("dash.consumables_bought")),
            ("net_result", "TELE_GREEN", _("dash.net_result")),
        ]))
        self._profit_status = QLabel("")
        self._profit_status.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._profit_status.setWordWrap(True)
        self._profit_status.setContentsMargins(2, 4, 0, 0)
        lay.addWidget(self._profit_status)
        lay.addSpacing(8)

        # ── Production (commandes / retards) ─────────────────────────────────
        lay.addWidget(self._section(_("dash.sec_orders")))
        lay.addLayout(self._row([
            ("orders_active", "ACCENT", _("dash.orders_active")),
            ("orders_todo", "ACCENT", _("dash.orders_todo")),
            ("overdue", "ERROR_RED", _("dash.overdue")),
        ]))
        lay.addSpacing(8)

        # ── Documents ────────────────────────────────────────────────────────
        lay.addWidget(self._section(_("dash.sec_docs")))
        lay.addLayout(self._row([
            ("invoices", "ACCENT", _("dash.invoices")),
            ("quotes", "ACCENT", _("dash.quotes")),
            ("clients", "ACCENT", _("dash.clients")),
        ]))
        lay.addSpacing(8)

        # ── Stock filament ───────────────────────────────────────────────────
        lay.addWidget(self._section(_("dash.sec_stock")))
        lay.addLayout(self._row([
            ("spools", "ACCENT", _("dash.spools")),
            ("stock_g", "TEXT_PRIMARY", _("dash.stock_g")),
            ("stock_value", "TEXT_PRIMARY", _("dash.stock_value")),
        ]))
        lay.addSpacing(12)

        # ── Rapport : CA des 6 derniers mois + export comptable ──────────────
        rep_head = QHBoxLayout()
        rep_head.addWidget(self._section(_("dash.report_title")))
        rep_head.addStretch()
        self._export_btn = QPushButton(_("dash.export"))
        self._export_btn.setFont(QFont(FONT_MAIN, 8)); self._export_btn.setFixedHeight(28)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.clicked.connect(self._do_export)
        rep_head.addWidget(self._export_btn)
        lay.addLayout(rep_head)
        self._chart = _RevenueChart()
        lay.addWidget(self._chart)
        # légende : carré vert = encaissé, carré gris = facturé en attente
        leg = QHBoxLayout(); leg.setSpacing(18); leg.setContentsMargins(14, 2, 0, 0)
        self._leg_paid = QLabel(); self._leg_paid.setFont(QFont(FONT_MAIN, 8))
        self._leg_billed = QLabel(); self._leg_billed.setFont(QFont(FONT_MAIN, 8))
        leg.addWidget(self._leg_paid); leg.addWidget(self._leg_billed); leg.addStretch()
        lay.addLayout(leg)
        lay.addStretch()

        scroll.setWidget(host)
        outer.addWidget(scroll)

    def _do_export(self):
        from PySide6.QtWidgets import QMessageBox, QInputDialog
        if not store.list_invoices():
            QMessageBox.information(self, _("dash.export"), _("dash.export_none"))
            return
        # Année à exporter : « Toutes » + les années réellement facturées —
        # l'expert-comptable veut UN exercice, pas tout l'historique mélangé.
        annee = None
        years = store.invoice_years()
        if len(years) > 1:
            choix = [_("dash.export_all_years")] + [str(a) for a in years]
            sel, ok = QInputDialog.getItem(self, _("dash.export"),
                                           _("dash.export_year"), choix, 0, False)
            if not ok:
                return
            annee = int(sel) if sel.isdigit() else None
        elif years:
            annee = years[0]
        from datetime import date as _d
        suffixe = str(annee) if annee else _d.today().isoformat()
        default = f"neoslice_compta_{suffixe}.csv"
        path, _flt = QFileDialog.getSaveFileName(self, _("dash.export"), default,
                                                 "CSV (*.csv)")
        if not path:
            return
        from pathlib import Path
        store.export_accounting_csv(Path(path), annee=annee)
        QMessageBox.information(self, _("dash.export"), _("dash.export_done", path=path))

    def _section(self, title: str) -> QLabel:
        lbl = QLabel(title); lbl.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        lbl.setObjectName("sec")
        return lbl

    def _row(self, specs: list[tuple[str, str, str]]) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(10)
        for key, color, title in specs:
            card = _Card(key, color)
            card.title.setText(title)
            self._cards[key] = card
            row.addWidget(card, 1)
        return row

    # ── Données ────────────────────────────────────────────────────────────────
    def refresh(self):
        st = store.dashboard_stats()
        cur = st["currency"]
        self._cards["billed"].value.setText(f"{st['billed']:.2f} {cur}")
        self._cards["paid"].value.setText(f"{st['paid']:.2f} {cur}")
        self._cards["due"].value.setText(f"{st['due']:.2f} {cur}")
        inv = self._cards["invoices"]
        inv.value.setText(str(st["n_invoices"]))
        if st["n_unpaid"]:
            inv.sub.setText(_("dash.unpaid", n=st["n_unpaid"])); inv.sub.show()
        else:
            inv.sub.hide()
        self._cards["quotes"].value.setText(str(st["n_quotes"]))
        self._cards["clients"].value.setText(str(st["n_clients"]))
        self._cards["spools"].value.setText(str(st["n_spools"]))
        sp = self._cards["spools"]
        if st["n_low_stock"]:
            sp.sub.setText(_("dash.low_stock", n=st["n_low_stock"])); sp.sub.show()
        else:
            sp.sub.hide()
        self._cards["stock_g"].value.setText(f"{st['stock_g']:.0f} g")
        self._cards["stock_value"].value.setText(f"{st['stock_value']:.2f} {cur}")

        # CA du mois
        self._cards["month_billed"].value.setText(f"{st['month_billed']:.2f} {cur}")

        # Rentabilité
        pal = _T.palette()
        self._cards["invested"].value.setText(f"{st['invested']:.2f} {cur}")
        self._cards["consumables_bought"].value.setText(f"{st['consumables_bought']:.2f} {cur}")
        nr = self._cards["net_result"]
        nr.value.setText(f"{st['net_result']:+.2f} {cur}")
        nr._color_role = "TELE_GREEN" if st["is_profitable"] else "ERROR_RED"
        nr.value.setStyleSheet(f"color: {pal[nr._color_role]}; background: transparent;")
        if st["is_profitable"]:
            self._profit_status.setText(_("dash.profit_ok",
                                          amount=f"{st['net_result']:.2f} {cur}"))
            self._profit_color_role = "TELE_GREEN"
        else:
            self._profit_status.setText(_("dash.profit_recover",
                                          amount=f"{st['to_recover']:.2f} {cur}",
                                          pct=f"{st['recover_pct']:.0f}"))
            self._profit_color_role = "AMBER"
        self._profit_status.setStyleSheet(
            f"color: {pal[self._profit_color_role]}; background: transparent;")

        # Production
        self._cards["orders_active"].value.setText(str(st["n_orders_active"]))
        oa = self._cards["orders_active"]
        if st["n_orders_printing"]:
            oa.sub.setText(_("ord.status_printing") + f" · {st['n_orders_printing']}"); oa.sub.show()
        else:
            oa.sub.hide()
        self._cards["orders_todo"].value.setText(str(st["n_orders_todo"]))

        # Retards
        od = self._cards["overdue"]
        od.value.setText(str(st["n_overdue"]))
        if st["n_overdue"]:
            od.sub.setText(f"{st['overdue_amount']:.2f} {cur}"); od.sub.show()
        else:
            od.sub.hide()
        if st["n_overdue"]:
            self._overdue_banner.setText(
                "⚠  " + _("dash.overdue") + f" : {st['n_overdue']} · "
                + _("dash.overdue_amount") + f" {st['overdue_amount']:.2f} {cur}")
            self._overdue_banner.show()
        else:
            self._overdue_banner.hide()

        # Graphe CA mensuel
        self._chart.set_data(store.monthly_revenue(6))

    # ── Thème ──────────────────────────────────────────────────────────────────
    def apply_theme(self):
        pal = _T.palette()
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._host.setStyleSheet("background: transparent;")
        self._welcome.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._welcome_sub.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        for lbl in self.findChildren(QLabel):
            if lbl.objectName() == "sec":
                lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; "
                                  f"letter-spacing: 2px;")
        for key, card in self._cards.items():
            card.setStyleSheet(f"QFrame#kpi {{ background: {pal['BG_ELEVATED']}; "
                               f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
            color = pal.get(card._color_role, pal["TEXT_PRIMARY"])
            card.value.setStyleSheet(f"color: {color}; background: transparent;")
            card.title.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
            sub_col = pal["ERROR_RED"] if key == "overdue" else pal["AMBER"]
            card.sub.setStyleSheet(f"color: {sub_col}; background: transparent;")
        # Statut de rentabilité : garder sa couleur cohérente au changement de thème
        role = getattr(self, "_profit_color_role", "TELE_GREEN")
        self._profit_status.setStyleSheet(f"color: {pal[role]}; background: transparent;")
        self._overdue_banner.setStyleSheet(
            f"color: {pal['ERROR_RED']}; background: rgba(239,83,80,0.10); "
            f"border: 1px solid {pal['ERROR_RED']}; border-radius: 4px; padding: 6px 10px;")
        self._export_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 0 10px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")
        self._leg_paid.setText(
            f"<span style='color:{pal['TELE_GREEN']};'>■</span> "
            f"<span style='color:{pal['TEXT_SECONDARY']};'>{_('dash.legend_paid')}</span>")
        self._leg_billed.setText(
            f"<span style='color:{pal['INACTIVE']};'>■</span> "
            f"<span style='color:{pal['TEXT_SECONDARY']};'>{_('dash.legend_billed')}</span>")
        self._chart.update()
