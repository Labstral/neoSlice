"""Onglet Commandes de l'Espace Pro — file de production.

Suit chaque commande de la prise en charge à l'encaissement :
  À faire → En impression → Terminé → Livré → Payé  (+ Annulé)

Liens : on peut créer une commande depuis un devis, et facturer une commande
(pré-remplit la facturation). Le stock filament est déduit automatiquement au
passage en « En impression » (voir core.business.store._maybe_consume_stock).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QScrollArea, QFrame, QMessageBox, QPlainTextEdit, QDialog, QSizePolicy,
)

from core.i18n import _
from core.business import store
from ui.styles.theme import MANAGER as _T, FONT_MAIN


# Couleur d'un statut (clé palette → résolue au rendu)
def _status_color(pal: dict, status: str) -> str:
    return {
        "todo":      pal["TEXT_LABEL"],
        "printing":  pal["ACCENT"],
        "done":      pal["AMBER"],
        "delivered": pal["ACCENT_BRIGHT"],
        "paid":      pal["TELE_GREEN"],
        "cancelled": pal["ERROR_RED"],
    }.get(status, pal["TEXT_LABEL"])


_NEXT_STATUS = {"todo": "printing", "printing": "done",
                "done": "delivered", "delivered": "paid"}


class _StatusButton(QPushButton):
    """Bouton « Avancer » qui ouvre un menu déroulant des statuts AU CLIC, pour
    sauter directement à l'étape voulue (pas au survol : évite les ouvertures
    intempestives quand la souris passe dessus par accident)."""

    def __init__(self, text: str, on_open, parent=None):
        super().__init__(text, parent)
        self._on_open = on_open
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: self._on_open(self))


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire commande (ajout / édition)
# ══════════════════════════════════════════════════════════════════════════════
class OrderForm(QDialog):
    def __init__(self, parent=None, order: dict | None = None):
        super().__init__(parent)
        self._order = order or {}
        self.setWindowTitle(_("ord.edit_title") if order else _("ord.create_title"))
        self.setMinimumWidth(440)
        self._build()
        self._apply_theme()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18); lay.setSpacing(10)
        self._title = QLabel(self.windowTitle())
        self._title.setFont(QFont(FONT_MAIN, 12, QFont.Bold))
        lay.addWidget(self._title)

        self._spools = store.list_spools()
        self._cons_rows: list = []

        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(7); lay.addLayout(g)
        o = self._order
        r = 0

        # Client
        self._client = QComboBox()
        self._client.addItem(_("ord.no_client"), "")
        for c in store.list_clients():
            self._client.addItem(store.client_label(c), c["id"])
        i = self._client.findData(o.get("client_id", ""))
        self._client.setCurrentIndex(max(0, i))
        g.addWidget(self._lbl(_("ord.client")), r, 0); g.addWidget(self._client, r, 1); r += 1

        # Désignation
        items = o.get("items") or []
        desig = items[0].get("designation", "") if items else ""
        self._desig = QLineEdit(desig)
        g.addWidget(self._lbl(_("ord.label")), r, 0); g.addWidget(self._desig, r, 1); r += 1

        # Prix
        price = float(items[0].get("unit_price_ht", 0)) if items else float(o.get("total_ttc", 0) or 0)
        self._price = QLineEdit(f"{price:.2f}" if price else "")
        g.addWidget(self._lbl(_("art.price")), r, 0); g.addWidget(self._price, r, 1); r += 1

        # Échéance
        ech = o.get("echeance") or (date.today() + timedelta(days=7)).isoformat()
        self._due = QLineEdit(ech)
        self._due.setPlaceholderText("AAAA-MM-JJ")
        g.addWidget(self._lbl(_("ord.due")), r, 0); g.addWidget(self._due, r, 1); r += 1

        # Statut
        self._status = QComboBox()
        for st in store.ORDER_STATUSES:
            self._status.addItem(_(f"ord.status_{st}"), st)
        i = self._status.findData(o.get("status", "todo"))
        self._status.setCurrentIndex(max(0, i))
        g.addWidget(self._lbl(_("ord.status")), r, 0)
        g.addWidget(self._status, r, 1); r += 1

        # ── Consommation filament (1 ligne par couleur) ──
        sec = QLabel(_("ord.consumptions")); sec.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._cons_sec = sec
        lay.addWidget(sec)
        self._cons_host = QWidget()
        self._cons_box = QVBoxLayout(self._cons_host)
        self._cons_box.setContentsMargins(0, 0, 0, 0); self._cons_box.setSpacing(5)
        lay.addWidget(self._cons_host)
        self._add_color_btn = QPushButton(_("ord.add_color"))
        self._add_color_btn.setCursor(Qt.PointingHandCursor); self._add_color_btn.setFixedHeight(26)
        self._add_color_btn.clicked.connect(lambda: (self._add_cons_row(), self._update_cons_note()))
        lay.addWidget(self._add_color_btn, alignment=Qt.AlignLeft)
        self._cons_note = QLabel(""); self._cons_note.setWordWrap(True)
        self._cons_note.setFont(QFont(FONT_MAIN, 8))
        lay.addWidget(self._cons_note)

        # Pré-remplissage des consommations existantes (sinon 1 ligne vide)
        existing = o.get("consumptions") or []
        if existing:
            for c in existing:
                self._add_cons_row(c.get("spool_id", ""), c.get("grams", ""))
        else:
            self._add_cons_row()
        self._update_cons_note()

        # Notes
        self._notes = QPlainTextEdit(o.get("notes", "")); self._notes.setFixedHeight(46)
        nl = QHBoxLayout(); nl.addWidget(self._lbl(_("ord.notes"))); lay.addLayout(nl)
        lay.addWidget(self._notes)

        hint = QLabel(_("ord.stock_note")); hint.setWordWrap(True)
        hint.setFont(QFont(FONT_MAIN, 8))
        self._hint = hint
        lay.addWidget(hint)

        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("client.cancel")); self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("ord.save")); self._save.clicked.connect(self.accept)
        for b in (self._cancel, self._save):
            b.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)

    def _lbl(self, t):
        q = QLabel(t); q.setFont(QFont(FONT_MAIN, 9)); return q

    def _input_css(self) -> str:
        pal = _T.palette()
        return (f"QLineEdit, QComboBox {{ background: {pal['BG_INPUT']}; "
                f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                f"border-radius: 3px; padding: 3px 6px; min-height: 22px; }}"
                f"QComboBox::down-arrow {{ width:0;height:0;border-left:4px solid transparent;"
                f"border-right:4px solid transparent;border-top:5px solid {pal['TEXT_SECONDARY']};"
                f"margin-right:6px; }}"
                f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
                f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")

    def _add_cons_row(self, spool_id: str = "", grams="") -> None:
        pal = _T.palette()
        row = QWidget()
        h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        combo = QComboBox(); combo.addItem(_("ord.no_spool"), "")
        for s in self._spools:
            lab = " ".join(p for p in (s.get("materiau", ""), s.get("marque", ""),
                                       s.get("couleur_nom", "")) if p)
            lab += f" — {store.pct_restant(s):.0f}%"
            combo.addItem(lab, s["id"])
        combo.setCurrentIndex(max(0, combo.findData(spool_id)))
        ge = QLineEdit(str(int(float(grams))) if str(grams).strip() not in ("", "0", "0.0") else "")
        ge.setPlaceholderText("g"); ge.setFixedWidth(64)
        rm = QPushButton("✕"); rm.setFixedSize(26, 26); rm.setCursor(Qt.PointingHandCursor)
        rm.clicked.connect(lambda _c=False, w=row: self._remove_cons_row(w))
        combo.setStyleSheet(self._input_css()); ge.setStyleSheet(self._input_css())
        rm.setStyleSheet(f"QPushButton {{ background: transparent; color: {pal['ERROR_RED']}; "
                         f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; }}"
                         f"QPushButton:hover {{ border-color: {pal['ERROR_RED']}; }}")
        h.addWidget(combo, 1); h.addWidget(ge); h.addWidget(rm)
        self._cons_box.addWidget(row)
        self._cons_rows.append((row, combo, ge))

    def _remove_cons_row(self, row: QWidget) -> None:
        self._cons_rows = [(w, c, e) for (w, c, e) in self._cons_rows if w is not row]
        row.setParent(None); row.deleteLater()
        if not self._cons_rows:          # toujours au moins une ligne
            self._add_cons_row()
        self._update_cons_note()

    def _update_cons_note(self) -> None:
        n = len(self._cons_rows)
        self._cons_note.setText(_("ord.est_mono") if n <= 1 else _("ord.fill_multi"))

    def _f(self, le: QLineEdit) -> float:
        try:
            return float(le.text().strip().replace(",", "."))
        except ValueError:
            return 0.0

    def _fs(self, s: str) -> float:
        try:
            return float(s.strip().replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    def data(self) -> dict:
        price = self._f(self._price)
        cid = self._client.currentData() or ""
        label = self._client.currentText() if cid else ""
        desig = self._desig.text().strip() or _("ord.label")
        cons = []
        for _w, combo, ge in self._cons_rows:
            sid = combo.currentData() or ""
            g = self._fs(ge.text())
            if sid or g > 0:
                cons.append({"spool_id": sid, "grams": g})
        return {
            "client_id": cid, "client_label": label,
            "items": [{"designation": desig, "qty": 1, "unit_price_ht": price}],
            "total_ttc": price,
            "consumptions": cons,
            "echeance": self._due.text().strip(),
            "status": self._status.currentData() or "todo",
            "notes": self._notes.toPlainText().strip(),
        }

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        css = (f"QLineEdit, QComboBox, QPlainTextEdit {{ background: {pal['BG_INPUT']}; "
               f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
               f"border-radius: 3px; padding: 3px 6px; min-height: 22px; }}"
               f"QComboBox::down-arrow {{ width:0;height:0;border-left:4px solid transparent;"
               f"border-right:4px solid transparent;border-top:5px solid {pal['TEXT_SECONDARY']};"
               f"margin-right:6px; }}"
               f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
               f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")
        for e in (self.findChildren(QLineEdit) + self.findChildren(QComboBox)
                  + self.findChildren(QPlainTextEdit)):
            e.setStyleSheet(css)
        from PySide6.QtGui import QPalette, QColor
        np = self._notes.palette()
        np.setColor(QPalette.ColorRole.Text, QColor(pal['TEXT_PRIMARY']))
        np.setColor(QPalette.ColorRole.Base, QColor(pal['BG_INPUT']))
        self._notes.setPalette(np)
        for q in self.findChildren(QLabel):
            if q is not self._title:
                q.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._hint.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        self._cons_sec.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 1px;")
        self._cons_note.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        self._add_color_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
            f"border: 1px dashed {pal['INACTIVE']}; border-radius: 3px; padding: 2px 10px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; }}")
        self._save.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self._cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}")


# ══════════════════════════════════════════════════════════════════════════════
# Onglet Commandes
# ══════════════════════════════════════════════════════════════════════════════
class OrdersPage(QWidget):
    invoice_requested = Signal(dict)   # émis pour facturer une commande

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(10)

        header = QHBoxLayout()
        self._intro = QLabel(_("ord.intro")); self._intro.setFont(QFont(FONT_MAIN, 9))
        header.addWidget(self._intro); header.addStretch()
        self._add_btn = QPushButton("＋ " + _("ord.new"))
        self._add_btn.setCursor(Qt.PointingHandCursor); self._add_btn.setFixedHeight(30)
        self._add_btn.clicked.connect(self._add_order)
        header.addWidget(self._add_btn)
        lay.addLayout(header)

        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0); self._lay.setSpacing(8)
        self._lay.addStretch()
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, 1)

        self._empty = QLabel(_("ord.none")); self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True); self._empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty)

        self.refresh()
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

    # ── Rafraîchissement de la liste ──────────────────────────────────────────
    def refresh(self):
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                # setParent(None) retire IMMÉDIATEMENT de l'affichage ; sans ça,
                # deleteLater() étant asynchrone, les anciennes cartes restent
                # visibles en fantômes par-dessus les nouvelles (bug d'affichage).
                w.setParent(None)
                w.deleteLater()
        orders = store.list_orders()
        active = [o for o in orders if o.get("status") in ("todo", "printing", "done")]
        done = [o for o in orders if o.get("status") in ("delivered", "paid", "cancelled")]
        idx = 0
        if active:
            self._lay.insertWidget(idx, self._section(_("ord.section_active"))); idx += 1
            for o in active:
                self._lay.insertWidget(idx, self._order_card(o)); idx += 1
        if done:
            self._lay.insertWidget(idx, self._section(_("ord.section_done"))); idx += 1
            for o in done:
                self._lay.insertWidget(idx, self._order_card(o)); idx += 1
        self._empty.setVisible(not orders)
        self._scroll.setVisible(bool(orders))

    def _section(self, t: str) -> QLabel:
        pal = _T.palette()
        l = QLabel(t); l.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        l.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 2px;")
        return l

    def _due_text(self, o: dict, pal: dict) -> tuple[str, str]:
        """(texte, couleur) de l'échéance pour une commande active."""
        ech = str(o.get("echeance") or "")
        if not ech or o.get("status") in ("paid", "delivered", "cancelled"):
            return "", pal["TEXT_LABEL"]
        try:
            d = datetime.strptime(ech[:10], "%Y-%m-%d").date()
        except ValueError:
            return "", pal["TEXT_LABEL"]
        delta = (d - date.today()).days
        if delta < 0:
            return _("ord.overdue_days", n=-delta), pal["ERROR_RED"]
        return _("ord.due_in", n=delta), pal["TEXT_SECONDARY"]

    def _order_card(self, o: dict) -> QFrame:
        pal = _T.palette()
        status = o.get("status", "todo")
        scol = _status_color(pal, status)
        card = QFrame(); card.setObjectName("ocard")
        # Hauteur FIXE : sinon la carte s'étire verticalement pour remplir l'espace
        # libre du panneau (gros bug d'affichage : badge/contenu géants).
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        card.setStyleSheet(f"QFrame#ocard {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(10)

        # Pastille de statut
        badge = QLabel(_(f"ord.status_{status}")); badge.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        badge.setAlignment(Qt.AlignCenter); badge.setFixedWidth(96)
        badge.setStyleSheet(f"color: {scol}; background: transparent; "
                            f"border: 1px solid {scol}; border-radius: 3px; padding: 3px 0;")
        lay.addWidget(badge)

        # Infos
        info = QVBoxLayout(); info.setSpacing(2)
        cl = o.get("client_label") or "—"
        t = QLabel(f"{o.get('number','')}  ·  {cl}"); t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)
        items = o.get("items") or []
        desig = items[0].get("designation", "") if items else ""
        due_txt, due_col = self._due_text(o, pal)
        sub_parts = [desig]
        if o.get("grams"):
            sub_parts.append(f"{float(o['grams']):.0f} g")
        sub = QLabel("  ·  ".join(p for p in sub_parts if p))
        sub.setFont(QFont(FONT_MAIN, 8)); sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        # Échéance
        if due_txt:
            due = QLabel(due_txt); due.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            due.setStyleSheet(f"color: {due_col}; background: transparent;")
            lay.addWidget(due)

        # Montant
        amount = QLabel(f"{float(o.get('total_ttc', 0) or 0):.2f} {o.get('currency','')}")
        amount.setFont(QFont(FONT_MAIN, 10, QFont.Bold)); amount.setAlignment(Qt.AlignRight)
        amount.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(amount)

        # Actions — « Avancer » ouvre un menu déroulant de TOUS les statuts (survol
        # ou clic) → on saute directement à l'étape voulue (et on peut corriger).
        if status != "cancelled":
            b = _StatusButton(_("ord.advance"),
                              lambda btn, oid=o["id"], cur=status: self._status_menu(btn, oid, cur))
            b.setFixedHeight(26)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
                f"border: 1px solid {pal['ACCENT']}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
                f"QPushButton:hover {{ background: {pal['ACCENT']}; color: #fff; }}")
            lay.addWidget(b)
        if status in ("todo", "printing", "done") and not o.get("invoice_id"):
            bi = self._mini_btn(_("ord.to_invoice"), pal["TELE_GREEN"])
            bi.clicked.connect(lambda _c=False, od=o: self._invoice(od))
            lay.addWidget(bi)
        bp = self._mini_btn(_("ord.pdf"), pal["TEXT_SECONDARY"])
        bp.clicked.connect(lambda _c=False, od=o: self._export_pdf(od))
        lay.addWidget(bp)
        be = self._mini_btn(_("pro.edit"), pal["TEXT_SECONDARY"])
        be.clicked.connect(lambda _c=False, od=o: self._edit(od))
        lay.addWidget(be)
        bd = self._mini_btn("✕", pal["ERROR_RED"])
        bd.setFixedWidth(28)
        bd.clicked.connect(lambda _c=False, od=o: self._delete(od))
        lay.addWidget(bd)
        return card

    def _mini_btn(self, txt: str, col: str) -> QPushButton:
        b = QPushButton(txt); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(26)
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {col}; "
            f"border: 1px solid {col}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {col}; color: #fff; }}")
        return b

    # ── Actions ───────────────────────────────────────────────────────────────
    def _add_order(self):
        f = OrderForm(self)
        if f.exec():
            store.add_order(f.data())
            self.refresh()

    def _edit(self, o: dict):
        f = OrderForm(self, order=o)
        if f.exec():
            store.update_order(o["id"], f.data())
            self.refresh()

    def _advance(self, oid: str, nxt: str):
        store.set_order_status(oid, nxt)
        self.refresh()

    def _status_menu(self, btn, oid: str, current: str):
        """Menu déroulant de tous les statuts → bascule directe à l'étape voulue."""
        # Ne pas re-ouvrir si déjà affiché (le survol peut redéclencher).
        m = getattr(self, "_open_status_menu", None)
        if m is not None and m.isVisible():
            return
        from PySide6.QtWidgets import QMenu
        from PySide6.QtCore import QPoint
        pal = _T.palette()
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background: {pal['ACCENT']}; color: #fff; }}")
        for st in store.ORDER_STATUSES:
            mark = "● " if st == current else "    "
            act = menu.addAction(mark + _(f"ord.status_{st}"))
            act.triggered.connect(lambda _c=False, s=st, _id=oid: self._set_status(_id, s))
        self._open_status_menu = menu
        menu.popup(btn.mapToGlobal(QPoint(0, btn.height() + 2)))

    def _set_status(self, oid: str, status: str):
        store.set_order_status(oid, status)
        self.refresh()

    def _invoice(self, o: dict):
        self.invoice_requested.emit(o)

    def _export_pdf(self, o: dict):
        """Génère le bon de production PDF et l'ouvre/le révèle."""
        import re as _re
        from pathlib import Path
        from PySide6.QtCore import QStandardPaths
        from core.export.order_pdf import render_order
        company = store.get_company()
        safe = _re.sub(r'[<>:"/\\|?*]', "_", f"neoSlice_{o.get('number','commande')}.pdf")
        dl = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        out = Path(dl) if dl else Path.home()
        out.mkdir(parents=True, exist_ok=True)
        path = str(out / safe)
        try:
            render_order(path, o, company)
        except Exception as exc:
            self._msg(_("ord.pdf"), str(exc)) if hasattr(self, "_msg") else None
            return
        import sys as _sys
        import subprocess as _sp
        try:
            if _sys.platform == "win32":
                _sp.Popen(f'explorer /select,"{path}"')
            elif _sys.platform == "darwin":
                _sp.run(["open", "-R", path], check=False)
            else:
                _sp.run(["xdg-open", str(out)], check=False)
        except Exception:
            pass

    def _delete(self, o: dict):
        if self._ask(_("ord.delete"), _("ord.delete_confirm", number=o.get("number", ""))):
            store.delete_order(o["id"])
            self.refresh()

    # ── Thème ──────────────────────────────────────────────────────────────────
    def apply_theme(self):
        pal = _T.palette()
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._host.setStyleSheet("background: transparent;")
        self._intro.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._empty.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 4px; padding: 0 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self.refresh()
