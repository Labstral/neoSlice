"""Sélecteur filament + imprimante avec vérification de compatibilité.

Flux guidé en deux étapes :
  ①  L'utilisateur choisit son imprimante et valide.
  ②  L'utilisateur choisit son filament et valide.
      → Émet `filament_confirmed` pour déverrouiller la suite.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel, QColor

from core.i18n import _
from data.filaments import FILAMENTS, FAMILLES_ORDRE
from data.printers import (
    PRINTERS, SERIES_ORDRE,
    catalogue_brands, models_for_brand, nozzles_for_model, is_catalogue_model,
    prusa_brands, prusa_models_for_brand, prusa_nozzles_for_model, is_prusa_model,
    split_popular,
)
from core.prefs import PREFS
from ui.components.brand_menu_button import BrandMenuButton
from ui.styles.theme import (
    BG_INPUT, BG_ELEVATED, BG_SURFACE,
    ACCENT, ACCENT_BRIGHT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, INACTIVE,
    TELE_GREEN, AMBER, ERROR_RED, FONT_MONO, MANAGER as _T,
    FONT_MAIN,)

_COMBO_STYLE = f"""
    QComboBox {{
        background: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {INACTIVE};
        border-radius: 3px;
        padding: 5px 8px;
        font-size: 13px;
        font-family: {FONT_MAIN};
    }}
    QComboBox:hover {{ border-color: {ACCENT}; }}
    QComboBox:disabled {{
        background: {BG_ELEVATED};
        color: {INACTIVE};
        border-color: {INACTIVE};
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox::down-arrow {{
        width: 0; height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {TEXT_SECONDARY};
    }}
    QComboBox QAbstractItemView {{
        background: {BG_ELEVATED};
        color: {TEXT_PRIMARY};
        border: 1px solid {INACTIVE};
        selection-background-color: {ACCENT};
        selection-color: #020408;
        outline: none;
        padding: 2px;
    }}
"""

_LABEL_STYLE = f"color: {TEXT_LABEL}; letter-spacing: 2px; background: transparent;"
_LABEL_STYLE_DIM = f"color: {INACTIVE}; letter-spacing: 2px; background: transparent;"

_BTN_VALIDATE = f"""
    QPushButton {{
        background: {ACCENT};
        color: #ffffff;
        border: none;
        border-radius: 3px;
        padding: 0 10px;
        font-size: 10px;
        font-family: {FONT_MAIN};
        font-weight: bold;
        letter-spacing: 1px;
    }}
    QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
"""
_BTN_DONE = f"""
    QPushButton {{
        background: transparent;
        color: {TELE_GREEN};
        border: 1px solid {TELE_GREEN};
        border-radius: 3px;
        padding: 0 8px;
        font-size: 10px;
    }}
"""


_NOZZLE_SIZES = [0.2, 0.4, 0.6, 0.8]
_NOZZLE_DEFAULT = 0.4

# Plateaux Bambu Studio / OrcaSlicer (label affiché, valeur curr_bed_type 3MF)
_PLATES_BAMBU = [
    ("Textured PEI Plate",                 "Textured PEI Plate"),
    ("Cool Plate / PLA Plate",             "Cool Plate"),
    ("Textured Cool Plate",                "Textured Cool Plate"),
    ("Smooth Cool Plate (H2)",             "Smooth Cool Plate"),
    ("Smooth PEI Plate / High Temp Plate", "Hot Plate"),
    ("Engineering Plate",                  "Engineering Plate"),
    ("Bambu Cool Plate SuperTack",         "Bambu Cool Plate SuperTack"),
]
_PLATE_DEFAULT_BAMBU = "Textured PEI Plate"

# Plateaux (« sheets » acier) PrusaSlicer — réellement différents de Bambu/Orca.
_PLATES_PRUSA = [
    ("Textured PEI Sheet",                 "Textured PEI Sheet"),
    ("Smooth PEI Sheet",                   "Smooth PEI Sheet"),
    ("Satin Sheet",                        "Satin Sheet"),
    ("Smooth PEI Sheet (High Temp)",       "Smooth PEI Sheet High Temp"),
]
_PLATE_DEFAULT_PRUSA = "Textured PEI Sheet"

# Compat : ancien nom encore référencé ailleurs → pointe sur le catalogue Bambu.
_PLATES = _PLATES_BAMBU
_PLATE_DEFAULT = _PLATE_DEFAULT_BAMBU


def _plates_for_slicer(slicer: str) -> tuple[list, str]:
    """Retourne (liste [(label, valeur), …], valeur par défaut) selon le slicer
    de sortie. PrusaSlicer a ses propres « sheets » acier ; Bambu et Orca
    partagent les plateaux Bambu Studio."""
    if slicer == "prusa":
        return _PLATES_PRUSA, _PLATE_DEFAULT_PRUSA
    return _PLATES_BAMBU, _PLATE_DEFAULT_BAMBU

# Combinaisons plateau × filament à signaler à l'utilisateur
_PLATE_WARNINGS: dict[str, dict[str, str]] = {
    "Cool Plate": {
        "PETG":  "⚠  PETG sur Cool Plate nécessite un agent de démoulage (colle PVA)",
        "ABS":   "⚠  ABS non recommandé sur Cool Plate — préférez Textured PEI ou Engineering Plate",
        "ASA":   "⚠  ASA non recommandé sur Cool Plate — préférez Textured PEI ou Engineering Plate",
        "Nylon": "⚠  Nylon non recommandé sur Cool Plate — préférez Engineering Plate",
        "PC":    "⚠  PC non recommandé sur Cool Plate — préférez Engineering Plate",
    },
    "Engineering Plate": {
        "PLA":   "⚠  PLA fonctionne mieux sur Textured PEI Plate",
        "TPU":   "⚠  TPU non recommandé sur Engineering Plate",
        "TPE":   "⚠  TPE non recommandé sur Engineering Plate",
    },
    "Bambu Cool Plate SuperTack": {
        # Seul PLA est officiellement documenté par Bambu sur ce plateau
        "PETG":  "⚠  PETG non officiel sur SuperTack — plateau conçu pour PLA uniquement",
        "ABS":   "⚠  ABS non recommandé sur SuperTack — température trop élevée",
        "ASA":   "⚠  ASA non recommandé sur SuperTack — température trop élevée",
        "Nylon": "⚠  Nylon non recommandé sur SuperTack — plateau conçu pour PLA uniquement",
        "PC":    "⚠  PC non recommandé sur SuperTack — plateau conçu pour PLA uniquement",
        "TPU":   "⚠  TPU non officiel sur SuperTack — plateau conçu pour PLA uniquement",
        "TPE":   "⚠  TPE non officiel sur SuperTack — plateau conçu pour PLA uniquement",
    },
}

_NOZZLE_COMBO_STYLE = f"""
    QComboBox {{
        background: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {INACTIVE};
        border-radius: 3px;
        padding: 4px 6px;
        font-size: 13px;
        font-family: {FONT_MAIN};
        min-width: 68px;
        max-width: 68px;
    }}
    QComboBox:hover {{ border-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 14px; }}
    QComboBox::down-arrow {{
        width: 0; height: 0;
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-top: 4px solid {TEXT_SECONDARY};
    }}
    QComboBox QAbstractItemView {{
        background: {BG_ELEVATED};
        color: {TEXT_PRIMARY};
        border: 1px solid {INACTIVE};
        selection-background-color: {ACCENT};
        selection-color: #020408;
        outline: none;
    }}
"""


class FilamentPrinterSelector(QWidget):
    """Widget compact en deux étapes guidées : imprimante → filament."""

    selection_changed  = Signal(str, str)  # printer_name, filament_name
    printer_confirmed  = Signal()          # émis quand l'étape ① est validée
    filament_confirmed = Signal()          # émis quand l'étape ② est validée
    nozzle_changed     = Signal(float)     # diamètre buse (mm) quand l'utilisateur change
    nozzle_changed     = Signal(float)     # émis quand le diamètre de buse change
    nozzle_changed     = Signal(float)     # diamètre buse (mm) quand l'utilisateur change

    def __init__(self, parent=None):
        super().__init__(parent)
        self._printer_done = False
        self._filament_done = False
        self._setup_ui()
        self._update_compatibility()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── ① Imprimante ──────────────────────────────────────────────────
        self._lbl_p = QLabel(_("selector.lbl_printer"))
        self._lbl_p.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._lbl_p.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(self._lbl_p)

        row_p = QHBoxLayout()
        row_p.setSpacing(6)

        self._printer_combo = BrandMenuButton()
        self._printer_combo.setStyleSheet(_COMBO_STYLE)
        self._populate_printers()
        self._printer_combo.selectionChanged.connect(self._on_changed)
        row_p.addWidget(self._printer_combo, 1)

        # ── Sélecteur buse (inline, toujours actif) ───────────────────────
        self._nozzle_combo = QComboBox()
        self._nozzle_combo.setStyleSheet(_NOZZLE_COMBO_STYLE)
        for d in _NOZZLE_SIZES:
            self._nozzle_combo.addItem(f"{d:.1f}mm", d)
        self._nozzle_combo.setCurrentIndex(_NOZZLE_SIZES.index(_NOZZLE_DEFAULT))
        self._nozzle_combo.setToolTip(_("selector.nozzle_tip"))
        self._nozzle_combo.currentIndexChanged.connect(
            lambda _: self.nozzle_changed.emit(float(self._nozzle_combo.currentData()))
        )
        row_p.addWidget(self._nozzle_combo)
        # Le combo imprimante est déjà peuplé : aligner les buses dispo sur la sélection
        self._sync_nozzles()

        self._btn_confirm_printer = QPushButton(_("selector.validate_btn"))
        self._btn_confirm_printer.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._btn_confirm_printer.setFixedHeight(32)
        self._btn_confirm_printer.setFixedWidth(76)
        self._btn_confirm_printer.setCursor(Qt.PointingHandCursor)
        self._btn_confirm_printer.setStyleSheet(_BTN_VALIDATE)
        self._btn_confirm_printer.clicked.connect(self._on_confirm_printer)
        row_p.addWidget(self._btn_confirm_printer)

        layout.addLayout(row_p)

        # Note imprimante non-Bambu (slicer cible) — masquée par défaut
        self._printer_note = QLabel("")
        self._printer_note.setFont(QFont(FONT_MAIN, 8))
        self._printer_note.setWordWrap(True)
        # Orange foncé (et non jaune) → lisible sur fond clair ET sombre
        self._printer_note.setStyleSheet("color: #E07000; background: transparent;")
        self._printer_note.hide()
        layout.addWidget(self._printer_note)
        layout.addSpacing(2)

        # ── ② Filament (verrouillé jusqu'à validation imprimante) ─────────
        self._lbl_f = QLabel(_("selector.lbl_filament"))
        self._lbl_f.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._lbl_f.setStyleSheet(_LABEL_STYLE_DIM)
        layout.addWidget(self._lbl_f)

        row_f = QHBoxLayout()
        row_f.setSpacing(6)

        self._filament_combo = QComboBox()
        self._filament_combo.setStyleSheet(_COMBO_STYLE)
        self._filament_combo.setEnabled(False)
        self._populate_filaments()
        self._filament_combo.currentIndexChanged.connect(self._on_changed)
        row_f.addWidget(self._filament_combo, 1)

        self._btn_confirm_filament = QPushButton(_("selector.validate_btn"))
        self._btn_confirm_filament.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._btn_confirm_filament.setFixedHeight(32)
        self._btn_confirm_filament.setFixedWidth(76)
        self._btn_confirm_filament.setEnabled(False)
        self._btn_confirm_filament.setCursor(Qt.PointingHandCursor)
        self._btn_confirm_filament.setStyleSheet(_BTN_VALIDATE)
        self._btn_confirm_filament.clicked.connect(self._on_confirm_filament)
        row_f.addWidget(self._btn_confirm_filament)

        layout.addLayout(row_f)

        # Hint sous le filament (visible avant validation imprimante)
        self._hint_filament = QLabel(_("selector.hint_printer_first"))
        self._hint_filament.setFont(QFont(FONT_MONO, 9))
        self._hint_filament.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        layout.addWidget(self._hint_filament)

        layout.addSpacing(6)

        # ── Plateau (verrouillé jusqu'à validation filament) ──────────────
        self._lbl_plate = QLabel(_("selector.lbl_plate"))
        self._lbl_plate.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._lbl_plate.setStyleSheet(_LABEL_STYLE_DIM)
        layout.addWidget(self._lbl_plate)

        self._plate_combo = QComboBox()
        self._plate_combo.setStyleSheet(_COMBO_STYLE)
        self._plate_combo.setEnabled(False)
        self._plate_combo.setToolTip(_("selector.plate_tip"))
        self._populate_plates()
        self._plate_combo.currentIndexChanged.connect(self._on_plate_changed)
        layout.addWidget(self._plate_combo)

        self._plate_warn_lbl = QLabel("")
        self._plate_warn_lbl.setFont(QFont(FONT_MONO, 9))
        self._plate_warn_lbl.setWordWrap(True)
        self._plate_warn_lbl.setStyleSheet(f"color: {_T.palette()['AMBER']}; background: transparent;")
        self._plate_warn_lbl.hide()
        layout.addWidget(self._plate_warn_lbl)

        layout.addSpacing(4)

        # ── Badge compatibilité ───────────────────────────────────────────
        self._compat_badge = QLabel()
        self._compat_badge.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._compat_badge.setWordWrap(True)
        self._compat_badge.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
        layout.addWidget(self._compat_badge)

    # ── Étapes ─────────────────────────────────────────────────────────────

    def _show_a2l_warning(self):
        """Avertissement BS 2.7.1 requis pour l'A2L — thème-aware avec case 'Ne plus afficher'."""
        from core.prefs import PREFS
        if PREFS.get("a2l_bs_warning_skip", False):
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton
        from PySide6.QtGui import QFont as _QFont

        pal = _T.palette()
        dlg = QDialog(self.window())
        dlg.setWindowTitle("Bambu Lab A2L")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(f"QDialog {{ background: {pal['BG_PANEL']}; }}")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        # Icône + titre
        title = QLabel("⚠  Bambu Studio 2.7.1 requis")
        title.setFont(_QFont(FONT_MAIN, 11, QFont.Bold))
        title.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        layout.addWidget(title)

        # Message
        msg = QLabel(
            "L'imprimante <b>Bambu Lab A2L</b> n'est disponible que dans "
            "<b>Bambu Studio 2.7.1</b> ou plus récent.<br><br>"
            "Si vous utilisez une version antérieure, le fichier .3MF généré "
            "ne s'ouvrira pas correctement dans Bambu Studio."
        )
        msg.setFont(_QFont(FONT_MAIN, 9))
        msg.setTextFormat(Qt.RichText)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        layout.addWidget(msg)

        # Case "Ne plus afficher"
        skip_cb = QCheckBox("Ne plus afficher ce message")
        skip_cb.setFont(_QFont(FONT_MAIN, 8))
        skip_cb.setStyleSheet(f"""
            QCheckBox {{ color: {pal['TEXT_SECONDARY']}; background: transparent; spacing: 5px; }}
            QCheckBox::indicator {{
                width: 12px; height: 12px;
                border: 1px solid {pal['INACTIVE']}; border-radius: 2px;
                background: {pal['BG_INPUT']};
            }}
            QCheckBox::indicator:checked {{
                background: {pal['ACCENT']}; border-color: {pal['ACCENT']};
            }}
        """)
        layout.addWidget(skip_cb)

        # Bouton OK
        btn = QPushButton("Compris →")
        btn.setFont(_QFont(FONT_MAIN, 9, QFont.Bold))
        btn.setFixedHeight(34)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                border: none; border-radius: 4px; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
        """)
        btn.clicked.connect(dlg.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        dlg.exec()
        if skip_cb.isChecked():
            PREFS.set("a2l_bs_warning_skip", True)

    def _on_confirm_printer(self):
        self._printer_done = True
        pal = _T.palette()
        tg = pal["TELE_GREEN"]; tl = pal["TEXT_LABEL"]

        self._btn_confirm_printer.setText("✓")
        self._btn_confirm_printer.setEnabled(False)
        self._btn_confirm_printer.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {tg};
                border: 1px solid {tg}; border-radius: 3px;
                padding: 0 8px; font-size: 10px;
            }}
        """)

        self._lbl_f.setStyleSheet(f"color: {tl}; letter-spacing: 2px; background: transparent;")
        self._filament_combo.setEnabled(True)
        self._btn_confirm_filament.setEnabled(True)
        self._hint_filament.hide()
        self.printer_confirmed.emit()

    def _on_confirm_filament(self):
        self._filament_done = True
        pal = _T.palette()
        tg = pal["TELE_GREEN"]; tl = pal["TEXT_LABEL"]

        self._btn_confirm_filament.setText("✓")
        self._btn_confirm_filament.setEnabled(False)
        self._btn_confirm_filament.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {tg};
                border: 1px solid {tg}; border-radius: 3px;
                padding: 0 8px; font-size: 10px;
            }}
        """)

        self._plate_combo.setEnabled(True)
        self._lbl_plate.setStyleSheet(f"color: {tl}; letter-spacing: 2px; background: transparent;")
        self._on_plate_changed()
        self.filament_confirmed.emit()

    def _on_plate_changed(self):
        if not self._filament_done:
            return
        plate = self.current_plate_type()
        filament = self.current_filament()
        warn = _PLATE_WARNINGS.get(plate, {}).get(filament, "")
        if warn:
            self._plate_warn_lbl.setText(warn)
            self._plate_warn_lbl.show()
        else:
            self._plate_warn_lbl.hide()

    # ── Populations ─────────────────────────────────────────────────────────

    def _printer_groups(self) -> list:
        """Construit [(libellé, payload), …] selon le slicer de sortie. Les marques
        courantes sont directes ; les autres sous « Autres marques ▸ »."""
        slicer = PREFS.get("slicer_output", "bambu")
        if slicer == "prusa":
            brands = prusa_brands()
            models = prusa_models_for_brand
            groups: list = []
        else:
            brands = catalogue_brands(slicer)
            models = lambda b: models_for_brand(b, slicer)
            by_serie: dict[str, list[str]] = {}
            for name, data in PRINTERS.items():
                by_serie.setdefault(data.get("serie", "Autre"), []).append(name)
            bambu = [(name, name) for serie in SERIES_ORDRE
                     for name in by_serie.get(serie, [])]
            groups = [("Bambu Lab", bambu)]

        popular, others = split_popular(brands)
        for b in popular:
            groups.append((b, models(b)))
        if others:
            groups.append(("Autres marques", [(b, models(b)) for b in others]))
        return groups

    def _populate_printers(self):
        self._printer_combo.set_groups(self._printer_groups())

    def _populate_filaments(self):
        model = QStandardItemModel()
        by_family: dict[str, list[str]] = {}
        for name, data in FILAMENTS.items():
            by_family.setdefault(data["famille"], []).append(name)

        for famille in FAMILLES_ORDRE:
            if famille not in by_family:
                continue
            header = QStandardItem(f"── {famille.upper()} ──")
            header.setEnabled(False)
            header.setForeground(QColor(TEXT_SECONDARY))
            header.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
            model.appendRow(header)
            for name in by_family[famille]:
                item = QStandardItem(f"  {name}")
                item.setData(name, Qt.UserRole)
                item.setFont(QFont(FONT_MAIN, 9))
                model.appendRow(item)

        self._filament_combo.setModel(model)
        for i in range(model.rowCount()):
            if model.item(i).isEnabled():
                self._filament_combo.setCurrentIndex(i)
                break

    # ── Logique ─────────────────────────────────────────────────────────────

    def _on_changed(self):
        self._sync_nozzles()
        self._update_printer_note()
        self._update_compatibility()
        printer = self.current_printer()
        # Avertissement A2L : affiché dès la sélection (pas seulement à la validation)
        if printer == "A2L":
            self._show_a2l_warning()
        filament = self.current_filament()
        if printer and filament:
            self.selection_changed.emit(printer, filament)

    def _update_compatibility(self):
        printer_name = self.current_printer()
        filament_name = self.current_filament()
        if not printer_name or not filament_name:
            self._compat_badge.setText("")
            return
        pal = _T.palette()
        status, _, msg = check_compatibility(printer_name, filament_name)
        color = {"ok": pal["TELE_GREEN"], "warning": pal["AMBER"], "error": pal["ERROR_RED"]}.get(status, pal["AMBER"])
        self._compat_badge.setStyleSheet(f"color: {color}; background: transparent;")
        self._compat_badge.setText(msg)

    def set_printer(self, name: str) -> None:
        if not name:
            return
        self._printer_combo.set_current_key(name, emit=False)

    def current_printer(self) -> str:
        return self._printer_combo.current_key()

    def current_filament(self) -> str:
        idx = self._filament_combo.currentIndex()
        data = self._filament_combo.model().item(idx)
        if data and data.isEnabled():
            return data.data(Qt.UserRole) or data.text().strip()
        return ""

    def refresh_printers(self) -> None:
        """Reconstruit la liste d'imprimantes (ex. après changement du slicer de
        sortie dans les réglages : on bascule entre catalogue Bambu/Orca et Prusa).
        Reconstruit aussi les plateaux : PrusaSlicer a ses propres « sheets »."""
        self._populate_printers()
        self._sync_nozzles()
        self._populate_plates()
        self._update_printer_note()

    def _populate_plates(self) -> None:
        """Remplit le combo de plateaux selon le slicer de sortie (Bambu/Orca ↔
        Prusa). Conserve le plateau courant s'il existe encore, sinon défaut."""
        slicer = PREFS.get("slicer_output", "bambu")
        plates, default = _plates_for_slicer(slicer)
        prev = self._plate_combo.currentData() if self._plate_combo.count() else None
        self._plate_combo.blockSignals(True)
        self._plate_combo.clear()
        for label, value in plates:
            self._plate_combo.addItem(label, value)
        values = [v for _, v in plates]
        target = prev if prev in values else default
        self._plate_combo.setCurrentIndex(values.index(target))
        self._plate_combo.blockSignals(False)
        # Réévaluer l'avertissement plateau×filament pour le nouveau catalogue
        self._on_plate_changed()

    def _update_printer_note(self) -> None:
        """Note adaptée au slicer de sortie choisi et à l'imprimante sélectionnée."""
        from data.printers import brand_of, is_prusa_model
        key = self.current_printer()
        slicer = PREFS.get("slicer_output", "bambu")

        if slicer == "prusa" or (key and is_prusa_model(key)):
            self._printer_note.setText(
                "ⓘ Sortie PrusaSlicer : ouvrez le 3MF dans PrusaSlicer. Pour le profil "
                "machine exact, installez l'imprimante (Configuration → Assistant)."
            )
            self._printer_note.show()
            return

        brand = brand_of(key) if key else ""
        if not brand:                      # imprimante Bambu Lab → rien à signaler
            self._printer_note.hide()
            return

        if slicer == "orca":
            self._printer_note.setText(
                f"ⓘ Imprimante {brand} : ouvrez le 3MF dans OrcaSlicer après avoir "
                f"ajouté ce modèle dans Orca si besoin."
            )
        else:  # bambu
            self._printer_note.setText(
                f"ⓘ Imprimante {brand} : ouvrez le 3MF dans Bambu Studio après avoir "
                f"ajouté ce modèle (menu « + » des imprimantes)."
            )
        self._printer_note.show()

    def _sync_nozzles(self) -> None:
        """Remplit le combo de buse avec les diamètres réellement disponibles pour
        l'imprimante choisie. Bambu Lab → 0.2/0.4/0.6/0.8 ; marques tierces →
        seulement les variantes présentes dans le catalogue."""
        key = self.current_printer()
        if key and is_prusa_model(key):
            sizes = prusa_nozzles_for_model(key) or list(_NOZZLE_SIZES)
        elif key and is_catalogue_model(key):
            sizes = nozzles_for_model(key) or list(_NOZZLE_SIZES)
        else:
            sizes = list(_NOZZLE_SIZES)
        prev = self.current_nozzle_diameter_mm()
        self._nozzle_combo.blockSignals(True)
        self._nozzle_combo.clear()
        for d in sizes:
            self._nozzle_combo.addItem(f"{d:.1f}mm", d)
        # Conserver la buse précédente si dispo, sinon 0.4 si présent, sinon la 1ère
        target = prev if prev in sizes else (_NOZZLE_DEFAULT if _NOZZLE_DEFAULT in sizes else sizes[0])
        self._nozzle_combo.setCurrentIndex(sizes.index(target))
        self._nozzle_combo.blockSignals(False)

    def current_nozzle_diameter_mm(self) -> float:
        """Retourne le diamètre de buse sélectionné (variable selon l'imprimante)."""
        return float(self._nozzle_combo.currentData() or _NOZZLE_DEFAULT)

    def current_plate_type(self) -> str:
        """Retourne la valeur du plateau sélectionné (curr_bed_type Bambu/Orca, ou
        « sheet » PrusaSlicer selon le slicer de sortie)."""
        slicer = PREFS.get("slicer_output", "bambu")
        _, default = _plates_for_slicer(slicer)
        return self._plate_combo.currentData() or default

    def refresh_theme(self):
        pal = _T.palette()
        bg_in  = pal["BG_INPUT"];   bg_el = pal["BG_ELEVATED"]
        tp     = pal["TEXT_PRIMARY"];  ts = pal["TEXT_SECONDARY"]
        tl     = pal["TEXT_LABEL"];   inc = pal["INACTIVE"]
        acc    = pal["ACCENT"];     accb = pal["ACCENT_BRIGHT"]
        tg     = pal["TELE_GREEN"]; amb  = pal["AMBER"]

        combo_style = f"""
            QComboBox {{
                background: {bg_in}; color: {tp};
                border: 1px solid {inc}; border-radius: 3px;
                padding: 5px 8px; font-size: 13px; font-family: {FONT_MAIN};
            }}
            QComboBox:hover {{ border-color: {acc}; }}
            QComboBox:disabled {{ background: {bg_el}; color: {inc}; border-color: {inc}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox::down-arrow {{
                width: 0; height: 0;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-top: 5px solid {ts};
            }}
            QComboBox QAbstractItemView {{
                background: {bg_el}; color: {tp}; border: 1px solid {inc};
                selection-background-color: {acc}; selection-color: #020408;
                outline: none; padding: 2px;
            }}
        """
        nozzle_style = f"""
            QComboBox {{
                background: {bg_in}; color: {tp};
                border: 1px solid {inc}; border-radius: 3px;
                padding: 4px 6px; font-size: 13px; font-family: {FONT_MAIN};
                min-width: 68px; max-width: 68px;
            }}
            QComboBox:hover {{ border-color: {acc}; }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox::down-arrow {{
                width: 0; height: 0;
                border-left: 3px solid transparent; border-right: 3px solid transparent;
                border-top: 4px solid {ts};
            }}
            QComboBox QAbstractItemView {{
                background: {bg_el}; color: {tp}; border: 1px solid {inc};
                selection-background-color: {acc}; selection-color: #020408; outline: none;
            }}
        """
        for combo in (self._printer_combo, self._filament_combo, self._plate_combo):
            combo.setStyleSheet(combo_style)
        self._printer_combo.apply_theme()   # style du menu déroulant en cascade
        self._nozzle_combo.setStyleSheet(nozzle_style)

        label_active = f"color: {tl}; letter-spacing: 2px; background: transparent;"
        label_dim    = f"color: {inc}; letter-spacing: 2px; background: transparent;"
        self._lbl_p.setStyleSheet(label_active)
        self._lbl_f.setStyleSheet(label_active if self._printer_done else label_dim)
        self._lbl_plate.setStyleSheet(label_active if self._filament_done else label_dim)

        btn_validate = f"""
            QPushButton {{
                background: {acc}; color: #ffffff; border: none; border-radius: 3px;
                padding: 0 10px; font-size: 10px; font-family: {FONT_MAIN};
                font-weight: bold; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {accb}; }}
        """
        btn_done = f"""
            QPushButton {{
                background: transparent; color: {tg};
                border: 1px solid {tg}; border-radius: 3px;
                padding: 0 8px; font-size: 10px;
            }}
        """
        self._btn_confirm_printer.setStyleSheet(btn_done if self._printer_done else btn_validate)
        self._btn_confirm_filament.setStyleSheet(btn_done if self._filament_done else btn_validate)

        self._hint_filament.setStyleSheet(f"color: {inc}; background: transparent;")
        self._plate_warn_lbl.setStyleSheet(f"color: {amb}; background: transparent;")
        self._compat_badge.setStyleSheet(f"color: {tg}; background: transparent;")
        self._update_compatibility()


