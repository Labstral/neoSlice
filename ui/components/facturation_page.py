"""Onglet Facturation de l'Espace Pro — création de factures professionnelles.

Société émettrice + factures (client, lignes, TVA selon pays, totaux HT/TVA/TTC),
enregistrement local, génération PDF, suivi du statut (brouillon / envoyée / payée).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QDoubleValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QScrollArea, QFrame, QFileDialog, QMessageBox, QPlainTextEdit,
)

from core.i18n import _
from core.business import store, invoicing
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO

_STATUS_KEYS = ["draft", "sent", "paid"]


def _status_label(key: str) -> str:
    return _("fact.status_" + key)


class _Row(QWidget):
    """Une ligne de facture : désignation, quantité, PU HT, suppression."""

    def __init__(self, page, designation="", qty="1", pu="", parent=None):
        super().__init__(parent)
        self._page = page
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.des = QLineEdit(designation); self.des.setFont(QFont(FONT_MAIN, 9))
        self.qty = QLineEdit(qty); self.qty.setFont(QFont(FONT_MAIN, 9))
        self.qty.setFixedWidth(60); self.qty.setAlignment(Qt.AlignRight)
        self.qty.setValidator(QDoubleValidator(0, 1e6, 3, self.qty))
        self.pu = QLineEdit(pu); self.pu.setFont(QFont(FONT_MAIN, 9))
        self.pu.setFixedWidth(90); self.pu.setAlignment(Qt.AlignRight)
        self.pu.setValidator(QDoubleValidator(0, 1e7, 2, self.pu))
        self.rm = QPushButton("✕"); self.rm.setFixedSize(26, 26)
        self.rm.setCursor(Qt.PointingHandCursor)
        self.rm.clicked.connect(lambda: page._remove_row(self))
        for w in (self.des, self.qty, self.pu):
            w.textChanged.connect(page._recompute)
        lay.addWidget(self.des, 1)
        lay.addWidget(self.qty)
        lay.addWidget(self.pu)
        lay.addWidget(self.rm)

    def data(self) -> dict:
        def _f(s):
            try:
                return float((s or "0").replace(",", "."))
            except ValueError:
                return 0.0
        return {"designation": self.des.text().strip(),
                "qty": _f(self.qty.text()), "unit_price_ht": _f(self.pu.text())}


class FacturationPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._company_edits: dict[str, QLineEdit] = {}
        self._client_edits: dict[str, QLineEdit] = {}
        self._rows: list[_Row] = []
        self._build()
        self._load_company()
        self._populate_clients()
        self._on_country_changed()
        self._add_row()
        self._refresh_invoices()
        self.apply_theme()
        _T.register(self.apply_theme)

    # ── Sélection de client enregistré ────────────────────────────────────────
    def _populate_clients(self, select_id: str = ""):
        self._client_combo.blockSignals(True)
        self._client_combo.clear()
        self._client_combo.addItem(_("fact.client_none"), "")
        for c in store.list_clients():
            self._client_combo.addItem(store.client_label(c), c["id"])
        if select_id:
            i = self._client_combo.findData(select_id)
            if i >= 0:
                self._client_combo.setCurrentIndex(i)
                self._client_id = select_id
        self._client_combo.blockSignals(False)

    def _on_client_selected(self):
        cid = self._client_combo.currentData()
        self._client_id = cid or ""
        if not cid:
            return
        c = store.get_client(cid)
        if not c:
            return
        # Remplir les champs client de la facture
        self._client_edits["nom"].setText(store.client_label(c))
        self._client_edits["adresse"].setText(c.get("adresse", ""))
        self._client_edits["cp"].setText(c.get("cp", ""))
        self._client_edits["ville"].setText(c.get("ville", ""))
        self._client_edits["email"].setText(c.get("email", ""))
        self._client_edits["id_fiscal"].setText(c.get("id_fiscal", ""))
        # Pays du client → pays de facturation
        i = self._country.findData(c.get("pays", ""))
        if i >= 0:
            self._country.setCurrentIndex(i)

    def _save_current_client(self):
        data = {
            "nom": self._client_edits["nom"].text().strip(),
            "adresse": self._client_edits["adresse"].text().strip(),
            "cp": self._client_edits["cp"].text().strip(),
            "ville": self._client_edits["ville"].text().strip(),
            "email": self._client_edits["email"].text().strip(),
            "id_fiscal": self._client_edits["id_fiscal"].text().strip(),
            "pays": self._country.currentData(),
        }
        if not (data["nom"] or data["email"]):
            self._msg(_("fact.client_select"), _("fact.need_line"), "warn")
            return
        c = store.add_client(data)
        self._populate_clients(select_id=c["id"])
        self._msg(_("fact.client_select"), _("fact.client_saved"))

    # ── Construction ──────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self._host = host
        lay = QVBoxLayout(host)
        lay.setContentsMargins(22, 16, 22, 18)
        lay.setSpacing(8)

        lay.addWidget(self._section(_("fact.sec_company")))
        lay.addWidget(self._build_company())
        lay.addSpacing(6)
        lay.addWidget(self._section(_("fact.sec_new")))
        lay.addWidget(self._build_invoice())
        lay.addSpacing(6)
        lay.addWidget(self._section(_("fact.sec_saved")))
        self._inv_host = QWidget()
        self._inv_lay = QVBoxLayout(self._inv_host)
        self._inv_lay.setContentsMargins(0, 0, 0, 0)
        self._inv_lay.setSpacing(6)
        lay.addWidget(self._inv_host)
        lay.addStretch()

        self._scroll.setWidget(host)
        outer.addWidget(self._scroll)

    def _section(self, title: str) -> QLabel:
        # Identique aux titres de section du devis intégré (police bumpée +1 → 10)
        lbl = QLabel(title.upper())
        lbl.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        lbl.setObjectName("sec")
        return lbl

    def _lbl(self, t: str) -> QLabel:
        q = QLabel(t); q.setFont(QFont(FONT_MAIN, 9)); q.setObjectName("fld")
        return q

    def _edit(self, store_dict, key, placeholder="") -> QLineEdit:
        e = QLineEdit(); e.setFont(QFont(FONT_MAIN, 9))
        e.setPlaceholderText(placeholder)
        store_dict[key] = e
        return e

    def _build_company(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(6)
        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(6)
        outer.addLayout(g)
        ce = self._company_edits
        rows = [
            (_("fact.c_name"), "nom"), (_("fact.c_form"), "forme"),
            (_("fact.c_address"), "adresse"), (_("fact.c_zip"), "cp"), (_("fact.c_city"), "ville"),
            (_("fact.c_email"), "email"), (_("fact.c_phone"), "tel"),
            (_("fact.c_taxid"), "id_fiscal"), (_("fact.c_iban"), "iban"),
            (_("fact.c_terms"), "conditions"),
        ]
        r = 0
        for label, key in rows:
            g.addWidget(self._lbl(label), r, 0)
            g.addWidget(self._edit(ce, key), r, 1)
            r += 1
        # pays société = combo → pilote les champs légaux dynamiques
        self._comp_country = QComboBox()
        for c in invoicing.PAYS_ORDRE:
            self._comp_country.addItem(c, c)
        self._comp_country.currentIndexChanged.connect(self._rebuild_legal_fields)
        g.addWidget(self._lbl(_("fact.country")), r, 0)
        g.addWidget(self._comp_country, r, 1); r += 1
        # Langue des documents (facture/devis/bon) : Auto selon le pays, ou forcée
        from core.business.doc_i18n import DOC_LANGS, DOC_LANG_LABELS
        self._doc_lang_combo = QComboBox()
        self._doc_lang_combo.addItem(_("fact.doc_lang_auto"), "")
        for lg in DOC_LANGS:
            self._doc_lang_combo.addItem(DOC_LANG_LABELS[lg], lg)
        g.addWidget(self._lbl(_("fact.doc_lang")), r, 0)
        g.addWidget(self._doc_lang_combo, r, 1); r += 1

        # ── Section légale dynamique (champs propres au pays) ──
        self._legal_section_lbl = QLabel(_("fact.legal_section"))
        self._legal_section_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._legal_section_lbl.setObjectName("fld")
        outer.addWidget(self._legal_section_lbl)
        self._legal_host = QWidget()
        self._legal_grid = QGridLayout(self._legal_host)
        self._legal_grid.setContentsMargins(0, 0, 0, 0)
        self._legal_grid.setHorizontalSpacing(10); self._legal_grid.setVerticalSpacing(6)
        outer.addWidget(self._legal_host)
        self._legal_edits: dict = {}
        self._regime_combo = None

        self._save_comp_btn = QPushButton(_("fact.save_company"))
        self._save_comp_btn.setCursor(Qt.PointingHandCursor)
        self._save_comp_btn.setFixedHeight(30)
        self._save_comp_btn.clicked.connect(self._save_company)
        outer.addWidget(self._save_comp_btn, alignment=Qt.AlignLeft)
        return w

    def _rebuild_legal_fields(self):
        """(Re)construit les champs société propres au pays sélectionné."""
        while self._legal_grid.count():
            it = self._legal_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._legal_edits = {}
        self._regime_combo = None
        country = self._comp_country.currentData() or ""
        fields = invoicing.company_legal_fields(country)
        self._legal_section_lbl.setVisible(bool(fields))
        self._legal_host.setVisible(bool(fields))
        cur = store.get_company()
        r = 0
        for key, label_key, placeholder, kind in fields:
            self._legal_grid.addWidget(self._lbl(_(label_key)), r, 0)
            if kind == "regime":
                from PySide6.QtWidgets import QComboBox as _QC
                combo = _QC()
                combo.addItem(_("fact.regime_normal"), "normal")
                combo.addItem(_("fact.regime_franchise"), "franchise")
                i = combo.findData(cur.get("regime", "normal"))
                combo.setCurrentIndex(max(0, i))
                self._regime_combo = combo
                self._legal_grid.addWidget(combo, r, 1)
            else:
                e = QLineEdit(str(cur.get(key, "")))
                e.setPlaceholderText(placeholder); e.setFont(QFont(FONT_MAIN, 9))
                self._legal_edits[key] = e
                self._legal_grid.addWidget(e, r, 1)
            r += 1
        self.apply_theme()

    def _build_invoice(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)

        # Sélecteur de client enregistré (remplissage auto) + ajout au répertoire
        self._client_id = ""
        sel = QHBoxLayout(); sel.setSpacing(6)
        self._client_combo = QComboBox()
        self._client_combo.setFont(QFont(FONT_MAIN, 8))
        self._client_combo.currentIndexChanged.connect(self._on_client_selected)
        sel.addWidget(self._lbl(_("fact.client_select")))
        sel.addWidget(self._client_combo, 1)
        self._save_client_btn = QPushButton(_("fact.client_save"))
        self._save_client_btn.setCursor(Qt.PointingHandCursor); self._save_client_btn.setFixedHeight(26)
        self._save_client_btn.clicked.connect(self._save_current_client)
        sel.addWidget(self._save_client_btn)
        v.addLayout(sel)

        # Client
        cg = QGridLayout(); cg.setHorizontalSpacing(10); cg.setVerticalSpacing(6)
        cl = self._client_edits
        client_rows = [(_("fact.client"), "nom"), (_("fact.c_address"), "adresse"),
                       (_("fact.c_zip"), "cp"), (_("fact.c_city"), "ville"),
                       (_("fact.c_email"), "email"), (_("fact.c_taxid"), "id_fiscal")]
        r = 0
        for label, key in client_rows:
            cg.addWidget(self._lbl(label), r, 0)
            cg.addWidget(self._edit(cl, key), r, 1)
            r += 1
        v.addLayout(cg)

        # Pays / dates / TVA / remise
        meta = QGridLayout(); meta.setHorizontalSpacing(10); meta.setVerticalSpacing(6)
        self._country = QComboBox()
        self._country.setFont(QFont(FONT_MAIN, 9))
        for c in invoicing.PAYS_ORDRE:
            self._country.addItem(c, c)
        self._country.currentIndexChanged.connect(self._on_country_changed)
        meta.addWidget(self._lbl(_("fact.bill_country")), 0, 0)
        meta.addWidget(self._country, 0, 1)

        self._date = QLineEdit(date.today().isoformat()); self._date.setFont(QFont(FONT_MAIN, 9))
        meta.addWidget(self._lbl(_("fact.date")), 1, 0); meta.addWidget(self._date, 1, 1)
        self._due = QLineEdit((date.today() + timedelta(days=30)).isoformat())
        self._due.setFont(QFont(FONT_MAIN, 9))
        meta.addWidget(self._lbl(_("fact.due")), 2, 0); meta.addWidget(self._due, 2, 1)

        self._vat = QComboBox(); self._vat.setEditable(True)
        self._vat.setFont(QFont(FONT_MAIN, 9))
        meta.addWidget(self._lbl(_("fact.vat_rate")), 3, 0); meta.addWidget(self._vat, 3, 1)
        self._vat.currentTextChanged.connect(self._recompute)

        self._disc = QLineEdit("0"); self._disc.setFont(QFont(FONT_MAIN, 9))
        self._disc.setValidator(QDoubleValidator(0, 100, 2, self._disc))
        self._disc.textChanged.connect(self._recompute)
        meta.addWidget(self._lbl(_("fact.discount")), 4, 0); meta.addWidget(self._disc, 4, 1)
        v.addLayout(meta)

        # Lignes
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        for t, w_ in ((_("fact.col_desig"), None), (_("fact.col_qty"), 60),
                      (_("fact.col_pu"), 90), ("", 26)):
            l = QLabel(t); l.setFont(QFont(FONT_MAIN, 8, QFont.Bold)); l.setObjectName("colh")
            if w_:
                l.setFixedWidth(w_); l.setAlignment(Qt.AlignRight)
            hdr.addWidget(l, 0 if w_ else 1)
        v.addLayout(hdr)
        self._items_box = QVBoxLayout(); self._items_box.setSpacing(4)
        v.addLayout(self._items_box)
        self._add_line_btn = QPushButton(_("fact.add_line"))
        self._add_line_btn.setCursor(Qt.PointingHandCursor)
        self._add_line_btn.setFixedHeight(28)
        self._add_line_btn.clicked.connect(lambda: (self._add_row(), self._recompute()))
        v.addWidget(self._add_line_btn, alignment=Qt.AlignLeft)

        # Notes
        self._notes = QPlainTextEdit(); self._notes.setFont(QFont(FONT_MAIN, 9))
        self._notes.setFixedHeight(48)
        self._notes.setPlaceholderText(_("fact.notes_ph"))
        v.addWidget(self._notes)

        # Totaux
        self._tot_box = QWidget()
        tg = QGridLayout(self._tot_box); tg.setContentsMargins(0, 6, 0, 6); tg.setVerticalSpacing(3)
        self._ht_lbl = self._tot_val(); self._disc_lbl = self._tot_val()
        self._tva_lbl = self._tot_val(); self._ttc_lbl = self._tot_val(big=True)
        self._ht_name = self._tot_name(_("fact.total_ht"))
        self._disc_name = self._tot_name(_("fact.discount_l"))
        self._tva_name = self._tot_name(_("fact.vat"))
        self._ttc_name = self._tot_name(_("fact.total_ttc"), big=True)
        for i, (n, val) in enumerate(((self._ht_name, self._ht_lbl),
                                      (self._disc_name, self._disc_lbl),
                                      (self._tva_name, self._tva_lbl),
                                      (self._ttc_name, self._ttc_lbl))):
            tg.addWidget(n, i, 0); tg.addWidget(val, i, 1)
        tg.setColumnStretch(0, 1)
        v.addWidget(self._tot_box)

        # Actions
        act = QHBoxLayout(); act.addStretch()
        self._save_inv_btn = QPushButton(_("fact.save_invoice"))
        self._save_inv_btn.setCursor(Qt.PointingHandCursor); self._save_inv_btn.setFixedHeight(32)
        self._save_inv_btn.clicked.connect(self._save_invoice)
        self._pdf_btn = QPushButton(_("fact.gen_pdf"))
        self._pdf_btn.setCursor(Qt.PointingHandCursor); self._pdf_btn.setFixedHeight(32)
        self._pdf_btn.clicked.connect(self._export_pdf)
        act.addWidget(self._save_inv_btn); act.addWidget(self._pdf_btn)
        v.addLayout(act)
        return w

    def _tot_name(self, t, big=False):
        l = QLabel(t); l.setFont(QFont(FONT_MAIN, 12 if big else 9, QFont.Bold if big else QFont.Normal))
        l.setObjectName("totname" if not big else "totbig")
        return l

    def _tot_val(self, big=False):
        l = QLabel("—"); l.setAlignment(Qt.AlignRight)
        l.setFont(QFont(FONT_MAIN, 12 if big else 9, QFont.Bold if big else QFont.Normal))
        l.setObjectName("totvalbig" if big else "totval")
        return l

    # ── Lignes ──────────────────────────────────────────────────────────────
    def _add_row(self, designation="", qty="1", pu=""):
        row = _Row(self, designation, qty, pu)
        self._rows.append(row)
        self._items_box.addWidget(row)
        self.apply_theme()

    def _remove_row(self, row: _Row):
        if row in self._rows:
            self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self._recompute()

    def _items(self) -> list[dict]:
        return [r.data() for r in self._rows if r.data()["designation"] or r.data()["unit_price_ht"]]

    # ── Calcul / pays ──────────────────────────────────────────────────────────
    def _cur(self) -> str:
        return invoicing.currency(self._country.currentData() or "")

    def _vat_value(self) -> float:
        try:
            return float((self._vat.currentText() or "0").replace(",", ".").replace("%", "").strip())
        except ValueError:
            return 0.0

    def _on_country_changed(self):
        country = self._country.currentData() or "Suisse"
        self._vat.blockSignals(True)
        self._vat.clear()
        for r in invoicing.vat_rates(country):
            self._vat.addItem(f"{r:g}", r)
        # défaut
        d = invoicing.default_vat(country)
        self._vat.setCurrentText(f"{d:g}")
        self._vat.blockSignals(False)
        self._recompute()

    def _recompute(self):
        cur = self._cur()
        t = invoicing.compute(self._items(), self._vat_value(), self._disc_value())
        self._ht_lbl.setText(f"{t['total_ht']:.2f} {cur}")
        self._disc_name.setVisible(t["discount"] > 0)
        self._disc_lbl.setVisible(t["discount"] > 0)
        self._disc_lbl.setText(f"-{t['discount']:.2f} {cur}")
        self._tva_name.setText(f"{invoicing.vat_label(self._country.currentData() or '')} ({self._vat_value():g} %)")
        self._tva_lbl.setText(f"{t['tva']:.2f} {cur}")
        self._ttc_lbl.setText(f"{t['ttc']:.2f} {cur}")

    def _disc_value(self) -> float:
        try:
            return float((self._disc.text() or "0").replace(",", "."))
        except ValueError:
            return 0.0

    # ── Société ──────────────────────────────────────────────────────────────
    def _load_company(self):
        c = store.get_company()
        for k, e in self._company_edits.items():
            e.setText(str(c.get(k, "")))
        i = self._comp_country.findData(c.get("pays", "Suisse"))
        self._comp_country.blockSignals(True)
        self._comp_country.setCurrentIndex(max(0, i))
        self._comp_country.blockSignals(False)
        j = self._doc_lang_combo.findData(c.get("doc_lang", ""))
        self._doc_lang_combo.setCurrentIndex(max(0, j))
        self._rebuild_legal_fields()   # construit + pré-remplit selon le pays

    def _save_company(self):
        data = {k: e.text().strip() for k, e in self._company_edits.items()}
        data["pays"] = self._comp_country.currentData()
        data["doc_lang"] = self._doc_lang_combo.currentData() or ""
        for k, e in self._legal_edits.items():
            data[k] = e.text().strip()
        if self._regime_combo is not None:
            data["regime"] = self._regime_combo.currentData()
        store.save_company(data)
        self._msg(_("fact.sec_company"), _("fact.company_saved"))

    # ── Facture : assemblage ────────────────────────────────────────────────
    def _build_invoice_dict(self) -> dict:
        return {
            "client": {k: e.text().strip() for k, e in self._client_edits.items()},
            "client_id": getattr(self, "_client_id", ""),
            "country": self._country.currentData(),
            "currency": self._cur(),
            "date": self._date.text().strip(),
            "due_date": self._due.text().strip(),
            "vat_rate": self._vat_value(),
            "discount_pct": self._disc_value(),
            "items": self._items(),
            "notes": self._notes.toPlainText().strip(),
        }

    def _save_invoice(self):
        if not self._items():
            self._msg(_("fact.invoice"), _("fact.need_line"), "warn")
            return
        inv = store.add_invoice(self._build_invoice_dict())
        # Si la facture provient d'une commande, on relie les deux et on marque
        # la commande comme livrée (facturée).
        oid = getattr(self, "_pending_order_id", "")
        if oid and store.get_order(oid):
            store.update_order(oid, {"invoice_id": inv["id"],
                                     "invoice_number": inv["number"],
                                     "status": "delivered"})
            self._pending_order_id = ""
        self._refresh_invoices()
        self._msg(_("fact.invoice"), _("fact.saved_msg", number=inv["number"]))

    def _export_pdf(self, inv: dict | None = None):
        from core.export.invoice_pdf import render_invoice
        company = store.get_company()
        if not isinstance(inv, dict):
            if not self._items():
                self._msg(_("fact.invoice"), _("fact.need_line"), "warn")
                return
            inv = store.add_invoice(self._build_invoice_dict())
            self._refresh_invoices()
        downloads = Path.home() / "Downloads"
        start = downloads if downloads.is_dir() else Path.home()
        default = f"facture_{inv.get('number','')}.pdf"
        path, _f = QFileDialog.getSaveFileName(self, _("fact.gen_pdf"),
                                               str(start / default), "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            render_invoice(path, inv, company)
            self._open_file(path)
        except Exception as exc:
            self._msg(_("fact.gen_pdf"), str(exc), "warn")

    @staticmethod
    def _open_file(path: str):
        import sys, subprocess, os
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception:
            pass

    # ── Liste des factures ──────────────────────────────────────────────────
    def _refresh_invoices(self):
        while self._inv_lay.count():
            it = self._inv_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        invoices = store.list_invoices()
        if not invoices:
            empty = QLabel(_("fact.empty"))
            empty.setFont(QFont(FONT_MAIN, 9)); empty.setObjectName("fld")
            self._inv_lay.addWidget(empty)
            return
        for inv in invoices:
            self._inv_lay.addWidget(self._invoice_card(inv))
        self.apply_theme()

    def _invoice_card(self, inv: dict) -> QWidget:
        pal = _T.palette()
        card = QFrame()
        card.setObjectName("invcard")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(10)
        cli = inv.get("client", {}).get("nom") or "—"
        ttc = invoicing.compute(inv.get("items", []), float(inv.get("vat_rate", 0) or 0),
                                float(inv.get("discount_pct", 0) or 0))["ttc"]
        days_late = store.days_overdue(inv)
        late_tag = (f"  <span style='color:{pal['ERROR_RED']}'>⚠ {_('fact.overdue')} "
                    f"({days_late} j)</span>") if days_late > 0 else ""
        info = QLabel(f"<b>{inv.get('number','')}</b> · {cli}  —  "
                      f"{ttc:.2f} {inv.get('currency','')}{late_tag}")
        info.setFont(QFont(FONT_MAIN, 9)); info.setObjectName("fld")
        lay.addWidget(info, 1)

        status = QComboBox()
        for val in _STATUS_KEYS:
            status.addItem(_status_label(val), val)
        cur_status = inv.get("status", "draft")
        status.setCurrentIndex(_STATUS_KEYS.index(cur_status) if cur_status in _STATUS_KEYS else 0)
        status.currentIndexChanged.connect(
            lambda _i, c=status, _id=inv["id"]: self._on_invoice_status(_id, c.currentData()))
        lay.addWidget(status)

        if days_late > 0:
            rel = QPushButton(_("fact.relance")); rel.setCursor(Qt.PointingHandCursor)
            rel.setFixedHeight(26)
            rel.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {pal['ERROR_RED']}; "
                f"border: 1px solid {pal['ERROR_RED']}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
                f"QPushButton:hover {{ background: {pal['ERROR_RED']}; color: #fff; }}")
            rel.clicked.connect(lambda _c=False, i=inv, t=ttc: self._relancer(i, t))
            lay.addWidget(rel)

        pdf = QPushButton(_("fact.pdf")); pdf.setCursor(Qt.PointingHandCursor); pdf.setFixedHeight(26)
        pdf.clicked.connect(lambda _c=False, i=inv: self._export_pdf(i))
        lay.addWidget(pdf)
        dele = QPushButton("✕"); dele.setFixedSize(26, 26); dele.setCursor(Qt.PointingHandCursor)
        dele.clicked.connect(lambda _c=False, i=inv: self._delete_invoice(i))
        lay.addWidget(dele)
        return card

    def _on_invoice_status(self, inv_id: str, status: str):
        """Change le statut d'une facture. Si elle passe « payée » et qu'elle est
        reliée à une commande, la commande passe aussi en « payée » (cohérence)."""
        store.set_invoice_status(inv_id, status)
        if status == "paid":
            o = store.order_for_invoice(inv_id)
            if o and o.get("status") != "paid":
                store.set_order_status(o["id"], "paid")
        self._refresh_invoices()

    def _delete_invoice(self, inv: dict):
        if self._ask(_("fact.delete"), _("fact.delete_confirm", number=inv.get("number", ""))):
            store.delete_invoice(inv["id"])
            self._refresh_invoices()

    def _relancer(self, inv: dict, ttc: float):
        """Enregistre une relance et affiche un message prêt à copier au client."""
        company = store.get_company().get("nom", "") or "—"
        msg = _("fact.relance_msg",
                number=inv.get("number", ""),
                amount=f"{ttc:.2f} {inv.get('currency','')}",
                due=inv.get("echeance", ""),
                company=company)
        store.mark_relance(inv["id"])
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton
        dlg = QDialog(self); dlg.setWindowTitle(_("fact.relance_title"))
        dlg.setMinimumWidth(460)
        pal = _T.palette()
        dlg.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        v = QVBoxLayout(dlg); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)
        head = QLabel(_("fact.relance_done")); head.setWordWrap(True)
        head.setFont(QFont(FONT_MAIN, 9))
        head.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        v.addWidget(head)
        box = QPlainTextEdit(msg); box.setReadOnly(True); box.setFixedHeight(170)
        box.setFont(QFont(FONT_MAIN, 9))
        box.setStyleSheet(f"QPlainTextEdit {{ background: {pal['BG_INPUT']}; "
                          f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                          f"border-radius: 3px; padding: 6px; }}")
        v.addWidget(box)
        copy = QPushButton("📋 " + _("fact.copy"))
        copy.setCursor(Qt.PointingHandCursor); copy.setFixedHeight(30)
        copy.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        from PySide6.QtWidgets import QApplication
        copy.clicked.connect(lambda: QApplication.clipboard().setText(msg))
        v.addWidget(copy, alignment=Qt.AlignRight)
        dlg.exec()
        self._refresh_invoices()

    def prefill_from_quote(self, q: dict):
        """Pré-remplit le formulaire de facture à partir d'un devis enregistré."""
        self._pending_order_id = ""   # source = devis, pas une commande
        for r in list(self._rows):
            self._remove_row(r)
        self._add_row(q.get("part_name", ""), str(int(q.get("qty", 1) or 1)),
                      f"{float(q.get('unit_price', 0) or 0):.2f}")
        # Report du client du devis (si rattaché) → remplit le bloc client
        cid = q.get("client_id")
        if cid and store.get_client(cid):
            i = self._client_combo.findData(cid)
            if i >= 0:
                self._client_combo.setCurrentIndex(i)
        self._notes.setPlainText(_("fact.from_quote", number=q.get("number", "")))
        self._recompute()

    def add_product_line(self, product: dict):
        """Ajoute une ligne de facture depuis un article du catalogue (cumulatif :
        n'efface pas les lignes existantes)."""
        self._add_row(product.get("nom", ""), "1",
                      f"{float(product.get('prix', 0) or 0):.2f}")
        self._recompute()

    def prefill_from_order(self, o: dict):
        """Pré-remplit la facture à partir d'une commande (file de production).
        La commande sera reliée à la facture à l'enregistrement."""
        for r in list(self._rows):
            self._remove_row(r)
        items = o.get("items") or []
        if items:
            for it in items:
                self._add_row(it.get("designation", ""),
                              str(int(it.get("qty", 1) or 1)),
                              f"{float(it.get('unit_price_ht', 0) or 0):.2f}")
        else:
            self._add_row(o.get("number", ""), "1",
                          f"{float(o.get('total_ttc', 0) or 0):.2f}")
        cid = o.get("client_id")
        if cid and store.get_client(cid):
            i = self._client_combo.findData(cid)
            if i >= 0:
                self._client_combo.setCurrentIndex(i)
        self._pending_order_id = o.get("id", "")
        self._notes.setPlainText(_("fact.from_quote", number=o.get("number", "")))
        self._recompute()

    # ── Boîtes de dialogue thématisées (texte toujours lisible) ───────────────
    def _box_qss(self) -> str:
        pal = _T.palette()
        return (f"QMessageBox {{ background: {pal['BG_PANEL']}; }}"
                f"QMessageBox QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }}"
                f"QMessageBox QPushButton {{ background: {pal['BG_SURFACE']}; "
                f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                f"border-radius: 3px; padding: 4px 16px; }}"
                f"QMessageBox QPushButton:hover {{ border-color: {pal['ACCENT']}; }}")

    def _msg(self, title: str, text: str, kind: str = "info"):
        m = QMessageBox(self)
        m.setWindowTitle(title); m.setText(text)
        m.setIcon(QMessageBox.Warning if kind == "warn" else QMessageBox.Information)
        m.setStyleSheet(self._box_qss())
        m.exec()

    def _ask(self, title: str, text: str) -> bool:
        m = QMessageBox(self)
        m.setWindowTitle(title); m.setText(text)
        m.setIcon(QMessageBox.Question)
        m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        m.setStyleSheet(self._box_qss())
        return m.exec() == QMessageBox.Yes

    # ── Thème ──────────────────────────────────────────────────────────────────
    def apply_theme(self):
        pal = _T.palette()
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._host.setStyleSheet("background: transparent;")
        edit_css = (f"QLineEdit, QComboBox, QPlainTextEdit {{ background: {pal['BG_INPUT']}; "
                    f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                    f"border-radius: 3px; padding: 2px 6px; min-height: 22px; }}"
                    f"QComboBox::drop-down {{ subcontrol-origin: padding; "
                    f"subcontrol-position: center right; width: 18px; border: none; }}"
                    f"QComboBox::down-arrow {{ width: 0; height: 0; "
                    f"border-left: 4px solid transparent; border-right: 4px solid transparent; "
                    f"border-top: 5px solid {pal['TEXT_SECONDARY']}; margin-right: 6px; }}"
                    f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
                    f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")
        for e in (self.findChildren(QLineEdit) + self.findChildren(QComboBox)
                  + self.findChildren(QPlainTextEdit)):
            e.setStyleSheet(edit_css)
        # QPlainTextEdit : forcer la palette (le texte tapé restait invisible)
        from PySide6.QtGui import QPalette, QColor
        np = self._notes.palette()
        np.setColor(QPalette.ColorRole.Text, QColor(pal['TEXT_PRIMARY']))
        np.setColor(QPalette.ColorRole.Base, QColor(pal['BG_INPUT']))
        self._notes.setPalette(np)
        for l in self.findChildren(QLabel):
            on = l.objectName()
            if on == "sec":
                l.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; "
                                f"letter-spacing: 2px;")
            elif on == "totbig":
                l.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            elif on == "totvalbig":
                l.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
            elif on in ("colh",):
                l.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
            else:
                l.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        accent_btn = (f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
                      f"border-radius: 4px; padding: 0 14px; font-weight: bold; }}"
                      f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        for b in (getattr(self, "_save_inv_btn", None), getattr(self, "_pdf_btn", None),
                  getattr(self, "_save_comp_btn", None)):
            if b:
                b.setStyleSheet(accent_btn)
        soft = (f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
                f"border: 1px solid {pal['INACTIVE']}; border-radius: 4px; }}"
                f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")
        for b in (getattr(self, "_add_line_btn", None), getattr(self, "_save_client_btn", None)):
            if b:
                b.setStyleSheet(soft)
        for r in self._rows:
            r.rm.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {pal['ERROR_RED']}; "
                f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; }}"
                f"QPushButton:hover {{ background: {pal['ERROR_RED']}; color: #fff; }}")
        for card in self.findChildren(QFrame):
            if card.objectName() == "invcard":
                card.setStyleSheet(
                    f"QFrame#invcard {{ background: {pal['BG_ELEVATED']}; "
                    f"border: 1px solid {pal['INACTIVE']}; border-radius: 5px; }}")
