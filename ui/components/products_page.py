"""Onglet Articles de l'Espace Pro — catalogue de produits récurrents.

Pour les makers qui revendent souvent les mêmes pièces : on enregistre un
article une fois (nom, prix, filament, durée) et on l'insère en un clic dans
une facture, sans tout recalculer.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMessageBox, QPlainTextEdit, QDialog,
)

from core.i18n import _
from core.business import store
from ui.styles.theme import MANAGER as _T, FONT_MAIN


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire article
# ══════════════════════════════════════════════════════════════════════════════
class ProductForm(QDialog):
    def __init__(self, parent=None, product: dict | None = None):
        super().__init__(parent)
        self._product = product or {}
        self.setWindowTitle(_("art.edit_title") if product else _("art.create_title"))
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
        p = self._product
        rows = [("art.name", "nom", p.get("nom", "")),
                ("art.price", "prix", f"{float(p.get('prix', 0) or 0):.2f}" if p.get("prix") else ""),
                ("art.grams", "grams", str(p.get("grams", "") or "")),
                ("art.duration", "duree_h", str(p.get("duree_h", "") or ""))]
        r = 0
        for key_i18n, key, val in rows:
            g.addWidget(self._lbl(_(key_i18n)), r, 0)
            e = QLineEdit(val); e.setFont(QFont(FONT_MAIN, 9))
            self._edits[key] = e
            g.addWidget(e, r, 1); r += 1
        self._notes = QPlainTextEdit(p.get("notes", "")); self._notes.setFixedHeight(46)
        g.addWidget(self._lbl(_("art.notes")), r, 0); g.addWidget(self._notes, r, 1)

        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("client.cancel")); self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("art.save")); self._save.clicked.connect(self.accept)
        for b in (self._cancel, self._save):
            b.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)

    def _lbl(self, t):
        q = QLabel(t); q.setFont(QFont(FONT_MAIN, 9)); return q

    def _f(self, s: str) -> float:
        try:
            return float(s.strip().replace(",", "."))
        except ValueError:
            return 0.0

    def data(self) -> dict:
        return {
            "nom": self._edits["nom"].text().strip(),
            "prix": self._f(self._edits["prix"].text()),
            "grams": self._f(self._edits["grams"].text()),
            "duree_h": self._f(self._edits["duree_h"].text()),
            "notes": self._notes.toPlainText().strip(),
        }

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        css = (f"QLineEdit, QPlainTextEdit {{ background: {pal['BG_INPUT']}; "
               f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
               f"border-radius: 3px; padding: 3px 6px; min-height: 22px; }}")
        for e in self.findChildren(QLineEdit) + self.findChildren(QPlainTextEdit):
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
# Onglet Articles
# ══════════════════════════════════════════════════════════════════════════════
class ProductsPage(QWidget):
    insert_requested = Signal(dict)   # insérer un article dans la facture
    order_requested = Signal(dict)    # créer une commande depuis un article

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(10)
        header = QHBoxLayout()
        self._intro = QLabel(_("art.intro")); self._intro.setFont(QFont(FONT_MAIN, 9))
        self._intro.setWordWrap(True)
        header.addWidget(self._intro, 1)
        self._add_btn = QPushButton("＋ " + _("art.new"))
        self._add_btn.setCursor(Qt.PointingHandCursor); self._add_btn.setFixedHeight(30)
        self._add_btn.clicked.connect(self._add)
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

        self._empty = QLabel(_("art.none")); self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True); self._empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty)

        self.refresh()
        self.apply_theme()
        _T.register(self.apply_theme)

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

    def refresh(self):
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)   # retire de l'affichage tout de suite (anti-fantôme)
                w.deleteLater()
        prods = store.list_products()
        for p in prods:
            self._lay.insertWidget(self._lay.count() - 1, self._card(p))
        self._empty.setVisible(not prods)
        self._scroll.setVisible(bool(prods))

    def _card(self, p: dict) -> QFrame:
        pal = _T.palette()
        card = QFrame(); card.setObjectName("pcard")
        card.setStyleSheet(f"QFrame#pcard {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(10)
        info = QVBoxLayout(); info.setSpacing(2)
        t = QLabel(p.get("nom", "—")); t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)
        bits = []
        if p.get("grams"):
            bits.append(f"{float(p['grams']):.0f} g")
        if p.get("duree_h"):
            bits.append(f"{float(p['duree_h']):.1f} h")
        sub = QLabel("  ·  ".join(bits)); sub.setFont(QFont(FONT_MAIN, 8))
        sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        price = QLabel(f"{float(p.get('prix', 0) or 0):.2f}")
        price.setFont(QFont(FONT_MAIN, 11, QFont.Bold))
        price.setStyleSheet(f"color: {pal['ACCENT']}; background: transparent;")
        lay.addWidget(price)

        for txt, cb, col in (
            (_("ord.from_quote"), lambda: self.order_requested.emit(p), pal["ACCENT"]),
            (_("ord.to_invoice"), lambda: self.insert_requested.emit(p), pal["TELE_GREEN"]),
            (_("pro.edit"), lambda: self._edit(p), pal["TEXT_SECONDARY"]),
            (_("art.delete"), lambda: self._delete(p), pal["ERROR_RED"]),
        ):
            b = QPushButton(txt); b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(26)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {col}; "
                f"border: 1px solid {col}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
                f"QPushButton:hover {{ background: {col}; color: #fff; }}")
            b.clicked.connect(cb)
            lay.addWidget(b)
        return card

    def _add(self):
        f = ProductForm(self)
        if f.exec():
            store.add_product(f.data())
            self.refresh()

    def _edit(self, p: dict):
        f = ProductForm(self, product=p)
        if f.exec():
            store.update_product(p["id"], f.data())
            self.refresh()

    def _delete(self, p: dict):
        if self._ask(_("art.delete"), _("art.delete_confirm", name=p.get("nom", ""))):
            store.delete_product(p["id"])
            self.refresh()

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
