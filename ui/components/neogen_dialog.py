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
from ui.styles.theme import MANAGER as _THEME, spinbox_qss as _spinbox_qss

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


class _RechercheWorker(QThread):
    """Demande en langage naturel -> OBJET de la bibliothèque le plus proche +
    paramètres. Ne génère JAMAIS de code : l'intelligence est dans la
    bibliothèque validée. Deux niveaux, du plus riche au plus fiable :
      1. le modèle neoGen (s'il est installé) extrait objet + dimensions/texte ;
      2. repli SANS modèle : recherche par mots-clés (instantané, ne peut pas
         « ne rien donner de correct »)."""
    trouve = Signal(str, object)         # (entry_id, params)
    aucun = Signal()
    erreur = Signal(str)

    def __init__(self, phrase: str, image: Path | None):
        super().__init__()
        self._phrase, self._image = phrase, image

    def run(self):
        try:
            from core.neogen import catalogue as C
            entry_id, params = None, {}
            # 1) extraction par le modèle (dimensions, texte) — best effort
            try:
                from core.neogen import pilote
                objet, p, _q = pilote.interpreter(self._phrase, image=self._image)
                if objet and objet != "__libre__" and objet in C.PAR_ID:
                    entry_id, params = objet, (p or {})
            except Exception:
                pass
            # 2) repli fiable : recherche par mots-clés dans la bibliothèque
            if entry_id is None:
                entry_id = C.rechercher(self._phrase)
            if entry_id is None:
                self.aucun.emit()
                return
            if self._image and C.PAR_ID[entry_id].get("image"):
                params = dict(params); params["image"] = str(self._image)
            self.trouve.emit(entry_id, params)
        except Exception as exc:
            self.erreur.emit(str(exc))


