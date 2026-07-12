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
    QFormLayout, QDialog, QDialogButtonBox, QCheckBox,
)

from core.i18n import _, lang
from core.neogen import carte_visite as CV
from ui.styles.theme import MANAGER as _THEME, spinbox_qss as _spinbox_qss

PRO_CYAN, PRO_VIOLET = "#22D3EE", "#A855F7"

_ALIGN_H = [("gauche", "Gauche", "Left"), ("centre", "Centre", "Center"),
            ("droite", "Droite", "Right")]
_ALIGN_V = [("haut", "Haut", "Top"), ("milieu", "Milieu", "Middle"),
            ("bas", "Bas", "Bottom")]
_ORIENT = [("horizontal", "Horizontal", "Horizontal"),
           ("vertical", "Vertical", "Vertical")]


def _fr(fr, en):
    return fr if lang() == "fr" else en


def _champ_style(pal: dict) -> str:
    """Style commun des champs (spin/combo/lineedit), dépendant du thème."""
    return (f"QDoubleSpinBox, QComboBox, QLineEdit {{ background: "
            f"{pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; border: "
            f"1px solid {pal['INACTIVE']}; border-radius: 4px; padding: "
            f"2px 5px; }}") + _spinbox_qss(pal, "rgba(34,211,238,0.35)")


