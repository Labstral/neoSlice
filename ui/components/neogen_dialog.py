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
    QComboBox, QFormLayout, QScrollArea, QFrame,
)

from core.i18n import _, lang
from ui.styles.theme import MANAGER as _THEME, spinbox_qss as _spinbox_qss

PRO_CYAN, PRO_VIOLET = "#22D3EE", "#A855F7"


def _fr_en(fr: str, en: str) -> str:
    return fr if lang() == "fr" else en


class _ColorButton(QPushButton):
    """Pastille de couleur : affiche le hex sur fond coloré, ouvre un sélecteur au
    clic et mémorise le choix. Lisible en thème clair ET sombre (le texte passe en
    noir/blanc selon la luminance de la couleur, jamais illisible)."""

    changed = Signal()          # couleur modifiée → rafraîchir l'aperçu

    def __init__(self, hex_defaut: str, parent=None):
        super().__init__(parent)
        self.hex = (hex_defaut or "#CCCCCC").upper()
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self):
        try:
            r, g, b = (int(self.hex[1:3], 16), int(self.hex[3:5], 16),
                       int(self.hex[5:7], 16))
            lum = 0.299 * r + 0.587 * g + 0.114 * b
        except Exception:
            lum = 200
        fg = "#000000" if lum > 140 else "#FFFFFF"
        self.setText(self.hex)
        self.setStyleSheet(
            f"QPushButton {{ background: {self.hex}; color: {fg};"
            " border: 1px solid rgba(128,128,128,0.7); border-radius: 6px;"
            " padding: 3px 10px; font-size: 8pt; font-weight: bold; }}")

    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        # Dialogue NON natif + feuille de style au thème neoSlice : sinon il s'affiche
        # avec la palette Qt (sombre) et devient illisible en thème clair.
        dlg = QColorDialog(QColor(self.hex), self)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setWindowTitle(_("neogen.pick_color"))
        pal = _THEME.palette()
        dlg.setStyleSheet(f"""
            QColorDialog, QColorDialog QWidget {{ background: {pal['BG_PANEL']};
                color: {pal['TEXT_PRIMARY']}; }}
            QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }}
            QLineEdit, QSpinBox {{ background: {pal['BG_SURFACE']};
                color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']};
                border-radius: 3px; padding: 2px 4px; }}
            QPushButton {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 4px;
                padding: 4px 12px; }}
            QPushButton:hover {{ border-color: {PRO_CYAN}; }}
        """)
        if dlg.exec() and dlg.currentColor().isValid():
            self.hex = dlg.currentColor().name().upper()
            self._refresh()
            self.changed.emit()


# ═══════════════════════════════ Workers ════════════════════════════════════
class _CatalogueWorker(QThread):
    """Construit un objet du catalogue (géométrie seule — pas de modèle IA).
    Objet BICOLORE (Scene à corps colorés) → `fini_multi` (route multicouleur,
    2 slots à l'export) ; sinon fichier normal via `fini`."""
    fini = Signal(object)                 # Path (objet mono-couleur)
    fini_multi = Signal(object, str)      # (scene, entree_id) — objet bicolore
    erreur = Signal(str)

    def __init__(self, entree_id: str, params: dict,
                 volume_plateau: tuple | None = None):
        super().__init__()
        self._id, self._params = entree_id, params
        self._volume = volume_plateau     # (x, y, z) mm de l'imprimante cible

    def run(self):
        try:
            from core.neogen.catalogue import (construire, est_multicouleur,
                                               generer_fichier, piece_hors_plateau)
            import trimesh as _tm
            piece = construire(self._id, self._params)
            # Garde-fou plateau : refuser une pièce plus grande que le plateau de
            # l'imprimante CIBLE (bornes élargies du catalogue → jusqu'à 1200 mm
            # possibles sinon, décidé avec Emmanuel après audit).
            if self._volume:
                _depasse = piece_hors_plateau(piece, self._volume)
                if _depasse:
                    self.erreur.emit(_("neogen.hors_plateau", dims=_depasse))
                    return
            # Scène MULTI-PLATEAUX (corps taggés plateau()) → route SCÈNE aussi (comme
            # bicolore) : garde la scène taggée en mémoire (_neogen_scene) pour
            # l'export multi-plateaux (les tags seraient perdus par un export fichier).
            _multiplate = False
            if isinstance(piece, _tm.Scene):
                _multiplate = any(
                    int((getattr(g, "metadata", {}) or {}).get("neoslice_plate", 0) or 0) > 0
                    for g in piece.geometry.values())
            if est_multicouleur(piece) or _multiplate:
                self.fini_multi.emit(piece, self._id)
            else:
                self.fini.emit(generer_fichier(self._id, self._params, piece=piece))
        except Exception as exc:
            self.erreur.emit(str(exc))


class _ApercuWorker(QThread):
    """Construit un objet du catalogue pour l'APERÇU en direct (sélection / réglage).
    Best-effort : en cas d'erreur (texte requis manquant…) on n'émet rien."""
    pret = Signal(object)

    def __init__(self, entree_id: str, params: dict):
        super().__init__()
        self._id, self._params = entree_id, params

    def run(self):
        try:
            from core.neogen.catalogue import construire
            self.pret.emit(construire(self._id, self._params))
        except Exception:
            pass


