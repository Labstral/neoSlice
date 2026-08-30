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
    cura_brands, cura_models_for_brand, cura_nozzles_for_model, is_cura_model,
    flashprint_brands, flashprint_models_for_brand, flashprint_nozzles_for_model,
    is_flashprint_model,
    split_popular, split_popular_souple,
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

# Types de plateau Bambu/Orca (label affiché, VALEUR = curr_bed_type écrit dans le
# 3MF). Noms canoniques OrcaSlicer (l'univers réel des profils Orca : 6 types), lus
# aussi par Bambu Studio pour les communs. La liste MONTRÉE dépend de l'imprimante :
# ensemble complet MOINS `not_support_bed_type` du modèle (data/bed_types.json).
# (« Bambu Cool Plate SuperTack » retiré : propre aux Bambu récentes, non déductible
#  par modèle depuis les profils — l'utilisateur le choisit dans le slicer si besoin.)
_BED_TYPES_ALL = [
    ("Textured PEI Plate",      "Textured PEI Plate"),      # défaut universel
    ("Smooth PEI Plate",        "Smooth PEI Plate"),        # = High Temp (code hot_plate)
    ("Cool Plate / PLA Plate",  "Cool Plate"),
    ("Engineering Plate",       "Engineering Plate"),
    ("Textured Cool Plate",     "Textured Cool Plate"),
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

# FlashPrint (FlashForge) : pas de notion de type de plateau dans les profils —
# une seule entrée neutre (le combo reste cohérent, la valeur n'est pas exportée).
# Libellé « Standard » identique FR/EN (comme les noms de plateaux Bambu/Prusa).
_PLATES_FLASHPRINT = [("Standard", "standard")]
_PLATE_DEFAULT_FLASHPRINT = "standard"

# Compat : ancien nom encore référencé ailleurs → ensemble complet Bambu/Orca.
_PLATES = _BED_TYPES_ALL
_PLATE_DEFAULT = _PLATE_DEFAULT_BAMBU


def _make_combo_shrinkable(combo: QComboBox) -> None:
    """Empêche un QComboBox de FORCER la largeur de la colonne à celle de son item
    le plus long. Sans ça, un plateau/filament au nom long impose une largeur mini
    énorme (mesuré : 480px) qui déborde du panneau de 360px → boutons ✓, flèches et
    bord droit COUPÉS (et aggravé par la mise à l'échelle Windows). On laisse le
    combo rétrécir et s'adapter à la place ; la liste déroulante reste complète."""
    from PySide6.QtWidgets import QSizePolicy
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(6)
    combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)


def _plates_for_printer(slicer: str, printer_key: str = "") -> tuple[list, str]:
    """Retourne (liste [(label, valeur), …], valeur par défaut) pour un slicer ET
    une imprimante. Bambu/Orca : ensemble complet des plateaux MOINS ceux que le
    modèle ne supporte pas (data/bed_types.json, ex. Bambu A1 mini sans Cool Plate),
    défaut = default_bed_type du modèle. PrusaSlicer : ses « sheets » acier.
    (Cura/FlashPrint : pas de plateau — géré/masqué par _populate_plates.)"""
    if slicer == "prusa":
        return _PLATES_PRUSA, _PLATE_DEFAULT_PRUSA
    if slicer == "flashprint":
        return _PLATES_FLASHPRINT, _PLATE_DEFAULT_FLASHPRINT
    from data.printers import printer_bed_info
    info = printer_bed_info(printer_key or "")
    ns = set(info.get("not_support", []))
    plates = [(lbl, val) for (lbl, val) in _BED_TYPES_ALL if val not in ns]
    if not plates:                                   # garde-fou (ne devrait pas arriver)
        plates = [_BED_TYPES_ALL[0]]
    values = [v for _lbl, v in plates]
    default = info.get("default", _PLATE_DEFAULT_BAMBU)
    if default not in values:
        default = values[0]
    return plates, default


