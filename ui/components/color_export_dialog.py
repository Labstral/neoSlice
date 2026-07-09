"""Repartition des couleurs apres export 3MF (version Pro), en WIDGET integrable.

Ce widget s'insere DANS la fenetre de succes d'export (sous les boutons PDF /
ouvrir dans le slicer), pour n'avoir qu'une seule fenetre. Selon les slots de
couleur detectes, il affiche le grammage estime par couleur (auto multi-objets,
approximatif peint, manuel STL), permet d'assigner une bobine du stock a chaque
couleur, previsualise les couleurs choisies EN DIRECT dans le viewer 3D, et
decompte le stock au clic sur Valider (via le callback `on_confirm`).

Reserve a la version Pro (le gating est fait par l'appelant).
"""
from __future__ import annotations
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.i18n import _
from ui.styles.theme import MANAGER as _T, FONT_MAIN

# Hauteur estimee d'une ligne (pour dimensionner la zone sans scrollbar prematuree).
_ROW_H = 32
_ROWS_CAP = 260


@dataclass
class DeductionRow:
    slot: int
    grams: float
    spool_id: str | None
    hex: str


class _SlotRow:
    """Une ligne de couleur (etat + widgets)."""

    def __init__(self, widget: "ColorBreakdownWidget", slot: int, grams: float, hex_color: str):
        self.owner = widget
        self.slot = slot
        self.hex = hex_color or "#AABBCC"
        pal = _T.palette()

        self.container = QWidget()
        row = QHBoxLayout(self.container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.swatch = QPushButton()
        self.swatch.setFixedSize(24, 24)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.clicked.connect(self._pick_color)
        row.addWidget(self.swatch)

        self.name = QLabel(_("color_export.slot_n", n=slot))
        self.name.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self.name.setFixedWidth(70)
        self.name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        row.addWidget(self.name)

        self.grams_edit = QLineEdit(f"{grams:.0f}")
        self.grams_edit.setFixedWidth(60)
        self.grams_edit.setAlignment(Qt.AlignRight)
        self.grams_edit.textChanged.connect(self.owner._update_remaining)
        row.addWidget(self.grams_edit)
        g_lbl = QLabel("g")
        g_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        row.addWidget(g_lbl)

        self.spool_combo = QComboBox()
        self.spool_combo.setMinimumWidth(150)
        self.spool_combo.currentIndexChanged.connect(self._on_spool_changed)
        row.addWidget(self.spool_combo, 1)

        self._apply_styles()
        self._refresh_swatch()

    def _apply_styles(self):
        pal = _T.palette()
        self.grams_edit.setStyleSheet(
            f"QLineEdit {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 3px 6px; }}")
        self.spool_combo.setStyleSheet(
            f"QComboBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 3px 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {pal['BG_ELEVATED']}; "
            f"color: {pal['TEXT_PRIMARY']}; selection-background-color: {pal['ACCENT']}; }}")

    def _refresh_swatch(self):
        self.swatch.setStyleSheet(
            f"QPushButton {{ background: {self.hex}; border: 1px solid #00000060; "
            f"border-radius: 4px; }}")

    def populate_spools(self, spools: list[dict]):
        prev = self.spool_combo.currentData()
        self.spool_combo.blockSignals(True)
        self.spool_combo.clear()
        self.spool_combo.addItem(_("color_export.no_spool"), None)
        for s in spools:
            label = (f"{s.get('marque','')} {s.get('couleur_nom','')} "
                     f"— {float(s.get('poids_restant_g') or 0):.0f} g").strip()
            self.spool_combo.addItem(label, s.get("id"))
        if prev:
            i = self.spool_combo.findData(prev)
            if i >= 0:
                self.spool_combo.setCurrentIndex(i)
        self.spool_combo.blockSignals(False)

    def _on_spool_changed(self, _idx: int):
        sid = self.spool_combo.currentData()
        if sid:
            s = self.owner._spool_by_id(sid)
            if s and s.get("couleur_hex"):
                self.hex = s["couleur_hex"]
                self._refresh_swatch()
        self.owner._update_preview()

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self.hex), self.owner, _("color_export.pick_color"))
        if col.isValid():
            self.hex = col.name()
            self._refresh_swatch()
            self.owner._update_preview()

    def grams(self) -> float:
        try:
            return max(0.0, float(self.grams_edit.text().replace(",", ".")))
        except Exception:
            return 0.0

    def to_row(self) -> DeductionRow:
        return DeductionRow(self.slot, self.grams(), self.spool_combo.currentData(), self.hex)