# NB : la recherche neoGen est désormais 100 % locale (mots-clés pondérés, cf.
# catalogue.rechercher_liste) — instantanée et fiable. Plus d'appel au modèle Oen
# (Ollama), qui rendait la recherche lente et pouvait figer jusqu'à 180 s.


# ═══════════════════════════════ Panneau ═════════════════════════════════════
class NeoGenPanel(QWidget):
    """Contenu neoGen pour la colonne de droite (~400 px de large)."""

    piece_ready = Signal(object)     # Path — branché sur le pipeline fichier déposé
    objet_multicouleur = Signal(object, str)  # (scene, entree_id) — objet bicolore
    apercu_objet = Signal(object)    # aperçu direct (piece Scene/Trimesh) à la sélection
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
            f"color: {self._pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 1px;")
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
            QTabBar::tab:selected {{ color: {self._pal['TEXT_PRIMARY']};
                                     border-bottom: 2px solid {self._pal['ACCENT_BRIGHT']}; }}
        """)
        # _ready : évite d'émettre ouvrir_carte pendant la CONSTRUCTION (avant que
        # main_window ait connecté le signal, et alors qu'on est sur l'onglet Recherche).
        self._ready = False
        # Bibliothèque en PREMIER (onglet 0, affiché par défaut), Rechercher ensuite.
        self._tabs.addTab(self._onglet_libre(), _("neogen.tab_search"))
        self._tabs.insertTab(0, self._onglet_bibliotheque(), _("neogen.tab_library"))
        self._tabs.setCurrentIndex(0)
        self._tabs.currentChanged.connect(self._on_tab_change)
        lay.addWidget(self._tabs, 1)
        self._ready = True

        self._statut = QLabel("")
        self._statut.setWordWrap(True)
        self._statut.setStyleSheet(
            f"color: {self._pal['TEXT_PRIMARY']}; background: transparent; font-size: 9pt;")
        lay.addWidget(self._statut)

        # « Proposer un objet » : les utilisateurs sont la roadmap de la
        # bibliothèque (la base se met à jour sans rebuild) — leur donner le
        # canal DEPUIS neoGen au lieu d'espérer qu'ils trouvent le formulaire.
        self._proposer = QLabel(
            f'<a href="https://neoslice-ai.com/retour" style="color: '
            f'{self._pal["ACCENT"]};">{_("neogen.suggest_object")}</a>')
        self._proposer.setOpenExternalLinks(True)
        self._proposer.setStyleSheet("background: transparent; font-size: 9pt;")
        lay.addWidget(self._proposer)

    def refresh_theme(self):
        """Ré-applique le thème SANS sortir l'utilisateur de l'objet en cours :
        titre + onglets, puis reconstruit le formulaire courant avec le nouveau
        thème en PRÉSERVANT les valeurs saisies (sinon les champs gardaient les
        couleurs de l'ancien thème → formulaire illisible/« sorti du menu »)."""
        self._pal = _THEME.palette()
        pal = self._pal
        # Fond de la colonne : posé au build (ligne 192) avec le thème d'alors —
        # il faut le RÉ-appliquer ici, sinon la colonne reste figée au thème de
        # départ pendant que les champs, eux, se mettent à jour (fond incohérent).
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        for w in self.findChildren(QLabel):
            if w.objectName() == "neogenTitre":
                w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;"
                                f" letter-spacing: 1px;")
        if hasattr(self, "_tabs"):
            self._tabs.setStyleSheet(f"""
                QTabWidget::pane {{ border: none; }}
                QTabBar::tab {{ background: transparent; color: {pal['TEXT_LABEL']};
                                padding: 5px 12px; font-weight: bold; }}
                QTabBar::tab:selected {{ color: {pal['TEXT_PRIMARY']};
                                         border-bottom: 2px solid {pal['ACCENT_BRIGHT']}; }}
            """)
        # Combos PERSISTANTS (domaine + objet) : re-stylés avec le nouveau thème
        # (ils survivent au refresh, donc gardaient sinon les couleurs de l'ancien).
        _style_combo = (
            f"QComboBox {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};"
            f" border: 1px solid {pal['INACTIVE']}; border-radius: 5px; padding: 4px 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {pal['BG_SURFACE']};"
            f" color: {pal['TEXT_PRIMARY']}; selection-background-color: rgba(34,211,238,0.25); }}")
        for _cb in (getattr(self, "_combo_domaine", None), getattr(self, "_combo_objet", None)):
            if _cb is not None:
                _cb.setStyleSheet(_style_combo)
        # Bas de panneau : statut + lien « Proposer un objet » (couleur ACCENT
        # embarquée dans le HTML du lien → à ré-émettre avec la palette à jour).
        if hasattr(self, "_statut"):
            self._statut.setStyleSheet(
                f"color: {pal['TEXT_PRIMARY']}; background: transparent; font-size: 9pt;")
        if hasattr(self, "_proposer"):
            self._proposer.setText(
                f'<a href="https://neoslice-ai.com/retour" style="color: '
                f'{pal["ACCENT"]};">{_("neogen.suggest_object")}</a>')
        self._rethemer_formulaire()

    def _rethemer_formulaire(self):
        """Reconstruit le formulaire de l'objet courant avec le thème à jour, en
        conservant l'objet sélectionné ET les valeurs déjà saisies."""
        champs = getattr(self, "_champs_courant", None)
        combo = getattr(self, "_combo_objet", None)
        if not champs or combo is None:
            return
        # 1) capturer les valeurs courantes. try/except : un widget dont l'objet C++
        # a déjà été supprimé (double refresh de thème, formulaire vidé) lève
        # RuntimeError → on l'ignore au lieu de planter.
        vals = {}
        for k, w in list(champs.items()):
            try:
                if k == "__image":
                    vals[k] = w                       # chemin (str)
                elif isinstance(w, QLineEdit):
                    vals[k] = ("text", w.text())
                elif isinstance(w, _ColorButton):
                    vals[k] = ("hex", w.hex)
                elif isinstance(w, QDoubleSpinBox):
                    vals[k] = ("val", w.value())
                elif isinstance(w, QComboBox):
                    vals[k] = ("data", w.currentData())
                elif isinstance(w, QCheckBox):
                    vals[k] = ("chk", w.isChecked())
            except RuntimeError:
                continue
        # 2) reconstruire le formulaire (utilise self._pal mis à jour)
        self._choisir_objet(combo.currentIndex())
        # 3) restaurer les valeurs
        new = getattr(self, "_champs_courant", {})
        for k, v in vals.items():
            if k == "__image":
                new["__image"] = v
                lbl = getattr(self, "_lbl_img_courant", None)
                if lbl is not None and v:
                    from pathlib import Path as _P
                    lbl.setText(_P(str(v)).name)
                continue
            w = new.get(k)
            if w is None:
                continue
            kind, val = v
            try:
                if kind == "text":
                    w.setText(val)
                elif kind == "hex":
                    w.hex = val
                    w._refresh()
                elif kind == "val":
                    w.setValue(float(val))
                elif kind == "data":
                    i = w.findData(val)
                    if i >= 0:
                        w.setCurrentIndex(i)
                elif kind == "chk":
                    w.setChecked(bool(val))
            except Exception:
                pass

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

        # Résultats : liste CLASSÉE cliquable (chaque objet ouvre son formulaire).
        # Masquée tant qu'aucune recherche n'a été lancée.
        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setFrameShape(QFrame.NoFrame)
        self._results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._results_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }")
        self._results_host = QWidget()
        self._results_host.setStyleSheet("background: transparent;")
        self._results_lay = QVBoxLayout(self._results_host)
        self._results_lay.setContentsMargins(0, 0, 0, 0)
        self._results_lay.setSpacing(5)
        self._results_lay.addStretch()
        self._results_scroll.setWidget(self._results_host)
        self._results_scroll.setVisible(False)
        v.addWidget(self._results_scroll, 1)

        # Exemples (suggestions) : masqués dès qu'une recherche renvoie des résultats.
        self._examples_box = QWidget()
        self._examples_box.setStyleSheet("background: transparent;")
        grille = QGridLayout(self._examples_box)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setSpacing(5)
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
        v.addWidget(self._examples_box)

        v.addStretch()
        return w

    def _choisir_exemple(self, txt: str):
        self._input.setText(txt)
        self._input.setFocus()
        self._lancer_recherche()

    def _lancer_recherche(self):
        """Recherche 100 % locale et instantanée : liste classée d'objets. Aucun
        thread, aucun modèle — plus jamais de gel."""
        phrase = self._input.text().strip()
        if not phrase:
            return
        from core.neogen import catalogue as C
        resultats = C.rechercher_liste(phrase, 8)
        self._afficher_resultats(resultats)

    def _afficher_resultats(self, resultats: list):
        pal = self._pal
        # vider la liste (on garde le stretch final en dernière position)
        while self._results_lay.count() > 1:
            it = self._results_lay.takeAt(0)
            wdg = it.widget()
            if wdg is not None:
                wdg.setParent(None)
                wdg.deleteLater()

        from core.neogen.catalogue import PAR_ID
        if not resultats:
            self._results_scroll.setVisible(False)
            self._examples_box.setVisible(True)
            self._statut.setText("💬 " + _("neogen.search_none"))
            return

        for i, (entry_id, _score) in enumerate(resultats):
            e = PAR_ID.get(entry_id, {})
            nom = _fr_en(e.get("fr", entry_id), e.get("en", entry_id))
            btn = QPushButton(nom)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
            # le meilleur résultat est mis en avant (bordure accent)
            bord = PRO_CYAN if i == 0 else pal["INACTIVE"]
            btn.setStyleSheet(f"""
                QPushButton {{ background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                    border: 1px solid {bord}; border-radius: 6px;
                    padding: 6px 12px; font-size: 10pt; text-align: left; }}
                QPushButton:hover {{ border-color: {PRO_CYAN}; color: {pal['ACCENT_BRIGHT']}; }}
            """)
            btn.clicked.connect(lambda _c=False, eid=entry_id: self._choisir_resultat(eid))
            self._results_lay.insertWidget(self._results_lay.count() - 1, btn)

        self._results_scroll.setVisible(True)
        self._examples_box.setVisible(False)
        self._statut.setText("✓ " + _("neogen.search_results", n=len(resultats)))

    def _choisir_resultat(self, entry_id: str):
        """Clic sur un résultat : ouvre l'objet dans la Bibliothèque, pré-rempli."""
        from core.neogen.catalogue import PAR_ID
        params = {}
        if self._image and PAR_ID.get(entry_id, {}).get("image"):
            params["image"] = str(self._image)
        self._ouvrir_dans_biblio(entry_id, params)

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
        self._vider_formulaire()
        if didx < 0 or idx < 0 or idx >= len(self._donnees[didx][1]):
            return
        e = self._donnees[didx][1][idx]
        if e["id"] == "carte_visite":
            # Carte de visite INLINE : main_window crée/câble le panneau carte et
            # l'insère dans le formulaire (embed_carte) — comme les autres objets,
            # dans la colonne, avec les onglets Rechercher/Bibliothèque au-dessus.
            # On n'émet PAS pendant la construction (signal pas encore connecté, et
            # onglet Recherche actif) : c'est _on_tab_change qui déclenche au besoin.
            if self._ready:
                self.ouvrir_carte.emit()
            return
        self._form_lay.addWidget(self._construire_formulaire(e))
        self._relier_apercu(self._champs_courant)      # aperçu en direct (réglages)
        self._planifier_apercu_objet()                 # aperçu immédiat à la sélection

    def _on_tab_change(self, idx: int) -> None:
        """Passage sur l'onglet Bibliothèque avec la carte sélectionnée → l'embarquer
        (couvre le cas où la carte est l'objet par défaut, jamais re-sélectionné)."""
        if not getattr(self, "_ready", False):
            return
        onglet = self._tabs.tabText(idx).lower()
        if _("neogen.tab_library").lower() not in onglet:
            return
        didx = self._combo_domaine.currentIndex()
        oidx = self._combo_objet.currentIndex()
        if 0 <= didx < len(self._donnees) and 0 <= oidx < len(self._donnees[didx][1]):
            if self._donnees[didx][1][oidx]["id"] == "carte_visite" \
                    and getattr(self, "_carte_embedded", None) is None:
                self.ouvrir_carte.emit()

    def _vider_formulaire(self) -> None:
        """Vide le formulaire, mais DÉTACHE (sans détruire) la carte embarquée que
        main_window réutilise d'un affichage à l'autre."""
        while self._form_lay.count():
            it = self._form_lay.takeAt(0)
            w = it.widget()
            if w is None:
                continue
            if w is getattr(self, "_carte_embedded", None):
                w.setParent(None)          # détacher sans détruire
            else:
                w.deleteLater()
        self._carte_embedded = None

    def embed_carte(self, panel) -> None:
        """Insère le panneau carte (créé/câblé par main_window) dans le formulaire,
        sous les onglets Rechercher/Bibliothèque."""
        self._vider_formulaire()
        self._carte_embedded = panel
        panel.setParent(self._form_holder)
        # stretch 1 : le panneau REMPLIT la colonne → sa liste (scroll, stretch 1)
        # pousse les boutons (export, litho, modèles) tout en BAS, collés au bord.
        self._form_lay.addWidget(panel, 1)
        panel.show()

    def _construire_formulaire(self, e: dict) -> QWidget:
        pal = self._pal
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 2, 2, 0)

        # (la carte de visite est désormais EMBARQUÉE inline par _choisir_objet →
        #  embed_carte ; plus de bouton « Ouvrir l'éditeur ».)
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
        param_rows = {}                              # pid -> (label, spinbox) pour pilotage
        for (pid, pfr, pen, mini, maxi, defaut, pas) in e["params"]:
            sp = QDoubleSpinBox()
            sp.setRange(mini, maxi)
            sp.setValue(defaut)
            sp.setSingleStep(pas)
            # Décimales alignées sur le PAS (sinon un pas de 0.05 avec 1 décimale
            # se ré-arrondit et les flèches semblent inertes).
            if pas >= 1:
                sp.setDecimals(0)
            elif pas >= 0.1:
                sp.setDecimals(1)
            else:
                sp.setDecimals(2)
            # Pas de « mm » sur les COMPTES (nombre de trous, de jeux, de cases…).
            # Générique : id dans la liste OU commençant par « nb » OU label « Nombre… »
            # -> aucun « mm » à lister objet par objet, marche pour toute nouvelle base.
            _compte = (pid in ("cases_x", "cases_y", "rangees", "colonnes", "branches",
                               "ondulations", "couleurs", "segments", "cotes")
                       or pid.startswith(("nb", "unites", "cases", "compartiments"))
                       or str(pfr).strip().lower().startswith(("nombre", "nb "))
                       or "(unités" in str(pfr).lower() or "(units" in str(pen).lower())
            _angle = pid == "angle" or pid.startswith("angle") or "angle" in str(pfr).lower()
            sp.setSuffix("°" if _angle else ("" if _compte else " mm"))
            sp.setStyleSheet(style_champ)
            _lbl_p = _lbl(_fr_en(pfr, pen))
            form.addRow(_lbl_p, sp)
            champs[pid] = sp
            param_rows[pid] = (_lbl_p, sp)
        for (cid, cfr, cen, options, defaut) in e["choix"]:
            cb = QComboBox()
            tips = {}
            for (val, ofr, oen) in options:
                cb.addItem(_fr_en(ofr, oen), val)
                _tk = f"neogen.tip.{val}"
                _tv = _(_tk)
                if _tv != _tk:                       # explication dispo pour cette option
                    tips[val] = _tv
            cb.setCurrentIndex(max(0, [o[0] for o in options].index(defaut)))
            cb.setStyleSheet(style_champ)
            form.addRow(_lbl(_fr_en(cfr, cen)), cb)
            champs[cid] = cb
            if tips:                                 # petite aide sous le choix, mise à jour au changement
                for i in range(cb.count()):
                    if cb.itemData(i) in tips:
                        cb.setItemData(i, tips[cb.itemData(i)], Qt.ItemDataRole.ToolTipRole)
                desc = QLabel(tips.get(defaut, ""))
                desc.setWordWrap(True)
                desc.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; font-size: 8pt;")
                form.addRow("", desc)
                cb.currentIndexChanged.connect(
                    lambda _ix, _c=cb, _l=desc, _t=tips: _l.setText(_t.get(_c.currentData(), "")))
        # Menu STYLE de texte (relief / gravé / lisse) : pilote le LIBELLÉ et la
        # VISIBILITÉ du champ de valeur — « Hauteur du texte » en relief,
        # « Profondeur » en gravé, champ MASQUÉ en lisse (rien à régler). Un seul
        # nom, une seule logique, partout.
        _style_cb = champs.get("style")
        _relief_row = param_rows.get("relief") or param_rows.get("ep_texte")
        if _style_cb is not None and _relief_row is not None:
            _rl, _rs = _relief_row

            def _sync_style(_ix=0, _cb=_style_cb, _lab=_rl, _sp=_rs):
                st = _cb.currentData()
                vis = (st != "lisse")
                _lab.setVisible(vis)
                _sp.setVisible(vis)
                if vis:
                    _lab.setText(_("neogen.text_depth") if st == "grave"
                                 else _("neogen.text_height"))
            _style_cb.currentIndexChanged.connect(_sync_style)
            _sync_style()
        # Menu FORME (ronde / carrée / rectangulaire) : « Diamètre / côté » pour
        # ronde-carrée, « Longueur » + « Largeur » pour rectangulaire (les champs
        # inutiles sont masqués selon le choix). Ne s'active que si l'objet a bien
        # les paramètres longueur ET largeur (donc uniquement la boîte).
        _forme_cb = champs.get("forme")
        _row_t = param_rows.get("taille")
        _row_lo = param_rows.get("longueur")
        _row_la = param_rows.get("largeur")
        if _forme_cb is not None and _row_lo is not None and _row_la is not None:
            def _sync_forme(_ix=0, _cb=_forme_cb, _t=_row_t, _lo=_row_lo, _la=_row_la):
                rect = (_cb.currentData() == "rectangulaire")
                if _t is not None:
                    _t[0].setVisible(not rect); _t[1].setVisible(not rect)
                for _r in (_lo, _la):
                    _r[0].setVisible(rect); _r[1].setVisible(rect)
            _forme_cb.currentIndexChanged.connect(_sync_forme)
            _sync_forme()
        # BOÎTE : affiche EN DIRECT la mesure INTÉRIEURE (le volume utile), calculée
        # depuis la forme, l'épaisseur des murs et le mode Extérieures/Intérieures.
        # L'utilisateur voit tout de suite ce que la boîte contiendra vraiment.
        _paroi_sp = champs.get("paroi")
        _mesures_cb = champs.get("mesures")
        if _paroi_sp is not None and _mesures_cb is not None and _forme_cb is not None:
            _info_int = QLabel("")
            _info_int.setWordWrap(True)
            _info_int.setStyleSheet(f"color: {PRO_CYAN}; background: transparent; "
                                    f"font-size: 8pt; font-weight: 600;")
            form.addRow("", _info_int)

            def _maj_interieur(*_a, _p=_paroi_sp, _m=_mesures_cb, _f=_forme_cb,
                               _ch=champs, _lab=_info_int):
                pv = _p.value()
                forme = _f.currentData()
                if forme == "rectangulaire":
                    L = _ch["longueur"].value(); W = _ch["largeur"].value()
                else:
                    L = _ch["taille"].value(); W = L
                Ht = _ch["hauteur"].value()
                if _m.currentData() == "int":
                    iL, iW, iH = L, W, Ht                       # saisi = intérieur
                else:
                    iL, iW, iH = L - 2 * pv, W - 2 * pv, Ht - pv  # extérieur - murs
                iL, iW, iH = max(0, iL), max(0, iW), max(0, iH)
                if forme == "ronde":
                    _lab.setText(_fr_en(
                        f"Intérieur : Ø {iL:.1f} × {iH:.1f} mm (haut.)",
                        f"Inside: Ø {iL:.1f} × {iH:.1f} mm (height)"))
                else:
                    _lab.setText(_fr_en(
                        f"Intérieur : {iL:.1f} × {iW:.1f} × {iH:.1f} mm  (L × l × h)",
                        f"Inside: {iL:.1f} × {iW:.1f} × {iH:.1f} mm  (L × W × h)"))
            for _w in (_paroi_sp, champs.get("longueur"), champs.get("largeur"),
                       champs.get("taille"), champs.get("hauteur")):
                if _w is not None:
                    _w.valueChanged.connect(_maj_interieur)
            _mesures_cb.currentIndexChanged.connect(_maj_interieur)
            _forme_cb.currentIndexChanged.connect(_maj_interieur)
            _maj_interieur()
        for (fid, ffr, fen, defaut) in e["flags"]:
            ch = QCheckBox(_fr_en(ffr, fen))
            ch.setChecked(defaut)
            ch.setCursor(Qt.PointingHandCursor)
            ch.setStyleSheet(style_check)
            # Ligne ENTIÈRE (pas de colonne étiquette vide devant) : les libellés
            # de cases partaient à mi-largeur et se faisaient couper à droite
            # dans la colonne ~400 px (vécu : « Lèvre d'empilage (bacs empi… »).
            form.addRow(ch)
            champs[fid] = ch
        # Visibilité conditionnelle de champs, pilotée par la BASE (générique) :
        #   e["visible_si"] = {champ: flag} -> champ visible SEULEMENT si le flag coché
        #   e["cache_si"]   = {champ: flag} -> champ CACHÉ si le flag coché
        # (ex. boîte lumineuse : profondeur/sortie visibles si « lightbox » ; cadre caché).
        _vis = e.get("visible_si") or {}
        _cache = e.get("cache_si") or {}
        if _vis or _cache:
            def _appliquer_vis(*_a, _v=_vis, _c=_cache, _ch=champs, _f=form):
                for _fid, _ctrl in _v.items():
                    _cw = _ch.get(_ctrl); _fw = _ch.get(_fid)
                    if _fw is not None:
                        _f.setRowVisible(_fw, bool(_cw is not None and _cw.isChecked()))
                for _fid, _ctrl in _c.items():
                    _cw = _ch.get(_ctrl); _fw = _ch.get(_fid)
                    if _fw is not None:
                        _f.setRowVisible(_fw, not bool(_cw is not None and _cw.isChecked()))
            for _ctrl in set(list(_vis.values()) + list(_cache.values())):
                _cw = champs.get(_ctrl)
                if _cw is not None and hasattr(_cw, "toggled"):
                    _cw.toggled.connect(_appliquer_vis)
            _appliquer_vis()
        # Sélecteurs de COULEUR (objet, texte…) → objet bicolore : 2 slots à l'export
        for (cid, cfr, cen, hexd) in e.get("couleurs", []):
            btn_c = _ColorButton(hexd)
            form.addRow(_lbl(_fr_en(cfr, cen)), btn_c)
            champs[f"couleur_{cid}"] = btn_c
        if e["texte"] != "aucun":
            # mode « lien » (URL, ex. QR code) : champ simple SANS police / espacement /
            # relief-gravure — ces réglages ne veulent rien dire pour une adresse web.
            _is_lien = (e["texte"] == "lien")
            le = QLineEdit()
            if _is_lien:
                le.setPlaceholderText(_("neogen.link_placeholder"))
                form.addRow(_lbl(_("neogen.link_label")), le)
            else:
                le.setPlaceholderText(_("neogen.text_placeholder")
                                      + (" *" if e["texte"] == "requis" else ""))
                form.addRow(_lbl(_("neogen.text_label")), le)
            le.setStyleSheet(style_champ)
            champs["texte"] = le
            # Police / espacement / relief-gravure : uniquement pour du VRAI texte
            # (pas pour un lien/URL).
            if not _is_lien:
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
                # Pas de case « gravé » si un menu de STYLE (relief/gravé/lisse) est
                # déjà présent (sinon doublon contradictoire).
                _has_style = any(c[0] == "style" for c in e["choix"])
                if not any(f[0] == "grave" for f in e["flags"]) and not _has_style:
                    ch = QCheckBox(_("neogen.engraved"))
                    ch.setCursor(Qt.PointingHandCursor)
                    ch.setStyleSheet(style_check)
                    form.addRow("", ch)
                    champs["grave"] = ch
        # Case « Logo » (porte-clé) : ouvre le sélecteur SVG à la coche et masque
        # les champs texte/police/espacement — pas de bouton séparé.
        _logo_cb = champs.get("logo")
        if _logo_cb is not None:
            _rows_txt = [champs.get("texte"), champs.get("police"), champs.get("espacement")]

            def _maj_logo_ui(_on, _rows=_rows_txt, _f=form):
                # UI seulement (visibilité + libellés) — se déclenche AUSSI sur un
                # changement programmatique (ré-ouverture), sans ouvrir de fenêtre.
                for _r in _rows:
                    if _r is not None:
                        _f.setRowVisible(_r, not _on)
                _fc = champs.get("forme")
                if _fc is not None:
                    _lbl = (_fr_en("Suit le logo", "Follow logo") if _on
                            else _fr_en("Suit les lettres", "Follows the letters"))
                    for _i in range(_fc.count()):
                        if _fc.itemData(_i) == "contour":
                            _fc.setItemText(_i, _lbl)
                _lo = _f.labelForField(champs.get("couleur_objet")) if champs.get("couleur_objet") is not None else None
                _lt = _f.labelForField(champs.get("couleur_texte")) if champs.get("couleur_texte") is not None else None
                if _lo is not None:
                    _lo.setText(_fr_en("Couleur du porte-clé", "Keychain color") if _on
                                else _fr_en("Couleur objet", "Object color"))
                if _lt is not None:
                    _lt.setText(_fr_en("Couleur du logo", "Logo color") if _on
                                else _fr_en("Couleur texte", "Text color"))

            def _clic_logo(_on, _cb=_logo_cb):
                # Ouverture du sélecteur : UNIQUEMENT sur clic UTILISATEUR (clicked),
                # jamais sur un setChecked programmatique (retour sur neoGen).
                if _on and not champs.get("__image"):
                    chemin, _x = QFileDialog.getOpenFileName(
                        self, _("neogen.attach_logo"), "", "SVG (*.svg)")
                    if not chemin:
                        _cb.setChecked(False)
                        return
                    champs["__image"] = chemin
                elif not _on:
                    champs.pop("__image", None)
                self._planifier_apercu_objet()

            _logo_cb.toggled.connect(_maj_logo_ui)
            _logo_cb.clicked.connect(_clic_logo)
            _maj_logo_ui(_logo_cb.isChecked())
        if e["image"]:
            # bouton PLEINE LARGEUR, même style visible que « Joindre un
            # logo » de la Création libre (avant : QPushButton sans style,
            # on ne voyait pas que c'était cliquable)
            if e["id"] == "photo_relief":
                cle_btn = "neogen.attach_photo"
            elif e["id"] == "logo":
                cle_btn = "neogen.attach_logo"
            else:                                   # HueForge & autres : image générique
                cle_btn = "neogen.attach_image"
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
            self._lbl_img_courant = lbl_img   # pour l'aperçu image pré-rempli

            # Logo 3D : SVG uniquement (le PNG/JPG rasterisé donne une silhouette
            # sale). Les autres objets image (photo en relief, HueForge) acceptent
            # les photos PNG/JPG.
            _filtre = ("SVG (*.svg)" if e["id"] == "logo"
                       else "Image (*.svg *.png *.jpg *.jpeg)")

            def _pick():
                from PySide6.QtGui import QFontMetrics
                chemin, _f2 = QFileDialog.getOpenFileName(
                    self, _(cle_btn), "", _filtre)
                if chemin:
                    fm = QFontMetrics(lbl_img.font())
                    lbl_img.setText(fm.elidedText(Path(chemin).name,
                                                  Qt.ElideMiddle, 330))
                    champs["__image"] = chemin
                    self._planifier_apercu_objet()   # aperçu direct dès l'image chargée
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
                lbl = getattr(self, "_lbl_img_courant", None)
                if lbl is not None:
                    from pathlib import Path as _P
                    lbl.setText(_P(str(val)).name)
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
        self._tabs.setCurrentIndex(0)          # bascule sur la Bibliothèque
        # génération immédiate si tout le nécessaire est là (sinon on laisse
        # l'utilisateur compléter — ex. texte requis, image manquante)
        e = self._entree_courante
        pret = not (e["texte"] == "requis" and not champs.get("texte")
                    and not str((params or {}).get("texte", "")).strip())
        pret = pret and not (e["image"] and not champs.get("__image"))
        if pret:
            self._generer_catalogue(e, champs, self._btn_cat)

    @staticmethod
    def _collecter_params(champs: dict) -> dict:
        """Lit les valeurs courantes du formulaire → dict de paramètres."""
        params = {}
        for k, wdg in champs.items():
            if k == "__image":
                params["image"] = wdg
            elif isinstance(wdg, QDoubleSpinBox):
                params[k] = wdg.value()
            elif isinstance(wdg, _ColorButton):
                params[k] = wdg.hex
            elif isinstance(wdg, QComboBox):
                params[k] = wdg.currentData()
            elif isinstance(wdg, QCheckBox):
                params[k] = wdg.isChecked()
            elif isinstance(wdg, QLineEdit):
                params[k] = wdg.text().strip()
        return params

    # ── Aperçu direct (comme la carte de visite) ──────────────────────────────
    def _relier_apercu(self, champs: dict) -> None:
        """Branche TOUS les widgets du formulaire sur l'aperçu en direct : dès qu'on
        change une dimension, une couleur, le style… le viewer se met à jour."""
        for wdg in champs.values():
            if isinstance(wdg, QDoubleSpinBox):
                wdg.valueChanged.connect(self._planifier_apercu_objet)
            elif isinstance(wdg, _ColorButton):
                wdg.changed.connect(self._planifier_apercu_objet)
            elif isinstance(wdg, QComboBox):
                wdg.currentIndexChanged.connect(self._planifier_apercu_objet)
            elif isinstance(wdg, QCheckBox):
                wdg.toggled.connect(self._planifier_apercu_objet)
            elif isinstance(wdg, QLineEdit):
                wdg.textChanged.connect(self._planifier_apercu_objet)

    def _planifier_apercu_objet(self, *args) -> None:
        """Débounce : regroupe les changements rapides avant de regénérer l'aperçu."""
        if not getattr(self, "_ready", False):
            return
        if not hasattr(self, "_apercu_timer"):
            from PySide6.QtCore import QTimer
            self._apercu_timer = QTimer(self)
            self._apercu_timer.setSingleShot(True)
            self._apercu_timer.timeout.connect(self._lancer_apercu)
        self._apercu_timer.start(250)

    def _lancer_apercu(self) -> None:
        e = getattr(self, "_entree_courante", None)
        champs = getattr(self, "_champs_courant", None)
        if not e or champs is None or getattr(self, "_carte_embedded", None) is not None:
            return
        params = self._collecter_params(champs)
        # texte manquant → placeholder pour voir la forme ET les 2 couleurs (l'objet
        # est bicolore dès qu'il porte du texte). Se met à jour dès qu'on tape.
        if e["texte"] != "aucun" and not params.get("texte"):
            params["texte"] = ("https://neoslice-ai.com" if e["texte"] == "lien"
                               else "Texte")
        if e["image"] and not params.get("image"):
            return                       # pas d'image → pas d'aperçu (lithophanie…)
        # NE JAMAIS lancer un 2e aperçu pendant qu'un tourne : les booléens
        # (manifold) ne sont PAS thread-safe et le vieux QThread serait GC en
        # cours d'exécution -> crash quand on règle vite un objet lourd (lightbox).
        # On ré-essaie juste après, avec les derniers réglages.
        _w = getattr(self, "_apercu_worker", None)
        if _w is not None and _w.isRunning():
            self._apercu_timer.start(200)
            return
        self._apercu_worker = _ApercuWorker(e["id"], params)
        self._apercu_worker.pret.connect(self.apercu_objet)
        self._apercu_worker.start()

    def _generer_catalogue(self, e: dict, champs: dict, btn: QPushButton):
        params = self._collecter_params(champs)
        if e["texte"] == "requis" and not params.get("texte"):
            self._statut.setText("⚠ " + _("neogen.text_required"))
            return
        if e["image"] and not params.get("image"):
            self._statut.setText("⚠ " + _("neogen.image_required"))
            return
        # Une génération à la fois : écraser self._worker pendant qu'un thread
        # tourne (ex. changer d'objet et regénérer aussitôt) ferait perdre sa
        # référence Python → GC du QThread en plein run → crash (même piège que
        # les workers thermomap). On garde aussi une liste de références vivantes.
        _w = getattr(self, "_worker", None)
        if _w is not None and _w.isRunning():
            self._statut.setText("⚙ " + _("neogen.building"))
            return
        btn.setEnabled(False)
        self._statut.setText("⚙ " + _("neogen.building"))
        self._worker = _CatalogueWorker(
            e["id"], params, getattr(self, "volume_plateau", None))
        self._workers_vivants = getattr(self, "_workers_vivants", [])
        self._workers_vivants.append(self._worker)
        self._worker.finished.connect(
            lambda w=self._worker: self._workers_vivants.remove(w)
            if w in self._workers_vivants else None)
        self._worker.fini.connect(self._sur_fini)
        self._worker.fini_multi.connect(self._sur_fini_multi)
        self._worker.erreur.connect(self._sur_erreur)
        self._worker.start()

    # ── Résultats ────────────────────────────────────────────────────────────
    def _sur_fini(self, chemin):
        """Objet Bibliothèque généré : le panneau reste — on ajuste, on regénère."""
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        self._statut.setText("✓ " + _("neogen.loaded_adjust_form"))
        self.piece_ready.emit(Path(chemin))

    def _sur_fini_multi(self, scene, entree_id: str):
        """Objet BICOLORE généré : route multicouleur (aperçu couleurs + 2 slots
        conservés à l'export). Le panneau reste — on ajuste, on regénère."""
        if hasattr(self, "_btn_cat"):
            self._btn_cat.setEnabled(True)
        self._statut.setText("✓ " + _("neogen.loaded_adjust_form"))
        self.objet_multicouleur.emit(scene, entree_id)

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