# ── Logique compatibilité ──────────────────────────────────────────────────

def check_compatibility(printer_name: str, filament_name: str) -> tuple[str, str, str]:
    """Retourne (status, couleur, message). status = 'ok' | 'warning' | 'error'."""
    printer = PRINTERS.get(printer_name, {})
    filament = FILAMENTS.get(filament_name, {})
    if not printer or not filament:
        return "ok", TELE_GREEN, ""

    incompatibles = printer.get("filaments_incompatibles", [])
    if filament_name in incompatibles:
        return "error", ERROR_RED, f"✕  {filament_name} incompatible avec {printer_name}"

    warnings = []

    if filament.get("enceinte_requise") and not printer.get("enceinte"):
        warnings.append(f"Enceinte requise — {printer_name} est ouvert")

    if filament_name in ("TPU", "TPE") and printer.get("ams"):
        warnings.append("AMS incompatible — chargement direct requis")

    plateau_req = filament.get("plateau", 0)
    plateau_max = printer.get("plateau_max_temp", 999)
    if plateau_req > plateau_max:
        warnings.append(f"Plateau requis {plateau_req}°C > max {plateau_max}°C")

    if warnings:
        return "warning", AMBER, "⚠  " + " — ".join(warnings)

    return "ok", TELE_GREEN, f"✓  Compatible avec {printer_name}"
