# -*- coding: utf-8 -*-
"""neoGen — fenêtre principale : Bibliothèque d'objets + Création libre (Pro).

Deux onglets :
  1. BIBLIOTHÈQUE — 54+ objets pré-construits en 8 domaines. Le formulaire de
     personnalisation (dimensions, options, texte relief/gravé, logo) est
     généré AUTOMATIQUEMENT depuis les schémas de core/neogen/catalogue.py.
  2. CRÉATION LIBRE — l'utilisateur décrit sa pièce en français : le pilote
     (extraction -> catalogue) tente d'abord le chemin rapide ; hors catalogue,
     l'atelier libre (le modèle écrit un script géométrique en bac à sable,
     boucle d'auto-correction + cookbook) prend le relais.

La pièce générée est chargée dans le viewer via `piece_ready` (même pipeline
qu'un fichier déposé). neoGen s'installe/se désinstalle dans les réglages
(modèle dédié qwen3:14b, indépendant de l'assistant Oen).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QWidget, QListWidget, QListWidgetItem, QTabWidget,
    QDoubleSpinBox, QCheckBox, QComboBox, QFormLayout, QScrollArea, QFrame,
)

from core.i18n import _, lang
from ui.styles.theme import MANAGER as _THEME

PRO_CYAN, PRO_VIOLET = "#22D3EE", "#A855F7"


def _fr_en(fr: str, en: str) -> str:
    return fr if lang() == "fr" else en


# ═══════════════════════════════ Workers ════════════════════════════════════
class _CatalogueWorker(QThread):
    """Construit un objet du catalogue (géométrie seule — pas de modèle IA)."""
    fini = Signal(object)
    erreur = Signal(str)

    def __init__(self, entree_id: str, params: dict):
        super().__init__()
        self._id, self._params = entree_id, params

    def run(self):
        try:
            from core.neogen.catalogue import generer_fichier
            self.fini.emit(generer_fichier(self._id, self._params))
        except Exception as exc:
            self.erreur.emit(str(exc))


class _LibreWorker(QThread):
    """Phrase française -> pilote (catalogue) OU atelier libre (script)."""
    question = Signal(str)
    statut = Signal(str)
    fini = Signal(object, str)
    erreur = Signal(str)

    def __init__(self, phrase: str, image: Path | None, historique: list):
        super().__init__()
        self._phrase, self._image, self._historique = phrase, image, historique

    def run(self):
        try:
            from core.neogen import pilote
            objet, params, q = pilote.interpreter(self._phrase, image=self._image,
                                                  historique=self._historique)
            if objet:                                   # chemin rapide catalogue
                resume = pilote.resume_params(objet, params)
                self.fini.emit(pilote.generer(objet, params), resume)
                return
            if q and not q.startswith("Quel objet"):    # info manquante -> question
                self.question.emit(q)
                return
            # Hors catalogue -> ATELIER LIBRE (le modèle écrit la géométrie)
            self.statut.emit(_("neogen.free_running"))
            from core.neogen.libre import generer_et_exporter
            chemin, journal = generer_et_exporter(self._phrase)
            if chemin is None:
                self.erreur.emit(_("neogen.free_failed"))
                return
            self.fini.emit(chemin, _("neogen.free_done"))
        except Exception as exc:
            self.erreur.emit(str(exc))


# ═══════════════════════════════ Fenêtre ═════════════════════════════════════
class NeoGenDialog(QDialog):
    piece_ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("neoGen")
        self.setMinimumSize(780, 560)
        self._pal = _THEME.palette()
        self._worker = None
        self._image: Path | None = None
        self._historique: list[dict] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        titre = QLabel("neoGen")
        titre.setFont(QFont("Segoe UI", 16, QFont.Bold))
        titre.setStyleSheet(f"color: {PRO_CYAN}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(titre)

        from core.neogen import installation
        if not installation.est_installe():
            self._ui_non_installe(lay)
            return

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {self._pal['INACTIVE']}; border-radius: 6px; }}
            QTabBar::tab {{ background: transparent; color: {self._pal['TEXT_LABEL']};
                            padding: 6px 18px; font-weight: bold; }}
            QTabBar::tab:selected {{ color: {PRO_CYAN};
                                     border-bottom: 2px solid {PRO_CYAN}; }}
        """)
        self._tabs.addTab(self._onglet_bibliotheque(), _("neogen.tab_library"))
        self._tabs.addTab(self._onglet_libre(), _("neogen.tab_free"))
        lay.addWidget(self._tabs, 1)

        self._statut = QLabel("")
        self._statut.setWordWrap(True)
        self._statut.setStyleSheet(
            f"color: {self._pal['TEXT_PRIMARY']}; background: transparent; font-size: 10pt;")
        lay.addWidget(self._statut)

    # ── neoGen non installé ──────────────────────────────────────────────────
    def _ui_non_installe(self, lay):
        msg = QLabel(_("neogen.not_installed"))
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {self._pal['TEXT_PRIMARY']}; font-size: 11pt;")
        lay.addWidget(msg)
        lay.addStretch()

    # ═════════════════════════ Onglet BIBLIOTHÈQUE ══════════════════════════
    def _onglet_bibliotheque(self) -> QWidget:
        from core.neogen.catalogue import par_domaine
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(10)

        style_liste = f"""
            QListWidget {{ background: {self._pal['BG_SURFACE']};
                border: 1px solid {self._pal['INACTIVE']}; border-radius: 6px;
                color: {self._pal['TEXT_PRIMARY']}; outline: none; }}
            QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
            QListWidget::item:selected {{ background: rgba(34,211,238,0.18);
                color: {PRO_CYAN}; }}
        """
        self._liste_domaines = QListWidget()
        self._liste_domaines.setStyleSheet(style_liste)
        self._liste_domaines.setFixedWidth(170)
        self._liste_objets = QListWidget()
        self._liste_objets.setStyleSheet(style_liste)
        self._liste_objets.setFixedWidth(190)

        self._donnees = par_domaine()
        for (did, dfr, den), _objs in self._donnees:
            self._liste_domaines.addItem(_fr_en(dfr, den))
        self._liste_domaines.currentRowChanged.connect(self._choisir_domaine)
        self._liste_objets.currentRowChanged.connect(self._choisir_objet)
        h.addWidget(self._liste_domaines)
        h.addWidget(self._liste_objets)

        # panneau de personnalisation (formulaire auto)
        self._form_scroll = QScrollArea()
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setFrameShape(QFrame.NoFrame)
        self._form_scroll.setStyleSheet("background: transparent;")
        h.addWidget(self._form_scroll, 1)

        self._liste_domaines.setCurrentRow(0)
        return w

    def _choisir_domaine(self, row: int):
        self._liste_objets.clear()
        if row < 0:
            return
        _dom, objs = self._donnees[row]
        for e in objs:
            self._liste_objets.addItem(QListWidgetItem(_fr_en(e["fr"], e["en"])))
        if objs:
            self._liste_objets.setCurrentRow(0)

    def _choisir_objet(self, row: int):
        drow = self._liste_domaines.currentRow()
        if row < 0 or drow < 0:
            return
        entree = self._donnees[drow][1][row]
        self._form_scroll.setWidget(self._construire_formulaire(entree))

    def _construire_formulaire(self, e: dict) -> QWidget:
        """Formulaire AUTO depuis le schéma du catalogue."""
        pal = self._pal
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 0, 6, 0)
        nom = QLabel(_fr_en(e["fr"], e["en"]))
        nom.setFont(QFont("Segoe UI", 12, QFont.Bold))
        nom.setStyleSheet(f"color: {PRO_VIOLET}; background: transparent;")
        v.addWidget(nom)

        form = QFormLayout()
        form.setSpacing(8)
        champs: dict = {}
        style_spin = f"""
            QDoubleSpinBox, QComboBox, QLineEdit {{
                background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 4px;
                padding: 3px 6px; min-width: 110px; }}
        """
        for (pid, pfr, pen, mini, maxi, defaut, pas) in e["params"]:
            sp = QDoubleSpinBox()
            sp.setRange(mini, maxi)
            sp.setValue(defaut)
            sp.setSingleStep(pas)
            sp.setDecimals(1 if pas < 1 else 0)
            sp.setSuffix(" mm" if pid not in ("cases_x", "cases_y", "rangees",
                                              "colonnes", "branches", "ondulations",
                                              "couleurs") else "")
            sp.setStyleSheet(style_spin)
            form.addRow(_fr_en(pfr, pen), sp)
            champs[pid] = sp
        for (cid, cfr, cen, options, defaut) in e["choix"]:
            cb = QComboBox()
            for (val, ofr, oen) in options:
                cb.addItem(_fr_en(ofr, oen), val)
            cb.setCurrentIndex(max(0, [o[0] for o in options].index(defaut)))
            cb.setStyleSheet(style_spin)
            form.addRow(_fr_en(cfr, cen), cb)
            champs[cid] = cb
        for (fid, ffr, fen, defaut) in e["flags"]:
            ch = QCheckBox(_fr_en(ffr, fen))
            ch.setChecked(defaut)
            ch.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            form.addRow("", ch)
            champs[fid] = ch
        if e["texte"] != "aucun":
            le = QLineEdit()
            le.setPlaceholderText(_("neogen.text_placeholder")
                                  + (" *" if e["texte"] == "requis" else ""))
            le.setStyleSheet(style_spin)
            form.addRow(_("neogen.text_label"), le)
            champs["texte"] = le
            if not any(f[0] == "grave" for f in e["flags"]):
                ch = QCheckBox(_("neogen.engraved"))
                ch.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
                form.addRow("", ch)
                champs["grave"] = ch
        if e["image"]:
            btn_img = QPushButton(_("neogen.attach_logo"))
            btn_img.setCursor(Qt.PointingHandCursor)
            lbl_img = QLabel("")
            lbl_img.setStyleSheet(f"color: {PRO_VIOLET}; background: transparent;")

            def _pick():
                chemin, _f2 = QFileDialog.getOpenFileName(
                    self, _("neogen.attach_logo"), "", "Logo (*.svg *.png *.jpg *.jpeg)")
                if chemin:
                    lbl_img.setText(Path(chemin).name)
                    champs["__image"] = chemin
            btn_img.clicked.connect(_pick)
            form.addRow(btn_img, lbl_img)
        v.addLayout(form)

        btn = QPushButton(_("neogen.generate"))
        btn.setMinimumHeight(34)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                color: #ffffff; border: none; border-radius: 6px;
                padding: 0 18px; font-weight: bold; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; }}
        """)
        btn.clicked.connect(lambda: self._generer_catalogue(e, champs, btn))
        v.addSpacing(6)
        v.addWidget(btn)
        v.addStretch()
        self._btn_cat = btn
        return w

    def _generer_catalogue(self, e: dict, champs: dict, btn: QPushButton):
        params = {}
        for k, wdg in champs.items():
            if k == "__image":
                params["image"] = wdg
            elif isinstance(wdg, QDoubleSpinBox):
                params[k] = wdg.value()
            elif isinstance(wdg, QComboBox):
                params[k] = wdg.currentData()
            elif isinstance(wdg, QCheckBox):
                params[k] = wdg.isChecked()
            elif isinstance(wdg, QLineEdit):
                params[k] = wdg.text().strip()
        if e["texte"] == "requis" and not params.get("texte"):
            self._statut.setText("⚠ " + _("neogen.text_required"))
            return
        if e["image"] and not params.get("image"):
            self._statut.setText("⚠ " + _("neogen.image_required"))
            return
        btn.setEnabled(False)
        self._statut.setText("⚙ " + _("neogen.building"))
        self._worker = _CatalogueWorker(e["id"], params)
        self._worker.fini.connect(self._sur_fini)
        self._worker.erreur.connect(self._sur_erreur)
        self._worker.start()

    # ═════════════════════════ Onglet CRÉATION LIBRE ════════════════════════
    def _onglet_libre(self) -> QWidget:
        pal = self._pal
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        sous = QLabel(_("neogen.free_subtitle"))
        sous.setWordWrap(True)
        sous.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        v.addWidget(sous)

        ligne = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(_("neogen.placeholder"))
        self._input.setMinimumHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 6px;
                padding: 4px 10px; font-size: 11pt; }}
            QLineEdit:focus {{ border-color: {PRO_CYAN}; }}
        """)
        self._input.returnPressed.connect(self._lancer_libre)
        ligne.addWidget(self._input, 1)
        self._btn_go = QPushButton(_("neogen.generate"))
        self._btn_go.setMinimumHeight(34)
        self._btn_go.setCursor(Qt.PointingHandCursor)
        self._btn_go.setStyleSheet(f"""
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                color: #ffffff; border: none; border-radius: 6px;
                padding: 0 18px; font-weight: bold; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; }}
        """)
        self._btn_go.clicked.connect(self._lancer_libre)
        ligne.addWidget(self._btn_go)
        v.addLayout(ligne)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for cle in ("neogen.ex1", "neogen.ex2", "neogen.ex3", "neogen.ex_free1",
                    "neogen.ex_free2"):
            txt = _(cle)
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 10px;
                    padding: 3px 10px; font-size: 8pt; }}
                QPushButton:hover {{ color: {PRO_CYAN}; border-color: {PRO_CYAN}; }}
            """)
            b.clicked.connect(lambda _c=False, t=txt: self._choisir_exemple(t))
            chips.addWidget(b)
        chips.addStretch()
        v.addLayout(chips)

        ligne2 = QHBoxLayout()
        self._btn_logo = QPushButton(_("neogen.attach_logo"))
        self._btn_logo.setCursor(Qt.PointingHandCursor)
        self._btn_logo.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};
                border: 1px dashed {pal['INACTIVE']}; border-radius: 6px;
                padding: 4px 12px; }}
            QPushButton:hover {{ color: {PRO_VIOLET}; border-color: {PRO_VIOLET}; }}
        """)
        self._btn_logo.clicked.connect(self._choisir_logo)
        ligne2.addWidget(self._btn_logo)
        self._lbl_logo = QLabel("")
        self._lbl_logo.setStyleSheet(f"color: {PRO_VIOLET}; background: transparent;")
        ligne2.addWidget(self._lbl_logo, 1)
        v.addLayout(ligne2)
        v.addStretch()
        return w

    def _choisir_exemple(self, txt: str):
        self._historique.clear()
        self._input.setText(txt)
        self._input.setFocus()

    def _choisir_logo(self):
        chemin, _f = QFileDialog.getOpenFileName(
            self, _("neogen.attach_logo"), "", "Logo (*.svg *.png *.jpg *.jpeg)")
        if chemin:
            self._image = Path(chemin)
            self._lbl_logo.setText(self._image.name)

    def _lancer_libre(self):
        phrase = self._input.text().strip()
        if not phrase or (self._worker and self._worker.isRunning()):
            return
        self._btn_go.setEnabled(False)
        self._statut.setText("🧠 " + _("neogen.thinking"))
        self._worker = _LibreWorker(phrase, self._image, list(self._historique))
        self._worker.question.connect(self._sur_question)
        self._worker.statut.connect(lambda s: self._statut.setText("🛠 " + s))
        self._worker.fini.connect(self._sur_fini_libre)
        self._worker.erreur.connect(self._sur_erreur)
        self._worker.start()
        self._historique.append({"role": "user", "content": phrase})
        self._input.clear()

    # ── Résultats ────────────────────────────────────────────────────────────
    def _sur_question(self, q: str):
        import json as _json
        self._historique.append({"role": "assistant",
                                 "content": _json.dumps({"question": q}, ensure_ascii=False)})
        self._btn_go.setEnabled(True)
        self._statut.setText(f"💬 {q}")
        self._input.setPlaceholderText(q)
        self._input.setFocus()

    def _sur_fini(self, chemin):
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        self._statut.setText("✓ " + _("neogen.loading_viewer"))
        self.piece_ready.emit(Path(chemin))
        self.accept()

    def _sur_fini_libre(self, chemin, resume: str):
        self._historique.clear()
        self._btn_go.setEnabled(True)
        self._statut.setText(f"✓ {resume} — {_('neogen.loading_viewer')}")
        self.piece_ready.emit(Path(chemin))
        self.accept()

    def _sur_erreur(self, msg: str):
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        if hasattr(self, "_btn_go"):
            self._btn_go.setEnabled(True)
        self._statut.setText(f"⚠ {msg}")
