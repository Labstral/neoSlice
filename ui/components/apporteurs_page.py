"""Onglet Apporteurs de l'Espace Pro — suivi des apporteurs d'affaires.

Un apporteur d'affaires (ou une plateforme de mise en relation) prélève une
commission sur le prix de vente. On l'enregistre une fois (nom + commission par
défaut), on le rattache à un devis dans la section « Canal de vente » du
calculateur, et cette page affiche pour chacun le CUMUL des commissions :
  - Prévu   = tous les devis rattachés à l'apporteur ;
  - Réalisé = uniquement les devis transformés en facture (affaires conclues).
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


def _fnum(s: str) -> float:
    try:
        return float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire apporteur (création / édition)
# ══════════════════════════════════════════════════════════════════════════════
class ApporteurForm(QDialog):
    def __init__(self, parent=None, apporteur: dict | None = None):
        super().__init__(parent)
        self._apporteur = apporteur or {}
        self.setWindowTitle(_("app.edit_title") if apporteur else _("app.create_title"))
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
        a = self._apporteur
        rows = [
            ("app.name", "nom", a.get("nom", "")),
            ("app.commission", "commission",
             f"{float(a.get('commission', 0) or 0):g}" if a.get("commission") else ""),
            ("app.email", "email", a.get("email", "")),
        ]
        r = 0
        for key_i18n, key, val in rows:
            g.addWidget(self._lbl(_(key_i18n)), r, 0)
            e = QLineEdit(val); e.setFont(QFont(FONT_MAIN, 9))
            self._edits[key] = e
            g.addWidget(e, r, 1); r += 1
        self._notes = QPlainTextEdit(a.get("notes", "")); self._notes.setFixedHeight(46)
        g.addWidget(self._lbl(_("app.notes")), r, 0); g.addWidget(self._notes, r, 1)

        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("client.cancel")); self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("app.save")); self._save.clicked.connect(self.accept)
        for b in (self._cancel, self._save):
            b.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)

    def _lbl(self, t):
        q = QLabel(t); q.setFont(QFont(FONT_MAIN, 9)); return q

    def data(self) -> dict:
        return {
            "nom": self._edits["nom"].text().strip(),
            "commission": _fnum(self._edits["commission"].text()),
            "email": self._edits["email"].text().strip(),
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
# Onglet Apporteurs
# ══════════════════════════════════════════════════════════════════════════════
class ApporteursPage(QWidget):
    changed = Signal()   # émis après ajout / modif / suppression (rafraîchir ailleurs)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(10)
        header = QHBoxLayout()
        self._intro = QLabel(_("app.intro")); self._intro.setFont(QFont(FONT_MAIN, 9))
        self._intro.setWordWrap(True)
        header.addWidget(self._intro, 1)
        self._add_btn = QPushButton("＋ " + _("app.new"))
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

        self._empty = QLabel(_("app.none")); self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True); self._empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty)

        self.refresh()
        self.apply_theme()
        _T.register(self.apply_theme)

    def showEvent(self, event):
        # Rafraîchit le cumul à chaque affichage de l'onglet : les commissions
        # « réalisées » changent quand un devis est facturé depuis un autre onglet.
        super().showEvent(event)
        self.refresh()

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
        apps = store.list_apporteurs()
        for a in apps:
            self._lay.insertWidget(self._lay.count() - 1, self._card(a))
        self._empty.setVisible(not apps)
        self._scroll.setVisible(bool(apps))

    def _card(self, a: dict) -> QFrame:
        pal = _T.palette()
        cum = store.commissions_for_apporteur(a["id"])
        cur = cum.get("currency", "")
        card = QFrame(); card.setObjectName("acard")
        card.setStyleSheet(f"QFrame#acard {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(10)

        # Identité : nom + commission par défaut
        info = QVBoxLayout(); info.setSpacing(2)
        t = QLabel(a.get("nom", "—")); t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)
        sub = QLabel(_("app.default_commission", pct=f"{float(a.get('commission', 0) or 0):g}"))
        sub.setFont(QFont(FONT_MAIN, 8))
        sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        # Cumul : Prévu (tous devis) + Réalisé (facturés) — côte à côte
        stats = QVBoxLayout(); stats.setSpacing(2)
        prevu = QLabel(_("app.prevu", total=f"{cum['total_prevu']:.2f} {cur}", n=cum["n_quotes"]))
        prevu.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        # Prévu = pipeline (neutre) ; Réalisé = argent réellement gagné (vert) →
        # distinction nette en thème clair comme sombre (l'accent vire au vert en clair).
        prevu.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        prevu.setAlignment(Qt.AlignRight)
        stats.addWidget(prevu)
        realise = QLabel(_("app.realise", total=f"{cum['total_realise']:.2f} {cur}", n=cum["n_invoiced"]))
        realise.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        realise.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        realise.setAlignment(Qt.AlignRight)
        stats.addWidget(realise)
        lay.addLayout(stats)

        for txt, cb, col in (
            (_("pro.edit"), lambda: self._edit(a), pal["TEXT_SECONDARY"]),
            (_("app.delete"), lambda: self._delete(a), pal["ERROR_RED"]),
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
        f = ApporteurForm(self)
        if f.exec():
            d = f.data()
            if d["nom"]:
                store.add_apporteur(d)
                self.refresh()
                self.changed.emit()

    def _edit(self, a: dict):
        f = ApporteurForm(self, apporteur=a)
        if f.exec():
            store.update_apporteur(a["id"], f.data())
            self.refresh()
            self.changed.emit()

    def _delete(self, a: dict):
        if self._ask(_("app.delete"), _("app.delete_confirm", name=a.get("nom", ""))):
            store.delete_apporteur(a["id"])
            self.refresh()
            self.changed.emit()

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
