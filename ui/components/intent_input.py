from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from ui.styles.theme import (
    ACCENT, ACCENT_BRIGHT, BG_INPUT, BG_ELEVATED, BG_SURFACE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, TELE_GREEN, INACTIVE,
    FONT_MONO, FONT_MAIN,
)

_PLACEHOLDER = 'Ex: "Je veux une pièce ultra solide" ou "Impression rapide prototype"'

_QUICK_INTENTS = [
    ("⬡ Ultra solide",       "Ultra solide"),
    ("⬡ Rapide",             "Impression rapide"),
    ("⬡ Qualité max",        "Meilleure qualité"),
    ("⬡ Supports faciles",   "Supports faciles à enlever"),
    ("⬡ Éco filament",       "Économiser filament"),
    ("⬡ Extérieur",          "Résistance extérieur"),
]


class IntentInput(QWidget):
    """Champ d'intention + presets rapides — style Mission Control."""

    intent_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- QTextEdit auto-resize ---
        self._input = QTextEdit()
        self._input.setPlaceholderText(_PLACEHOLDER)
        self._input.setFont(QFont(FONT_MAIN, 10))
        self._input.setFixedHeight(72)
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_INPUT};
                border: 1px solid {INACTIVE};
                border-radius: 3px;
                color: {TEXT_PRIMARY};
                padding: 8px 10px;
                selection-background-color: {ACCENT};
            }}
            QTextEdit:focus {{
                border: 1px solid {ACCENT_BRIGHT};
            }}
        """)
        self._input.document().contentsChanged.connect(self._adjust_height)
        layout.addWidget(self._input)

        # --- Bouton GÉNÉRER ---
        self._btn = QPushButton("GÉNÉRER CONFIGURATION →")
        self._btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self._btn.setFixedHeight(38)
        self._btn.setEnabled(False)
        self._btn.clicked.connect(self._on_submit)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #020408;
                border: none;
                border-radius: 3px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {ACCENT_BRIGHT};
            }}
            QPushButton:disabled {{
                background: {INACTIVE};
                color: {TEXT_LABEL};
            }}
        """)
        layout.addWidget(self._btn)

        # --- Presets en chips wrapping ---
        chips_label = QLabel("PRESETS RAPIDES")
        chips_label.setFont(QFont("Segoe UI", 7, QFont.Bold))
        chips_label.setStyleSheet(f"color: {TEXT_LABEL}; letter-spacing: 2px;")
        layout.addWidget(chips_label)

        chips_wrap = QWidget()
        chips_wrap.setStyleSheet("background: transparent;")
        self._chips_layout = _WrapLayout(chips_wrap)
        self._chips_layout.setSpacing(4)

        for label, intent_text in _QUICK_INTENTS:
            chip = QPushButton(label)
            chip.setFont(QFont(FONT_MONO, 8))
            chip.setFixedHeight(24)
            chip.setStyleSheet(f"""
                QPushButton {{
                    background: {BG_ELEVATED};
                    color: {TEXT_SECONDARY};
                    border: 1px solid {INACTIVE};
                    border-radius: 2px;
                    padding: 0 8px;
                }}
                QPushButton:hover {{
                    background: {BG_SURFACE};
                    border-color: {ACCENT};
                    color: {ACCENT_BRIGHT};
                }}
            """)
            chip.clicked.connect(lambda checked, t=intent_text: self._apply_quick(t))
            self._chips_layout.addWidget(chip)

        layout.addWidget(chips_wrap)
        layout.addStretch()

        self._input.textChanged.connect(self._on_text_changed)

    def _adjust_height(self):
        doc_h = int(self._input.document().size().height())
        margins = self._input.contentsMargins()
        target = min(max(doc_h + margins.top() + margins.bottom() + 18, 72), 160)
        self._input.setFixedHeight(target)

    def _on_text_changed(self):
        has_text = len(self._input.toPlainText().strip()) > 0
        self._btn.setEnabled(has_text and not self._loading)

    def _apply_quick(self, text: str):
        self._input.setPlainText(text)
        self._input.setFocus()

    def _on_submit(self):
        text = self._input.toPlainText().strip()
        if text:
            self.intent_submitted.emit(text)

    def enable_generate(self, enabled: bool):
        self._btn.setEnabled(enabled and len(self._input.toPlainText().strip()) > 0)

    def set_loading(self, loading: bool):
        self._loading = loading
        if loading:
            self._btn.setText("◌  ANALYSE EN COURS...")
            self._btn.setEnabled(False)
        else:
            self._btn.setText("GÉNÉRER CONFIGURATION →")
            self._btn.setEnabled(len(self._input.toPlainText().strip()) > 0)


class _WrapLayout:
    """Layout wrapping minimal pour les chips (FlowLayout simplifié)."""

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._widgets: list[QWidget] = []
        self._spacing = 4

    def setSpacing(self, s: int):
        self._spacing = s

    def addWidget(self, w: QWidget):
        w.setParent(self._parent)
        self._widgets.append(w)
        self._relayout()
        self._parent.resizeEvent = self._on_resize

    def _on_resize(self, event):
        self._relayout()

    def _relayout(self):
        x, y, row_h = 0, 0, 0
        w = self._parent.width() or 240
        for widget in self._widgets:
            sh = widget.sizeHint()
            if x + sh.width() > w and x > 0:
                x = 0
                y += row_h + self._spacing
                row_h = 0
            widget.setGeometry(x, y, sh.width(), sh.height())
            x += sh.width() + self._spacing
            row_h = max(row_h, sh.height())
        total_h = y + row_h if self._widgets else 0
        self._parent.setFixedHeight(max(total_h, 24))
