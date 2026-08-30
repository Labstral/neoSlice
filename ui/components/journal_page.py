# -*- coding: utf-8 -*-
"""Onglet Journal de l'Espace Pro — journal des impressions réelles.

Chaque impression (réussie ou ratée) devient une ligne : au fil des semaines,
le journal donne le TAUX D'ÉCHEC RÉEL de l'atelier, détaillé par machine et par
filament — réutilisable dans le calculateur de devis à la place du forfait 5 %.
Il se remplit de deux façons :
  - automatiquement : une commande qui atteint « Terminé » ajoute une réussite ;
  - à la main : bouton « Enregistrer une impression » (notamment les ÉCHECS,
    qui n'existent nulle part ailleurs et sont précisément l'information utile).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMessageBox, QPlainTextEdit, QDialog, QComboBox,
)

from core.i18n import _
from core.business import store
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO


def _fnum(s: str) -> float:
    try:
        return float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire d'impression (création / édition)
# ══════════════════════════════════════════════════════════════════════════════
class PrintForm(QDialog):
    def __init__(self, parent=None, entry: dict | None = None):
        super().__init__(parent)
        self._entry = entry or {}
        self.setWindowTitle(_("journal.edit_title") if entry else _("journal.create_title"))
        self.setMinimumWidth(430)
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
        e0 = self._entry
        r = 0

        def _line(key_i18n, key, val, placeholder=""):
            nonlocal r
            g.addWidget(self._lbl(_(key_i18n)), r, 0)
            e = QLineEdit(str(val) if val not in (None, "", 0, 0.0) else "")
            e.setFont(QFont(FONT_MAIN, 9))
            if placeholder:
                e.setPlaceholderText(placeholder)
            self._edits[key] = e
            g.addWidget(e, r, 1); r += 1
            return e

        _line("journal.piece", "piece", e0.get("piece", ""))
        # Machine : auto-complétée par « Mes machines » (mêmes libellés que le
        # sélecteur d'imprimante) — saisie libre toujours possible.
        e_machine = _line("journal.machine", "machine", e0.get("machine", ""))
        try:
            from PySide6.QtWidgets import QCompleter
            from core import mes_machines as _mm
            noms = [m["label"] for m in _mm.list_machines()]
            if noms:
                comp = QCompleter(noms)
                comp.setCaseSensitivity(Qt.CaseInsensitive)
                comp.setFilterMode(Qt.MatchContains)
                e_machine.setCompleter(comp)
        except Exception:
            pass
        _line("journal.filament", "filament", e0.get("filament", ""), "PLA, PETG…")

        # Statut : Réussie / Ratée — le défaut n'apparaît que pour une ratée.
        g.addWidget(self._lbl(_("journal.status")), r, 0)
        self._statut = QComboBox()
        self._statut.setFont(QFont(FONT_MAIN, 9))
        self._statut.addItem(_("journal.status_ok"), "ok")
        self._statut.addItem(_("journal.status_fail"), "echec")
        if e0.get("statut") == "echec":
            self._statut.setCurrentIndex(1)
        self._statut.currentIndexChanged.connect(self._maj_defaut)
        g.addWidget(self._statut, r, 1); r += 1

        self._defaut_lbl = self._lbl(_("journal.defect"))
        g.addWidget(self._defaut_lbl, r, 0)
        self._defaut = QLineEdit(e0.get("defaut", ""))
        self._defaut.setFont(QFont(FONT_MAIN, 9))
        self._defaut.setPlaceholderText(_("journal.defect_hint"))
        g.addWidget(self._defaut, r, 1); r += 1

        _line("journal.grams", "grams", e0.get("grams") or "")
        _line("journal.duration", "duree_h", e0.get("duree_h") or "")
        self._notes = QPlainTextEdit(e0.get("notes", "")); self._notes.setFixedHeight(46)
        g.addWidget(self._lbl(_("journal.notes")), r, 0); g.addWidget(self._notes, r, 1)

        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("client.cancel")); self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("journal.save")); self._save.clicked.connect(self.accept)
        for b in (self._cancel, self._save):
            b.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)
        self._maj_defaut()

    def _maj_defaut(self):
        ratee = self._statut.currentData() == "echec"
        self._defaut_lbl.setVisible(ratee)
        self._defaut.setVisible(ratee)

    def _lbl(self, t):
        q = QLabel(t); q.setFont(QFont(FONT_MAIN, 9)); return q

    def data(self) -> dict:
        return {
            "piece": self._edits["piece"].text().strip(),
            "machine": self._edits["machine"].text().strip(),
            "filament": self._edits["filament"].text().strip().upper(),
            "statut": self._statut.currentData(),
            "defaut": self._defaut.text().strip()
                      if self._statut.currentData() == "echec" else "",
            "grams": _fnum(self._edits["grams"].text()),
            "duree_h": _fnum(self._edits["duree_h"].text()),
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
        self._statut.setStyleSheet(
            f"QComboBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 3px 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
            f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")
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
# Onglet Journal
# ══════════════════════════════════════════════════════════════════════════════
class JournalPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(22, 16, 22, 18); lay.setSpacing(10)
        header = QHBoxLayout()
        self._intro = QLabel(_("journal.intro")); self._intro.setFont(QFont(FONT_MAIN, 9))
        self._intro.setWordWrap(True)
        header.addWidget(self._intro, 1)
        self._add_btn = QPushButton("＋ " + _("journal.new"))
        self._add_btn.setCursor(Qt.PointingHandCursor); self._add_btn.setFixedHeight(30)
        self._add_btn.clicked.connect(self._add)
        header.addWidget(self._add_btn)
        lay.addLayout(header)

        # Bandeau statistiques : le CHIFFRE que tout le reste prépare.
        self._stats = QLabel("")
        self._stats.setFont(QFont(FONT_MAIN, 9))
        self._stats.setWordWrap(True)
        lay.addWidget(self._stats)

        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0); self._lay.setSpacing(8)
        self._lay.addStretch()
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, 1)

        self._empty = QLabel(_("journal.none")); self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True); self._empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty)

        self.refresh()
        self.apply_theme()
        _T.register(self.apply_theme)

    def showEvent(self, event):
        # Les commandes « Terminées » alimentent le journal depuis un autre onglet.
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
                w.setParent(None)
                w.deleteLater()
        prints = store.list_prints()
        for p in prints:
            self._lay.insertWidget(self._lay.count() - 1, self._card(p))
        self._empty.setVisible(not prints)
        self._scroll.setVisible(bool(prints))
        self._refresh_stats()

    def _refresh_stats(self):
        pal = _T.palette()
        s = store.failure_stats()
        if s["taux_pct"] is None:
            self._stats.setText("")
            self._stats.setStyleSheet("background: transparent;")
            return
        lignes = [_("journal.stats", n=s["n"], pct=f"{s['taux_pct']:g}")]
        det = [f"{m} : {g['taux_pct']:g} % ({g['n']})"
               for m, g in sorted(s["par_machine"].items())]
        if det:
            lignes.append(_("journal.stats_machines", detail=" · ".join(det)))
        col = pal["TELE_GREEN"] if s["taux_pct"] <= 5 else pal["AMBER"]
        _r, _g, _b = (int(col[i:i + 2], 16) for i in (1, 3, 5))
        self._stats.setText("\n".join(lignes))
        self._stats.setStyleSheet(
            f"color: {col}; background: rgba({_r},{_g},{_b},0.08); "
            f"border-left: 2px solid {col}; border-radius: 2px; padding: 4px 8px;")

    def _card(self, p: dict) -> QFrame:
        pal = _T.palette()
        ok = p.get("statut") != "echec"
        card = QFrame(); card.setObjectName("jcard")
        card.setStyleSheet(f"QFrame#jcard {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(10)

        badge = QLabel(_("journal.badge_ok") if ok else _("journal.badge_fail"))
        badge.setFont(QFont(FONT_MONO, 8, QFont.Bold))
        bcol = pal["TELE_GREEN"] if ok else pal["ERROR_RED"]
        badge.setFixedWidth(74)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"color: {bcol}; border: 1px solid {bcol}; "
                            f"border-radius: 3px; padding: 2px 4px; background: transparent;")
        lay.addWidget(badge)

        info = QVBoxLayout(); info.setSpacing(2)
        t = QLabel(p.get("piece") or "—")
        t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)
        sub_bits = [p.get("date", "")]
        if p.get("machine"):
            sub_bits.append(p["machine"])
        if p.get("filament"):
            sub_bits.append(p["filament"])
        if float(p.get("grams") or 0) > 0:
            sub_bits.append(f"{float(p['grams']):g} g")
        if not ok and p.get("defaut"):
            sub_bits.append(p["defaut"])
        sub = QLabel("  ·  ".join(b for b in sub_bits if b))
        sub.setFont(QFont(FONT_MAIN, 8))
        sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        for txt, cb, col in (
            (_("pro.edit"), lambda: self._edit(p), pal["TEXT_SECONDARY"]),
            ("✕", lambda: self._delete(p), pal["ERROR_RED"]),
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
        f = PrintForm(self)
        if f.exec():
            store.add_print(f.data())
            self.refresh()
            self.changed.emit()

    def _edit(self, p: dict):
        f = PrintForm(self, entry=p)
        if f.exec():
            store.update_print(p["id"], f.data())
            self.refresh()
            self.changed.emit()

    def _delete(self, p: dict):
        if self._ask(_("journal.delete"), _("journal.delete_confirm")):
            store.delete_print(p["id"])
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
