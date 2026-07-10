# -*- coding: utf-8 -*-
"""neoGen — fenêtre « Décris ta pièce, elle apparaît dans le viewer » (Pro).

L'utilisateur écrit une phrase en français ; Oen (modèle local, prompt dédié)
extrait les paramètres ; le code les valide (bornes strictes) ; le générateur
produit la pièce ; elle est chargée dans le viewer principal via le même
pipeline qu'un fichier déposé (signal `piece_ready`).

Oen ne calcule JAMAIS la géométrie : au pire il comprend mal une dimension
(visible immédiatement, corrigeable en une phrase), jamais une pièce cassée.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QWidget, QSizePolicy,
)

from core.i18n import _
from ui.styles.theme import MANAGER as _THEME

PRO_CYAN, PRO_VIOLET = "#22D3EE", "#A855F7"


class _GenWorker(QThread):
    """Interprétation (Oen) + génération (code) hors du thread UI."""
    question = Signal(str)          # Oen a besoin d'une précision
    fini = Signal(object, str)      # (Path de la pièce, résumé lisible)
    erreur = Signal(str)

    def __init__(self, phrase: str, image: Path | None):
        super().__init__()
        self._phrase = phrase
        self._image = image

    def run(self):
        try:
            from core.neogen import pilote
            objet, params, q = pilote.interpreter(self._phrase, image=self._image)
            if q:
                self.question.emit(q)
                return
            resume = pilote.resume_params(objet, params)
            chemin = pilote.generer(objet, params)
            self.fini.emit(chemin, resume)
        except Exception as exc:  # réseau/Ollama/génération — jamais de crash UI
            self.erreur.emit(str(exc))


class NeoGenDialog(QDialog):
    """Fenêtre neoGen : phrase -> Oen -> pièce dans le viewer."""

    piece_ready = Signal(object)    # Path — connecté au pipeline de chargement

    _EXEMPLES = [
        "neogen.ex1", "neogen.ex2", "neogen.ex3", "neogen.ex4", "neogen.ex5",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("neoGen")
        self.setMinimumWidth(560)
        self._image: Path | None = None
        self._worker: _GenWorker | None = None
        pal = _THEME.palette()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        titre = QLabel("neoGen")
        titre.setFont(QFont("Segoe UI", 16, QFont.Bold))
        titre.setStyleSheet(
            f"color: {PRO_CYAN}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(titre)

        sous = QLabel(_("neogen.subtitle"))
        sous.setWordWrap(True)
        sous.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        lay.addWidget(sous)

        # ── Saisie ────────────────────────────────────────────────────────────
        ligne = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(_("neogen.placeholder"))
        self._input.setMinimumHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 6px;
                padding: 4px 10px; font-size: 11pt;
            }}
            QLineEdit:focus {{ border-color: {PRO_CYAN}; }}
        """)
        self._input.returnPressed.connect(self._lancer)
        ligne.addWidget(self._input, 1)

        self._btn_go = QPushButton(_("neogen.generate"))
        self._btn_go.setMinimumHeight(34)
        self._btn_go.setCursor(Qt.PointingHandCursor)
        self._btn_go.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                color: #ffffff; border: none; border-radius: 6px;
                padding: 0 18px; font-weight: bold;
            }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; }}
        """)
        self._btn_go.clicked.connect(self._lancer)
        ligne.addWidget(self._btn_go)
        lay.addLayout(ligne)

        # ── Exemples cliquables + logo ───────────────────────────────────────
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for cle in self._EXEMPLES:
            txt = _(cle)
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {pal['TEXT_LABEL']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 10px;
                    padding: 3px 10px; font-size: 8pt;
                }}
                QPushButton:hover {{ color: {PRO_CYAN}; border-color: {PRO_CYAN}; }}
            """)
            b.clicked.connect(lambda _c=False, t=txt: self._input.setText(t))
            chips.addWidget(b)
        chips.addStretch()
        lay.addLayout(chips)

        ligne2 = QHBoxLayout()
        self._btn_logo = QPushButton(_("neogen.attach_logo"))
        self._btn_logo.setCursor(Qt.PointingHandCursor)
        self._btn_logo.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_LABEL']};
                border: 1px dashed {pal['INACTIVE']}; border-radius: 6px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ color: {PRO_VIOLET}; border-color: {PRO_VIOLET}; }}
        """)
        self._btn_logo.clicked.connect(self._choisir_logo)
        ligne2.addWidget(self._btn_logo)
        self._lbl_logo = QLabel("")
        self._lbl_logo.setStyleSheet(f"color: {PRO_VIOLET}; background: transparent;")
        ligne2.addWidget(self._lbl_logo, 1)
        lay.addLayout(ligne2)

        # ── Statut / dialogue avec Oen ───────────────────────────────────────
        self._statut = QLabel("")
        self._statut.setWordWrap(True)
        self._statut.setMinimumHeight(40)
        self._statut.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; font-size: 10pt;")
        lay.addWidget(self._statut)

    # ── Interactions ─────────────────────────────────────────────────────────
    def _choisir_logo(self):
        chemin, _f = QFileDialog.getOpenFileName(
            self, _("neogen.attach_logo"), "",
            "Logo (*.svg *.png *.jpg *.jpeg)")
        if chemin:
            self._image = Path(chemin)
            self._lbl_logo.setText(self._image.name)
            if not self._input.text().strip():
                self._input.setText(_("neogen.ex_logo"))

    def _lancer(self):
        phrase = self._input.text().strip()
        if not phrase or (self._worker and self._worker.isRunning()):
            return
        from core.assistant.engine import AssistantEngine
        if not AssistantEngine.available():
            self._statut.setText("⚠ " + _("neogen.need_oen"))
            return
        self._btn_go.setEnabled(False)
        self._statut.setText("🧠 " + _("neogen.thinking"))
        self._worker = _GenWorker(phrase, self._image)
        self._worker.question.connect(self._sur_question)
        self._worker.fini.connect(self._sur_fini)
        self._worker.erreur.connect(self._sur_erreur)
        self._worker.start()

    def _sur_question(self, q: str):
        self._btn_go.setEnabled(True)
        self._statut.setText(f"💬 {q}")
        self._input.setFocus()

    def _sur_fini(self, chemin, resume: str):
        self._btn_go.setEnabled(True)
        self._statut.setText(f"✓ {resume} — {_('neogen.loading_viewer')}")
        self.piece_ready.emit(Path(chemin))
        self.accept()   # la pièce se charge dans le viewer principal

    def _sur_erreur(self, msg: str):
        self._btn_go.setEnabled(True)
        self._statut.setText(f"⚠ {_('neogen.error')} : {msg}")
