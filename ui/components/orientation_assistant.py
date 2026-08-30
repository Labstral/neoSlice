"""Assistant d'orientation — carte compacte (colonne gauche) + panneau complet
(COLONNE DE DROITE, bascule façon neoGen).

La carte vit sous les jauges d'analyse : score de la pose actuelle, gain détecté,
deux boutons. Le panneau complet (marquage des zones, effort, propositions
scorées) s'ouvre DANS LA COLONNE DE DROITE — largeur fixe : le viewer reste
visible en entier, rien ne bouge (retour Emmanuel : l'accordéon en colonne
gauche élargissait la colonne et masquait le viewer).

La logique métier est dans core/geometry/orientation_advisor.py ; le câblage
mesh/viewer/bascule dans main_window (_orient_*).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSlider,
    QLayout, QScrollArea, QFrame,
)

from core.i18n import _
from ui.styles.theme import MANAGER as _T, FONT_MAIN

# Vermillon Okabe-Ito : identique à la surbrillance des zones dans le viewer,
# lisible en vision normale ET daltonienne, dans les deux thèmes.
ZONE_COLOR = "#D55E00"


class _ScoreBar(QWidget):
    """Barre fine 0→1 (thème-aware), libellé à gauche, nombre à droite.

    `text` : texte affiché à droite (défaut : valeur ×100). `color_score` :
    0→1 pilotant la couleur (1 = vert) — permet d'afficher un RATIO (surplombs :
    barre pleine = mauvais) avec la même sémantique couleur que les jauges."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._value = 0.0
        self._text: str | None = None
        self._color_score: float | None = None
        self.setFixedHeight(16)

    def set_value(self, v: float, text: str | None = None,
                  color_score: float | None = None):
        self._value = max(0.0, min(1.0, float(v)))
        self._text = text
        self._color_score = color_score
        self.update()

    def paintEvent(self, _ev):
        pal = _T.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont(FONT_MAIN, 8))
        p.setPen(QColor(pal["TEXT_SECONDARY"]))
        lw = 74
        p.drawText(0, 0, lw, self.height(), Qt.AlignLeft | Qt.AlignVCenter, self._label)
        x0, h = lw + 6, 6
        w = max(10, self.width() - x0 - 38)
        y = (self.height() - h) // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["BG_ELEVATED"]))
        p.drawRoundedRect(x0, y, w, h, 3, 3)
        cs = self._color_score if self._color_score is not None else self._value
        if cs > 0.66:
            col = QColor(pal["TELE_GREEN"])
        elif cs > 0.33:
            col = QColor(pal["AMBER"])
        else:
            col = QColor(pal["ERROR_RED"])
        p.setBrush(col)
        p.drawRoundedRect(x0, y, int(w * self._value), h, 3, 3)
        p.setPen(QColor(pal["TEXT_LABEL"]))
        p.drawText(x0 + w + 4, 0, 34, self.height(), Qt.AlignLeft | Qt.AlignVCenter,
                   self._text if self._text is not None else f"{self._value * 100:.0f}")
        p.end()