class ColorBreakdownWidget(QWidget):
    """Section couleur/decompte, integree dans la fenetre de succes. Voir en-tete."""

    def __init__(self, parent, breakdown, material: str, viewer=None,
                 spool_provider=None, register_cb=None, on_confirm=None):
        super().__init__(parent)
        self._breakdown = breakdown
        self._material = material or ""
        self._viewer = viewer
        self._spool_provider = spool_provider or (lambda: [])
        self._register_cb = register_cb
        self._on_confirm = on_confirm
        self._rows: list[_SlotRow] = []
        self._spools_cache: list[dict] = []
        self._confirmed = False
        self._build()
        self._reload_spools()
        self._update_preview()
        self._update_remaining()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        pal = _T.palette()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Avertissement : ne pas fermer avant slicing pour le grammage exact.
        # Le padding est porte par un CONTENEUR, pas par le QLabel : un QLabel
        # word-wrap + padding en stylesheet calcule mal sa hauteur (padding non
        # deduit de la largeur de wrap) -> derniere ligne tronquee, surtout avec
        # les metriques de police macOS. Ici le label wrappe a sa vraie largeur.
        warn = QLabel(_("color_export.warning"))
        warn.setWordWrap(True)
        warn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        warn.setStyleSheet("color: #000; background: transparent;")
        warn_box = QFrame()
        warn_box.setStyleSheet(f"background: {pal['AMBER']}; border-radius: 5px;")
        _wl = QVBoxLayout(warn_box)
        _wl.setContentsMargins(10, 8, 10, 8)
        _wl.addWidget(warn)
        lay.addWidget(warn_box)

        sub_key = {
            "multiobject": "color_export.detected_multi",
            "painted": "color_export.detected_painted",
            "single": "color_export.detected_single",
        }.get(self._breakdown.kind, "color_export.detected_single")
        sub = QLabel(_(sub_key, n=len(self._breakdown.slots)))
        sub.setWordWrap(True)
        sub.setFont(QFont(FONT_MAIN, 8))
        col = pal["AMBER"] if self._breakdown.approximate else pal["TEXT_SECONDARY"]
        sub.setStyleSheet(f"color: {col}; background: transparent;")
        lay.addWidget(sub)

        self._total_lbl = QLabel()
        self._total_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._total_lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(self._total_lbl)

        # Zone des lignes (grandit avec le contenu jusqu'a un plafond, puis scroll).
        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(8)
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_host = QWidget()
        self._rows_host.setLayout(self._rows_box)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._rows_host)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")
        lay.addWidget(self._scroll)

        for slot in self._breakdown.slots:
            self._add_row(slot.slot, slot.grams, slot.default_hex)

        if self._breakdown.kind == "single":
            add_btn = QPushButton(_("color_export.add_color"))
            add_btn.setCursor(Qt.PointingHandCursor)
            add_btn.setFont(QFont(FONT_MAIN, 8))
            add_btn.clicked.connect(self._on_add_color)
            add_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {pal['ACCENT']}; "
                f"border: 1px dashed {pal['INACTIVE']}; border-radius: 4px; padding: 5px; }}"
                f"QPushButton:hover {{ border-color: {pal['ACCENT']}; }}")
            lay.addWidget(add_btn)

        # Marge de purge (AMS) optionnelle.
        purge_row = QHBoxLayout()
        self._purge_cb = QCheckBox(_("color_export.purge_label"))
        self._purge_cb.setStyleSheet(f"QCheckBox {{ color: {pal['TEXT_SECONDARY']}; background: transparent; }}")
        self._purge_spin = QDoubleSpinBox()
        self._purge_spin.setRange(0, 100)
        self._purge_spin.setDecimals(0)
        self._purge_spin.setValue(3)
        self._purge_spin.setSuffix(" g")
        self._purge_spin.setFixedWidth(92)
        self._purge_spin.setStyleSheet(
            f"QDoubleSpinBox {{ background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 2px 20px 2px 6px; }}"
            f"QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; "
            f"width: 16px; border-left: 1px solid {pal['INACTIVE']}; }}"
            f"QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; "
            f"width: 16px; border-left: 1px solid {pal['INACTIVE']}; }}"
            f"QDoubleSpinBox::up-arrow {{ width: 7px; height: 7px; }}"
            f"QDoubleSpinBox::down-arrow {{ width: 7px; height: 7px; }}")
        purge_row.addWidget(self._purge_cb)
        purge_row.addStretch()
        purge_row.addWidget(self._purge_spin)
        lay.addLayout(purge_row)

        # Aucune bobine -> proposer l'enregistrement.
        self._no_spool_lbl = QLabel(_("color_export.no_spool_hint"))
        self._no_spool_lbl.setWordWrap(True)
        self._no_spool_lbl.setFont(QFont(FONT_MAIN, 8))
        self._no_spool_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        lay.addWidget(self._no_spool_lbl)

        self._register_btn = QPushButton(_("color_export.register_spools"))
        self._register_btn.setCursor(Qt.PointingHandCursor)
        self._register_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._register_btn.clicked.connect(self._on_register)
        self._register_btn.setStyleSheet(
            f"QPushButton {{ background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['ACCENT']}; border-radius: 4px; padding: 6px 12px; }}"
            f"QPushButton:hover {{ background: {pal['BG_SURFACE']}; }}")
        lay.addWidget(self._register_btn)

        # Bouton de decompte + confirmation inline.
        crow = QHBoxLayout()
        self._confirm_status = QLabel("")
        self._confirm_status.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._confirm_status.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        crow.addWidget(self._confirm_status)
        crow.addStretch()
        self._confirm_btn = QPushButton(_("color_export.validate"))
        self._confirm_btn.setCursor(Qt.PointingHandCursor)
        self._confirm_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._confirm_btn.clicked.connect(self._on_confirm_clicked)
        self._confirm_btn.setStyleSheet(
            f"QPushButton {{ background: {pal['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 4px; padding: 6px 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}"
            f"QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['TEXT_SECONDARY']}; }}")
        crow.addWidget(self._confirm_btn)
        lay.addLayout(crow)

        self._fit_rows()

    def _add_row(self, slot: int, grams: float, hex_color: str):
        row = _SlotRow(self, slot, grams, hex_color)
        self._rows.append(row)
        self._rows_box.addWidget(row.container)

    def _on_add_color(self):
        next_slot = (max((r.slot for r in self._rows), default=0) + 1)
        from core.export.color_breakdown import DEFAULT_SLOT_HEX
        self._add_row(next_slot, 0.0, DEFAULT_SLOT_HEX.get(next_slot, "#AABBCC"))
        self._rows[-1].populate_spools(self._spools_cache)
        self._update_remaining()
        self._fit_rows()

    def _fit_rows(self):
        """La zone des lignes prend la hauteur de son contenu, jusqu'a un plafond
        (au-dela = scrollbar). Deterministe (offscreen-safe)."""
        n = len(self._rows)
        content_h = n * _ROW_H + max(0, n - 1) * self._rows_box.spacing()
        self._scroll.setFixedHeight(max(_ROW_H, min(content_h + 4, _ROWS_CAP)))

    # ── bobines / preview ─────────────────────────────────────────────────────
    def _reload_spools(self):
        try:
            self._spools_cache = list(self._spool_provider() or [])
        except Exception:
            self._spools_cache = []
        for r in self._rows:
            r.populate_spools(self._spools_cache)
        has = bool(self._spools_cache)
        # Le rappel "aucune bobile" ne s'affiche que si le stock est vide, mais le
        # bouton d'ouverture de l'Espace Pro (onglet Bobines) reste TOUJOURS
        # accessible pour ajouter une bobine a la volee.
        self._no_spool_lbl.setVisible(not has)
        self._register_btn.setVisible(True)

    def _spool_by_id(self, sid: str) -> dict | None:
        for s in self._spools_cache:
            if s.get("id") == sid:
                return s
        return None

    def _current_mapping(self) -> dict:
        return {r.slot: r.hex for r in self._rows}

    def _update_preview(self):
        if self._viewer is not None:
            try:
                self._viewer.set_slot_colors(self._current_mapping())
            except Exception:
                pass

    def _update_remaining(self):
        assigned = sum(r.grams() for r in self._rows)
        total = self._breakdown.total_g
        rem = total - assigned
        txt = _("color_export.total_line", total=f"{total:.0f}", assigned=f"{assigned:.0f}")
        if abs(rem) >= 1:
            txt += "  " + _("color_export.remaining", g=f"{rem:.0f}")
        self._total_lbl.setText(txt)

    def _on_register(self):
        if self._register_cb is None:
            return
        try:
            self._register_cb()
        except Exception:
            pass
        self._reload_spools()

    def _on_confirm_clicked(self):
        if self._confirmed:
            return
        purge = self._purge_spin.value() if self._purge_cb.isChecked() else 0.0
        rows = [r.to_row() for r in self._rows]
        n = 0
        if self._on_confirm:
            try:
                n = self._on_confirm(rows, float(purge)) or 0
            except Exception:
                n = 0
        self._confirmed = True
        self._confirm_btn.setEnabled(False)
        self._confirm_status.setText(_("color_export.confirmed"))