class LithoParamsDialog(QDialog):
    """Réglages de conversion en lithophanie : épaisseur mini (zones claires),
    contraste (épaisseur ajoutée aux zones foncées), et inversion clair/foncé."""

    def __init__(self, pal: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_fr("Lithophanie — réglages", "Lithophane — settings"))
        self.setStyleSheet(
            f"QDialog {{ background: {pal['BG_PANEL']}; }} "
            f"QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }} "
            + _champ_style(pal)
            + f"QCheckBox {{ color: {pal['TEXT_PRIMARY']}; }}")
        v = QVBoxLayout(self)
        info = QLabel(_fr(
            "La carte devient une plaque translucide DEBOUT : l'épaisseur module "
            "la lumière (fin = clair, épais = foncé). À imprimer en PLA blanc.",
            "The card becomes a STANDING translucent plate: thickness modulates "
            "light (thin = bright, thick = dark). Print in white PLA."))
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {pal['TEXT_LABEL']}; font-size: 9pt;")
        v.addWidget(info)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.sp_base = QDoubleSpinBox(); self.sp_base.setRange(0.4, 1.5)
        self.sp_base.setValue(0.8); self.sp_base.setSingleStep(0.1)
        self.sp_base.setDecimals(1); self.sp_base.setSuffix(" mm")
        form.addRow(QLabel(_fr("Épaisseur mini (clair)", "Min thickness (bright)")), self.sp_base)
        self.sp_contr = QDoubleSpinBox(); self.sp_contr.setRange(0.6, 4.0)
        self.sp_contr.setValue(2.2); self.sp_contr.setSingleStep(0.2)
        self.sp_contr.setDecimals(1); self.sp_contr.setSuffix(" mm")
        form.addRow(QLabel(_fr("Contraste (relief foncé)", "Contrast (dark relief)")), self.sp_contr)
        v.addLayout(form)
        self.cb_inv = QCheckBox(_fr("Inverser (design clair sur fond foncé)",
                                    "Invert (bright design on dark background)"))
        v.addWidget(self.cb_inv)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def params(self) -> dict:
        return {"ep_base": self.sp_base.value(),
                "contraste": self.sp_contr.value(),
                "inverser": self.cb_inv.isChecked()}


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
        self._reduit = False
        self._build()

    def set_actif(self, actif: bool):
        """Encadre l'éditeur quand SON élément est sélectionné dans le viewer
        (clic sur l'élément de la carte) → on voit tout de suite duquel il s'agit."""
        pal = self._pal
        if actif:
            self.setStyleSheet(
                f"QFrame {{ background: {pal['BG_ELEVATED']}; border: 2px solid "
                f"{PRO_CYAN}; border-radius: 6px; }}")
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {pal['BG_SURFACE']}; border: 1px solid "
                f"{pal['INACTIVE']}; border-radius: 6px; }}")

    def _build(self):
        pal = self._pal
        self.setStyleSheet(
            f"QFrame {{ background: {pal['BG_SURFACE']}; border: 1px solid "
            f"{pal['INACTIVE']}; border-radius: 6px; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(5)
        champ = _champ_style(pal)

        # en-tête CLIQUABLE : flèche + titre (repli/dépli) + supprimer
        _titres = {"texte": _fr("Texte", "Text"),
                   "logo": _fr("Logo (image)", "Logo (image)"),
                   "trait": _fr("Trait", "Line"),
                   "cadre": _fr("Cadre", "Frame")}
        self._titre_base = _titres.get(self.type_el, self.type_el)
        head = QHBoxLayout()
        self._btn_titre = QPushButton()
        self._btn_titre.setCursor(Qt.PointingHandCursor)
        self._btn_titre.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_PRIMARY']};"
            f" border: none; text-align: left; font-weight: bold; }}")
        self._btn_titre.clicked.connect(self._toggle_reduit)
        head.addWidget(self._btn_titre, 1)
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(20, 20)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_LABEL']};"
            f" border: none; }} QPushButton:hover {{ color: #E5484D; }}")
        btn_x.clicked.connect(lambda: self.supprime.emit(self))
        head.addWidget(btn_x)
        v.addLayout(head)

        # corps repliable (masqué quand la case est réduite)
        self._corps = QWidget()
        self._corps.setStyleSheet("background: transparent;")
        corps_lay = QVBoxLayout(self._corps)
        corps_lay.setContentsMargins(0, 2, 0, 0)
        corps_lay.setSpacing(5)

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
            self.le.textChanged.connect(self._maj_titre)   # titre = contenu du texte
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
            self.sp_esp = self._spin(0.0, 10.0, 0.0, 0.5, champ, " mm")
            form.addRow(_lbl(_fr("Espacement", "Spacing")), self.sp_esp)
        elif self.type_el == "logo":
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
        elif self.type_el == "trait":
            self.sp_long = self._spin(1, 100, 40.0, 1.0, champ, " mm")
            form.addRow(_lbl(_fr("Longueur", "Length")), self.sp_long)
            self.sp_ep = self._spin(0.3, 8, 1.0, 0.1, champ, " mm")
            form.addRow(_lbl(_fr("Épaisseur", "Thickness")), self.sp_ep)
            self.cb_orient = self._combo(_ORIENT, "horizontal", champ)
            form.addRow(_lbl(_fr("Orientation", "Orientation")), self.cb_orient)
        elif self.type_el == "cadre":
            self.sp_larg = self._spin(3, 100, 60.0, 1.0, champ, " mm")
            form.addRow(_lbl(_fr("Largeur", "Width")), self.sp_larg)
            self.sp_haut = self._spin(3, 80, 35.0, 1.0, champ, " mm")
            form.addRow(_lbl(_fr("Hauteur", "Height")), self.sp_haut)
            self.sp_ep = self._spin(0.3, 10, 1.5, 0.1, champ, " mm")
            form.addRow(_lbl(_fr("Épaisseur", "Thickness")), self.sp_ep)

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
        corps_lay.addLayout(form)

        # couleur
        crow = QHBoxLayout()
        crow.addWidget(_lbl(_fr("Couleur", "Color")))
        self.btn_coul = QPushButton()
        self.btn_coul.setFixedHeight(24)
        self.btn_coul.setCursor(Qt.PointingHandCursor)
        self._maj_bouton_couleur()
        self.btn_coul.clicked.connect(self._choisir_couleur)
        crow.addWidget(self.btn_coul, 1)
        corps_lay.addLayout(crow)
        v.addWidget(self._corps)
        self._maj_titre()

    def _maj_titre(self):
        """Titre = flèche de repli + type ; pour un texte, on y ajoute le contenu
        saisi (pour reconnaître chaque case une fois réduite)."""
        fleche = "▶  " if getattr(self, "_reduit", False) else "▼  "
        base = self._titre_base
        if self.type_el == "texte":
            txt = (self.le.text() or "").strip()
            if txt:
                base = f"{base} : {txt[:18]}"
        self._btn_titre.setText(fleche + base)

    def _toggle_reduit(self):
        self.set_reduit(not getattr(self, "_reduit", False))

    def set_reduit(self, reduit: bool):
        """Réduit (masque le corps) ou déplie l'éditeur."""
        self._reduit = bool(reduit)
        self._corps.setVisible(not self._reduit)
        self._maj_titre()

    def refresh_theme(self):
        """Ré-applique les couleurs du thème courant (titres, labels, champs)."""
        self._pal = _THEME.palette()
        pal = self._pal
        champ = _champ_style(pal)
        self.setStyleSheet(
            f"QFrame {{ background: {pal['BG_SURFACE']}; border: 1px solid "
            f"{pal['INACTIVE']}; border-radius: 6px; }}")
        if hasattr(self, "_btn_titre"):
            self._btn_titre.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {pal['TEXT_PRIMARY']};"
                f" border: none; text-align: left; font-weight: bold; }}")
        for w in self.findChildren(QLabel):
            if w.objectName() == "carteTitre":
                w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; font-weight: bold;"
                                f" border: none; background: transparent;")
            else:
                w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; border: none;"
                                f" background: transparent;")
        for cls in (QDoubleSpinBox, QComboBox, QLineEdit):
            for w in self.findChildren(cls):
                w.setStyleSheet(champ)
        self._maj_bouton_couleur()

    @staticmethod
    def _selc(cb, val):
        for i in range(cb.count()):
            if cb.itemData(i) == val:
                cb.setCurrentIndex(i)
                return

    def charger(self, d: dict):
        """Recharge les valeurs d'un élément sauvegardé dans les widgets."""
        self._couleur = d.get("couleur", self._couleur)
        self._maj_bouton_couleur()
        if self.type_el == "texte":
            self.le.setText(d.get("texte", ""))
            self._selc(self.cb_pol, d.get("police"))
            self.sp_h.setValue(float(d.get("hauteur", 5.0)))
            self.sp_esp.setValue(float(d.get("espacement", 0.0)))
        elif self.type_el == "logo":
            self._image = d.get("chemin", "") or ""
            if self._image:
                self.btn_img.setText(Path(self._image).name[:24])
            self.sp_h.setValue(float(d.get("largeur", 18.0)))
        elif self.type_el == "trait":
            self.sp_long.setValue(float(d.get("longueur", 40.0)))
            self.sp_ep.setValue(float(d.get("epaisseur", 1.0)))
            self._selc(self.cb_orient, d.get("orientation", "horizontal"))
        elif self.type_el == "cadre":
            self.sp_larg.setValue(float(d.get("largeur", 60.0)))
            self.sp_haut.setValue(float(d.get("hauteur", 35.0)))
            self.sp_ep.setValue(float(d.get("epaisseur", 1.5)))
        # alignements AVANT les décalages (sinon « centre » remet dx/dy à 0)
        self._selc(self.cb_ah, d.get("align_h", "centre"))
        self._selc(self.cb_av, d.get("align_v", "milieu"))
        self.sp_dx.setValue(float(d.get("dx", 0.0)))
        self.sp_dy.setValue(float(d.get("dy", 0.0)))
        self.sp_relief.setValue(float(d.get("relief", 0.6)))

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
        _common = dict(align_h=self.cb_ah.currentData(),
                       align_v=self.cb_av.currentData(),
                       dx=self.sp_dx.value(), dy=self.sp_dy.value(),
                       relief=self.sp_relief.value(), couleur=self._couleur)
        if self.type_el == "texte":
            return CV.ElementTexte(
                texte=self.le.text(), police=self.cb_pol.currentData(),
                hauteur=self.sp_h.value(), espacement=self.sp_esp.value(),
                **_common)
        if self.type_el == "trait":
            return CV.ElementTrait(
                longueur=self.sp_long.value(), epaisseur=self.sp_ep.value(),
                orientation=self.cb_orient.currentData(), **_common)
        if self.type_el == "cadre":
            return CV.ElementCadre(
                largeur=self.sp_larg.value(), hauteur=self.sp_haut.value(),
                epaisseur=self.sp_ep.value(), **_common)
        return CV.ElementLogo(chemin=self._image, largeur=self.sp_h.value(),
                              **_common)