def _plates_for_slicer(slicer: str) -> tuple[list, str]:
    """Compat : plateaux d'un slicer SANS imprimante précise (ensemble complet)."""
    return _plates_for_printer(slicer, "")

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
    slicer_switched    = Signal(str)       # « Mes machines » a basculé le slicer de sortie
    status_message     = Signal(str)       # message court pour la barre d'état
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

        # Épingler dans « Mes machines » (★ = épinglée) — glyphe discret, pas d'emoji
        self._pin_btn = QPushButton("☆")
        self._pin_btn.setFixedSize(30, 32)
        self._pin_btn.setCursor(Qt.PointingHandCursor)
        self._pin_btn.setToolTip(_("selector.pin_tip"))
        self._pin_btn.clicked.connect(self._on_pin_clicked)
        row_p.addWidget(self._pin_btn)
        self._refresh_pin_btn()

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
        # Ambre de la palette (comme l'avertissement plateau) : l'orange en dur
        # ignorait le thème et ternissait sur fond sombre. Rejoué par refresh_theme.
        self._printer_note.setStyleSheet(
            f"color: {_T.palette()['AMBER']}; background: transparent;")
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
        _make_combo_shrinkable(self._filament_combo)
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
        self._hint_filament.setWordWrap(True)   # sinon sa largeur mini déborde le panneau (coupure droite)
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
        _make_combo_shrinkable(self._plate_combo)
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

    # ── « Mes machines » : épingler la machine courante ───────────────────────
    def _refresh_pin_btn(self):
        """★ si la machine courante est épinglée, ☆ sinon (thème via _COMBO_STYLE-like)."""
        if not hasattr(self, "_pin_btn"):
            return
        try:
            from core import mes_machines as _mm
            slicer = PREFS.get("slicer_output", "bambu")
            printer = self.current_printer()
            pinned = bool(printer) and _mm.is_pinned(slicer, printer)
        except Exception:
            pinned = False
        pal = _T.palette()
        col = pal["ACCENT"] if pinned else pal["TEXT_LABEL"]
        self._pin_btn.setText("★" if pinned else "☆")
        # L'étoile est une BASCULE : dire ce que le clic va faire, sinon l'infobulle
        # promet « épingler » alors qu'elle va retirer (personne ne devine le retrait).
        self._pin_btn.setToolTip(_("selector.unpin_tip") if pinned
                                 else _("selector.pin_tip"))
        self._pin_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {col}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; font-size: 13px; }}"
            f"QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}")

    def _on_pin_clicked(self):
        try:
            from core import mes_machines as _mm
            slicer = PREFS.get("slicer_output", "bambu")
            printer = self.current_printer()
            if not printer:
                return
            label = self._printer_combo._key_label.get(printer, printer)
            _mm.toggle(slicer, printer, label)
            self._populate_printers()       # le groupe « Mes machines » suit
            self._refresh_pin_btn()
        except Exception:
            pass

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
        self._update_compatibility()          # badge « Compatible » : après validation
        self.filament_confirmed.emit()

    def _on_plate_changed(self):
        if not self._filament_done:
            return
        plate = self.current_plate_type()
        from data.filaments import base_materiau
        filament = base_materiau(self.current_filament())   # marque -> base
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
        elif slicer == "cura":
            brands = cura_brands()
            models = cura_models_for_brand
            groups = []
        elif slicer == "flashprint":
            brands = flashprint_brands()
            models = flashprint_models_for_brand
            groups = []
        else:
            brands = catalogue_brands(slicer)
            models = lambda b: models_for_brand(b, slicer)
            by_serie: dict[str, list[str]] = {}
            for name, data in PRINTERS.items():
                by_serie.setdefault(data.get("serie", "Autre"), []).append(name)
            bambu = [(name, name) for serie in SERIES_ORDRE
                     for name in by_serie.get(serie, [])]
            # Groupe « Bambu Lab » UNIQUEMENT pour les slicers qui ciblent vraiment
            # les Bambu Lab : Bambu Studio (natif) et OrcaSlicer (universel, embarque
            # le vendor Bambu). Les slicers de FABRICANT (CrealityPrint/ElegooSlicer/
            # Anycubic/Snapmaker) sont choisis par les possesseurs de CES machines ;
            # y proposer une Bambu Lab n'a pas de sens ET risque un export cassé (un
            # fork allégé peut ne pas connaître le preset Bambu -> mauvaise imprimante
            # au chargement). Le catalogue ne les marque d'ailleurs jamais compatibles.
            groups = [("Bambu Lab", bambu)] if slicer in ("bambu", "orca") else []

        # Cura : comparaison SOUPLE (fabricants suffixés différemment : « Creality3D »,
        # « Ultimaker B.V. » au lieu de « Creality »/« UltiMaker » → l'égalité stricte
        # les ratait tous, reléguant Creality et Ultimaker (marque native de Cura !)
        # sous « Autres marques »).
        popular, others = (split_popular_souple(brands) if slicer == "cura"
                          else split_popular(brands))
        for b in popular:
            groups.append((b, models(b)))
        if others:
            groups.append(("Autres marques", [(b, models(b)) for b in others]))

        # « Mes machines » EN TÊTE : les imprimantes épinglées (toutes marques et
        # tous slicers confondus) — en choisir une bascule slicer + imprimante
        # d'un seul geste (cf. _on_changed).
        try:
            from core import mes_machines as _mm
            pinned = _mm.list_machines()
            if pinned:
                entries = [(f"{m['label']}  ·  {_mm.slicer_label(m['slicer'])}",
                            _mm.machine_key(m)) for m in pinned]
                groups.insert(0, (_("selector.my_machines"), entries))
        except Exception:
            pass
        return groups

    def _populate_printers(self):
        self._printer_combo.set_groups(self._printer_groups())
        # La sélection par DÉFAUT ne doit jamais être une entrée « Mes machines »
        # (clé spéciale @mm) : au premier peuplement, le combo prend la première
        # feuille du menu — qui serait justement ce groupe s'il existe. On
        # rebascule silencieusement sur la première vraie imprimante.
        try:
            from core import mes_machines as _mm
            if _mm.parse_machine_key(self._printer_combo.current_key()) is not None:
                for _k in self._printer_combo._key_label:
                    if _mm.parse_machine_key(_k) is None:
                        self._printer_combo.set_current_key(_k, emit=False)
                        break
        except Exception:
            pass

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
                # affichage = label du catalogue (ex. « Nylon (PA) ») ;
                # la CLÉ interne reste dans UserRole (moteur, export)
                item = QStandardItem(f"  {FILAMENTS[name].get('label', name)}")
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
        # « Mes machines » : clé spéciale @mm:<slicer>:<imprimante> → basculer le
        # slicer de sortie si besoin, puis sélectionner la vraie imprimante (la
        # re-sélection repasse par la voie normale ci-dessous).
        try:
            from core import mes_machines as _mm
            _pk = _mm.parse_machine_key(self._printer_combo.current_key())
        except Exception:
            _pk = None
        if _pk is not None:
            _slicer_cible, _printer_cible = _pk
            if PREFS.get("slicer_output", "bambu") != _slicer_cible:
                PREFS.set("slicer_output", _slicer_cible)
                self.refresh_printers()             # catalogue + plateaux du slicer
                self.slicer_switched.emit(_slicer_cible)
            if _printer_cible in self._printer_combo._key_label:
                self._printer_combo.set_current_key(_printer_cible, emit=True)
            else:
                # Clé catalogue disparue (catalogue régénéré, machine renommée…).
                # On la RETIRE de « Mes machines » : sans ça le favori restait dans
                # le menu sans jamais pouvoir être sélectionné — donc l'étoile ne
                # passait jamais en ★ et il devenait IMPOSSIBLE à dépingler.
                _lbl = _printer_cible
                for _m in _mm.list_machines():
                    if _m["slicer"] == _slicer_cible and _m["printer"] == _printer_cible:
                        _lbl = _m.get("label") or _printer_cible
                        break
                _mm.unpin(_slicer_cible, _printer_cible)
                self._populate_printers()
                self.status_message.emit(
                    _("selector.pin_stale").format(
                        name=_lbl, slicer=_mm.slicer_label(_slicer_cible)))
                # puis première VRAIE imprimante, jamais une entrée @mm (aucune boucle)
                for _k in self._printer_combo._key_label:
                    if _mm.parse_machine_key(_k) is None:
                        self._printer_combo.set_current_key(_k, emit=True)
                        break
            return
        self._refresh_pin_btn()
        self._sync_nozzles()
        self._update_printer_note()
        self._populate_plates()          # les plateaux dépendent de l'imprimante choisie
        self._update_compatibility()
        printer = self.current_printer()
        # Avertissement A2L : affiché dès la sélection (pas seulement à la validation)
        if printer == "A2L":
            self._show_a2l_warning()
        filament = self.current_filament()
        if printer and filament:
            self.selection_changed.emit(printer, filament)

    def _update_compatibility(self):
        # Le badge ne s'affiche qu'une fois l'imprimante ET le filament VALIDÉS.
        # Avant, les combos ont des valeurs par défaut (X1 Carbon / PLA) mais rien
        # n'est confirmé → « Compatible avec X1 Carbon » était trompeur au démarrage.
        if not (self._printer_done and self._filament_done):
            self._compat_badge.setText("")
            return
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

    def restaurer_choix(self, printer: str, filament: str,
                        plate: str = "", nozzle_mm: float = 0.0) -> None:
        """Restaure une sélection complète et VALIDE les deux étapes (✓) — utilisé
        par « Réimprimer à l'identique » (bibliothèque de pièces). Chaque bloc est
        isolé : une imprimante disparue du catalogue n'empêche pas de restaurer
        le filament, etc."""
        if printer:
            try:
                self._printer_combo.set_current_key(printer, emit=False)
                self._sync_nozzles()
                self._populate_plates()
                self._update_printer_note()
                self._refresh_pin_btn()
            except Exception:
                pass
        if nozzle_mm:
            try:
                for i in range(self._nozzle_combo.count()):
                    if abs(float(self._nozzle_combo.itemData(i)) - nozzle_mm) < 1e-6:
                        self._nozzle_combo.setCurrentIndex(i)
                        break
            except Exception:
                pass
        if filament:
            try:
                model = self._filament_combo.model()
                for i in range(model.rowCount()):
                    it = model.item(i)
                    if it and it.isEnabled() and \
                            (it.data(Qt.UserRole) or it.text().strip()) == filament:
                        self._filament_combo.setCurrentIndex(i)
                        break
            except Exception:
                pass
        try:
            if not self._printer_done:
                self._on_confirm_printer()
            if not self._filament_done:
                self._on_confirm_filament()
        except Exception:
            pass
        if plate:
            try:
                idx = self._plate_combo.findData(plate)
                if idx >= 0:
                    self._plate_combo.setCurrentIndex(idx)
            except Exception:
                pass

    def est_valide(self) -> bool:
        """Étape ① complète : imprimante ET filament validés (✓) — le plateau
        reçoit alors sa valeur par défaut. Sert à verrouiller la génération
        pour les pièces qui arrivent SANS glisser-déposer (neoGen)."""
        return bool(self._printer_done and self._filament_done)

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
        Prusa). Conserve le plateau courant s'il existe encore, sinon défaut.
        Certains slicers de sortie n'ont PAS de « type de plateau » Bambu et leur
        builder ignore ce réglage → on masque le sélecteur pour éviter un faux choix :
          • FlashPrint : plateau fixe par machine, seule la température compte ;
          • Cura : notion inexistante (adhérence = jupe/bordure/radeau) — son builder
            ne reçoit jamais plate_type ; afficher les plateaux Bambu était trompeur.
        (Bambu/Orca et leurs forks — Creality/Elegoo/Anycubic/Snapmaker — comprennent
        curr_bed_type : le sélecteur reste. PrusaSlicer a ses propres feuilles acier.)"""
        slicer = PREFS.get("slicer_output", "bambu")
        _no_plate = slicer in ("flashprint", "cura")
        self._lbl_plate.setVisible(not _no_plate)
        self._plate_combo.setVisible(not _no_plate)
        if _no_plate:
            if hasattr(self, "_plate_warn_lbl"):     # peut être appelé avant sa création
                self._plate_warn_lbl.hide()
            return
        # Plateaux COHÉRENTS avec l'imprimante choisie (ensemble complet moins les
        # plateaux non supportés par ce modèle, ex. Bambu A1 mini sans Cool Plate).
        try:
            _printer = self.current_printer()
        except Exception:
            _printer = ""
        plates, default = _plates_for_printer(slicer, _printer)
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

        if slicer == "cura" or (key and is_cura_model(key)):
            self._printer_note.setText(
                "ⓘ À l'export, le fichier .3MF contiendra déjà cette imprimante, la buse "
                "et vos réglages : il suffira de l'ouvrir dans UltiMaker Cura, rien à "
                "configurer de plus."
            )
            self._printer_note.show()
            return

        if slicer == "flashprint" or (key and is_flashprint_model(key)):
            self._printer_note.setText(_("selector.note_flashprint"))
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
        elif slicer == "creality":
            self._printer_note.setText(
                f"ⓘ Imprimante {brand} : ouvrez le 3MF dans CrealityPrint après avoir "
                f"ajouté ce modèle dans CrealityPrint si besoin."
            )
        elif slicer == "elegoo":
            self._printer_note.setText(
                f"ⓘ Imprimante {brand} : ouvrez le 3MF dans ElegooSlicer après avoir "
                f"ajouté ce modèle dans ElegooSlicer si besoin."
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
        elif key and is_cura_model(key):
            sizes = cura_nozzles_for_model(key) or list(_NOZZLE_SIZES)
        elif key and is_flashprint_model(key):
            sizes = flashprint_nozzles_for_model(key) or list(_NOZZLE_SIZES)
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
        try:
            _, default = _plates_for_printer(slicer, self.current_printer())
        except Exception:
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
        self._printer_note.setStyleSheet(f"color: {amb}; background: transparent;")
        self._compat_badge.setStyleSheet(f"color: {tg}; background: transparent;")
        # L'étoile « Mes machines » a son style figé à sa dernière bascule : sans
        # ce rappel elle gardait la couleur de l'ANCIEN thème jusqu'au prochain clic.
        self._refresh_pin_btn()
        self._update_compatibility()


# ── Logique compatibilité ──────────────────────────────────────────────────

def check_compatibility(printer_name: str, filament_name: str) -> tuple[str, str, str]:
    """Retourne (status, couleur, message). status = 'ok' | 'warning' | 'error'."""
    printer = PRINTERS.get(printer_name, {})
    filament = FILAMENTS.get(filament_name, {})
    if not printer or not filament:
        return "ok", TELE_GREEN, ""
    from data.filaments import base_materiau
    base = base_materiau(filament_name)     # marque -> matériau de base

    incompatibles = printer.get("filaments_incompatibles", [])
    warnings = []
    if base in incompatibles:
        # Une fiche FABRICANT qui annonce « sans enceinte » (ex. Sunlu Easy PA,
        # PA basse déformation) lève le blocage générique de sa base — on
        # avertit au lieu d'interdire.
        if filament.get("marque") and filament.get("enceinte_requise") is False:
            warnings.append(f"{base} générique déconseillé sur {printer_name} — "
                            "cette fiche fabricant (basse déformation) permet "
                            "l'impression ouverte, surveillez l'adhérence")
        else:
            return "error", ERROR_RED, f"✕  {filament_name} incompatible avec {printer_name}"

    if filament.get("enceinte_requise") and not printer.get("enceinte"):
        warnings.append(f"Enceinte requise — {printer_name} est ouvert")

    if base in ("TPU", "TPE") and printer.get("ams"):
        warnings.append("AMS incompatible — chargement direct requis")

    plateau_req = filament.get("plateau", 0)
    plateau_max = printer.get("plateau_max_temp", 999)
    if plateau_req > plateau_max:
        warnings.append(f"Plateau requis {plateau_req}°C > max {plateau_max}°C")

    if warnings:
        return "warning", AMBER, "⚠  " + " — ".join(warnings)

    return "ok", TELE_GREEN, f"✓  Compatible avec {printer_name}"
