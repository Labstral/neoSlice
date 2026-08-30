"""Onglet Clients de l'Espace Pro — mini-CRM relié aux devis et factures.

Liste des clients + fiche détail avec historique (devis + factures, CA payé/dû).
Les clients sont réutilisables dans la facturation (sélection + remplissage auto).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QScrollArea, QFrame, QStackedWidget, QMessageBox, QPlainTextEdit,
    QDialog, QDateEdit, QSpinBox,
)

from core.i18n import _
from core.business import store, invoicing
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire client (ajout / édition)
# ══════════════════════════════════════════════════════════════════════════════
class ClientForm(QDialog):
    def __init__(self, parent=None, client: dict | None = None):
        super().__init__(parent)
        self._client = client or {}
        self.setWindowTitle(_("client.edit") if client else _("client.add"))
        self.setMinimumWidth(420)
        self._edits: dict[str, QLineEdit] = {}
        self._build()
        self._apply_theme()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18); lay.setSpacing(10)
        self._title = QLabel(self.windowTitle())
        self._title.setFont(QFont(FONT_MAIN, 12, QFont.Bold))
        lay.addWidget(self._title)
        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(7); lay.addLayout(g)
        rows = [("client.name", "nom"), ("client.company", "societe"),
                ("client.address", "adresse"), ("client.zip", "cp"),
                ("client.city", "ville"), ("client.email", "email"),
                ("client.phone", "tel"), ("client.taxid", "id_fiscal")]
        r = 0
        for key_i18n, key in rows:
            g.addWidget(self._lbl(_(key_i18n)), r, 0)
            e = QLineEdit(str(self._client.get(key, ""))); e.setFont(QFont(FONT_MAIN, 9))
            self._edits[key] = e
            g.addWidget(e, r, 1); r += 1
        # pays
        self._country = QComboBox()
        for c in invoicing.PAYS_ORDRE:
            self._country.addItem(c, c)
        i = self._country.findData(self._client.get("pays", "Suisse"))
        self._country.setCurrentIndex(max(0, i))
        g.addWidget(self._lbl(_("client.country")), r, 0); g.addWidget(self._country, r, 1); r += 1

        # ── Attribution apporteur d'affaires (optionnel) ──────────────────────
        # Rattache un apporteur au client pour une période : à la création d'un
        # devis pour ce client, l'apporteur sera sélectionné automatiquement tant
        # que la période est active.
        from core.business import store as _st
        self._apporteur = QComboBox()
        self._apporteur.addItem(_("client.apporteur_none"), "")
        for a in _st.list_apporteurs():
            self._apporteur.addItem(a.get("nom", ""), a["id"])
        ai = self._apporteur.findData(self._client.get("apporteur_id", ""))
        self._apporteur.setCurrentIndex(max(0, ai))
        g.addWidget(self._lbl(_("client.apporteur")), r, 0); g.addWidget(self._apporteur, r, 1); r += 1

        self._app_debut = QDateEdit()
        self._app_debut.setCalendarPopup(True)
        self._app_debut.setDisplayFormat("dd/MM/yyyy")
        _deb = self._client.get("apporteur_debut", "")
        _qd = QDate.fromString(_deb[:10], "yyyy-MM-dd") if _deb else QDate.currentDate()
        self._app_debut.setDate(_qd if _qd.isValid() else QDate.currentDate())
        g.addWidget(self._lbl(_("client.apporteur_debut")), r, 0); g.addWidget(self._app_debut, r, 1); r += 1

        self._app_duree = QSpinBox()
        self._app_duree.setRange(0, 120)
        self._app_duree.setSuffix(" " + _("client.months"))
        self._app_duree.setValue(int(self._client.get("apporteur_duree_mois", 0) or 0) or 6)
        self._app_duree.setToolTip(_("client.apporteur_duree_tip"))
        g.addWidget(self._lbl(_("client.apporteur_duree")), r, 0); g.addWidget(self._app_duree, r, 1); r += 1

        # notes
        self._notes = QPlainTextEdit(self._client.get("notes", "")); self._notes.setFixedHeight(46)
        self._notes.setFont(QFont(FONT_MAIN, 9))
        g.addWidget(self._lbl(_("client.notes")), r, 0); g.addWidget(self._notes, r, 1)

        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("client.cancel")); self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("client.save")); self._save.clicked.connect(self.accept)
        for b in (self._cancel, self._save):
            b.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)

    def _lbl(self, t):
        q = QLabel(t); q.setFont(QFont(FONT_MAIN, 9)); q.setObjectName("fld"); return q

    def data(self) -> dict:
        d = {k: e.text().strip() for k, e in self._edits.items()}
        d["pays"] = self._country.currentData()
        d["notes"] = self._notes.toPlainText().strip()
        # Attribution apporteur : fin = début + durée (mois) ; vide si pas d'apporteur
        aid = self._apporteur.currentData() or ""
        d["apporteur_id"] = aid
        if aid:
            deb = self._app_debut.date()
            duree = int(self._app_duree.value())
            d["apporteur_debut"] = deb.toString("yyyy-MM-dd")
            d["apporteur_duree_mois"] = duree
            d["apporteur_fin"] = deb.addMonths(duree).toString("yyyy-MM-dd") if duree > 0 else ""
        else:
            d["apporteur_debut"] = ""
            d["apporteur_duree_mois"] = 0
            d["apporteur_fin"] = ""
        return d

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        css = (f"QLineEdit, QComboBox, QPlainTextEdit, QDateEdit, QSpinBox {{ background: {pal['BG_INPUT']}; "
               f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
               f"border-radius: 3px; padding: 3px 6px; min-height: 22px; }}"
               f"QComboBox::down-arrow {{ width:0;height:0;border-left:4px solid transparent;"
               f"border-right:4px solid transparent;border-top:5px solid {pal['TEXT_SECONDARY']};"
               f"margin-right:6px; }}"
               f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
               f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}"
               f"QCalendarWidget QWidget {{ background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; }}"
               f"QCalendarWidget QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
               f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")
        for e in (self.findChildren(QLineEdit) + self.findChildren(QComboBox)
                  + self.findChildren(QPlainTextEdit) + self.findChildren(QDateEdit)
                  + self.findChildren(QSpinBox)):
            e.setStyleSheet(css)
        from PySide6.QtGui import QPalette, QColor
        np = self._notes.palette()
        np.setColor(QPalette.ColorRole.Text, QColor(pal['TEXT_PRIMARY']))
        np.setColor(QPalette.ColorRole.Base, QColor(pal['BG_INPUT']))
        self._notes.setPalette(np)
        for q in self.findChildren(QLabel):
            if q is not self._title:
                q.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._save.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self._cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}")


# ══════════════════════════════════════════════════════════════════════════════
# Onglet Clients
# ══════════════════════════════════════════════════════════════════════════════
class ClientsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack = QStackedWidget()
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(self._stack)
        self._stack.addWidget(self._build_list_page())   # index 0
        self._detail_host = QWidget()                     # index 1 (rempli à la volée)
        QVBoxLayout(self._detail_host).setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._detail_host)
        self._refresh_clients()
        self.apply_theme()
        _T.register(self.apply_theme)

    # ── Boîtes thématisées ────────────────────────────────────────────────────
    def _box_qss(self):
        pal = _T.palette()
        return (f"QMessageBox {{ background: {pal['BG_PANEL']}; }}"
                f"QMessageBox QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }}"
                f"QMessageBox QPushButton {{ background: {pal['BG_SURFACE']}; "
                f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                f"border-radius: 3px; padding: 4px 16px; }}")

    def _ask(self, title, text) -> bool:
        m = QMessageBox(self); m.setWindowTitle(title); m.setText(text)
        m.setIcon(QMessageBox.Question)
        m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        m.setStyleSheet(self._box_qss())
        return m.exec() == QMessageBox.Yes

    # ── Page liste ──────────────────────────────────────────────────────────────
    def _build_list_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(10)
        header = QHBoxLayout(); header.addStretch()
        self._add_btn = QPushButton("＋ " + _("client.add"))
        self._add_btn.setCursor(Qt.PointingHandCursor); self._add_btn.setFixedHeight(30)
        self._add_btn.clicked.connect(self._add_client)
        header.addWidget(self._add_btn)
        lay.addLayout(header)

        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0); self._list_lay.setSpacing(8)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._list_host)
        lay.addWidget(self._scroll, 1)

        self._empty = QLabel(_("client.empty")); self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True); self._empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty)
        return page

    def _refresh_clients(self):
        while self._list_lay.count() > 1:
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)   # anti-fantôme (deleteLater est asynchrone)
                w.deleteLater()
        clients = store.list_clients()
        for c in clients:
            self._list_lay.insertWidget(self._list_lay.count() - 1, self._client_card(c))
        self._empty.setVisible(not clients)
        self._scroll.setVisible(bool(clients))

    def _client_card(self, c: dict) -> QFrame:
        pal = _T.palette()
        st = store.client_stats(c["id"])
        card = QFrame(); card.setObjectName("ccard")
        card.setStyleSheet(f"QFrame#ccard {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(10)
        info = QVBoxLayout(); info.setSpacing(2)
        t = QLabel(store.client_label(c)); t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)
        sub = QLabel(f"{c.get('email','')}  ·  "
                     f"{_('client.n_quotes', n=st['n_quotes'])} · {_('client.n_invoices', n=st['n_invoices'])}  ·  "
                     f"{_('client.due')} {st['due']:.2f}")
        sub.setFont(QFont(FONT_MAIN, 8)); sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        for txt, cb, danger in ((_("client.open"), lambda: self._open_client(c), False),
                                (_("client.edit"), lambda: self._edit_client(c), False),
                                (_("client.delete"), lambda: self._delete_client(c), True)):
            b = QPushButton(txt); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(26)
            col = pal["ERROR_RED"] if danger else pal["ACCENT"]
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {col}; "
                f"border: 1px solid {col}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
                f"QPushButton:hover {{ background: {col}; color: #fff; }}")
            b.clicked.connect(cb)
            lay.addWidget(b)
        return card

    # ── CRUD ────────────────────────────────────────────────────────────────
    def _add_client(self):
        f = ClientForm(self)
        if f.exec():
            store.add_client(f.data())
            self._refresh_clients()

    def _edit_client(self, c: dict):
        f = ClientForm(self, client=c)
        if f.exec():
            store.update_client(c["id"], f.data())
            self._refresh_clients()

    def _delete_client(self, c: dict):
        if self._ask(_("client.delete"), _("client.delete_confirm")):
            store.delete_client(c["id"])
            self._refresh_clients()

    # ── Fiche détail (historique) ─────────────────────────────────────────────
    def _open_client(self, c: dict):
        old = self._detail_host.layout()
        while old.count():
            it = old.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        old.addWidget(self._build_detail(c))
        self._stack.setCurrentIndex(1)

    def _build_detail(self, c: dict) -> QWidget:
        pal = _T.palette()
        st = store.client_stats(c["id"])
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.NoFrame)
        page.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        host = QWidget(); host.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(host); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(8)

        back = QPushButton(_("client.back")); back.setCursor(Qt.PointingHandCursor)
        back.setFixedHeight(28)
        back.setStyleSheet(f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
                           f"border: none; text-align: left; }} QPushButton:hover {{ color: {pal['ACCENT_BRIGHT']}; }}")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        lay.addWidget(back, alignment=Qt.AlignLeft)

        name = QLabel(store.client_label(c)); name.setFont(QFont(FONT_MAIN, 15, QFont.Bold))
        name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(name)
        coord = QLabel("  ·  ".join(x for x in (c.get("email"), c.get("tel"),
                       f"{c.get('cp','')} {c.get('ville','')}".strip(), c.get("pays")) if x and str(x).strip()))
        coord.setFont(QFont(FONT_MAIN, 9)); coord.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        coord.setWordWrap(True); lay.addWidget(coord)

        # Bandeau stats (facturé / payé / dû)
        stats = QHBoxLayout(); stats.setSpacing(18)
        for label, val, color in ((_("client.billed"), st["billed"], pal["TEXT_PRIMARY"]),
                                   (_("client.paid"), st["paid"], pal["TELE_GREEN"]),
                                   (_("client.due"), st["due"], pal["AMBER"])):
            box = QVBoxLayout(); box.setSpacing(0)
            v = QLabel(f"{val:.2f}"); v.setFont(QFont(FONT_MAIN, 13, QFont.Bold))
            v.setStyleSheet(f"color: {color}; background: transparent;")
            n = QLabel(label); n.setFont(QFont(FONT_MAIN, 8))
            n.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
            box.addWidget(v); box.addWidget(n); stats.addLayout(box)
        stats.addStretch()
        lay.addSpacing(8); lay.addLayout(stats); lay.addSpacing(10)

        # Historique : factures puis devis
        lay.addWidget(self._hist_title(_("client.section_invoices")))
        invs = store.invoices_for_client(c["id"])
        if invs:
            for inv in invs:
                lay.addWidget(self._doc_row(inv, is_invoice=True))
        else:
            lay.addWidget(self._hist_empty())
        lay.addSpacing(8)
        lay.addWidget(self._hist_title(_("client.section_quotes")))
        quos = store.quotes_for_client(c["id"])
        if quos:
            for q in quos:
                lay.addWidget(self._doc_row(q, is_invoice=False))
        else:
            lay.addWidget(self._hist_empty())
        lay.addStretch()
        page.setWidget(host)
        return page

    def _hist_title(self, t: str) -> QLabel:
        pal = _T.palette()
        l = QLabel(t.upper()); l.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        l.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 2px;")
        return l

    def _hist_empty(self) -> QLabel:
        pal = _T.palette()
        l = QLabel("—"); l.setFont(QFont(FONT_MAIN, 9))
        l.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        return l

    def _doc_row(self, doc: dict, is_invoice: bool) -> QFrame:
        pal = _T.palette()
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 4px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(10, 6, 10, 6)
        if is_invoice:
            ttc = invoicing.compute(doc.get("items", []), float(doc.get("vat_rate", 0) or 0),
                                    float(doc.get("discount_pct", 0) or 0))["ttc"]
            amount = f"{ttc:.2f} {doc.get('currency','')}"
            paid = doc.get("status") == "paid"
            tag = f"<span style='color:{pal['TELE_GREEN'] if paid else pal['AMBER']}'>" \
                  f"{'✓' if paid else '•'}</span>"
        else:
            amount = f"{doc.get('total_price',0):.2f} {doc.get('currency','')}"
            tag = ""
        t = QLabel(f"<b>{doc.get('number','')}</b> · {doc.get('date','')}  {tag}")
        t.setFont(QFont(FONT_MAIN, 9)); t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(t, 1)
        a = QLabel(amount); a.setFont(QFont(FONT_MAIN, 9, QFont.Bold)); a.setAlignment(Qt.AlignRight)
        a.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(a)
        return card

    # ── Thème ──────────────────────────────────────────────────────────────────
    def apply_theme(self):
        pal = _T.palette()
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._list_host.setStyleSheet("background: transparent;")
        self._empty.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        accent = (f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
                  f"border-radius: 4px; padding: 0 14px; font-weight: bold; }}"
                  f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self._add_btn.setStyleSheet(accent)
        self._refresh_clients()
