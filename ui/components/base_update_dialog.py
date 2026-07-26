# -*- coding: utf-8 -*-
"""Fenêtre unique de NOTIFICATION des mises à jour de BASE (au lancement).

Dès qu'il y a du nouveau dans la bibliothèque neoGen OU dans la base de
connaissances d'Oen, cette petite fenêtre s'affiche au démarrage et propose de
tout mettre à jour en un clic — sans réinstaller neoSlice.

Réutilise les mécanismes existants :
  neoGen : core.neogen.maj.verifier_maj_objets / appliquer_objets + catalogue.recharger_objets_module
  Oen    : core.assistant.kb_update.available_update / KBUpdater.update

Simulation (pour prévisualiser la fenêtre) : variable d'environnement
NEOSLICE_SIMULATE_BASE_UPDATE=1 → la fenêtre apparaît au lancement avec des
nouveautés factices ; le bouton simule la mise à jour (aucun téléchargement).
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)

from core.i18n import _
from ui.styles.theme import MANAGER as _T

FONT_MAIN = "Segoe UI"


def simulation_active() -> bool:
    return bool(os.environ.get("NEOSLICE_SIMULATE_BASE_UPDATE", "").strip())


def check_base_updates(simulate: bool = False) -> dict | None:
    """Résumé des nouveautés de base disponibles, ou None si rien.
    {'neogen': {...}|None, 'oen': {...}|None, '_simulate': bool}.
    HORS-LIGNE-SAFE : ne lève jamais (renvoie None en cas d'erreur)."""
    if simulate:
        return {
            "neogen": {"version": "démo", "manifest": None},
            "oen": {"kb_version": "démo", "download_mo": 12.0, "info": None},
            "_simulate": True,
        }
    res: dict = {"neogen": None, "oen": None, "_simulate": False}
    # neoGen ET Oen sont des fonctions Pro : on ne notifie QUE les utilisateurs Pro
    # (un gratuit ne peut pas s'en servir → notification inutile et déroutante).
    try:
        from core import licensing
        if not licensing.est_pro():
            return None
    except Exception:
        return None
    # neoGen — de nouveaux objets dans la bibliothèque ?
    try:
        from core.neogen import maj
        m = maj.verifier_maj_objets()
        if m:
            res["neogen"] = {"version": str(m.get("version", "")), "manifest": m}
    except Exception:
        pass
    # Oen — nouvelle base de connaissances ? (Oen installé seulement)
    try:
        from core.assistant.engine import AssistantEngine
        from core.assistant.installer import is_installed
        if is_installed() or AssistantEngine.available():
            from core.assistant.kb_update import available_update
            info = available_update()
            if info and info.get("kb_version") and not info.get("incompatible_app"):
                res["oen"] = {
                    "kb_version": str(info.get("kb_version", "")),
                    "download_mo": round(int(info.get("download_size", 0) or 0) / 1048576, 1),
                    "info": info,
                }
    except Exception:
        pass
    return res if (res["neogen"] or res["oen"]) else None


class _ApplyWorker(QThread):
    """Applique les mises à jour de base en arrière-plan (neoGen puis Oen)."""
    progress = Signal(str, float)   # (étape, fraction 0..1)
    done = Signal()
    failed = Signal(str)

    def __init__(self, summary: dict, parent=None):
        super().__init__(parent)
        self._summary = summary

    def run(self):
        try:
            sim = bool(self._summary.get("_simulate"))
            # ── neoGen ────────────────────────────────────────────────────
            if self._summary.get("neogen"):
                self.progress.emit(_("base_update.updating"), 0.12)
                if sim:
                    time.sleep(0.7)
                else:
                    from core.neogen import maj
                    m = self._summary["neogen"].get("manifest") or maj.verifier_maj_objets()
                    if m:
                        maj.appliquer_objets(m)
                        try:
                            from core.neogen import catalogue as _C
                            _C.recharger_objets_module()      # rechargement à chaud
                        except Exception:
                            pass
                    try:                                       # cookbook (aide création)
                        m_cb = maj.verifier_maj()
                        if m_cb:
                            maj.appliquer(m_cb)
                    except Exception:
                        pass
                self.progress.emit(_("base_update.updating"), 0.45)
            # ── Oen (base de connaissances) ───────────────────────────────
            if self._summary.get("oen"):
                if sim:
                    for f in (0.6, 0.75, 0.9):
                        self.progress.emit(_("base_update.updating"), f)
                        time.sleep(0.35)
                else:
                    info = self._summary["oen"].get("info")
                    if info:
                        from core.assistant.kb_update import KBUpdater
                        up = KBUpdater(
                            progress=lambda s, fr: self.progress.emit(s, 0.5 + fr * 0.45))
                        up.update(info)
            self.progress.emit(_("base_update.done"), 1.0)
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class BaseUpdateDialog(QDialog):
    """Petite fenêtre : « des nouveautés sont disponibles » + bouton mettre à jour."""

    def __init__(self, summary: dict, parent=None):
        super().__init__(parent)
        self._summary = summary
        self._worker: _ApplyWorker | None = None
        pal = _T.palette()

        self.setWindowTitle("neoSlice")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(
            f"QDialog {{ background: {pal['BG_PANEL']}; }}"
            f"QLabel {{ background: transparent; }}")
        self._build_ui(pal)

    def _build_ui(self, pal):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 26, 30, 22)
        lay.setSpacing(13)

        title = QLabel(_("base_update.title"))
        title.setFont(QFont(FONT_MAIN, 14, QFont.Bold))
        title.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']};")
        lay.addWidget(title)

        intro = QLabel(_("base_update.intro"))
        intro.setFont(QFont(FONT_MAIN, 10))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
        lay.addWidget(intro)
        lay.addSpacing(4)

        for key, present in (("base_update.neogen", self._summary.get("neogen")),
                             ("base_update.oen", self._summary.get("oen"))):
            if present:
                row = QLabel("•  " + _(key))
                row.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
                row.setWordWrap(True)
                row.setStyleSheet(f"color: {pal['TEXT_PRIMARY']};")
                lay.addWidget(row)
        lay.addSpacing(8)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: {pal['BG_SURFACE']}; border: 1px solid "
            f"{pal['INACTIVE']}; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {pal['ACCENT']}; border-radius: 3px; }}")
        self._bar.hide()
        lay.addWidget(self._bar)

        self._status = QLabel("")
        self._status.setFont(QFont(FONT_MAIN, 9))
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
        self._status.hide()
        lay.addWidget(self._status)
        lay.addSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._later = QPushButton(_("base_update.btn_later"))
        self._later.setFont(QFont(FONT_MAIN, 9))
        self._later.setFixedHeight(32)
        self._later.setCursor(Qt.PointingHandCursor)
        self._later.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 0 14px; }}"
            f"QPushButton:hover {{ color: {pal['TEXT_PRIMARY']}; "
            f"border-color: {pal['TEXT_SECONDARY']}; }}")
        self._later.clicked.connect(self.reject)

        self._now = QPushButton(_("base_update.btn_now"))
        self._now.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._now.setFixedHeight(32)
        self._now.setCursor(Qt.PointingHandCursor)
        self._now.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: {pal['EXPORT_FG']}; "
            f"border: none; border-radius: 4px; padding: 0 18px; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}"
            f"QPushButton:disabled {{ background: {pal['INACTIVE']}; "
            f"color: {pal['TEXT_LABEL']}; }}")
        self._now.clicked.connect(self._start)

        row.addWidget(self._later)
        row.addStretch()
        row.addWidget(self._now)
        lay.addLayout(row)

    def _start(self):
        if self._worker is not None:
            return
        self._now.setEnabled(False)
        self._later.setEnabled(False)
        self._bar.show()
        self._status.show()
        self._status.setText(_("base_update.updating"))
        self._worker = _ApplyWorker(self._summary, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, msg: str, frac: float):
        if msg:
            self._status.setText(msg)
        if frac >= 0:
            self._bar.setValue(int(frac * 100))

    def _on_done(self):
        pal = _T.palette()
        self._bar.setValue(100)
        self._status.setText(_("base_update.done"))
        self._status.setStyleSheet(f"color: {pal['TELE_GREEN']};")
        self._now.hide()
        self._later.setText(_("base_update.btn_close"))
        self._later.setEnabled(True)

    def _on_failed(self, err: str):
        pal = _T.palette()
        self._status.setText(_("base_update.failed", err=err))
        self._status.setStyleSheet(f"color: {pal['ERROR_RED']};")
        self._now.setEnabled(True)
        self._later.setEnabled(True)
