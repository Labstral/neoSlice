"""Espace Pro — hub de gestion d'atelier (réservé aux licences Pro).

Phase 1 : inventaire de bobines + accès au devis. Onglets Clients / Facturation /
Tableau de bord présents mais marqués « Bientôt ». Données 100 % locales
(core.business.store). Thème clair/sombre.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QScrollArea, QFrame, QStackedWidget, QFileDialog, QMessageBox,
    QColorDialog, QGridLayout,
)

from core.i18n import _
from core.business import store
from data.filaments import FILAMENTS, FAMILLES_ORDRE
from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO

_LOW_STOCK_G = 100.0

# Finitions d'aspect (le « PLA Mat » de Kévin = matériau PLA + finition Mat).
# On stocke une clé canonique ; le libellé est traduit à l'affichage.
_FINITIONS = [
    ("", "spool.finish_none"), ("mat", "spool.finish_matte"),
    ("soie", "spool.finish_silk"), ("metallique", "spool.finish_metal"),
    ("bois", "spool.finish_wood"), ("paillete", "spool.finish_glitter"),
    ("translucide", "spool.finish_translucent"), ("fluo", "spool.finish_fluo"),
    ("bicolore", "spool.finish_dual"),
]


def _finition_label(key: str) -> str:
    for k, i18n_key in _FINITIONS:
        if k == key:
            return _(i18n_key)
    return key or ""


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire d'ajout / édition d'une bobine
# ══════════════════════════════════════════════════════════════════════════════
class SpoolForm(QDialog):
    def __init__(self, parent=None, spool: dict | None = None):
        super().__init__(parent)
        self._spool = spool or {}
        self._color_hex = self._spool.get("couleur_hex", "#1E90FF")
        self.setWindowTitle(_("spool.edit") if spool else _("spool.add"))
        self.setMinimumWidth(420)
        self._edits: dict[str, QLineEdit] = {}
        self._build()
        self._apply_theme()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        title = QLabel(self.windowTitle())
        title.setFont(QFont(FONT_MAIN, 12, QFont.Bold))
        lay.addWidget(title)
        self._title = title

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        lay.addLayout(grid)
        row = 0

        # Matériau (catalogue de types)
        self._material = QComboBox()
        for fam in FAMILLES_ORDRE:
            for name, d in FILAMENTS.items():
                if d.get("famille") == fam:
                    self._material.addItem(name, name)
        # filaments hors familles ordonnées
        for name in FILAMENTS:
            if self._material.findData(name) < 0:
                self._material.addItem(name, name)
        cur_mat = self._spool.get("materiau", "PLA")
        i = self._material.findData(cur_mat)
        self._material.setCurrentIndex(max(0, i))
        grid.addWidget(self._lbl(_("spool.material")), row, 0)
        grid.addWidget(self._material, row, 1); row += 1

        # Finition (aspect) — Mat, Soie, Métallique… → « PLA Mat » = PLA + Mat
        self._finition = QComboBox()
        for key, i18n_key in _FINITIONS:
            self._finition.addItem(_(i18n_key), key)
        fi = self._finition.findData(self._spool.get("finition", ""))
        self._finition.setCurrentIndex(max(0, fi))
        grid.addWidget(self._lbl(_("spool.finish")), row, 0)
        grid.addWidget(self._finition, row, 1); row += 1

        # Marque / nom couleur
        row = self._add_edit(grid, row, "marque", _("spool.brand"))
        row = self._add_edit(grid, row, "couleur_nom", _("spool.color_name"))

        # Couleur (bouton ouvrant un sélecteur)
        self._color_btn = QPushButton()
        self._color_btn.setFixedHeight(26)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)
        grid.addWidget(self._lbl(_("spool.color")), row, 0)
        grid.addWidget(self._color_btn, row, 1); row += 1

        # Stock & coût
        row = self._add_edit(grid, row, "poids_total_g", _("spool.total_g"), num=True,
                             default="1000")
        row = self._add_edit(grid, row, "poids_restant_g", _("spool.remaining_g"), num=True,
                             default="1000")
        row = self._add_edit(grid, row, "cout_total", _("spool.cost_total"), num=True,
                             default="0")
        row = self._add_edit(grid, row, "seuil_reappro_g", _("spool.threshold"), num=True,
                             default="150")
        # Détails
        row = self._add_edit(grid, row, "fournisseur", _("spool.vendor"))
        row = self._add_edit(grid, row, "emplacement", _("spool.location"))

        # Boutons
        btns = QHBoxLayout()
        btns.addStretch()
        self._cancel = QPushButton(_("spool.cancel"))
        self._cancel.setCursor(Qt.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("spool.save"))
        self._save.setCursor(Qt.PointingHandCursor)
        self._save.clicked.connect(self.accept)
        btns.addWidget(self._cancel)
        btns.addWidget(self._save)
        lay.addLayout(btns)

    def _lbl(self, text: str) -> QLabel:
        q = QLabel(text)
        q.setFont(QFont(FONT_MAIN, 9))
        return q

    def _add_edit(self, grid, row, key, label, num=False, default=""):
        e = QLineEdit(str(self._spool.get(key, default)))
        e.setFont(QFont(FONT_MONO, 9))
        if num:
            from PySide6.QtGui import QDoubleValidator
            e.setValidator(QDoubleValidator(0.0, 1e7, 2, e))
        self._edits[key] = e
        grid.addWidget(self._lbl(label), row, 0)
        grid.addWidget(e, row, 1)
        return row + 1

    def _pick_color(self):
        from PySide6.QtGui import QColor
        col = QColorDialog.getColor(QColor(self._color_hex), self, _("spool.color"))
        if col.isValid():
            self._color_hex = col.name()
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._color_btn.setText(self._color_hex)
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background: {self._color_hex}; color: white; "
            f"border: 1px solid rgba(0,0,0,0.3); border-radius: 3px; }}"
        )

    def data(self) -> dict:
        out = {"materiau": self._material.currentData() or "PLA",
               "finition": self._finition.currentData() or "",
               "couleur_hex": self._color_hex}
        for key, e in self._edits.items():
            txt = e.text().strip()
            if key in ("poids_total_g", "poids_restant_g", "cout_total", "seuil_reappro_g"):
                try:
                    out[key] = float(txt.replace(",", ".") or 0)
                except ValueError:
                    out[key] = 0.0
            else:
                out[key] = txt
        return out

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        edit_css = (f"QLineEdit, QComboBox {{ background: {pal['BG_INPUT']}; "
                    f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                    f"border-radius: 3px; padding: 3px 6px; }}")
        self._material.setStyleSheet(edit_css)
        self._finition.setStyleSheet(edit_css)
        for e in self._edits.values():
            e.setStyleSheet(edit_css)
        for q in self.findChildren(QLabel):
            if q is not self._title:
                q.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._refresh_color_btn()
        self._save.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self._cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire d'ajout d'un achat (investissement ou consommable)
# ══════════════════════════════════════════════════════════════════════════════
# Catégories par nature. Filament → auto-création de bobines ; carton/emballage →
# incrément d'une fourniture (voir store.add_purchase).
_PURCHASE_CATS = {
    "investissement": [("imprimante", "purchase.cat_printer"),
                       ("materiel", "purchase.cat_equipment"),
                       ("logiciel", "purchase.cat_software"),
                       ("autre", "purchase.cat_other")],
    "consommable": [("filament", "purchase.cat_filament"),
                    ("carton", "purchase.cat_box"),
                    ("emballage", "purchase.cat_packaging"),
                    ("autre", "purchase.cat_other")],
}


def _purchase_nature_label(nature: str) -> str:
    return _("purchase.nature_invest" if nature == "investissement"
             else "purchase.nature_consum")


def _purchase_cat_label(cat: str) -> str:
    for lst in _PURCHASE_CATS.values():
        for key, i18n_key in lst:
            if key == cat:
                return _(i18n_key)
    return cat or ""


class PurchaseForm(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("purchase.add"))
        self.setMinimumWidth(440)
        self._color_hex = "#1E90FF"
        self._edits: dict[str, QLineEdit] = {}
        self._fil_rows: list[tuple] = []   # (label, widget) du bloc filament
        self._build()
        self._on_nature_changed()
        self._apply_theme()

    def _lbl(self, text: str) -> QLabel:
        q = QLabel(text); q.setFont(QFont(FONT_MAIN, 9))
        return q

    def _add_edit(self, grid, row, key, label, num=False, default="", fil=False):
        lblw = self._lbl(label)
        e = QLineEdit(str(default)); e.setFont(QFont(FONT_MONO, 9))
        if num:
            from PySide6.QtGui import QDoubleValidator
            e.setValidator(QDoubleValidator(0.0, 1e9, 2, e))
        self._edits[key] = e
        grid.addWidget(lblw, row, 0); grid.addWidget(e, row, 1)
        if fil:
            self._fil_rows.append((lblw, e))
        return row + 1

    def _grid_row(self, grid, row, label, widget, fil=True):
        lblw = self._lbl(label)
        grid.addWidget(lblw, row, 0); grid.addWidget(widget, row, 1)
        if fil:
            self._fil_rows.append((lblw, widget))
        return row + 1

    def _build(self):
        from datetime import date as _date
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 18, 20, 18); lay.setSpacing(10)
        self._title = QLabel(_("purchase.add"))
        self._title.setFont(QFont(FONT_MAIN, 13, QFont.Bold))
        lay.addWidget(self._title)

        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(8)
        lay.addLayout(grid); row = 0

        self._nature = QComboBox()
        self._nature.addItem(_("purchase.nature_invest"), "investissement")
        self._nature.addItem(_("purchase.nature_consum"), "consommable")
        self._nature.setCurrentIndex(1)   # consommable par défaut
        self._nature.currentIndexChanged.connect(self._on_nature_changed)
        row = self._grid_row(grid, row, _("purchase.nature"), self._nature, fil=False)

        self._category = QComboBox()
        self._category.currentIndexChanged.connect(self._on_category_changed)
        row = self._grid_row(grid, row, _("purchase.category"), self._category, fil=False)

        row = self._add_edit(grid, row, "designation", _("purchase.designation"))
        row = self._add_edit(grid, row, "date", _("purchase.date"), default=_date.today().isoformat())
        row = self._add_edit(grid, row, "montant", _("purchase.amount"), num=True, default="0")
        row = self._add_edit(grid, row, "quantite", _("purchase.qty"), num=True, default="1")
        row = self._add_edit(grid, row, "fournisseur", _("purchase.vendor"))

        # Bloc filament (visible uniquement pour Consommable → Filament)
        self._material = QComboBox()
        for name in FILAMENTS:
            self._material.addItem(name, name)
        row = self._grid_row(grid, row, _("spool.material"), self._material)
        self._finition = QComboBox()
        for key, i18n_key in _FINITIONS:
            self._finition.addItem(_(i18n_key), key)
        row = self._grid_row(grid, row, _("spool.finish"), self._finition)
        row = self._add_edit(grid, row, "couleur_nom", _("spool.color_name"), fil=True)
        self._color_btn = QPushButton(); self._color_btn.setFixedHeight(26)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)
        row = self._grid_row(grid, row, _("spool.color"), self._color_btn)
        row = self._add_edit(grid, row, "poids_bobine_g", _("purchase.weight_g"),
                             num=True, default="1000", fil=True)

        self._hint = QLabel("")
        self._hint.setFont(QFont(FONT_MAIN, 8)); self._hint.setWordWrap(True)
        lay.addWidget(self._hint)

        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("spool.cancel")); self._cancel.setCursor(Qt.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("spool.save")); self._save.setCursor(Qt.PointingHandCursor)
        self._save.clicked.connect(self.accept)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)

    def _on_nature_changed(self):
        nature = self._nature.currentData()
        self._category.blockSignals(True)
        self._category.clear()
        for key, i18n_key in _PURCHASE_CATS.get(nature, []):
            self._category.addItem(_(i18n_key), key)
        self._category.setCurrentIndex(0)
        self._category.blockSignals(False)
        self._on_category_changed()

    def _on_category_changed(self):
        is_fil = (self._nature.currentData() == "consommable"
                  and self._category.currentData() == "filament")
        for lblw, w in self._fil_rows:
            lblw.setVisible(is_fil); w.setVisible(is_fil)
        if is_fil:
            self._hint.setText(_("purchase.hint_filament"))
        elif self._category.currentData() in ("carton", "emballage"):
            self._hint.setText(_("purchase.hint_supply"))
        else:
            self._hint.setText("")
        self.adjustSize()

    def _pick_color(self):
        from PySide6.QtGui import QColor
        col = QColorDialog.getColor(QColor(self._color_hex), self, _("spool.color"))
        if col.isValid():
            self._color_hex = col.name()
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._color_btn.setText(self._color_hex)
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background: {self._color_hex}; color: white; "
            f"border: 1px solid rgba(0,0,0,0.3); border-radius: 3px; }}")

    def _num(self, key: str) -> float:
        try:
            return float(self._edits[key].text().strip().replace(",", ".") or 0)
        except ValueError:
            return 0.0

    def data(self) -> dict:
        nature = self._nature.currentData()
        cat = self._category.currentData()
        out = {
            "nature": nature, "categorie": cat,
            "designation": self._edits["designation"].text().strip(),
            "date": self._edits["date"].text().strip(),
            "fournisseur": self._edits["fournisseur"].text().strip(),
            "montant": self._num("montant"), "quantite": self._num("quantite") or 1,
        }
        if nature == "consommable" and cat == "filament":
            out.update({
                "materiau": self._material.currentData() or "PLA",
                "finition": self._finition.currentData() or "",
                "couleur_nom": self._edits["couleur_nom"].text().strip(),
                "couleur_hex": self._color_hex,
                "poids_bobine_g": self._num("poids_bobine_g") or 1000,
            })
            if not out["designation"]:
                fin = _finition_label(out["finition"]) if out["finition"] else ""
                out["designation"] = " ".join(
                    p for p in (out["materiau"], fin, out["couleur_nom"]) if p).strip()
        return out

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._hint.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        edit_css = (f"QLineEdit, QComboBox {{ background: {pal['BG_INPUT']}; "
                    f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                    f"border-radius: 3px; padding: 3px 6px; }}")
        for w in (self._nature, self._category, self._material, self._finition):
            w.setStyleSheet(edit_css)
        for e in self._edits.values():
            e.setStyleSheet(edit_css)
        for q in self.findChildren(QLabel):
            if q not in (self._title, self._hint):
                q.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._refresh_color_btn()
        self._save.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self._cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")


# ══════════════════════════════════════════════════════════════════════════════
# Formulaire d'une fourniture (carton, emballage…) — régler quantité + seuil
# ══════════════════════════════════════════════════════════════════════════════
class SupplyForm(QDialog):
    def __init__(self, parent=None, supply: dict | None = None):
        super().__init__(parent)
        self._supply = supply or {}
        self.setWindowTitle(_("supply.edit") if supply else _("supply.add"))
        self.setMinimumWidth(400)
        self._edits: dict[str, QLineEdit] = {}
        self._build()
        self._apply_theme()

    def _lbl(self, text: str) -> QLabel:
        q = QLabel(text); q.setFont(QFont(FONT_MAIN, 9))
        return q

    def _add_edit(self, grid, row, key, label, num=False, default=""):
        e = QLineEdit(str(self._supply.get(key, default))); e.setFont(QFont(FONT_MONO, 9))
        if num:
            from PySide6.QtGui import QDoubleValidator
            e.setValidator(QDoubleValidator(0.0, 1e9, 2, e))
        self._edits[key] = e
        grid.addWidget(self._lbl(label), row, 0); grid.addWidget(e, row, 1)
        return row + 1

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 18, 20, 18); lay.setSpacing(10)
        self._title = QLabel(_("supply.edit") if self._supply else _("supply.add"))
        self._title.setFont(QFont(FONT_MAIN, 13, QFont.Bold))
        lay.addWidget(self._title)
        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(8)
        lay.addLayout(grid); row = 0
        row = self._add_edit(grid, row, "nom", _("supply.name"))
        row = self._add_edit(grid, row, "quantite", _("supply.qty"), num=True, default="0")
        row = self._add_edit(grid, row, "unite", _("supply.unit"), default="u")
        row = self._add_edit(grid, row, "seuil", _("supply.threshold"), num=True, default="0")
        row = self._add_edit(grid, row, "fournisseur", _("spool.vendor"))
        hint = QLabel(_("supply.threshold_hint"))
        hint.setFont(QFont(FONT_MAIN, 8)); hint.setWordWrap(True); hint.setObjectName("hint")
        lay.addWidget(hint)
        btns = QHBoxLayout(); btns.addStretch()
        self._cancel = QPushButton(_("spool.cancel")); self._cancel.setCursor(Qt.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)
        self._save = QPushButton(_("spool.save")); self._save.setCursor(Qt.PointingHandCursor)
        self._save.clicked.connect(self.accept)
        btns.addWidget(self._cancel); btns.addWidget(self._save)
        lay.addLayout(btns)

    def data(self) -> dict:
        out = {}
        for k, e in self._edits.items():
            t = e.text().strip()
            if k in ("quantite", "seuil"):
                try:
                    out[k] = float(t.replace(",", ".") or 0)
                except ValueError:
                    out[k] = 0.0
            else:
                out[k] = t
        return out

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        edit_css = (f"QLineEdit {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
                    f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 3px 6px; }}")
        for e in self._edits.values():
            e.setStyleSheet(edit_css)
        for q in self.findChildren(QLabel):
            if q is self._title:
                continue
            col = pal['TEXT_LABEL'] if q.objectName() == "hint" else pal['TEXT_SECONDARY']
            q.setStyleSheet(f"color: {col}; background: transparent;")
        self._save.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 5px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        self._cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")


# ══════════════════════════════════════════════════════════════════════════════
# Carte d'une bobine dans la liste
# ══════════════════════════════════════════════════════════════════════════════
class _SpoolCard(QFrame):
    def __init__(self, spool: dict, on_edit, on_delete, parent=None):
        super().__init__(parent)
        self._spool = spool
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._build()

    def _build(self):
        s = self._spool
        pal = _T.palette()
        self.setStyleSheet(
            f"_SpoolCard {{ background: {pal['BG_ELEVATED']}; border: 1px solid {pal['INACTIVE']}; "
            f"border-radius: 6px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        # Pastille couleur
        swatch = QLabel()
        swatch.setFixedSize(34, 34)
        swatch.setStyleSheet(
            f"background: {s.get('couleur_hex', '#888')}; border-radius: 17px; "
            f"border: 2px solid {pal['BG_SURFACE']};")
        lay.addWidget(swatch)

        # Infos
        info = QVBoxLayout()
        info.setSpacing(2)
        nom = s.get("couleur_nom") or s.get("materiau", "")
        marque = s.get("marque", "")
        mat = s.get("materiau", "")
        fin = _finition_label(s.get("finition", ""))
        mat_fin = f"{mat} {fin}".strip() if fin else mat
        titre = f"{mat_fin} · {marque}".strip(" ·")
        if nom and nom != mat:
            titre = f"{titre} — {nom}" if titre else nom
        t = QLabel(titre)
        t.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        t.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(t)

        rem = float(s.get("poids_restant_g") or 0)
        tot = float(s.get("poids_total_g") or 0)
        pct = store.pct_restant(s)
        bar = _StockBar(pct, low=(0 < rem <= _LOW_STOCK_G))
        info.addWidget(bar)
        sub = QLabel(f"{rem:.0f} / {tot:.0f} g {_('spool.remaining')}  ·  "
                     f"{_('spool.cost_kg')} {store.cout_par_kg(s):.2f}")
        sub.setFont(QFont(FONT_MONO, 8))
        sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        # Actions
        for txt, cb, danger in ((_("spool.edit"), self._edit, False),
                                (_("spool.delete"), self._delete, True)):
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(26)
            col = pal["ERROR_RED"] if danger else pal["ACCENT"]
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {col}; "
                f"border: 1px solid {col}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
                f"QPushButton:hover {{ background: {col}; color: #fff; }}")
            b.clicked.connect(cb)
            lay.addWidget(b)

    def _edit(self):
        self._on_edit(self._spool)

    def _delete(self):
        self._on_delete(self._spool)


class _StockBar(QFrame):
    """Barre de stock restant (verte/ambre selon niveau)."""

    def __init__(self, pct: float, low: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(7)
        self.setMinimumWidth(160)
        self._pct = max(0.0, min(100.0, pct))
        self._low = low

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        pal = _T.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["INACTIVE"]))
        p.drawRoundedRect(r, 3, 3)
        w = int(r.width() * self._pct / 100.0)
        if w > 0:
            col = pal["AMBER"] if self._low else pal["TELE_GREEN"]
            p.setBrush(QColor(col))
            p.drawRoundedRect(0, 0, w, r.height(), 3, 3)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
# Hub principal
# ══════════════════════════════════════════════════════════════════════════════
class ProHubDialog(QDialog):
    """Fenêtre Espace Pro. `devis_launcher` : callable() ouvrant le devis (contexte
    fourni par la fenêtre principale)."""

    def __init__(self, parent=None, devis_context: dict | None = None,
                 initial_tab: str | None = None):
        super().__init__(parent)
        self._devis_context = devis_context or {}
        self._devis_calc = None
        self._initial_tab = initial_tab
        # Barre de titre : « Espace Pro » seul (le sous-titre est dans la sidebar)
        self.setWindowTitle(_("pro.hub_title").split("—")[0].strip())
        # Boutons agrandir/réduire → l'utilisateur peut passer en plein écran
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        # Large par défaut : la ligne d'une commande (badge + infos + 5 boutons
        # d'action) ne doit jamais être tronquée. Redimensionnable + maximisable.
        self.resize(1180, 640)
        self.setSizeGripEnabled(True)
        self._nav_btns: list[QPushButton] = []
        self._centered = False
        self._build()
        self._apply_theme()
        _T.register(self._apply_theme)
        self._refresh_spools()

    def showEvent(self, event):
        """Centre parfaitement la fenêtre sur l'écran au premier affichage.
        Fait ici (et pas avant exec) car Qt recentre un dialogue à parent sur son
        parent à l'ouverture → un move() antérieur serait écrasé."""
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            try:
                from PySide6.QtWidgets import QApplication
                screen = (self.screen()
                          or (self.parent().screen() if self.parent() else None)
                          or QApplication.primaryScreen())
                g = screen.availableGeometry()
                self.move(g.x() + (g.width() - self.width()) // 2,
                          g.y() + (g.height() - self.height()) // 2)
            except Exception:
                pass
            # Basculer sur l'onglet initial demandé APRÈS le premier affichage
            # (fenêtre dimensionnée) → pas d'artefact de peinture sur la liste.
            if self._initial_tab and self._initial_tab in getattr(self, "_tab_index", {}):
                from PySide6.QtCore import QTimer
                _idx = self._tab_index[self._initial_tab]
                QTimer.singleShot(0, lambda: self._select(_idx))

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        # Le calculateur intégré enregistre aussi son thème → on le libère
        if self._devis_calc is not None:
            try:
                _T.unregister(self._devis_calc._apply_theme)
                self._devis_calc._save_rates()
            except Exception:
                pass
        for pg in (getattr(self, "_facturation_page", None),
                   getattr(self, "_clients_page", None),
                   getattr(self, "_dashboard_page", None),
                   getattr(self, "_orders_page", None),
                   getattr(self, "_products_page", None)):
            if pg is not None:
                try:
                    _T.unregister(pg.apply_theme)
                except Exception:
                    pass
        super().closeEvent(event)

    # ── Construction ────────────────────────────────────────────────────────
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self._sidebar = QWidget()
        self._sidebar.setFixedWidth(204)
        side = QVBoxLayout(self._sidebar)
        side.setContentsMargins(12, 16, 12, 16)
        side.setSpacing(4)

        self._brand = QLabel(_("pro.hub_title").split("—")[-1].strip())
        self._brand.setFont(QFont(FONT_MAIN, 14, QFont.Bold))
        self._brand.setWordWrap(True)
        side.addWidget(self._brand)
        side.addSpacing(16)

        self._stack = QStackedWidget()

        # Flux logique : Tableau de bord · Bobines · Devis · Commandes ·
        # Facturation · Clients · Articles
        tabs = [
            ("dashboard", _("pro.tab_dashboard"), self._build_dashboard_page),
            ("spools",    _("pro.tab_spools"),    self._build_spools_page),
            ("purchases", _("pro.tab_purchases"), self._build_purchases_page),
            ("quote",     _("pro.tab_quote"),     self._build_devis_page),
            ("orders",    _("pro.tab_orders"),    self._build_orders_page),
            ("invoice",   _("pro.tab_invoice"),   self._build_invoice_page),
            ("clients",   _("pro.tab_clients"),   self._build_clients_page),
            ("products",  _("pro.tab_products"),  self._build_products_page),
        ]
        self._tab_index = {key: i for i, (key, _l, _b) in enumerate(tabs)}
        self._spools_tab_index = self._tab_index["spools"]
        for idx, (key, label, builder) in enumerate(tabs):
            self._stack.addWidget(builder())
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
            b.setFixedHeight(34)
            b.clicked.connect(lambda _c=False, i=idx: self._select(i))
            self._nav_btns.append(b)
            side.addWidget(b)

        side.addStretch()

        # Sauvegarde automatique (ZIP dans un dossier choisi) + export/import manuels
        self._autobk_status = QLabel(_("pro.autobk_active"))
        self._autobk_status.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._autobk_status.setWordWrap(False)   # une seule ligne
        side.addWidget(self._autobk_status)
        self._autobk_btn = QPushButton(_("pro.autobk_configure"))
        self._autobk_btn.setFont(QFont(FONT_MAIN, 8))
        self._autobk_btn.setCursor(Qt.PointingHandCursor)
        self._autobk_btn.setFixedHeight(30)
        self._autobk_btn.clicked.connect(self._open_autobk)
        side.addWidget(self._autobk_btn)
        side.addSpacing(8)
        self._export_btn = QPushButton(_("pro.export"))
        self._export_btn.setFont(QFont(FONT_MAIN, 8))
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setFixedHeight(30)
        self._export_btn.clicked.connect(self._do_export)
        side.addWidget(self._export_btn)
        self._import_btn = QPushButton(_("pro.import"))
        self._import_btn.setFont(QFont(FONT_MAIN, 8))
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setFixedHeight(30)
        self._import_btn.clicked.connect(self._do_import)
        side.addWidget(self._import_btn)

        root.addWidget(self._sidebar)
        root.addWidget(self._stack, 1)
        # Toujours construire sur le Tableau de bord (léger). Un éventuel onglet
        # initial (ex. "spools" depuis la fenêtre d'export) est sélectionné APRÈS
        # affichage (showEvent) pour éviter un rendu avant dimensionnement de la
        # fenêtre → artefacts de peinture sur la liste des bobines.
        self._select(0)

        # Sauvegarde automatique : statut + déclenchement si due, à l'ouverture
        self._refresh_autobk_status()
        try:
            store.run_auto_backup_if_due()
        except Exception:
            pass

    def _select(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._nav_btns):
            b.setChecked(i == idx)
        self._restyle_nav()
        ti = getattr(self, "_tab_index", {})
        # Recalculer/rafraîchir les pages dynamiques à chaque affichage
        if idx == ti.get("dashboard") and getattr(self, "_dashboard_page", None) is not None:
            self._dashboard_page.refresh()
        elif idx == ti.get("orders") and getattr(self, "_orders_page", None) is not None:
            self._orders_page.refresh()
        elif idx == ti.get("products") and getattr(self, "_products_page", None) is not None:
            self._products_page.refresh()
        elif idx == ti.get("spools"):
            self._refresh_spools()
        elif idx == ti.get("purchases"):
            self._refresh_purchases()

    # ── Boîtes de dialogue thématisées (texte toujours lisible) ───────────────
    def _box_qss(self) -> str:
        pal = _T.palette()
        return (f"QMessageBox {{ background: {pal['BG_PANEL']}; }}"
                f"QMessageBox QLabel {{ color: {pal['TEXT_PRIMARY']}; background: transparent; }}"
                f"QMessageBox QPushButton {{ background: {pal['BG_SURFACE']}; "
                f"color: {pal['TEXT_PRIMARY']}; border: 1px solid {pal['INACTIVE']}; "
                f"border-radius: 3px; padding: 4px 16px; }}"
                f"QMessageBox QPushButton:hover {{ border-color: {pal['ACCENT']}; }}")

    def _msg(self, title: str, text: str, kind: str = "info"):
        m = QMessageBox(self); m.setWindowTitle(title); m.setText(text)
        m.setIcon(QMessageBox.Warning if kind == "warn" else QMessageBox.Information)
        m.setStyleSheet(self._box_qss()); m.exec()

    def _ask(self, title: str, text: str) -> bool:
        m = QMessageBox(self); m.setWindowTitle(title); m.setText(text)
        m.setIcon(QMessageBox.Question)
        m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        m.setStyleSheet(self._box_qss())
        return m.exec() == QMessageBox.Yes

    # ── Page Bobines ──────────────────────────────────────────────────────────
    def _build_spools_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        header = QHBoxLayout()
        # Pas de gros titre « Bobines » : l'onglet actif l'indique déjà.
        header.addStretch()
        self._shop_btn = QPushButton("🛒 " + _("shop.title").title())
        self._shop_btn.setCursor(Qt.PointingHandCursor)
        self._shop_btn.setFixedHeight(30)
        self._shop_btn.setFont(QFont(FONT_MAIN, 8))
        self._shop_btn.clicked.connect(self._show_shopping_list)
        header.addWidget(self._shop_btn)
        self._add_btn = QPushButton("＋ " + _("spool.add"))
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setFixedHeight(30)
        self._add_btn.clicked.connect(self._add_spool)
        header.addWidget(self._add_btn)
        lay.addLayout(header)

        self._low_banner = QLabel("")
        self._low_banner.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._low_banner.hide()
        lay.addWidget(self._low_banner)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(8)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._list_host)
        lay.addWidget(self._scroll, 1)

        self._empty_lbl = QLabel(_("spool.empty"))
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._empty_lbl)
        return page

    def _build_color_summary(self, groups: list[dict]) -> QWidget:
        """Résumé du stock AGRÉGÉ par couleur (cumul des bobines de même
        matériau+couleur) → l'alerte se lit sur le total, pas bobine par bobine."""
        pal = _T.palette()
        box = QFrame()
        box.setStyleSheet(f"QFrame {{ background: {pal['BG_ELEVATED']}; "
                          f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        v = QVBoxLayout(box); v.setContentsMargins(12, 10, 12, 10); v.setSpacing(6)
        title = QLabel(_("spool.by_color_title"))
        title.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        title.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; "
                            f"letter-spacing: 1px;")
        v.addWidget(title)
        for g in groups:
            row = QHBoxLayout(); row.setSpacing(8)
            sw = QLabel(); sw.setFixedSize(16, 16)
            sw.setStyleSheet(f"background: {g['couleur_hex']}; border-radius: 8px; "
                             f"border: 1px solid {pal['BG_SURFACE']};")
            row.addWidget(sw)
            fin = f" {_finition_label(g['finition'])}" if g['finition'] else ""
            col = g['couleur_nom'] or ""
            name = f"{g['materiau']}{fin} — {col}".strip(" —")
            lbl = QLabel(f"{name}  ·  " + _("spool.color_n_spools", n=g['n_bobines']))
            lbl.setFont(QFont(FONT_MAIN, 9))
            lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            row.addWidget(lbl); row.addStretch()
            grams = QLabel(f"{g['restant_g']:.0f} g")
            grams.setFont(QFont(FONT_MONO, 9))
            grams.setStyleSheet(f"color: {pal['ERROR_RED'] if g['manque'] else pal['TEXT_SECONDARY']}; "
                                f"background: transparent;")
            row.addWidget(grams)
            if g['manque']:
                tag = QLabel("⚠ " + _("spool.color_low"))
                tag.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
                tag.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
                row.addWidget(tag)
            v.addLayout(row)
        return box

    def _refresh_spools(self):
        # vider la liste (sauf le stretch final)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        spools = store.list_spools()

        # Résumé « stock par couleur » (cumul) en tête de liste
        groups = store.stock_by_color()
        if groups:
            self._list_lay.insertWidget(self._list_lay.count() - 1,
                                        self._build_color_summary(groups))
        for s in spools:
            card = _SpoolCard(s, self._edit_spool, self._delete_spool)
            self._list_lay.insertWidget(self._list_lay.count() - 1, card)

        self._empty_lbl.setVisible(not spools)
        self._scroll.setVisible(bool(spools))

        # Alerte PAR COULEUR (cumul), plus par bobine → fini les fausses alertes
        low = store.low_stock_by_color()
        if low:
            self._low_banner.setText("⚠  " + _("spool.low_color_banner", n=len(low)))
            self._low_banner.show()
        else:
            self._low_banner.hide()

    def _show_shopping_list(self):
        """Liste de courses PAR COULEUR : couleurs dont le cumul est sous le seuil."""
        items = store.shopping_list_by_color()
        if not items:
            self._msg(_("shop.title").title(), _("shop.none"))
            return
        lines = []
        for x in items:
            fin = f" {_finition_label(x['finition'])}" if x.get("finition") else ""
            name = f"{x['materiau']}{fin} {x['couleur_nom']}".strip()
            lines.append(f"• {name or x['materiau']} : "
                         + _("shop.remaining", g=int(x["restant_g"]))
                         + "  →  " + _("shop.missing", g=int(x["racheter_g"])))
        self._msg(_("shop.title").title(), "\n".join(lines))

    def _add_spool(self):
        form = SpoolForm(self)
        if form.exec() == QDialog.Accepted:
            store.add_spool(form.data())
            self._refresh_spools()

    def _edit_spool(self, spool: dict):
        form = SpoolForm(self, spool=spool)
        if form.exec() == QDialog.Accepted:
            store.update_spool(spool["id"], form.data())
            self._refresh_spools()

    def _delete_spool(self, spool: dict):
        if self._ask(_("spool.delete"), _("spool.delete_confirm")):
            store.delete_spool(spool["id"])
            self._refresh_spools()

    # ── Page Achats (investissements + consommables) ──────────────────────────
    def _build_purchases_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page); lay.setContentsMargins(22, 18, 22, 18); lay.setSpacing(12)

        header = QHBoxLayout()
        self._purch_totals = QLabel("")
        self._purch_totals.setFont(QFont(FONT_MAIN, 9))
        self._purch_totals.setWordWrap(True)
        header.addWidget(self._purch_totals, 1)
        _btn_font = QFont(FONT_MAIN, 9)
        sup_btn = QPushButton("＋ " + _("supply.add"))
        sup_btn.setCursor(Qt.PointingHandCursor); sup_btn.setFixedHeight(30)
        sup_btn.setFont(_btn_font)
        sup_btn.clicked.connect(self._add_supply_manual)
        header.addWidget(sup_btn)
        add_btn = QPushButton("＋ " + _("purchase.add"))
        add_btn.setCursor(Qt.PointingHandCursor); add_btn.setFixedHeight(30)
        add_btn.setFont(_btn_font)
        add_btn.clicked.connect(self._add_purchase)
        header.addWidget(add_btn)
        lay.addLayout(header)

        self._purch_scroll = QScrollArea(); self._purch_scroll.setWidgetResizable(True)
        self._purch_scroll.setFrameShape(QFrame.NoFrame)
        self._purch_host = QWidget()
        self._purch_lay = QVBoxLayout(self._purch_host)
        self._purch_lay.setContentsMargins(0, 0, 0, 0); self._purch_lay.setSpacing(8)
        self._purch_lay.addStretch()
        self._purch_scroll.setWidget(self._purch_host)
        lay.addWidget(self._purch_scroll, 1)

        self._purch_empty = QLabel(_("purchase.empty"))
        self._purch_empty.setAlignment(Qt.AlignCenter); self._purch_empty.setWordWrap(True)
        self._purch_empty.setFont(QFont(FONT_MAIN, 10))
        lay.addWidget(self._purch_empty)
        return page

    def _purch_section(self, text: str) -> QLabel:
        pal = _T.palette()
        lbl = QLabel(text); lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent; "
                          f"letter-spacing: 1px;")
        return lbl

    def _purchase_card(self, p: dict, cur: str) -> QFrame:
        pal = _T.palette()
        invest = p.get("nature") == "investissement"
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(10)

        info = QVBoxLayout(); info.setSpacing(2)
        title = QLabel(p.get("designation") or _purchase_cat_label(p.get("categorie", "")))
        title.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        info.addWidget(title)
        bits = [p.get("date", ""), _purchase_nature_label(p.get("nature", "")),
                _purchase_cat_label(p.get("categorie", ""))]
        if p.get("spool_ids"):
            bits.append(_("purchase.created_spools", n=len(p["spool_ids"])))
        elif p.get("supply_id"):
            bits.append(_("purchase.supply_added"))
        sub = QLabel("  ·  ".join(b for b in bits if b))
        sub.setFont(QFont(FONT_MONO, 8))
        sub.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        amount = QLabel(f"{float(p.get('montant', 0) or 0):.2f} {cur}")
        amount.setFont(QFont(FONT_MAIN, 11, QFont.Bold))
        amount.setStyleSheet(f"color: {pal['AMBER'] if invest else pal['TEXT_PRIMARY']}; "
                             f"background: transparent;")
        lay.addWidget(amount)

        dele = QPushButton(_("spool.delete"))
        dele.setCursor(Qt.PointingHandCursor); dele.setFixedHeight(26)
        dele.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ERROR_RED']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 0 10px; }}"
            f"QPushButton:hover {{ border-color: {pal['ERROR_RED']}; }}")
        dele.clicked.connect(lambda _c=False, pid=p.get("id"): self._delete_purchase(pid))
        lay.addWidget(dele)
        return card

    def _supply_row(self, s: dict) -> QFrame:
        pal = _T.palette()
        low = float(s.get("seuil") or 0) > 0 and float(s.get("quantite") or 0) <= float(s.get("seuil") or 0)
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 6px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(10)
        name = QLabel(s.get("nom", "")); name.setFont(QFont(FONT_MAIN, 9))
        name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(name, 1)
        qty = QLabel(f"{float(s.get('quantite', 0) or 0):.0f} {s.get('unite', 'u')}")
        qty.setFont(QFont(FONT_MONO, 9))
        qty.setStyleSheet(f"color: {pal['ERROR_RED'] if low else pal['TEXT_SECONDARY']}; "
                          f"background: transparent;")
        lay.addWidget(qty)
        if low:
            tag = QLabel("⚠ " + _("spool.color_low"))
            tag.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            tag.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
            lay.addWidget(tag)
        edit = QPushButton(_("spool.edit"))
        edit.setCursor(Qt.PointingHandCursor); edit.setFixedHeight(24)
        edit.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 0 8px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; }}")
        edit.clicked.connect(lambda _c=False, sup=s: self._edit_supply(sup))
        lay.addWidget(edit)
        dele = QPushButton(_("spool.delete"))
        dele.setCursor(Qt.PointingHandCursor); dele.setFixedHeight(24)
        dele.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ERROR_RED']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 0 8px; }}"
            f"QPushButton:hover {{ border-color: {pal['ERROR_RED']}; }}")
        dele.clicked.connect(lambda _c=False, sid=s.get("id"): self._delete_supply(sid))
        lay.addWidget(dele)
        return card

    def _refresh_purchases(self):
        from core.business import invoicing
        cur = invoicing.currency(store.get_company().get("pays", ""))
        while self._purch_lay.count() > 1:
            item = self._purch_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        purchases = store.list_purchases()
        supplies = store.list_supplies()
        pos = 0

        def _add(widget):
            nonlocal pos
            self._purch_lay.insertWidget(pos, widget); pos += 1

        # Totaux
        inv = store.total_investments(); con = store.total_consumables_purchased()
        self._purch_totals.setText(
            _("purchase.total_invest", amount=f"{inv:.2f} {cur}") + "   ·   "
            + _("purchase.total_consum", amount=f"{con:.2f} {cur}"))

        if purchases:
            _add(self._purch_section(_("purchase.sec_purchases")))
            for p in purchases:
                _add(self._purchase_card(p, cur))
        if supplies:
            _add(self._purch_section(_("purchase.sec_supplies")))
            for s in supplies:
                _add(self._supply_row(s))

        has_any = bool(purchases or supplies)
        self._purch_empty.setVisible(not has_any)
        self._purch_scroll.setVisible(has_any)

    def _add_purchase(self):
        form = PurchaseForm(self)
        if form.exec() == QDialog.Accepted:
            data = form.data()
            if float(data.get("montant") or 0) <= 0 and not data.get("designation"):
                return
            store.add_purchase(data)
            self._refresh_purchases()
            # L'achat a pu créer des bobines / fournitures → garder le stock à jour
            if getattr(self, "_list_lay", None) is not None:
                self._refresh_spools()

    def _delete_purchase(self, pid: str):
        if not pid:
            return
        if self._ask(_("purchase.delete"), _("purchase.delete_confirm")):
            store.delete_purchase(pid)
            self._refresh_purchases()

    def _add_supply_manual(self):
        form = SupplyForm(self)
        if form.exec() == QDialog.Accepted:
            data = form.data()
            if not data.get("nom"):
                return
            store.add_supply(data)
            self._refresh_purchases()

    def _edit_supply(self, supply: dict):
        form = SupplyForm(self, supply=supply)
        if form.exec() == QDialog.Accepted:
            store.update_supply(supply["id"], form.data())
            self._refresh_purchases()

    def _delete_supply(self, sid: str):
        if not sid:
            return
        if self._ask(_("purchase.delete"), _("purchase.delete_confirm")):
            store.delete_supply(sid)
            self._refresh_purchases()

    # ── Page Devis (calculateur intégré, pas de fenêtre séparée) ──────────────
    def _build_devis_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        hlay = QVBoxLayout(host)
        hlay.setContentsMargins(18, 14, 18, 18)
        hlay.setSpacing(0)

        try:
            from ui.components.cost_calculator import CostCalculatorDialog
            self._devis_calc = CostCalculatorDialog(self, embedded=True, **self._devis_context)
            hlay.addWidget(self._devis_calc._card)   # remplit la largeur
            self._devis_calc.quote_saved.connect(self._refresh_quotes)
        except Exception as exc:
            err = QLabel(f"Devis indisponible : {exc}")
            err.setWordWrap(True)
            hlay.addWidget(err)

        # ── Devis enregistrés ────────────────────────────────────────────────
        hlay.addSpacing(14)
        self._quotes_title = QLabel(_("cost.saved_quotes").upper())
        self._quotes_title.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        self._quotes_title.setObjectName("qtitle")
        hlay.addWidget(self._quotes_title)
        sep = QFrame(); sep.setFixedHeight(1); sep.setObjectName("qsep")
        hlay.addSpacing(4); hlay.addWidget(sep); hlay.addSpacing(8)
        self._quotes_host = QWidget()
        self._quotes_lay = QVBoxLayout(self._quotes_host)
        self._quotes_lay.setContentsMargins(0, 0, 0, 0)
        self._quotes_lay.setSpacing(6)
        hlay.addWidget(self._quotes_host)
        hlay.addStretch()

        scroll.setWidget(host)
        outer.addWidget(scroll)
        self._devis_scroll = scroll
        self._refresh_quotes()
        return page

    # ── Liste des devis enregistrés ───────────────────────────────────────────
    def _refresh_quotes(self):
        while self._quotes_lay.count():
            it = self._quotes_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)   # détache tout de suite (deleteLater est async → fantômes)
                w.deleteLater()
        quotes = store.list_quotes()
        pal = _T.palette()
        if not quotes:
            empty = QLabel(_("cost.no_quotes"))
            empty.setFont(QFont(FONT_MAIN, 9))
            empty.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
            self._quotes_lay.addWidget(empty)
            return
        for q in quotes:
            self._quotes_lay.addWidget(self._quote_card(q))

    def _quote_card(self, q: dict) -> QFrame:
        pal = _T.palette()
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {pal['BG_ELEVATED']}; "
                           f"border: 1px solid {pal['INACTIVE']}; border-radius: 5px; }}")
        lay = QHBoxLayout(card); lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(10)
        converted = q.get("status") == "converted"
        txt = (f"<b>{q.get('number','')}</b> · {q.get('part_name','')} ×{q.get('qty',1)}  —  "
               f"{q.get('total_price',0):.2f} {q.get('currency','')}")
        if converted:
            txt += f"  ·  <span style='color:{pal['TELE_GREEN']}'>✓ {q.get('invoice_number','')}</span>"
        info = QLabel(txt)
        info.setFont(QFont(FONT_MAIN, 9))
        info.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(info, 1)

        # → Commande : envoie le devis dans la file de production
        to_ord = QPushButton(_("ord.from_quote"))
        to_ord.setCursor(Qt.PointingHandCursor); to_ord.setFixedHeight(26)
        to_ord.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['TELE_GREEN']}; "
            f"border: 1px solid {pal['TELE_GREEN']}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {pal['TELE_GREEN']}; color: #fff; }}")
        to_ord.clicked.connect(lambda _c=False, qq=q: self._quote_to_order(qq))
        lay.addWidget(to_ord)

        conv = QPushButton(_("cost.to_invoice"))
        conv.setCursor(Qt.PointingHandCursor); conv.setFixedHeight(26)
        conv.setToolTip(_("cost.to_invoice_full"))
        conv.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
            f"border: 1px solid {pal['ACCENT']}; border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT']}; color: #fff; }}")
        conv.clicked.connect(lambda _c=False, qq=q: self._convert_quote(qq))
        lay.addWidget(conv)

        dele = QPushButton("✕"); dele.setFixedSize(26, 26); dele.setCursor(Qt.PointingHandCursor)
        dele.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {pal['ERROR_RED']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {pal['ERROR_RED']}; color: #fff; }}")
        dele.clicked.connect(lambda _c=False, qq=q: self._delete_quote(qq))
        lay.addWidget(dele)
        return card

    def _delete_quote(self, q: dict):
        if self._ask(_("cost.del"), _("cost.del_quote_confirm", number=q.get("number", ""))):
            store.delete_quote(q["id"])
            self._refresh_quotes()

    def _convert_quote(self, q: dict):
        """Convertit un devis en facture : pré-remplit la facturation + bascule dessus."""
        if getattr(self, "_facturation_page", None) is None:
            return
        self._facturation_page.prefill_from_quote(q)
        self._select(self._tab_index["invoice"])

    def _quote_to_order(self, q: dict):
        """Envoie un devis dans la file de production (crée une commande à faire)."""
        o = store.order_from_quote(q)
        if getattr(self, "_orders_page", None) is not None:
            self._orders_page.refresh()
        self._select(self._tab_index["orders"])
        self._msg(_("pro.tab_orders"), _("ord.created", number=o.get("number", "")))

    # ── Page Facturation ──────────────────────────────────────────────────────
    def _build_invoice_page(self) -> QWidget:
        from ui.components.facturation_page import FacturationPage
        self._facturation_page = FacturationPage(self)
        return self._facturation_page

    # ── Page Commandes (file de production) ───────────────────────────────────
    def _build_orders_page(self) -> QWidget:
        from ui.components.orders_page import OrdersPage
        self._orders_page = OrdersPage(self)
        self._orders_page.invoice_requested.connect(self._invoice_from_order)
        return self._orders_page

    def _invoice_from_order(self, order: dict):
        """Facturer une commande : pré-remplit la facturation + bascule dessus."""
        if getattr(self, "_facturation_page", None) is None:
            return
        self._facturation_page.prefill_from_order(order)
        self._select(self._tab_index["invoice"])

    # ── Page Articles (catalogue récurrent) ───────────────────────────────────
    def _build_products_page(self) -> QWidget:
        from ui.components.products_page import ProductsPage
        self._products_page = ProductsPage(self)
        self._products_page.insert_requested.connect(self._insert_product)
        self._products_page.order_requested.connect(self._product_to_order)
        return self._products_page

    def _insert_product(self, product: dict):
        """Insère un article du catalogue comme ligne de facture + bascule dessus."""
        if getattr(self, "_facturation_page", None) is None:
            return
        self._facturation_page.add_product_line(product)
        self._select(self._tab_index["invoice"])

    def _product_to_order(self, product: dict):
        """Crée une commande depuis un article du catalogue + bascule dessus."""
        o = store.order_from_product(product)
        if getattr(self, "_orders_page", None) is not None:
            self._orders_page.refresh()
        self._select(self._tab_index["orders"])
        self._msg(_("pro.tab_orders"), _("ord.created", number=o.get("number", "")))

    # ── Page Clients ────────────────────────────────────────────────────────────
    def _build_clients_page(self) -> QWidget:
        from ui.components.clients_page import ClientsPage
        self._clients_page = ClientsPage(self)
        return self._clients_page

    # ── Page Tableau de bord ──────────────────────────────────────────────────
    def _build_dashboard_page(self) -> QWidget:
        from ui.components.dashboard_page import DashboardPage
        self._dashboard_page = DashboardPage(self)
        return self._dashboard_page

    # ── Page « Bientôt » ──────────────────────────────────────────────────────
    def _build_placeholder(self, name: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        t = QLabel(name)
        t.setAlignment(Qt.AlignCenter)
        t.setFont(QFont(FONT_MAIN, 15, QFont.Bold))
        lay.addWidget(t)
        badge = QLabel("⏳ " + _("pro.coming_soon"))
        badge.setAlignment(Qt.AlignCenter)
        badge.setFont(QFont(FONT_MAIN, 11, QFont.Bold))
        badge.setObjectName("coming")
        lay.addWidget(badge)
        sub = QLabel(_("pro.coming_soon_desc"))
        sub.setAlignment(Qt.AlignCenter)
        sub.setFont(QFont(FONT_MAIN, 9))
        sub.setObjectName("comingsub")
        lay.addWidget(sub)
        return page

    def _refresh_autobk_status(self):
        """Affiche « ✓ Sauvegarde automatique active » (vert) seulement si configurée."""
        from core.prefs import PREFS
        on = bool(PREFS.get("autobk_enabled", False)) and bool(PREFS.get("autobk_dir", ""))
        if hasattr(self, "_autobk_status"):
            self._autobk_status.setVisible(on)

    def _open_autobk(self):
        from ui.components.auto_backup_dialog import AutoBackupDialog
        from ui.styles.theme import apply_title_bar_theme
        dlg = AutoBackupDialog(self)
        apply_title_bar_theme(dlg)
        dlg.configured.connect(self._on_autobk_configured)
        dlg.exec()

    def _on_autobk_configured(self):
        self._refresh_autobk_status()
        # Lance une 1re sauvegarde tout de suite si elle est due
        try:
            path = store.run_auto_backup_if_due()
            if path:
                self._msg(_("pro.autobk_title"), _("pro.autobk_done", path=str(path)))
            else:
                self._msg(_("pro.autobk_title"), _("pro.autobk_saved"))
        except Exception:
            self._msg(_("pro.autobk_title"), _("pro.autobk_saved"))

    def _do_export(self):
        downloads = Path.home() / "Downloads"
        start = downloads if downloads.is_dir() else Path.home()
        path, _f = QFileDialog.getSaveFileName(
            self, _("pro.export"), str(start / "neoslice_atelier.zip"), "ZIP (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            store.export_backup(Path(path))
            self._msg(_("pro.export"), _("pro.export_done", path=path))
        except Exception as exc:
            self._msg(_("pro.export"), str(exc), "warn")

    def _do_import(self):
        if not self._ask(_("pro.import"), _("pro.import_confirm")):
            return
        start = Path.home() / "Downloads"
        path, _f = QFileDialog.getOpenFileName(
            self, _("pro.import"), str(start if start.is_dir() else Path.home()), "ZIP (*.zip)")
        if not path:
            return
        try:
            n = store.import_backup(Path(path))
            self._refresh_spools()
            self._msg(_("pro.import"), _("pro.import_done", n=n))
        except Exception as exc:
            self._msg(_("pro.import"), str(exc), "warn")

    # ── Thème ──────────────────────────────────────────────────────────────────
    def _restyle_nav(self):
        pal = _T.palette()
        for b in self._nav_btns:
            if b.isChecked():
                b.setStyleSheet(
                    f"QPushButton {{ text-align: left; padding: 0 12px; border: none; "
                    f"border-radius: 5px; background: {pal['ACCENT']}; color: #fff; "
                    f"font-weight: bold; }}")
            else:
                b.setStyleSheet(
                    f"QPushButton {{ text-align: left; padding: 0 12px; border: none; "
                    f"border-radius: 5px; background: transparent; color: {pal['TEXT_SECONDARY']}; }}"
                    f"QPushButton:hover {{ background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; }}")

    def _apply_theme(self):
        pal = _T.palette()
        self.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")
        self._sidebar.setStyleSheet(f"background: {pal['BG_SURFACE']};")
        # padding-left ajusté → le « G » s'aligne sur les initiales des onglets (T/B/D…)
        self._brand.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; padding-left: 9px;")
        self._restyle_nav()

        if hasattr(self, "_spools_title"):
            self._spools_title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        if hasattr(self, "_devis_scroll"):
            self._devis_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            self._devis_scroll.widget().setStyleSheet("background: transparent;")
        if hasattr(self, "_quotes_title"):
            self._quotes_title.setStyleSheet(f"color: {pal['TEXT_LABEL']}; "
                                             f"background: transparent; letter-spacing: 2px;")
            for fr in self.findChildren(QFrame):
                if fr.objectName() == "qsep":
                    fr.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")
            self._refresh_quotes()
        if hasattr(self, "_empty_lbl"):
            self._empty_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        if hasattr(self, "_low_banner"):
            self._low_banner.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        if hasattr(self, "_scroll"):
            self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            self._list_host.setStyleSheet("background: transparent;")

        accent_btn = (f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
                      f"border-radius: 4px; padding: 0 14px; font-weight: bold; }}"
                      f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}")
        if hasattr(self, "_add_btn"):
            self._add_btn.setStyleSheet(accent_btn)
        _soft_btn = (
            f"QPushButton {{ background: transparent; color: {pal['TEXT_SECONDARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 0 6px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")
        if hasattr(self, "_shop_btn"):
            self._shop_btn.setStyleSheet(_soft_btn)
        for b in (getattr(self, "_export_btn", None), getattr(self, "_import_btn", None),
                  getattr(self, "_autobk_btn", None)):
            if b:
                b.setStyleSheet(_soft_btn)
        if hasattr(self, "_autobk_status"):
            self._autobk_status.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        # Placeholders « Bientôt »
        for badge in self.findChildren(QLabel):
            if badge.objectName() == "coming":
                badge.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
            elif badge.objectName() == "comingsub":
                badge.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