class _PropositionCard(QWidget):
    """Une proposition d'orientation : nom, barres, explication, APPLIQUER.
    (Pas d'aperçu au survol : jugé visuellement instable — retiré à la demande
    d'Emmanuel. On applique, et « Revenir à l'origine » annule.)"""

    def __init__(self, data: dict, on_apply, parent=None):
        super().__init__(parent)
        self._data = data
        pal = _T.palette()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("propCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        # Les labels à retour à la ligne dans des layouts imbriqués se laissent
        # écraser (textes superposés, boutons coupés — vécu) : le layout impose
        # sa hauteur minimale, la colonne scrolle si besoin.
        lay.setSizeConstraint(QLayout.SetMinimumSize)

        head = QHBoxLayout()
        self._title_lbl = t = QLabel(data.get("titre", ""))
        t.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        head.addWidget(t, 1)
        self._reco_lbl = None
        if data.get("recommande"):
            self._reco_lbl = r = QLabel(_("orient.recommended"))
            r.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            head.addWidget(r)
        lay.addLayout(head)

        if data.get("solidite") is not None:
            b = _ScoreBar(_("orient.bar_strength")); b.set_value(data["solidite"])
            lay.addWidget(b)
        # Surplombs : MÊME libellé, MÊME nombre et MÊME logique couleur que la
        # jauge du panneau d'analyse (cohérence exigée — la carte affichée doit
        # être identique à la jauge une fois l'orientation appliquée).
        ratio = float(data.get("surplombs", 0.0))
        b2 = _ScoreBar(_("analysis.gauge_oh"))
        b2.set_value(min(1.0, ratio), text=data.get("surplombs_label", ""),
                     color_score=1.0 - ratio)
        lay.addWidget(b2)
        # Stabilité : MÊME moteur et MÊME libellé que la jauge du panneau, pour
        # que le chiffre annoncé soit celui affiché après application.
        stab = data.get("stabilite")
        if stab is not None:
            b3 = _ScoreBar(_("analysis.gauge_stab"))
            # int() (troncature) et NON round() : c'est la formule exacte de la
            # jauge du panneau — sinon 4,55 % s'affiche « 4 % » d'un côté et
            # « 5 % » de l'autre pour la même pièce.
            b3.set_value(float(stab), text=f"{int(float(stab) * 100)}%")
        else:
            b3 = _ScoreBar(_("orient.bar_adhesion"))
            b3.set_value(data.get("adherence", 0.0))
        lay.addWidget(b3)

        expl = data.get("explication", "")
        self._expl_lbl = None
        if expl:
            self._expl_lbl = e = QLabel(expl)
            e.setWordWrap(True)
            e.setFont(QFont(FONT_MAIN, 8))
            # un label wrap n'annonce qu'UNE ligne de hauteur minimale → réserver
            # 2 lignes quand le texte est long (sinon il chevauche les barres)
            if len(expl) > 45:
                e.setMinimumHeight(e.fontMetrics().height() * 2 + 4)
            lay.addWidget(e)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._apply_btn = apply_btn = QPushButton(_("orient.apply"))
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setFixedHeight(24)
        apply_btn.clicked.connect(lambda: on_apply(self._data))
        btn_row.addWidget(apply_btn)
        lay.addLayout(btn_row)
        self.apply_theme()

    def apply_theme(self):
        """Re-applique les couleurs du thème COURANT. Sans ça, une carte créée en
        thème sombre gardait son fond sombre après bascule en clair (vécu)."""
        pal = _T.palette()
        bord = pal["ACCENT"] if self._data.get("recommande") else pal["INACTIVE"]
        self.setStyleSheet(
            f"QWidget#propCard {{ background: {pal['BG_SURFACE']}; "
            f"border: 1px solid {bord}; border-radius: 6px; }}")
        self._title_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; border: none;")
        if self._reco_lbl is not None:
            self._reco_lbl.setStyleSheet(
                f"color: {pal['ACCENT']}; background: transparent; border: none; letter-spacing: 1px;")
        if self._expl_lbl is not None:
            self._expl_lbl.setStyleSheet(
                f"color: {pal['TEXT_LABEL']}; background: transparent; border: none; font-style: italic;")
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
            f"border: 1px solid {pal['ACCENT']}; border-radius: 3px; padding: 0 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT']}; color: #fff; }}")
        self.update()