class CartePanel(QWidget):
    """Panneau de conception de carte de visite (colonne de droite)."""

    apercu_pret = Signal(object)        # trimesh.Scene
    exporter_demande = Signal(object, object)   # (CarteSpec, couleurs)
    exporter_litho_demande = Signal(object, object)   # (CarteSpec, params litho)
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
        titre.setObjectName("carteTitre")
        titre.setFont(QFont("Segoe UI", 13, QFont.Bold))
        titre.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
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
        champ = _champ_style(pal)
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
                        (_fr("+ Logo", "+ Logo"), "logo"),
                        (_fr("+ Trait", "+ Line"), "trait"),
                        (_fr("+ Cadre", "+ Frame"), "cadre")):
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

        # enregistrer / rouvrir / supprimer un modèle
        modrow = QHBoxLayout()
        modrow.setSpacing(4)
        for txt, slot in ((_fr("Enregistrer", "Save"), self._enregistrer_modele),
                          (_fr("Ouvrir…", "Open…"), self._ouvrir_modele),
                          (_fr("Supprimer…", "Delete…"), self._supprimer_modele)):
            bm = QPushButton(txt)
            bm.setMinimumHeight(26)
            bm.setCursor(Qt.PointingHandCursor)
            bm.setStyleSheet(
                f"QPushButton {{ background: {pal['BG_SURFACE']}; color: "
                f"{pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                f"border-radius: 6px; }} "
                f"QPushButton:hover {{ border-color: {pal['ACCENT_BRIGHT']}; }}")
            bm.clicked.connect(slot)
            modrow.addWidget(bm)
        root.addLayout(modrow)

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

        # Conversion lithophanie : même carte, mais préparée comme une plaque
        # translucide monomatière (l'épaisseur des reliefs donne le rendu
        # rétroéclairé) + profil d'impression lithophanie (100 % / 4 parois / fin).
        self.btn_litho = QPushButton(_fr("Convertir en lithophanie",
                                         "Convert to lithophane"))
        self.btn_litho.setMinimumHeight(30)
        self.btn_litho.setCursor(Qt.PointingHandCursor)
        self.btn_litho.setStyleSheet(
            f"QPushButton {{ background: {pal['BG_ELEVATED']}; color: "
            f"{pal['TEXT_PRIMARY']}; border: 1px solid {PRO_CYAN}; "
            f"border-radius: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: rgba(34,211,238,0.15); }}")
        self.btn_litho.setToolTip(_fr(
            "Prépare un .3MF lithophanie : une seule matière translucide + "
            "réglages d'impression lithophanie (à imprimer en PLA blanc/naturel).",
            "Prepares a lithophane .3MF: a single translucent material + "
            "lithophane print settings (print in white/natural PLA)."))
        self.btn_litho.clicked.connect(self._exporter_litho)
        root.addWidget(self.btn_litho)

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
        # Réduire les cases existantes pour gagner de la place : seule la
        # nouvelle reste dépliée.
        for ed_existant in self._editeurs:
            ed_existant.set_reduit(True)
        ed = _ElementEditor(type_el, self._pal)
        ed.change.connect(self._planifier_apercu)
        ed.supprime.connect(self._retirer)
        self._editeurs.append(ed)
        self._liste.insertWidget(self._liste.count() - 1, ed)
        self._planifier_apercu()
        return ed

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

    # ── sauvegarde / réédition ──
    def to_dict(self) -> dict:
        import dataclasses
        spec = self._spec()
        return {"largeur": spec.largeur, "hauteur": spec.hauteur, "ep": spec.ep,
                "couleur_base": spec.couleur_base,
                "elements": [dataclasses.asdict(e) for e in spec.elements]}

    def from_dict(self, d: dict):
        self.sp_l.setValue(float(d.get("largeur", 85.0)))
        self.sp_h.setValue(float(d.get("hauteur", 55.0)))
        self.sp_ep.setValue(float(d.get("ep", 1.6)))
        self._couleur_base = d.get("couleur_base", "#FFFFFF")
        self._maj_base()
        for ed in list(self._editeurs):
            self._retirer(ed)
        for eld in d.get("elements", []):
            ed = self._ajouter(eld.get("type", "texte"))
            ed.charger(eld)
        self._planifier_apercu()

    def _dossier_cartes(self):
        d = Path.home() / ".neoslice" / "cartes"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _enregistrer_modele(self):
        import json, re
        from PySide6.QtWidgets import QInputDialog
        nom, ok = QInputDialog.getText(
            self, _fr("Enregistrer le modèle", "Save model"),
            _fr("Nom du modèle :", "Model name:"))
        if not ok or not nom.strip():
            return
        slug = re.sub(r"[^\w\- ]", "", nom.strip())[:40] or "carte"
        try:
            (self._dossier_cartes() / (slug + ".json")).write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8")
            self.set_statut("✓ " + _fr(f"Modèle « {slug} » enregistré",
                                       f'Model "{slug}" saved'))
        except Exception as exc:
            self.set_statut("⚠ " + str(exc)[:80])

    def _ouvrir_modele(self):
        import json
        from PySide6.QtWidgets import QInputDialog
        fichiers = sorted(self._dossier_cartes().glob("*.json"))
        if not fichiers:
            self.set_statut(_fr("Aucun modèle enregistré.", "No saved model."))
            return
        noms = [f.stem for f in fichiers]
        nom, ok = QInputDialog.getItem(
            self, _fr("Ouvrir un modèle", "Open model"),
            _fr("Modèle :", "Model:"), noms, 0, False)
        if not ok or not nom:
            return
        try:
            data = json.loads(
                (self._dossier_cartes() / (nom + ".json")).read_text(encoding="utf-8"))
            self.from_dict(data)
            self.set_statut("✓ " + _fr(f"Modèle « {nom} » chargé",
                                       f'Model "{nom}" loaded'))
        except Exception as exc:
            self.set_statut("⚠ " + str(exc)[:80])

    def _supprimer_modele(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        fichiers = sorted(self._dossier_cartes().glob("*.json"))
        if not fichiers:
            self.set_statut(_fr("Aucun modèle enregistré.", "No saved model."))
            return
        noms = [f.stem for f in fichiers]
        nom, ok = QInputDialog.getItem(
            self, _fr("Supprimer un modèle", "Delete model"),
            _fr("Modèle :", "Model:"), noms, 0, False)
        if not ok or not nom:
            return
        rep = QMessageBox.question(
            self, _fr("Supprimer", "Delete"),
            _fr(f"Supprimer définitivement le modèle « {nom} » ?",
                f'Permanently delete model "{nom}"?'))
        if rep != QMessageBox.StandardButton.Yes:
            return
        try:
            (self._dossier_cartes() / (nom + ".json")).unlink()
            self.set_statut("✓ " + _fr(f"Modèle « {nom} » supprimé",
                                       f'Model "{nom}" deleted'))
        except Exception as exc:
            self.set_statut("⚠ " + str(exc)[:80])

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

    def supprimer_element(self, index: int):
        """Reçu du viewer quand on presse Suppr avec un élément sélectionné :
        retire l'éditeur correspondant."""
        if 0 <= index < len(self._editeurs):
            self._retirer(self._editeurs[index])

    def surligner_element(self, index: int):
        """Reçu du viewer au clic sur un élément de la carte : encadre la section
        correspondante dans la colonne (et la fait défiler à vue). index=-1 → aucune."""
        for i, ed in enumerate(self._editeurs):
            ed.set_actif(i == index)
        if 0 <= index < len(self._editeurs):
            self._editeurs[index].set_reduit(False)   # déplie l'élément cliqué
            try:
                self._scroll.ensureWidgetVisible(self._editeurs[index])
            except Exception:
                pass

    def _exporter(self):
        try:
            spec = self._spec()
            _scene, couleurs = CV.construire(spec)
            self.exporter_demande.emit(spec, couleurs)
        except Exception as exc:
            self._statut.setText("⚠ " + str(exc)[:80])

    def _exporter_litho(self):
        """Ouvre le menu de personnalisation LITHOPHANIE, puis prépare la carte en
        vraie lithophanie DEBOUT (plaque translucide à épaisseur modulée)."""
        try:
            spec = self._spec()
        except Exception as exc:
            self._statut.setText("⚠ " + str(exc)[:80])
            return
        dlg = LithoParamsDialog(self._pal, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.exporter_litho_demande.emit(spec, dlg.params())

    def set_statut(self, txt: str):
        self._statut.setText(txt)

    def refresh_theme(self):
        """Ré-applique le thème courant (corrige les labels invisibles quand le
        panneau a été construit dans un autre thème). Titres = accent standard
        du thème (comme les autres modules), plus de cyan sur les polices."""
        self._pal = _THEME.palette()
        pal = self._pal
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")
        champ = _champ_style(pal)
        for w in self.findChildren(QLabel):
            if w.objectName() == "carteTitre":
                w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            elif w is getattr(self, "_statut", None):
                w.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; font-size: 9pt;")
            else:
                w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; border: none; background: transparent;")
        for w in self.findChildren(QDoubleSpinBox):
            w.setStyleSheet(champ)
        self._maj_base()
        for ed in self._editeurs:
            ed.refresh_theme()
