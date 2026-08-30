"""Onglet Apporteurs de l'Espace Pro — suivi des apporteurs d'affaires.

Un apporteur d'affaires (ou une plateforme de mise en relation) prélève une
commission sur le prix de vente. On l'enregistre une fois (nom + commission par
défaut), on le rattache à un devis dans la section « Canal de vente » du
calculateur, et cette page affiche pour chacun le CUMUL des commissions :
  - Prévu   = tous les devis rattachés à l'apporteur ;
  - Réalisé = uniquement les devis transformés en facture (affaires conclues).
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMessageBox, QPlainTextEdit, QDialog, QComboBox,
)

_MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]
_MONTHS_EN = ["", "January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]


def _periodes(n: int = 12) -> list:
    """[(label, debut_iso, fin_iso), …] : les n derniers mois (courant en tête) +
    « Tout ». Sert au filtre « commissions réalisées par période »."""
    from core.i18n import lang
    import calendar
    en = (lang() == "en")
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _i in range(n):
        last = calendar.monthrange(y, m)[1]
        label = f"{(_MONTHS_EN if en else _MOIS_FR)[m]} {y}"
        out.append((label, f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    out.append((_("app.period_all"), "", ""))
    return out

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

        # Sélecteur de période : « commissions réalisées » du mois choisi = montant
        # à régler à chaque apporteur en fin de mois.
        prow = QHBoxLayout()
        self._period_lbl = QLabel(_("app.period"))
        self._period_lbl.setFont(QFont(FONT_MAIN, 9))
        prow.addWidget(self._period_lbl)
        self._period_combo = QComboBox()
        self._period_combo.setFont(QFont(FONT_MAIN, 9))
        self._periodes = _periodes()
        for label, _d, _f in self._periodes:
            self._period_combo.addItem(label)
        self._period_combo.setCurrentIndex(0)   # mois courant par défaut
        self._period_combo.currentIndexChanged.connect(self._on_period_changed)
        prow.addWidget(self._period_combo, 1)
        lay.addLayout(prow)

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

    def _periode_courante(self):
        idx = self._period_combo.currentIndex() if getattr(self, "_period_combo", None) else 0
        if 0 <= idx < len(self._periodes):
            return self._periodes[idx]
        return self._periodes[0]

    def _on_period_changed(self, *_a):
        self.refresh()

    def _card(self, a: dict) -> QFrame:
        pal = _T.palette()
        label, debut, fin = self._periode_courante()
        allc = store.commissions_for_apporteur(a["id"])                 # cumul total
        per = store.commissions_for_apporteur(a["id"], debut, fin)      # période choisie
        cur = allc.get("currency", "")
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

        # À régler pour la PÉRIODE (réalisé/facturé) — le montant du mois — en avant,
        # puis le cumul total (réalisé / prévu) en petit pour le contexte.
        stats = QVBoxLayout(); stats.setSpacing(2)
        a_regler = QLabel(_("app.to_pay", label=label,
                            total=f"{per['total_realise']:.2f} {cur}", n=per["n_invoiced"]))
        a_regler.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        a_regler.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        a_regler.setAlignment(Qt.AlignRight)
        a_regler.setWordWrap(True)
        stats.addWidget(a_regler)
        cumul = QLabel(_("app.cumul_total",
                         realise=f"{allc['total_realise']:.2f} {cur}",
                         prevu=f"{allc['total_prevu']:.2f} {cur}"))
        cumul.setFont(QFont(FONT_MAIN, 8))
        cumul.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        cumul.setAlignment(Qt.AlignRight)
        stats.addWidget(cumul)
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
        self._period_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._period_combo.setStyleSheet(
            f"QComboBox {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 5px; padding: 4px 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
            f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 4px; padding: 0 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self.refresh()