# ═══════════════════════════════ Panneau ═════════════════════════════════════
class NeoGenPanel(QWidget):
    """Contenu neoGen pour la colonne de droite (~400 px de large)."""

    piece_ready = Signal(object)     # Path — branché sur le pipeline fichier déposé
    close_requested = Signal()       # ✕ -> revenir aux paramètres générés
    ouvrir_carte = Signal()          # « Carte de visite » sélectionnée dans Perso

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pal = _THEME.palette()
        self._worker = None
        self._image: Path | None = None
        self.setStyleSheet(f"background: {self._pal['BG_PANEL']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        # ── En-tête : titre + ✕ ──────────────────────────────────────────────
        entete = QHBoxLayout()
        titre = QLabel("neoGen")
        titre.setObjectName("neogenTitre")
        titre.setFont(QFont("Segoe UI", 13, QFont.Bold))
        titre.setStyleSheet(
            f"color: {self._pal['ACCENT_BRIGHT']}; background: transparent; letter-spacing: 1px;")
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
            QTabBar::tab:selected {{ color: {self._pal['ACCENT_BRIGHT']};
                                     border-bottom: 2px solid {self._pal['ACCENT_BRIGHT']}; }}
        """)
        self._tabs.addTab(self._onglet_bibliotheque(), _("neogen.tab_library"))
        self._tabs.insertTab(0, self._onglet_libre(), _("neogen.tab_search"))
        self._tabs.setCurrentIndex(0)
        lay.addWidget(self._tabs, 1)

        self._statut = QLabel("")
        self._statut.setWordWrap(True)
        self._statut.setStyleSheet(
            f"color: {self._pal['TEXT_PRIMARY']}; background: transparent; font-size: 9pt;")
        lay.addWidget(self._statut)

    def refresh_theme(self):
        """Ré-applique le thème (titre + onglets) : plus de cyan sur les polices,
        accent standard du thème comme les autres modules."""
        self._pal = _THEME.palette()
        pal = self._pal
        for w in self.findChildren(QLabel):
            if w.objectName() == "neogenTitre":
                w.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']}; background: transparent;"
                                f" letter-spacing: 1px;")
        if hasattr(self, "_tabs"):
            self._tabs.setStyleSheet(f"""
                QTabWidget::pane {{ border: none; }}
                QTabBar::tab {{ background: transparent; color: {pal['TEXT_LABEL']};
                                padding: 5px 12px; font-weight: bold; }}
                QTabBar::tab:selected {{ color: {pal['ACCENT_BRIGHT']};
                                         border-bottom: 2px solid {pal['ACCENT_BRIGHT']}; }}
            """)

    # ═════════════════════════ Onglet RECHERCHER ════════════════════════════
    def _onglet_libre(self) -> QWidget:
        pal = self._pal
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 8, 2, 2)
        v.setSpacing(8)

        sous = QLabel(_("neogen.search_subtitle"))
        sous.setWordWrap(True)
        sous.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent; font-size: 9pt;")
        v.addWidget(sous)

        self._input = QLineEdit()
        self._input.setPlaceholderText(_("neogen.search_placeholder"))
        self._input.setMinimumHeight(32)
        self._input.setStyleSheet(f"""
            QLineEdit {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 6px;
                padding: 4px 10px; font-size: 10pt; }}
            QLineEdit:focus {{ border-color: {PRO_CYAN}; }}
        """)
        self._input.returnPressed.connect(self._lancer_recherche)
        v.addWidget(self._input)

        self._btn_go = QPushButton(_("neogen.search_btn"))
        self._btn_go.setMinimumHeight(32)
        self._btn_go.setCursor(Qt.PointingHandCursor)
        self._btn_go.setStyleSheet(f"""
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                color: #ffffff; border: none; border-radius: 6px;
                padding: 0 18px; font-weight: bold; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; }}
        """)
        self._btn_go.clicked.connect(self._lancer_recherche)
        v.addWidget(self._btn_go)

        # exemples : chacun correspond à un objet de la bibliothèque
        grille = QGridLayout()
        grille.setSpacing(5)
        # 4 exemples (grille 2×2), chacun tombe sur un objet réel de la biblio
        exemples = ["neogen.ex1", "neogen.ex2", "neogen.ex3", "neogen.ex_free1"]
        for i, cle in enumerate(exemples):
            txt = _(cle)
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 10px;
                    padding: 4px 9px; font-size: 9pt; text-align: left; }}
                QPushButton:hover {{ color: {pal['ACCENT_BRIGHT']}; border-color: {pal['ACCENT_BRIGHT']}; }}
            """)
            b.clicked.connect(lambda _c=False, t=txt: self._choisir_exemple(t))
            grille.addWidget(b, i // 2, i % 2)
        v.addLayout(grille)

        # (l'ajout d'image se fait dans Bibliothèque > Personnalisation, sur les
        # objets Logo/Photo qui en ont besoin — pas ici)
        v.addStretch()
        return w

    def _choisir_exemple(self, txt: str):
        self._input.setText(txt)
        self._input.setFocus()
        self._lancer_recherche()

    def _lancer_recherche(self):
        phrase = self._input.text().strip()
        if not phrase or (self._worker and self._worker.isRunning()):
            return
        self._btn_go.setEnabled(False)
        self._statut.setText("🔎 " + _("neogen.searching"))
        self._worker = _RechercheWorker(phrase, self._image)
        self._worker.trouve.connect(self._sur_trouve)
        self._worker.aucun.connect(self._sur_aucun)
        self._worker.erreur.connect(self._sur_erreur)
        self._worker.start()

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
        # injecte une « Carte de visite » en tête de Personnalisation (ouvre
        # l'éditeur dédié) — pseudo-entrée id=carte_visite traitée à part
        _carte = {"id": "carte_visite", "fr": "Carte de visite",
                  "en": "Business card", "domaine": "perso", "texte": "aucun",
                  "image": False, "params": [], "flags": [], "choix": [],
                  "construire": None}
        for _dom, _ents in self._donnees:
            if _dom[0] == "perso":
                _ents.insert(0, _carte)
                break
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

        # cas spécial : la carte de visite a son PROPRE éditeur (multi-éléments,
        # couleurs) -> un bouton l'ouvre dans la colonne de droite
        if e["id"] == "carte_visite":
            info = QLabel(_("carte.pitch"))
            info.setWordWrap(True)
            info.setStyleSheet(
                f"color: {pal['TEXT_LABEL']}; background: transparent; font-size: 9pt;")
            v.addWidget(info)
            btn = QPushButton(_("carte.open_editor"))
            btn.setMinimumHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET});
                    color: #ffffff; border: none; border-radius: 6px;
                    padding: 0 14px; font-weight: bold; }}
            """)
            btn.clicked.connect(self.ouvrir_carte)
            v.addSpacing(4)
            v.addWidget(btn)
            v.addStretch()
            return w

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
            QComboBox QAbstractItemView {{
                background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                selection-background-color: rgba(34,211,238,0.25);
                selection-color: {pal['TEXT_PRIMARY']}; }}
        """ + _spinbox_qss(pal, "rgba(34,211,238,0.35)")

        def _lbl(txt: str) -> QLabel:
            """Label de formulaire à couleur EXPLICITE (l'implicite héritait du
            mauvais contraste en thème clair : illisible)."""
            l = QLabel(txt)
            l.setStyleSheet(
                f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            return l

        # cases à cocher avec un INDICATEUR dessiné : sans lui, on ne voyait
        # que la coche — impossible de deviner que c'était cliquable/décochable
        style_check = f"""
            QCheckBox {{ color: {pal['TEXT_PRIMARY']}; background: transparent;
                         spacing: 7px; }}
            QCheckBox::indicator {{ width: 15px; height: 15px;
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
                background: {pal['BG_SURFACE']}; }}
            QCheckBox::indicator:hover {{ border-color: {PRO_CYAN}; }}
            QCheckBox::indicator:checked {{ background: {PRO_CYAN};
                border-color: {PRO_CYAN}; }}
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
            ch.setCursor(Qt.PointingHandCursor)
            ch.setStyleSheet(style_check)
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
            sp_esp = QDoubleSpinBox()
            sp_esp.setRange(0.0, 10.0)
            sp_esp.setValue(0.0)
            sp_esp.setSingleStep(0.5)
            sp_esp.setDecimals(1)
            sp_esp.setSuffix(" mm")
            sp_esp.setStyleSheet(style_champ)
            form.addRow(_lbl(_("neogen.spacing_label")), sp_esp)
            champs["espacement"] = sp_esp
            if not any(f[0] == "grave" for f in e["flags"]):
                ch = QCheckBox(_("neogen.engraved"))
                ch.setCursor(Qt.PointingHandCursor)
                ch.setStyleSheet(style_check)
                form.addRow("", ch)
                champs["grave"] = ch
        if e["image"]:
            # bouton PLEINE LARGEUR, même style visible que « Joindre un
            # logo » de la Création libre (avant : QPushButton sans style,
            # on ne voyait pas que c'était cliquable)
            cle_btn = ("neogen.attach_photo" if e["id"] == "photo_relief"
                       else "neogen.attach_logo")
            btn_img = QPushButton(_(cle_btn))
            btn_img.setCursor(Qt.PointingHandCursor)
            btn_img.setMinimumHeight(30)
            btn_img.setStyleSheet(f"""
                QPushButton {{ background: {pal['BG_SURFACE']};
                    color: {pal['TEXT_PRIMARY']};
                    border: 1px solid {PRO_VIOLET}; border-radius: 6px;
                    padding: 5px 12px; font-size: 9pt; font-weight: bold; }}
                QPushButton:hover {{ background: rgba(168,85,247,0.18); }}
            """)
            lbl_img = QLabel("")
            lbl_img.setStyleSheet(f"color: {PRO_VIOLET}; background: transparent;"
                                  " font-size: 9pt;")

            def _pick():
                from PySide6.QtGui import QFontMetrics
                chemin, _f2 = QFileDialog.getOpenFileName(
                    self, _(cle_btn), "",
                    "Image (*.svg *.png *.jpg *.jpeg)")
                if chemin:
                    fm = QFontMetrics(lbl_img.font())
                    lbl_img.setText(fm.elidedText(Path(chemin).name,
                                                  Qt.ElideMiddle, 330))
                    champs["__image"] = chemin
            btn_img.clicked.connect(_pick)
            v.addLayout(form)
            v.addSpacing(2)
            v.addWidget(btn_img)
            v.addWidget(lbl_img)
            form = QFormLayout()          # (rien après, mais reste cohérent)
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
        # exposés pour la recherche (pré-remplissage + génération auto)
        self._champs_courant = champs
        self._entree_courante = e
        return w

    def _ouvrir_dans_biblio(self, entry_id: str, params: dict) -> None:
        """Sélectionne l'objet `entry_id` dans la Bibliothèque, PRÉ-REMPLIT son
        formulaire avec `params`, bascule sur l'onglet et génère une fois — la
        recherche en langage naturel aboutit à un objet validé, ajustable."""
        di = oi = None
        for i, (_dom, entrees) in enumerate(self._donnees):
            for j, e in enumerate(entrees):
                if e["id"] == entry_id:
                    di, oi = i, j
                    break
            if di is not None:
                break
        if di is None:
            return
        self._combo_domaine.blockSignals(True)
        self._combo_domaine.setCurrentIndex(di)
        self._combo_domaine.blockSignals(False)
        self._choisir_domaine(di)
        self._combo_objet.blockSignals(True)
        self._combo_objet.setCurrentIndex(oi)
        self._combo_objet.blockSignals(False)
        self._choisir_objet(oi)
        # pré-remplissage du formulaire fraîchement construit
        champs = getattr(self, "_champs_courant", {})
        for k, val in (params or {}).items():
            if k == "image":
                champs["__image"] = val
                continue
            wdg = champs.get(k)
            if wdg is None:
                continue
            if isinstance(wdg, QDoubleSpinBox):
                try:
                    wdg.setValue(float(val))
                except (TypeError, ValueError):
                    pass
            elif isinstance(wdg, QComboBox):
                idx = wdg.findData(val)
                if idx >= 0:
                    wdg.setCurrentIndex(idx)
            elif isinstance(wdg, QCheckBox):
                wdg.setChecked(bool(val))
            elif isinstance(wdg, QLineEdit):
                wdg.setText(str(val))
        self._tabs.setCurrentIndex(1)          # bascule sur la Bibliothèque
        # génération immédiate si tout le nécessaire est là (sinon on laisse
        # l'utilisateur compléter — ex. texte requis, image manquante)
        e = self._entree_courante
        pret = not (e["texte"] == "requis" and not champs.get("texte")
                    and not str((params or {}).get("texte", "")).strip())
        pret = pret and not (e["image"] and not champs.get("__image"))
        if pret:
            self._generer_catalogue(e, champs, self._btn_cat)

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
    def _sur_trouve(self, entry_id: str, params: object):
        """Recherche aboutie : ouvre l'objet de bibliothèque le plus proche,
        paramètres pré-remplis, et le génère."""
        self._btn_go.setEnabled(True)
        from core.neogen.catalogue import PAR_ID
        e = PAR_ID.get(entry_id, {})
        nom = _fr_en(e.get("fr", entry_id), e.get("en", entry_id))
        self._statut.setText("✓ " + _("neogen.search_found", nom=nom))
        self._ouvrir_dans_biblio(entry_id, params or {})

    def _sur_aucun(self):
        self._btn_go.setEnabled(True)
        self._statut.setText("💬 " + _("neogen.search_none"))
        self._tabs.setCurrentIndex(1)          # invite à parcourir la biblio

    def _sur_fini(self, chemin):
        """Objet Bibliothèque généré : le panneau reste — on ajuste, on regénère."""
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        self._statut.setText("✓ " + _("neogen.loaded_adjust_form"))
        self.piece_ready.emit(Path(chemin))

    def _sur_erreur(self, msg: str):
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        if hasattr(self, "_btn_go"):
            self._btn_go.setEnabled(True)
        self._statut.setText(f"⚠ {msg}")

    # ── Thème : le panneau capture sa palette à la construction. Au changement
    # de thème, main_window le RECONSTRUIT et transplante cet état (l'image
    # jointe et l'onglet actif survivent au changement).
    def exporter_etat(self) -> dict:
        return {
            "image": self._image,
            "statut": self._statut.text() if hasattr(self, "_statut") else "",
            "onglet": self._tabs.currentIndex() if hasattr(self, "_tabs") else 0,
        }

    def importer_etat(self, etat: dict) -> None:
        self._image = etat.get("image")
        if hasattr(self, "_statut") and etat.get("statut"):
            self._statut.setText(etat["statut"])
        if hasattr(self, "_tabs"):
            self._tabs.setCurrentIndex(int(etat.get("onglet", 0)))