# ══════════════════════════════════════════════════════════════════════════════
# Panneau COMPLET — colonne de droite (bascule façon neoGen)
# ══════════════════════════════════════════════════════════════════════════════
class OrientationSidePanel(QWidget):
    """Contenu de la colonne de droite quand l'assistant est ouvert."""

    marquage_change = Signal(bool)       # mode marquage de zones on/off
    zones_effacees = Signal()
    taille_zone_changee = Signal(float)  # facteur 0.5 → 2.0 du rayon par défaut
    analyser_demande = Signal()          # calculer les propositions
    appliquer_demande = Signal(object)   # matrice 4×4 (list)
    revenir_demande = Signal()           # revenir à l'orientation d'origine
    effort_change = Signal(str)          # "", "z", "x", "y" — repli sans zones
    close_requested = Signal()           # ✕ → rendre la colonne aux paramètres

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.apply_theme()
        _T.register(self.apply_theme)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        # En-tête : titre + ✕ (même pattern que neoGen)
        head = QHBoxLayout()
        self._title = QLabel(_("orient.open"))
        self._title.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        head.addWidget(self._title, 1)
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(26, 26)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.close_requested.emit)
        head.addWidget(self._close_btn)
        root.addLayout(head)

        self._mark_btn = QPushButton(_("orient.mark_zones"))
        self._mark_btn.setCheckable(True)
        self._mark_btn.setCursor(Qt.PointingHandCursor)
        self._mark_btn.setMinimumHeight(30)
        self._mark_btn.toggled.connect(self._on_mark_toggled)
        root.addWidget(self._mark_btn)

        size_row = QHBoxLayout()
        self._size_lbl = QLabel(_("orient.zone_size"))
        self._size_lbl.setFont(QFont(FONT_MAIN, 8))
        size_row.addWidget(self._size_lbl)
        self._size_slider = QSlider(Qt.Horizontal)
        self._size_slider.setRange(50, 200)      # % du rayon par défaut
        self._size_slider.setValue(100)
        self._size_slider.valueChanged.connect(
            lambda v: self.taille_zone_changee.emit(v / 100.0))
        size_row.addWidget(self._size_slider, 1)
        root.addLayout(size_row)

        zrow = QHBoxLayout()
        self._zones_lbl = QLabel(_("orient.zones_none"))
        self._zones_lbl.setFont(QFont(FONT_MAIN, 8))
        self._zones_lbl.setWordWrap(True)
        zrow.addWidget(self._zones_lbl, 1)
        self._clear_btn = QPushButton(_("orient.clear_zones"))
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setFixedHeight(22)
        self._clear_btn.clicked.connect(self.zones_effacees.emit)
        self._clear_btn.setEnabled(False)
        zrow.addWidget(self._clear_btn)
        root.addLayout(zrow)

        # Direction d'effort de REPLI (utile sans zones ; les zones priment)
        erow = QHBoxLayout()
        self._effort_lbl = QLabel(_("orient.effort"))
        self._effort_lbl.setFont(QFont(FONT_MAIN, 8))
        self._effort_lbl.setWordWrap(True)
        erow.addWidget(self._effort_lbl, 1)
        self._effort_combo = QComboBox()
        self._effort_combo.setFont(QFont(FONT_MAIN, 8))
        for key, code in (("orient.effort_none", ""), ("orient.effort_z", "z"),
                          ("orient.effort_x", "x"), ("orient.effort_y", "y")):
            self._effort_combo.addItem(_(key), code)
        self._effort_combo.currentIndexChanged.connect(
            lambda _i: self.effort_change.emit(self._effort_combo.currentData() or ""))
        erow.addWidget(self._effort_combo)
        root.addLayout(erow)

        self._analyse_btn = QPushButton(_("orient.analyse"))
        self._analyse_btn.setCursor(Qt.PointingHandCursor)
        self._analyse_btn.setMinimumHeight(32)
        self._analyse_btn.clicked.connect(self.analyser_demande.emit)
        root.addWidget(self._analyse_btn)

        self._busy_lbl = QLabel("")
        self._busy_lbl.setFont(QFont(FONT_MAIN, 8))
        self._busy_lbl.setWordWrap(True)
        self._busy_lbl.hide()
        root.addWidget(self._busy_lbl)

        # Propositions : zone défilante (jusqu'à 4 cartes + explications)
        self._props_scroll = QScrollArea()
        self._props_scroll.setWidgetResizable(True)
        self._props_scroll.setFrameShape(QFrame.NoFrame)
        self._props_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._props_host = QWidget()
        self._props_host.setStyleSheet("background: transparent;")
        self._props_lay = QVBoxLayout(self._props_host)
        self._props_lay.setContentsMargins(0, 0, 0, 0)
        self._props_lay.setSpacing(6)
        self._props_lay.addStretch()
        self._props_scroll.setWidget(self._props_host)
        root.addWidget(self._props_scroll, 1)

        self._revert_btn = QPushButton(_("orient.revert"))
        self._revert_btn.setCursor(Qt.PointingHandCursor)
        self._revert_btn.setMinimumHeight(26)
        self._revert_btn.clicked.connect(self.revenir_demande.emit)
        self._revert_btn.hide()
        root.addWidget(self._revert_btn)

    # ── interactions ─────────────────────────────────────────────────────────
    def _on_mark_toggled(self, on: bool):
        self._mark_btn.setText(_("orient.mark_zones_on") if on else _("orient.mark_zones"))
        self.marquage_change.emit(on)

    def stop_marking(self):
        """Sort du mode marquage (fermeture du panneau, nouvelle pièce…)."""
        if self._mark_btn.isChecked():
            self._mark_btn.setChecked(False)

    # ── état affiché ─────────────────────────────────────────────────────────
    def set_zones(self, n: int):
        self._zones_lbl.setText(_("orient.zones_n", n=n) if n else _("orient.zones_none"))
        self._clear_btn.setEnabled(n > 0)

    def set_busy(self, busy: bool):
        self._analyse_btn.setEnabled(not busy)
        self._busy_lbl.setVisible(busy)
        self._busy_lbl.setText(_("orient.computing") if busy else "")

    def set_applied(self, applied: bool):
        self._revert_btn.setVisible(applied)

    def set_propositions(self, props: list[dict]):
        while self._props_lay.count() > 1:      # garde le stretch final
            it = self._props_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for d in props:
            self._props_lay.insertWidget(
                self._props_lay.count() - 1,
                _PropositionCard(
                    d,
                    on_apply=lambda dd: self.appliquer_demande.emit(dd.get("matrice")),
                ))

    # ── thème ────────────────────────────────────────────────────────────────
    def apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        # Les cartes déjà affichées doivent suivre la bascule de thème.
        for i in range(self._props_lay.count()):
            w = self._props_lay.itemAt(i).widget()
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()
        self._title.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 1px;")
        self._close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; }}"
            f"QPushButton:hover {{ border-color: {pal['ERROR_RED']}; color: {pal['ERROR_RED']}; }}")
        for lbl in (self._size_lbl, self._effort_lbl, self._zones_lbl, self._busy_lbl):
            lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._props_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            f"QScrollBar:vertical {{ background: {pal['BG_ELEVATED']}; width: 10px; border-radius: 5px; }}"
            f"QScrollBar::handle:vertical {{ background: {pal['TEXT_SECONDARY']}; border-radius: 5px; min-height: 30px; }}")
        btn = (f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
               f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; font-size: 11px; }}"
               f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")
        for b in (self._clear_btn, self._revert_btn):
            b.setStyleSheet(btn)
        self._mark_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ZONE_COLOR}; "
            f"border: 1px solid {ZONE_COLOR}; border-radius: 3px; font-size: 11px; }}"
            f"QPushButton:checked {{ background: {ZONE_COLOR}; color: #ffffff; }}")
        # même taille de texte que « MARQUER LES ZONES » (11 px) : les deux
        # boutons principaux doivent être visuellement cohérents.
        self._analyse_btn.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #ffffff; border: none; "
            f"border-radius: 3px; font-weight: bold; letter-spacing: 1px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}"
            f"QPushButton:disabled {{ background: {pal['INACTIVE']}; }}")
        self._effort_combo.setStyleSheet(
            f"QComboBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 2px 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
            f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")


# ══════════════════════════════════════════════════════════════════════════════
# Carte compacte — colonne gauche (panneau d'analyse)
# ══════════════════════════════════════════════════════════════════════════════
class OrientationAssistant(QWidget):
    """Carte ORIENTATION compacte. Le panneau complet s'ouvre à DROITE."""

    open_requested = Signal()            # ouvrir/fermer le panneau (colonne droite)
    poser_face_change = Signal(bool)     # mode « poser sur cette face » on/off

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panel_open = False
        self._last_score = None          # (score, gain) — rejoué à la bascule de thème
        self._setup_ui()
        self.apply_theme()
        _T.register(self.apply_theme)
        self.set_visible_card(False)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("orientCard")
        self._card.setAttribute(Qt.WA_StyledBackground, True)
        c = QVBoxLayout(self._card)
        c.setContentsMargins(10, 8, 10, 8)
        c.setSpacing(4)
        head = QHBoxLayout()
        self._title = QLabel(_("orient.title"))
        self._title.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        head.addWidget(self._title)
        # Badge PRO : la carte reste VISIBLE hors Pro (elle montre le potentiel
        # d'amélioration et fait découvrir la fonctionnalité) ; le clic ouvre le
        # paywall — même logique que le bouton « ESPACE PRO ».
        self._pro_badge = QLabel("PRO")
        self._pro_badge.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        self._pro_badge.hide()
        head.addWidget(self._pro_badge)
        head.addStretch()
        self._score_lbl = QLabel("—")
        self._score_lbl.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        head.addWidget(self._score_lbl)
        c.addLayout(head)
        self._gain_lbl = QLabel("")
        self._gain_lbl.setFont(QFont(FONT_MAIN, 8))
        self._gain_lbl.setWordWrap(True)
        c.addWidget(self._gain_lbl)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._open_btn = QPushButton(_("orient.open"))
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.setFixedHeight(26)
        self._open_btn.clicked.connect(self.open_requested.emit)
        row.addWidget(self._open_btn, 1)
        self._face_btn = QPushButton(_("orient.lay_face"))
        self._face_btn.setCursor(Qt.PointingHandCursor)
        self._face_btn.setFixedHeight(26)
        self._face_btn.setCheckable(True)
        self._face_btn.toggled.connect(self.poser_face_change.emit)
        row.addWidget(self._face_btn, 1)
        c.addLayout(row)
        root.addWidget(self._card)

    # ── état ─────────────────────────────────────────────────────────────────
    def set_visible_card(self, visible: bool):
        self._card.setVisible(visible)

    def set_pro(self, est_pro: bool):
        """Affiche (ou non) le badge PRO sur la carte. Le verrou lui-même est
        appliqué par main_window : clic → paywall si non-Pro."""
        self._pro_badge.setVisible(not est_pro)

    def set_panel_open(self, opened: bool):
        self._panel_open = bool(opened)
        self._open_btn.setText(_("orient.close") if opened else _("orient.open"))

    def panel_open(self) -> bool:
        return self._panel_open

    def set_score(self, score: float, gain_pct: float):
        self.set_visible_card(True)
        self._last_score = (float(score), float(gain_pct))   # re-jouable au switch
        self._score_lbl.setText(f"{score:.0f}/100")
        pal = _T.palette()
        # Le score colore aussi le chiffre : 39/100 en vert avec « orientation
        # déjà favorable » était contradictoire (vécu).
        if score >= 70:
            self._score_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        elif score >= 45:
            self._score_lbl.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        else:
            self._score_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        if gain_pct >= 2.0:
            self._gain_lbl.setText(_("orient.gain", pct=f"{gain_pct:.0f}"))
            self._gain_lbl.setStyleSheet(f"color: {pal['AMBER']}; background: transparent; border: none;")
        elif score >= 70:
            self._gain_lbl.setText(_("orient.optimal"))
            self._gain_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent; border: none;")
        else:
            # peu de gain MAIS pièce difficile : ne pas dire « déjà favorable »
            self._gain_lbl.setText(_("orient.hard_part"))
            self._gain_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent; border: none;")

    def stop_click_modes(self):
        """Décoche « poser sur une face » (pièce changée, panneau fermé…)."""
        if self._face_btn.isChecked():
            self._face_btn.setChecked(False)

    # ── thème ────────────────────────────────────────────────────────────────
    def apply_theme(self):
        pal = _T.palette()
        self._card.setStyleSheet(
            f"QWidget#orientCard {{ background: {pal['BG_SURFACE']}; border-radius: 3px; }}")
        # Titre en TEXT_PRIMARY (noir en thème clair, blanc en sombre) : plus net
        # que le gris des libellés — demandé par Emmanuel.
        self._title.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 2px;")
        self._pro_badge.setStyleSheet(
            f"color: {pal['ACCENT']}; background: transparent; "
            f"border: 1px solid {pal['ACCENT']}; border-radius: 2px; padding: 0 4px;")
        btn = (f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
               f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; font-size: 11px; }}"
               f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}"
               f"QPushButton:checked {{ background: {pal['ACCENT']}; color: #ffffff; "
               f"border-color: {pal['ACCENT']}; }}")
        self._open_btn.setStyleSheet(btn)
        self._face_btn.setStyleSheet(btn)
        # Score + message : couleurs dépendantes de la valeur → les rejouer avec
        # la palette courante (sinon le vert/ambre reste celui de l'ancien thème).
        if getattr(self, "_last_score", None) is not None:
            self.set_score(*self._last_score)
