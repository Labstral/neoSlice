# -*- coding: utf-8 -*-
"""Personnalisateur de CARTE DE VISITE — panneau de la colonne de droite.

Le bouton CARTE (barre du haut) bascule la colonne de droite vers ce panneau ;
la caméra passe en vue de dessus sur la carte. On compose la carte par
ÉLÉMENTS (texte, logo), chacun avec sa police/taille/alignement/décalage/relief
et SA COULEUR — chaque couleur devient un slot de filament à l'export.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QDoubleSpinBox, QComboBox, QColorDialog, QScrollArea, QFrame, QFileDialog,
    QFormLayout,
)

from core.i18n import _, lang
from core.neogen import carte_visite as CV
from ui.styles.theme import MANAGER as _THEME, spinbox_qss as _spinbox_qss

PRO_CYAN, PRO_VIOLET = "#22D3EE", "#A855F7"

_ALIGN_H = [("gauche", "Gauche", "Left"), ("centre", "Centre", "Center"),
            ("droite", "Droite", "Right")]
_ALIGN_V = [("haut", "Haut", "Top"), ("milieu", "Milieu", "Middle"),
            ("bas", "Bas", "Bottom")]


def _fr(fr, en):
    return fr if lang() == "fr" else en


def _choisir_couleur(parent, initiale: str, titre: str) -> QColor:
    """Sélecteur de couleur à texte LISIBLE : le dialogue Qt héritait de la
    palette sombre de l'app (labels Teinte/Sat/RVB illisibles, cf. retour). On
    force une palette claire standard sur le dialogue (non natif)."""
    dlg = QColorDialog(QColor(initiale), parent)
    dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dlg.setWindowTitle(titre)
    dlg.setStyleSheet("""
        QColorDialog, QColorDialog QWidget { background:#f4f4f6; color:#111; }
        QLabel { color:#111; }
        QSpinBox, QLineEdit { background:#ffffff; color:#111;
            border:1px solid #b8b8be; border-radius:3px; padding:1px 3px; }
        QPushButton { background:#e6e6ea; color:#111;
            border:1px solid #b8b8be; border-radius:4px; padding:4px 12px; }
        QPushButton:hover { background:#d8d8de; }
    """)
    return dlg.currentColor() if dlg.exec() else QColor()


class _ElementEditor(QFrame):
    """Éditeur d'un élément (texte ou logo) : contenu + style + couleur."""
    change = Signal()
    supprime = Signal(object)

    def __init__(self, type_el: str, pal: dict, parent=None):
        super().__init__(parent)
        self.type_el = type_el
        self._pal = pal
        self._image = ""
        self._couleur = "#111111"
        self._build()

    def _build(self):
        pal = self._pal
        self.setStyleSheet(
            f"QFrame {{ background: {pal['BG_SURFACE']}; border: 1px solid "
            f"{pal['INACTIVE']}; border-radius: 6px; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(5)
        champ = (f"QDoubleSpinBox, QComboBox, QLineEdit {{ background: "
                 f"{pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; border: "
                 f"1px solid {pal['INACTIVE']}; border-radius: 4px; padding: "
                 f"2px 5px; }}") + _spinbox_qss(pal, "rgba(34,211,238,0.35)")

        # en-tête : titre + supprimer
        head = QHBoxLayout()
        titre = QLabel(_fr("Texte", "Text") if self.type_el == "texte"
                       else _fr("Logo (image)", "Logo (image)"))
        titre.setStyleSheet(f"color: {PRO_CYAN}; font-weight: bold; border: none;")
        head.addWidget(titre)
        head.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(20, 20)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};"
            f" border: none; }} QPushButton:hover {{ color: #E5484D; }}")
        btn_x.clicked.connect(lambda: self.supprime.emit(self))
        head.addWidget(btn_x)
        v.addLayout(head)

        form = QFormLayout()
        form.setSpacing(4)
        # les champs s'étirent/rétrécissent à la largeur de la colonne (jamais
        # de débordement à droite)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; border: none;")
            return l

        if self.type_el == "texte":
            self.le = QLineEdit()
            self.le.setPlaceholderText(_fr("Votre texte", "Your text"))
            self.le.setStyleSheet(champ)
            self.le.textChanged.connect(self.change)
            form.addRow(_lbl(_fr("Texte", "Text")), self.le)
            self.cb_pol = QComboBox()
            self.cb_pol.addItem(_fr("(par défaut)", "(default)"), None)
            try:
                from core.neogen.catalogue import polices_disponibles
                for f in polices_disponibles():
                    self.cb_pol.addItem(f, f)
            except Exception:
                pass
            # ne PAS dimensionner le combo sur le nom de police le plus long
            # (sinon il pousse toute la colonne à ~590 px -> contenu coupé) ;
            # le popup, lui, affiche les noms complets
            self.cb_pol.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.cb_pol.setMinimumContentsLength(6)
            self.cb_pol.setStyleSheet(champ)
            self.cb_pol.currentIndexChanged.connect(self.change)
            form.addRow(_lbl(_fr("Police", "Font")), self.cb_pol)
            self.sp_h = self._spin(1.5, 20, 5.0, 0.5, champ)
            form.addRow(_lbl(_fr("Taille (mm)", "Size (mm)")), self.sp_h)
        else:
            row = QHBoxLayout()
            self.btn_img = QPushButton(_fr("Choisir une image…", "Choose image…"))
            self.btn_img.setCursor(Qt.PointingHandCursor)
            self.btn_img.setStyleSheet(
                f"QPushButton {{ background: {pal['BG_ELEVATED']}; color: "
                f"{pal['TEXT_PRIMARY']}; border: 1px solid {PRO_VIOLET}; "
                f"border-radius: 4px; padding: 4px; }}")
            self.btn_img.clicked.connect(self._choisir_image)
            row.addWidget(self.btn_img)
            form.addRow(_lbl(_fr("Fichier", "File")), row)
            self.sp_h = self._spin(6, 60, 18.0, 1.0, champ)
            form.addRow(_lbl(_fr("Largeur (mm)", "Width (mm)")), self.sp_h)

        self.cb_ah = self._combo(_ALIGN_H, "centre", champ)
        # « Centre » horizontal -> remet le décalage X à 0 (parfaitement centré)
        self.cb_ah.currentIndexChanged.connect(self._recentrer_x)
        form.addRow(_lbl(_fr("Horizontal", "Horizontal")), self.cb_ah)
        self.cb_av = self._combo(_ALIGN_V, "milieu", champ)
        self.cb_av.currentIndexChanged.connect(self._recentrer_y)
        form.addRow(_lbl(_fr("Vertical", "Vertical")), self.cb_av)
        row_off = QHBoxLayout()
        row_off.setSpacing(4)
        self.sp_dx = self._spin(-60, 60, 0.0, 0.5, champ, " mm")
        self.sp_dy = self._spin(-40, 40, 0.0, 0.5, champ, " mm")
        for s in (self.sp_dx, self.sp_dy):
            s.setMaximumWidth(76)               # deux côte à côte -> rentre
        row_off.addWidget(self.sp_dx)
        row_off.addWidget(self.sp_dy)
        form.addRow(_lbl(_fr("Décalage X / Y", "Offset X / Y")), row_off)
        self.sp_relief = self._spin(0.3, 1.5, 0.6, 0.1, champ, " mm")
        form.addRow(_lbl(_fr("Relief", "Relief")), self.sp_relief)
        v.addLayout(form)

        # couleur
        crow = QHBoxLayout()
        crow.addWidget(_lbl(_fr("Couleur", "Color")))
        self.btn_coul = QPushButton()
        self.btn_coul.setFixedHeight(24)
        self.btn_coul.setCursor(Qt.PointingHandCursor)
        self._maj_bouton_couleur()
        self.btn_coul.clicked.connect(self._choisir_couleur)
        crow.addWidget(self.btn_coul, 1)
        v.addLayout(crow)

    def _recentrer_x(self):
        if self.cb_ah.currentData() == "centre":
            self.sp_dx.setValue(0.0)            # centrage horizontal parfait

    def _recentrer_y(self):
        if self.cb_av.currentData() == "milieu":
            self.sp_dy.setValue(0.0)            # centrage vertical parfait

    def _spin(self, mini, maxi, val, pas, style, suffix=""):
        s = QDoubleSpinBox()
        s.setRange(mini, maxi)
        s.setValue(val)
        s.setSingleStep(pas)
        s.setDecimals(1)
        s.setSuffix(suffix)
        s.setStyleSheet(style)
        from PySide6.QtWidgets import QSizePolicy
        s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        s.valueChanged.connect(self.change)
        return s

    def _combo(self, options, defaut, style):
        c = QComboBox()
        for val, fr, en in options:
            c.addItem(_fr(fr, en), val)
        c.setCurrentIndex(max(0, [o[0] for o in options].index(defaut)))
        c.setStyleSheet(style)
        c.currentIndexChanged.connect(self.change)
        return c

    def _maj_bouton_couleur(self):
        c = QColor(self._couleur)
        fg = "#000000" if c.lightnessF() > 0.6 else "#FFFFFF"
        self.btn_coul.setText(self._couleur.upper())
        self.btn_coul.setStyleSheet(
            f"QPushButton {{ background: {self._couleur}; color: {fg}; border: "
            f"1px solid {self._pal['INACTIVE']}; border-radius: 4px; "
            f"font-weight: bold; }}")

    def _choisir_couleur(self):
        c = _choisir_couleur(self, self._couleur,
                             _fr("Couleur de l'élément", "Element color"))
        if c.isValid():
            self._couleur = c.name()
            self._maj_bouton_couleur()
            self.change.emit()

    def _choisir_image(self):
        chemin, _f = QFileDialog.getOpenFileName(
            self, _fr("Choisir une image", "Choose image"), "",
            "Image (*.svg *.png *.jpg *.jpeg)")
        if chemin:
            self._image = chemin
            self.btn_img.setText(Path(chemin).name[:24])
            self.change.emit()

    def element(self):
        if self.type_el == "texte":
            return CV.ElementTexte(
                texte=self.le.text(), police=self.cb_pol.currentData(),
                hauteur=self.sp_h.value(), align_h=self.cb_ah.currentData(),
                align_v=self.cb_av.currentData(), dx=self.sp_dx.value(),
                dy=self.sp_dy.value(), relief=self.sp_relief.value(),
                couleur=self._couleur)
        return CV.ElementLogo(
            chemin=self._image, largeur=self.sp_h.value(),
            align_h=self.cb_ah.currentData(), align_v=self.cb_av.currentData(),
            dx=self.sp_dx.value(), dy=self.sp_dy.value(),
            relief=self.sp_relief.value(), couleur=self._couleur)


class CartePanel(QWidget):
    """Panneau de conception de carte de visite (colonne de droite)."""

    apercu_pret = Signal(object)        # trimesh.Scene
    exporter_demande = Signal(object, object)   # (CarteSpec, couleurs)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pal = _THEME.palette()
        self._couleur_base = "#F2EEE6"
        self.setStyleSheet(f"background: {self._pal['BG_PANEL']};")
        self._editeurs: list[_ElementEditor] = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._emettre_apercu)
        self._build()
        QTimer.singleShot(0, self._planifier_apercu)   # aperçu initial (carte vide)

    def _build(self):
        pal = self._pal
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        entete = QHBoxLayout()
        titre = QLabel(_fr("Carte de visite", "Business card"))
        titre.setFont(QFont("Segoe UI", 13, QFont.Bold))
        titre.setStyleSheet(f"color: {PRO_CYAN}; background: transparent;")
        entete.addWidget(titre)
        entete.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(24, 24)
        bx.setCursor(Qt.PointingHandCursor)
        bx.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};"
            f" border: none; font-size: 12px; }} QPushButton:hover {{ color: "
            f"{pal['TEXT_PRIMARY']}; }}")
        bx.clicked.connect(self.close_requested)
        entete.addWidget(bx)
        root.addLayout(entete)

        # carte : format + couleur de base
        champ = (f"QDoubleSpinBox {{ background: {pal['BG_SURFACE']}; color: "
                 f"{pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                 f"border-radius: 4px; padding: 2px 5px; }}"
                 ) + _spinbox_qss(pal, "rgba(34,211,238,0.35)")
        from PySide6.QtWidgets import QSizePolicy
        fmt = QFormLayout()
        fmt.setSpacing(4)
        fmt.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            return l

        def _fmt_spin(sp):
            sp.setStyleSheet(champ)
            sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            sp.valueChanged.connect(self._planifier_apercu)
            return sp
        self.sp_l = _fmt_spin(QDoubleSpinBox()); self.sp_l.setRange(40, 120); self.sp_l.setDecimals(0); self.sp_l.setValue(85); self.sp_l.setSuffix(" mm")
        self.sp_h = _fmt_spin(QDoubleSpinBox()); self.sp_h.setRange(30, 90); self.sp_h.setDecimals(0); self.sp_h.setValue(55); self.sp_h.setSuffix(" mm")
        row = QHBoxLayout(); row.setSpacing(4)
        for s in (self.sp_l, self.sp_h):
            s.setMaximumWidth(84)
        row.addWidget(self.sp_l); row.addWidget(self.sp_h)
        fmt.addRow(_lbl(_fr("Format L × H", "Size W × H")), row)
        self.sp_ep = _fmt_spin(QDoubleSpinBox()); self.sp_ep.setRange(0.8, 4); self.sp_ep.setValue(1.6); self.sp_ep.setSingleStep(0.2); self.sp_ep.setDecimals(1); self.sp_ep.setSuffix(" mm")
        fmt.addRow(_lbl(_fr("Épaisseur", "Thickness")), self.sp_ep)
        crow = QHBoxLayout()
        crow.addWidget(_lbl(_fr("Couleur du fond", "Base color")))
        self.btn_base = QPushButton()
        self.btn_base.setFixedHeight(24)
        self.btn_base.setCursor(Qt.PointingHandCursor)
        self._maj_base()
        self.btn_base.clicked.connect(self._choisir_base)
        crow.addWidget(self.btn_base, 1)
        root.addLayout(fmt)
        root.addLayout(crow)

        # boutons d'ajout
        addrow = QHBoxLayout()
        for txt, tp in ((_fr("+ Texte", "+ Text"), "texte"),
                        (_fr("+ Logo", "+ Logo"), "logo")):
            b = QPushButton(txt)
            b.setMinimumHeight(28)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: {pal['BG_SURFACE']}; color: "
                f"{pal['TEXT_PRIMARY']}; border: 1px solid {PRO_CYAN}; "
                f"border-radius: 6px; font-weight: bold; }} "
                f"QPushButton:hover {{ background: rgba(34,211,238,0.15); }}")
            b.clicked.connect(lambda _c=False, t=tp: self._ajouter(t))
            addrow.addWidget(b)
        root.addLayout(addrow)

        # liste scrollable des éléments
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._liste = QVBoxLayout(holder)
        self._liste.setContentsMargins(0, 0, 0, 0)
        self._liste.setSpacing(6)
        self._liste.addStretch()
        self._scroll.setWidget(holder)
        root.addWidget(self._scroll, 1)

        # export
        self.btn_export = QPushButton(_fr("Exporter la carte (multicouleur)",
                                          "Export card (multicolor)"))
        self.btn_export.setMinimumHeight(34)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, "
            f"stop:0 {PRO_CYAN}, stop:1 {PRO_VIOLET}); color: #fff; border: "
            f"none; border-radius: 6px; font-weight: bold; }}")
        self.btn_export.clicked.connect(self._exporter)
        root.addWidget(self.btn_export)
        self._statut = QLabel("")
        self._statut.setWordWrap(True)
        self._statut.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent; font-size: 9pt;")
        root.addWidget(self._statut)

    # ── couleur de base ──
    def _maj_base(self):
        c = QColor(self._couleur_base)
        fg = "#000000" if c.lightnessF() > 0.6 else "#FFFFFF"
        self.btn_base.setText(self._couleur_base.upper())
        self.btn_base.setStyleSheet(
            f"QPushButton {{ background: {self._couleur_base}; color: {fg}; "
            f"border: 1px solid {self._pal['INACTIVE']}; border-radius: 4px; "
            f"font-weight: bold; }}")

    def _choisir_base(self):
        c = _choisir_couleur(self, self._couleur_base,
                             _fr("Couleur du fond", "Base color"))
        if c.isValid():
            self._couleur_base = c.name()
            self._maj_base()
            self._planifier_apercu()

    # ── éléments ──
    def _ajouter(self, type_el: str):
        ed = _ElementEditor(type_el, self._pal)
        ed.change.connect(self._planifier_apercu)
        ed.supprime.connect(self._retirer)
        self._editeurs.append(ed)
        self._liste.insertWidget(self._liste.count() - 1, ed)
        self._planifier_apercu()

    def _retirer(self, ed):
        if ed in self._editeurs:
            self._editeurs.remove(ed)
            ed.setParent(None)
            ed.deleteLater()
            self._planifier_apercu()

    # ── aperçu ──
    def _spec(self) -> CV.CarteSpec:
        return CV.CarteSpec(
            largeur=self.sp_l.value(), hauteur=self.sp_h.value(),
            ep=self.sp_ep.value(), couleur_base=self._couleur_base,
            elements=[e.element() for e in self._editeurs])

    def _planifier_apercu(self):
        self._debounce.start()

    def _emettre_apercu(self):
        try:
            # aperçu PAR ÉLÉMENT (mise à jour en place côté viewer -> pas de
            # clignotement quand on tape, et chaque élément est déplaçable)
            scene = CV.construire_apercu(self._spec())
            self.apercu_pret.emit(scene)
        except Exception as exc:
            self._statut.setText("⚠ " + str(exc)[:80])

    def deplacer_element(self, index: int, dx: float, dy: float):
        """Reçu du viewer quand un élément est glissé à la souris : ajoute le
        décalage aux champs X/Y de l'élément (l'aperçu se met à jour en place)."""
        if 0 <= index < len(self._editeurs):
            ed = self._editeurs[index]
            ed.sp_dx.setValue(ed.sp_dx.value() + dx)
            ed.sp_dy.setValue(ed.sp_dy.value() + dy)

    def _exporter(self):
        try:
            spec = self._spec()
            _scene, couleurs = CV.construire(spec)
            self.exporter_demande.emit(spec, couleurs)
        except Exception as exc:
            self._statut.setText("⚠ " + str(exc)[:80])

    def set_statut(self, txt: str):
        self._statut.setText(txt)
