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

from data.filaments import FILAMENTS, FAMILLES_ORDRE
from data.printers import PRINTERS, SERIES_ORDRE
from ui.styles.theme import (
    BG_INPUT, BG_ELEVATED, BG_SURFACE,
    ACCENT, ACCENT_BRIGHT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, INACTIVE,
    TELE_GREEN, AMBER, ERROR_RED, FONT_MONO,
)

_COMBO_STYLE = f"""
    QComboBox {{
        background: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {INACTIVE};
        border-radius: 3px;
        padding: 5px 8px;
        font-size: 9px;
        font-family: "Segoe UI";
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
        color: #020408;
        border: none;
        border-radius: 3px;
        padding: 0 10px;
        font-size: 8px;
        font-family: "Segoe UI";
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

_NOZZLE_COMBO_STYLE = f"""
    QComboBox {{
        background: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {INACTIVE};
        border-radius: 3px;
        padding: 4px 6px;
        font-size: 9px;
        font-family: "Segoe UI";
        min-width: 64px;
        max-width: 64px;
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
        self._lbl_p = QLabel("① IMPRIMANTE CIBLE")
        self._lbl_p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        self._lbl_p.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(self._lbl_p)

        row_p = QHBoxLayout()
        row_p.setSpacing(6)

        self._printer_combo = QComboBox()
        self._printer_combo.setStyleSheet(_COMBO_STYLE)
        self._populate_printers()
        self._printer_combo.currentIndexChanged.connect(self._on_changed)
        row_p.addWidget(self._printer_combo, 1)

        # ── Sélecteur buse (inline, toujours actif) ───────────────────────
        self._nozzle_combo = QComboBox()
        self._nozzle_combo.setStyleSheet(_NOZZLE_COMBO_STYLE)
        for d in _NOZZLE_SIZES:
            self._nozzle_combo.addItem(f"O {d:.1f}mm", d)
        self._nozzle_combo.setCurrentIndex(_NOZZLE_SIZES.index(_NOZZLE_DEFAULT))
        self._nozzle_combo.setToolTip("Diamètre de buse installée sur l'imprimante")
        row_p.addWidget(self._nozzle_combo)

        self._btn_confirm_printer = QPushButton("VALIDER →")
        self._btn_confirm_printer.setFont(QFont("Segoe UI", 7, QFont.Bold))
        self._btn_confirm_printer.setFixedHeight(32)
        self._btn_confirm_printer.setFixedWidth(76)
        self._btn_confirm_printer.setCursor(Qt.PointingHandCursor)
        self._btn_confirm_printer.setStyleSheet(_BTN_VALIDATE)
        self._btn_confirm_printer.clicked.connect(self._on_confirm_printer)
        row_p.addWidget(self._btn_confirm_printer)

        layout.addLayout(row_p)
        layout.addSpacing(2)

        # ── ② Filament (verrouillé jusqu'à validation imprimante) ─────────
        self._lbl_f = QLabel("② FILAMENT")
        self._lbl_f.setFont(QFont("Segoe UI", 7, QFont.Bold))
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

        self._btn_confirm_filament = QPushButton("VALIDER →")
        self._btn_confirm_filament.setFont(QFont("Segoe UI", 7, QFont.Bold))
        self._btn_confirm_filament.setFixedHeight(32)
        self._btn_confirm_filament.setFixedWidth(76)
        self._btn_confirm_filament.setEnabled(False)
        self._btn_confirm_filament.setCursor(Qt.PointingHandCursor)
        self._btn_confirm_filament.setStyleSheet(_BTN_VALIDATE)
        self._btn_confirm_filament.clicked.connect(self._on_confirm_filament)
        row_f.addWidget(self._btn_confirm_filament)

        layout.addLayout(row_f)

        # Hint sous le filament (visible avant validation imprimante)
        self._hint_filament = QLabel("← Validez d'abord votre imprimante")
        self._hint_filament.setFont(QFont(FONT_MONO, 7))
        self._hint_filament.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        layout.addWidget(self._hint_filament)

        layout.addSpacing(4)

        # ── Badge compatibilité ───────────────────────────────────────────
        self._compat_badge = QLabel()
        self._compat_badge.setFont(QFont(FONT_MONO, 8))
        self._compat_badge.setWordWrap(True)
        self._compat_badge.setStyleSheet(f"color: {TELE_GREEN}; background: transparent;")
        layout.addWidget(self._compat_badge)

    # ── Étapes ─────────────────────────────────────────────────────────────

    def _on_confirm_printer(self):
        self._printer_done = True

        # Bouton imprimante → état "fait"
        self._btn_confirm_printer.setText("✓")
        self._btn_confirm_printer.setEnabled(False)
        self._btn_confirm_printer.setStyleSheet(_BTN_DONE)

        # Déverrouiller filament
        self._lbl_f.setStyleSheet(_LABEL_STYLE)
        self._filament_combo.setEnabled(True)
        self._btn_confirm_filament.setEnabled(True)
        self._hint_filament.hide()
        self.printer_confirmed.emit()

    def _on_confirm_filament(self):
        self._filament_done = True

        # Bouton filament → état "fait"
        self._btn_confirm_filament.setText("✓")
        self._btn_confirm_filament.setEnabled(False)
        self._btn_confirm_filament.setStyleSheet(_BTN_DONE)

        self.filament_confirmed.emit()

    # ── Populations ─────────────────────────────────────────────────────────

    def _populate_printers(self):
        model = QStandardItemModel()
        by_serie: dict[str, list[str]] = {}
        for name, data in PRINTERS.items():
            by_serie.setdefault(data.get("serie", "Autre"), []).append(name)

        for serie in SERIES_ORDRE:
            if serie not in by_serie:
                continue
            header = QStandardItem(f"── {serie.upper()} ──")
            header.setEnabled(False)
            header.setForeground(QColor(TEXT_SECONDARY))
            header.setFont(QFont("Segoe UI", 7, QFont.Bold))
            model.appendRow(header)
            for name in by_serie[serie]:
                item = QStandardItem(f"  {name}")
                item.setData(name, Qt.UserRole)
                item.setFont(QFont("Segoe UI", 9))
                model.appendRow(item)

        self._printer_combo.setModel(model)
        for i in range(model.rowCount()):
            if model.item(i).isEnabled():
                self._printer_combo.setCurrentIndex(i)
                break

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
            header.setFont(QFont("Segoe UI", 7, QFont.Bold))
            model.appendRow(header)
            for name in by_family[famille]:
                item = QStandardItem(f"  {name}")
                item.setData(name, Qt.UserRole)
                item.setFont(QFont("Segoe UI", 9))
                model.appendRow(item)

        self._filament_combo.setModel(model)
        for i in range(model.rowCount()):
            if model.item(i).isEnabled():
                self._filament_combo.setCurrentIndex(i)
                break

    # ── Logique ─────────────────────────────────────────────────────────────

    def _on_changed(self):
        self._update_compatibility()
        printer = self.current_printer()
        filament = self.current_filament()
        if printer and filament:
            self.selection_changed.emit(printer, filament)

    def _update_compatibility(self):
        printer_name = self.current_printer()
        filament_name = self.current_filament()
        if not printer_name or not filament_name:
            self._compat_badge.setText("")
            return
        status, color, msg = check_compatibility(printer_name, filament_name)
        self._compat_badge.setStyleSheet(f"color: {color}; background: transparent;")
        self._compat_badge.setText(msg)

    def current_printer(self) -> str:
        idx = self._printer_combo.currentIndex()
        data = self._printer_combo.model().item(idx)
        if data and data.isEnabled():
            return data.data(Qt.UserRole) or data.text().strip()
        return ""

    def current_filament(self) -> str:
        idx = self._filament_combo.currentIndex()
        data = self._filament_combo.model().item(idx)
        if data and data.isEnabled():
            return data.data(Qt.UserRole) or data.text().strip()
        return ""

    def current_nozzle_diameter_mm(self) -> float:
        """Retourne le diamètre de buse sélectionné (0.2 / 0.4 / 0.6 / 0.8 mm)."""
        return float(self._nozzle_combo.currentData() or _NOZZLE_DEFAULT)


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
