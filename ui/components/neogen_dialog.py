# -*- coding: utf-8 -*-
"""neoGen — PANNEAU de la colonne de droite (Pro).

Le bouton NEOGEN bascule la colonne de droite (celle des paramètres générés)
vers ce panneau : le viewer reste visible en entier pendant qu'on crée et
qu'on itère sur une pièce. La colonne re-bascule vers les paramètres à la
demande (✕) ou automatiquement quand on génère une configuration 3MF.

Deux onglets :
  1. BIBLIOTHÈQUE — 54+ objets pré-construits ; formulaire AUTO-généré
     (dimensions, options, texte relief/gravé, logo) depuis catalogue.py.
  2. CRÉATION LIBRE — description en français ; catalogue instantané si
     l'objet est connu, sinon construction sur mesure. MODE ITÉRATIF : après
     génération, chaque phrase MODIFIE la pièce (« plus grand », « trou de
     8 mm »...) — le modèle retravaille son propre script.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTabWidget, QDoubleSpinBox, QCheckBox,
    QComboBox, QFormLayout,
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
    """Phrase française -> pilote (catalogue) OU atelier libre (script).
    Si `code_precedent` est fourni : MODIFICATION de la pièce déjà générée."""
    question = Signal(str)
    statut = Signal(str)
    fini = Signal(object, str, object)   # (Path, résumé, contexte {code, objet, params})
    erreur = Signal(str)

    def __init__(self, phrase: str, image: Path | None, historique: list,
                 code_precedent: str | None = None):
        super().__init__()
        self._phrase, self._image, self._historique = phrase, image, historique
        self._code_precedent = code_precedent

    def run(self):
        try:
            from core.neogen.libre import generer_et_exporter
            if self._code_precedent:            # MODE ITÉRATIF : on modifie
                self.statut.emit(_("neogen.modifying"))
                chemin, code, _j = generer_et_exporter(
                    self._phrase, code_precedent=self._code_precedent)
                if chemin is None:
                    self.erreur.emit(_("neogen.free_failed"))
                    return
                self.fini.emit(chemin, _("neogen.free_done"), {"code": code})
                return
            from core.neogen import pilote
            objet, params, q = pilote.interpreter(self._phrase, image=self._image,
                                                  historique=self._historique)
            if objet and objet != "__libre__":  # chemin rapide catalogue
                resume = pilote.resume_params(objet, params)
                self.fini.emit(pilote.generer(objet, params), resume,
                               {"objet": objet, "params": params})
                return
            # Question du modèle : SEULEMENT si ce n'est pas un « hors
            # catalogue » reformulé (le modèle rédige ses propres phrases).
            if (objet != "__libre__" and q
                    and not q.startswith("Quel objet")
                    and "catalogue" not in q.lower()):
                self.question.emit(q)
                return
            self.statut.emit(_("neogen.free_running"))
            chemin, code, _journal = generer_et_exporter(self._phrase)
            if chemin is None:
                self.erreur.emit(_("neogen.free_failed"))
                return
            self.fini.emit(chemin, _("neogen.free_done"), {"code": code})
        except Exception as exc:
            self.erreur.emit(str(exc))


# ═══════════════════════════════ Panneau ═════════════════════════════════════
class NeoGenPanel(QWidget):
    """Contenu neoGen pour la colonne de droite (~400 px de large)."""

    piece_ready = Signal(object)     # Path — branché sur le pipeline fichier déposé
    close_requested = Signal()       # ✕ -> revenir aux paramètres générés

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pal = _THEME.palette()
        self._worker = None
        self._image: Path | None = None
        self._historique: list[dict] = []
        self._dernier_code: str | None = None   # mode itératif (pièce sur mesure)
        self.setStyleSheet(f"background: {self._pal['BG_PANEL']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        # ── En-tête : titre + ✕ ──────────────────────────────────────────────
        entete = QHBoxLayout()
        titre = QLabel("neoGen")
        titre.setFont(QFont("Segoe UI", 13, QFont.Bold))
        titre.setStyleSheet(
            f"color: {PRO_CYAN}; background: transparent; letter-spacing: 1px;")
        entete.addWidget(titre)
        entete.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip(_("neogen.close_tip"))
        btn_close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {self._pal['TEXT_LABEL']};
                border: none; border-radius: 12px; font-size: 12px; }}
            QPushButton:hover {{ background: {self._pal['BG_ELEVATED']};
                color: {self._pal['TEXT_PRIMARY']}; }}
        """)
        btn_close.clicked.connect(self.close_requested)
        entete.addWidget(btn_close)
        lay.addLayout(entete)

        from core.neogen import installation
        if not installation.est_installe():
            msg = QLabel(_("neogen.not_installed"))
            msg.setWordWrap(True)
            msg.setStyleSheet(
                f"color: {self._pal['TEXT_PRIMARY']}; background: transparent;")
            lay.addWidget(msg)
            lay.addStretch()
            return

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{ background: transparent; color: {self._pal['TEXT_LABEL']};
                            padding: 5px 12px; font-weight: bold; }}
            QTabBar::tab:selected {{ color: {PRO_CYAN};
                                     border-bottom: 2px solid {PRO_CYAN}; }}
        """)
        self._tabs.addTab(self._onglet_libre(), _("neogen.tab_free"))
        self._tabs.addTab(self._onglet_bibliotheque(), _("neogen.tab_library"))
        lay.addWidget(self._tabs, 1)

        self._statut = QLabel("")
        self._statut.setWordWrap(True)
        self._statut.setStyleSheet(
            f"color: {self._pal['TEXT_PRIMARY']}; background: transparent; font-size: 9pt;")
        lay.addWidget(self._statut)

    # ═════════════════════════ Onglet CRÉATION LIBRE ════════════════════════
    def _onglet_libre(self) -> QWidget:
        pal = self._pal
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 8, 2, 2)
        v.setSpacing(8)

        sous = QLabel(_("neogen.free_subtitle"))
        sous.setWordWrap(True)
        sous.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent; font-size: 9pt;")
        v.addWidget(sous)

        self._input = QLineEdit()
        self._input.setPlaceholderText(_("neogen.placeholder"))
        self._input.setMinimumHeight(32)
        self._input.setStyleSheet(f"""
            QLineEdit {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 6px;
                padding: 4px 10px; font-size: 10pt; }}
            QLineEdit:focus {{ border-color: {PRO_CYAN}; }}
        """)
        self._input.returnPressed.connect(self._lancer_libre)
        v.addWidget(self._input)

        self._btn_go = QPushButton(_("neogen.generate"))
        self._btn_go.setMinimumHeight(32)
        self._btn_go.setCursor(Qt.PointingHandCursor)
        self._btn_go.setStyleSheet(f"""
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                color: #ffffff; border: none; border-radius: 6px;
                padding: 0 18px; font-weight: bold; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; }}
        """)
        self._btn_go.clicked.connect(self._lancer_libre)
        v.addWidget(self._btn_go)

        # exemples en grille 2 colonnes (colonne étroite)
        grille = QGridLayout()
        grille.setSpacing(5)
        exemples = ["neogen.ex1", "neogen.ex2", "neogen.ex3",
                    "neogen.ex_free1", "neogen.ex_free2"]
        for i, cle in enumerate(exemples):
            txt = _(cle)
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 10px;
                    padding: 4px 9px; font-size: 9pt; text-align: left; }}
                QPushButton:hover {{ color: {PRO_CYAN}; border-color: {PRO_CYAN}; }}
            """)
            b.clicked.connect(lambda _c=False, t=txt: self._choisir_exemple(t))
            grille.addWidget(b, i // 2, i % 2)
        v.addLayout(grille)

        # boutons d'action BIEN VISIBLES (fond plein + bordure colorée)
        ligne2 = QHBoxLayout()
        self._btn_logo = QPushButton(_("neogen.attach_logo"))
        self._btn_logo.setCursor(Qt.PointingHandCursor)
        self._btn_logo.setMinimumHeight(30)
        self._btn_logo.setStyleSheet(f"""
            QPushButton {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {PRO_VIOLET}; border-radius: 6px;
                padding: 5px 12px; font-size: 9pt; font-weight: bold; }}
            QPushButton:hover {{ background: rgba(168,85,247,0.18); }}
        """)
        self._btn_logo.clicked.connect(self._choisir_logo)
        ligne2.addWidget(self._btn_logo, 1)
        self._btn_reset = QPushButton(_("neogen.new_request"))
        self._btn_reset.setCursor(Qt.PointingHandCursor)
        self._btn_reset.setMinimumHeight(30)
        self._btn_reset.setStyleSheet(f"""
            QPushButton {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {PRO_CYAN}; border-radius: 6px;
                padding: 5px 12px; font-size: 9pt; font-weight: bold; }}
            QPushButton:hover {{ background: rgba(34,211,238,0.18); }}
        """)
        self._btn_reset.clicked.connect(self._nouvelle_demande)
        self._btn_reset.hide()
        ligne2.addWidget(self._btn_reset, 1)
        v.addLayout(ligne2)
        # nom du logo SOUS les boutons, élidé : un nom long ne peut plus
        # élargir la colonne et casser la mise en page
        self._lbl_logo = QLabel("")
        self._lbl_logo.setStyleSheet(
            f"color: {PRO_VIOLET}; background: transparent; font-size: 9pt;")
        v.addWidget(self._lbl_logo)
        v.addStretch()
        return w

    def _nouvelle_demande(self):
        self._historique.clear()
        self._dernier_code = None
        self._btn_reset.hide()
        self._btn_go.setText(_("neogen.generate"))
        self._statut.setText("")
        self._input.clear()
        self._input.setPlaceholderText(_("neogen.placeholder"))
        self._input.setFocus()

    def _choisir_exemple(self, txt: str):
        self._nouvelle_demande()
        self._input.setText(txt)
        self._input.setFocus()

    def _nom_logo_elide(self, nom: str) -> str:
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self._lbl_logo.font())
        return fm.elidedText(nom, Qt.ElideMiddle, 350)

    def _choisir_logo(self):
        chemin, _f = QFileDialog.getOpenFileName(
            self, _("neogen.attach_logo"), "", "Logo (*.svg *.png *.jpg *.jpeg)")
        if chemin:
            self._image = Path(chemin)
            self._lbl_logo.setText(self._nom_logo_elide(self._image.name))

    def _lancer_libre(self):
        phrase = self._input.text().strip()
        if not phrase or (self._worker and self._worker.isRunning()):
            return
        self._btn_go.setEnabled(False)
        self._statut.setText("🧠 " + _("neogen.thinking"))
        self._worker = _LibreWorker(phrase, self._image, list(self._historique),
                                    code_precedent=self._dernier_code)
        self._worker.question.connect(self._sur_question)
        self._worker.statut.connect(lambda s: self._statut.setText("🛠 " + s))
        self._worker.fini.connect(self._sur_fini_libre)
        self._worker.erreur.connect(self._sur_erreur)
        self._worker.start()
        self._historique.append({"role": "user", "content": phrase})
        self._input.clear()

    # ═════════════════════════ Onglet BIBLIOTHÈQUE ══════════════════════════
    def _onglet_bibliotheque(self) -> QWidget:
        from core.neogen.catalogue import par_domaine
        pal = self._pal
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 8, 2, 2)
        v.setSpacing(8)

        style_combo = f"""
            QComboBox {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 5px;
                padding: 4px 8px; }}
            QComboBox QAbstractItemView {{ background: {pal['BG_SURFACE']};
                color: {pal['TEXT_PRIMARY']}; selection-background-color: rgba(34,211,238,0.25); }}
        """
        self._donnees = par_domaine()
        self._combo_domaine = QComboBox()
        self._combo_domaine.setStyleSheet(style_combo)
        for (did, dfr, den), _objs in self._donnees:
            self._combo_domaine.addItem(_fr_en(dfr, den))
        self._combo_domaine.currentIndexChanged.connect(self._choisir_domaine)
        v.addWidget(self._combo_domaine)

        self._combo_objet = QComboBox()
        self._combo_objet.setStyleSheet(style_combo)
        self._combo_objet.currentIndexChanged.connect(self._choisir_objet)
        v.addWidget(self._combo_objet)

        self._form_holder = QWidget()
        self._form_holder.setStyleSheet("background: transparent;")
        self._form_lay = QVBoxLayout(self._form_holder)
        self._form_lay.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._form_holder, 1)

        self._choisir_domaine(0)
        return w

    def _choisir_domaine(self, idx: int):
        self._combo_objet.blockSignals(True)
        self._combo_objet.clear()
        if 0 <= idx < len(self._donnees):
            for e in self._donnees[idx][1]:
                self._combo_objet.addItem(_fr_en(e["fr"], e["en"]))
        self._combo_objet.blockSignals(False)
        self._choisir_objet(0)

    def _choisir_objet(self, idx: int):
        didx = self._combo_domaine.currentIndex()
        while self._form_lay.count():
            it = self._form_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if didx < 0 or idx < 0 or idx >= len(self._donnees[didx][1]):
            return
        self._form_lay.addWidget(
            self._construire_formulaire(self._donnees[didx][1][idx]))

    def _construire_formulaire(self, e: dict) -> QWidget:
        pal = self._pal
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 2, 0)

        form = QFormLayout()
        form.setSpacing(6)
        champs: dict = {}
        # flèches de spinbox EXPLICITES (largeur garantie : sans sous-contrôle,
        # certaines sections les rendaient trop étroites pour être cliquées)
        # + popup de combo stylée (sinon illisible en thème clair)
        style_champ = f"""
            QDoubleSpinBox, QComboBox, QLineEdit {{
                background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 4px;
                padding: 3px 6px; min-width: 90px; }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 18px; background: {pal['BG_ELEVATED']};
                border-left: 1px solid {pal['INACTIVE']}; }}
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
                background: rgba(34,211,238,0.25); }}
            QComboBox QAbstractItemView {{
                background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                selection-background-color: rgba(34,211,238,0.25);
                selection-color: {pal['TEXT_PRIMARY']}; }}
        """

        def _lbl(txt: str) -> QLabel:
            """Label de formulaire à couleur EXPLICITE (l'implicite héritait du
            mauvais contraste en thème clair : illisible)."""
            l = QLabel(txt)
            l.setStyleSheet(
                f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            return l
        for (pid, pfr, pen, mini, maxi, defaut, pas) in e["params"]:
            sp = QDoubleSpinBox()
            sp.setRange(mini, maxi)
            sp.setValue(defaut)
            sp.setSingleStep(pas)
            sp.setDecimals(1 if pas < 1 else 0)
            sp.setSuffix(" mm" if pid not in ("cases_x", "cases_y", "rangees",
                                              "colonnes", "branches", "ondulations",
                                              "couleurs") else "")
            sp.setStyleSheet(style_champ)
            form.addRow(_lbl(_fr_en(pfr, pen)), sp)
            champs[pid] = sp
        for (cid, cfr, cen, options, defaut) in e["choix"]:
            cb = QComboBox()
            for (val, ofr, oen) in options:
                cb.addItem(_fr_en(ofr, oen), val)
            cb.setCurrentIndex(max(0, [o[0] for o in options].index(defaut)))
            cb.setStyleSheet(style_champ)
            form.addRow(_lbl(_fr_en(cfr, cen)), cb)
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
            le.setStyleSheet(style_champ)
            form.addRow(_lbl(_("neogen.text_label")), le)
            champs["texte"] = le
            cb_pol = QComboBox()
            cb_pol.addItem(_("neogen.font_default"), None)
            try:
                from core.neogen.catalogue import polices_disponibles
                for fam in polices_disponibles():
                    cb_pol.addItem(fam, fam)
            except Exception:
                pass
            cb_pol.setStyleSheet(style_champ)
            form.addRow(_lbl(_("neogen.font_label")), cb_pol)
            champs["police"] = cb_pol
            if not any(f[0] == "grave" for f in e["flags"]):
                ch = QCheckBox(_("neogen.engraved"))
                ch.setStyleSheet(
                    f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
                form.addRow("", ch)
                champs["grave"] = ch
        if e["image"]:
            btn_img = QPushButton(_("neogen.attach_logo"))
            btn_img.setCursor(Qt.PointingHandCursor)
            lbl_img = QLabel("")
            lbl_img.setStyleSheet(f"color: {PRO_VIOLET}; background: transparent;")

            def _pick():
                chemin, _f2 = QFileDialog.getOpenFileName(
                    self, _("neogen.attach_logo"), "",
                    "Logo (*.svg *.png *.jpg *.jpeg)")
                if chemin:
                    lbl_img.setText(Path(chemin).name)
                    champs["__image"] = chemin
            btn_img.clicked.connect(_pick)
            form.addRow(btn_img, lbl_img)
        v.addLayout(form)

        btn = QPushButton(_("neogen.generate"))
        btn.setMinimumHeight(32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                color: #ffffff; border: none; border-radius: 6px;
                padding: 0 18px; font-weight: bold; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; }}
        """)
        btn.clicked.connect(lambda: self._generer_catalogue(e, champs, btn))
        v.addSpacing(4)
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

    # ── Résultats ────────────────────────────────────────────────────────────
    def _sur_question(self, q: str):
        import json as _json
        self._historique.append({"role": "assistant",
                                 "content": _json.dumps({"question": q},
                                                        ensure_ascii=False)})
        self._btn_go.setEnabled(True)
        self._statut.setText(f"💬 {q}")
        self._input.setPlaceholderText(q)
        self._input.setFocus()

    def _sur_fini(self, chemin):
        """Objet Bibliothèque généré : le panneau reste — on ajuste, on regénère."""
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        self._statut.setText("✓ " + _("neogen.loaded_adjust_form"))
        self.piece_ready.emit(Path(chemin))

    def _sur_fini_libre(self, chemin, resume: str, contexte: dict):
        """Pièce générée/modifiée : MODE ITÉRATIF — les phrases suivantes
        modifient la pièce."""
        import json as _json
        self._btn_go.setEnabled(True)
        code = (contexte or {}).get("code")
        if code:
            self._dernier_code = code
        elif (contexte or {}).get("objet"):
            self._dernier_code = None
            self._historique.append({"role": "assistant", "content": _json.dumps(
                {"objet": contexte["objet"],
                 **{k: v for k, v in contexte["params"].items() if k != "image"}},
                ensure_ascii=False)})
        self._btn_reset.show()
        self._btn_go.setText(_("neogen.modify_btn"))   # le bouton dit ce qu'il fait
        self._statut.setText(f"✓ {resume} — {_('neogen.loaded_iterate')}")
        self._input.setPlaceholderText(_("neogen.modify_placeholder"))
        self.piece_ready.emit(Path(chemin))

    def _sur_erreur(self, msg: str):
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        if hasattr(self, "_btn_go"):
            self._btn_go.setEnabled(True)
        self._statut.setText(f"⚠ {msg}")

    # ── Thème : le panneau capture sa palette à la construction. Au changement
    # de thème, main_window le RECONSTRUIT et transplante cet état (la pièce en
    # cours de modification et la conversation survivent au changement).
    def exporter_etat(self) -> dict:
        return {
            "historique": list(self._historique),
            "dernier_code": self._dernier_code,
            "image": self._image,
            "statut": self._statut.text() if hasattr(self, "_statut") else "",
            "onglet": self._tabs.currentIndex() if hasattr(self, "_tabs") else 0,
        }

    def importer_etat(self, etat: dict) -> None:
        self._historique = list(etat.get("historique") or [])
        self._dernier_code = etat.get("dernier_code")
        self._image = etat.get("image")
        if hasattr(self, "_statut") and etat.get("statut"):
            self._statut.setText(etat["statut"])
        if hasattr(self, "_tabs"):
            self._tabs.setCurrentIndex(int(etat.get("onglet", 0)))
        if self._image and hasattr(self, "_lbl_logo"):
            self._lbl_logo.setText(self._nom_logo_elide(Path(self._image).name))
        if self._dernier_code and hasattr(self, "_btn_reset"):
            self._btn_reset.show()
            self._btn_go.setText(_("neogen.modify_btn"))
            self._input.setPlaceholderText(_("neogen.modify_placeholder"))
