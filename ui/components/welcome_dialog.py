"""Popup de bienvenue — affiché au premier lancement de neoSlice."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame, QWidget,
)
from PySide6.QtCore import Qt, QUrl, QPoint
from PySide6.QtGui import QFont, QPixmap, QDesktopServices, QMouseEvent

from ui.styles.theme import (
    BG_PANEL, BG_SURFACE, BG_ELEVATED,
    ACCENT, ACCENT_BRIGHT, TELE_GREEN, AMBER, INACTIVE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL,
    FONT_MONO,
)

_PREFS_FILE = Path.home() / ".neoslice" / "prefs.json"
_COFFEE_URL = "https://buymeacoffee.com/bambulabpourlesnuls"


def _load_prefs() -> dict:
    try:
        if _PREFS_FILE.exists():
            return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_prefs(prefs: dict) -> None:
    _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_FILE.write_text(
        json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def should_show_welcome() -> bool:
    return not _load_prefs().get("skip_welcome", False)


class WelcomeDialog(QDialog):
    """Fenêtre de bienvenue modale, sans cadre natif, déplaçable."""

    def __init__(self, parent=None, assets_path: Path | None = None):
        super().__init__(parent)
        self._assets = assets_path
        self._drag_pos: QPoint | None = None

        self.setWindowTitle("neoSlice")
        self.setMinimumWidth(480)
        self.setMaximumWidth(520)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG_PANEL};
                border: 1px solid {ACCENT};
                border-radius: 6px;
            }}
        """)
        self._setup_ui()

    # ── Drag-to-move ───────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    # ── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 26)
        root.setSpacing(0)

        # ── Logo + Titre ──────────────────────────────────────────────────
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)

        logo_loaded = False
        if self._assets:
            px_path = self._assets / "neoSlice.png"
            if px_path.exists():
                px = QPixmap(str(px_path))
                if not px.isNull():
                    logo_lbl.setPixmap(
                        px.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    logo_loaded = True

        if not logo_loaded:
            logo_lbl.setText("◈")
            logo_lbl.setFont(QFont("Segoe UI", 72))
            logo_lbl.setStyleSheet(f"color: {ACCENT_BRIGHT}; background: transparent;")

        root.addWidget(logo_lbl)
        root.addSpacing(8)

        title_lbl = QLabel("neoSlice")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; letter-spacing: 6px; background: transparent;"
        )
        root.addWidget(title_lbl)

        sub_lbl = QLabel("AI-POWERED 3D PRINT OPTIMIZER")
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setFont(QFont(FONT_MONO, 8))
        sub_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; letter-spacing: 3px; background: transparent;"
        )
        root.addWidget(sub_lbl)

        root.addSpacing(12)

        # Badges version / bêta / auteur
        badges = QHBoxLayout()
        badges.setAlignment(Qt.AlignCenter)
        badges.setSpacing(8)

        for text, fg, bg, border in [
            ("v0.1.0",                ACCENT_BRIGHT, BG_SURFACE,            ACCENT),
            ("BÊTA",                  AMBER,          "rgba(255,184,0,0.10)", AMBER),
            ("© 2026 Emmanuel Percheron", INACTIVE,   "transparent",         "transparent"),
        ]:
            lbl = QLabel(text)
            lbl.setFont(QFont(FONT_MONO, 7, QFont.Bold if text == "BÊTA" else QFont.Normal))
            lbl.setStyleSheet(
                f"color: {fg}; background: {bg}; border: 1px solid {border}; "
                f"border-radius: 3px; padding: 2px 7px;"
            )
            badges.addWidget(lbl)

        root.addLayout(badges)
        root.addSpacing(20)
        root.addWidget(self._sep())
        root.addSpacing(16)

        # ── Message de bienvenue ──────────────────────────────────────────
        welcome = QLabel(
            "Merci d'avoir téléchargé <b>neoSlice</b> !<br>"
            "Ce logiciel a été entièrement conçu et développé par "
            "<b>Emmanuel Percheron</b>, pour simplifier et optimiser "
            "l'impression 3D avec les imprimantes Bambu Lab.<br><br>"
            "J'espère sincèrement qu'il vous sera utile dans vos projets."
        )
        welcome.setFont(QFont("Segoe UI", 9))
        welcome.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        welcome.setWordWrap(True)
        welcome.setAlignment(Qt.AlignCenter)
        root.addWidget(welcome)
        root.addSpacing(14)

        # Encart bêta
        beta_box = QWidget()
        beta_box.setStyleSheet(f"""
            QWidget {{
                background: rgba(255,184,0,0.07);
                border-left: 3px solid {AMBER};
                border-radius: 2px;
            }}
        """)
        beta_lay = QVBoxLayout(beta_box)
        beta_lay.setContentsMargins(12, 8, 12, 8)
        beta_lbl = QLabel(
            f"<b style='color:{AMBER}'>⚠  Version Bêta</b><br>"
            f"<span style='color:{TEXT_LABEL}'>Ce logiciel est en développement actif. "
            "Des correctifs et de nouvelles fonctionnalités seront apportés régulièrement. "
            "Si vous rencontrez un problème, n'hésitez pas à le signaler.</span>"
        )
        beta_lbl.setFont(QFont("Segoe UI", 8))
        beta_lbl.setStyleSheet("background: transparent;")
        beta_lbl.setWordWrap(True)
        beta_lay.addWidget(beta_lbl)
        root.addWidget(beta_box)

        root.addSpacing(16)
        root.addWidget(self._sep())
        root.addSpacing(14)

        # ── Buy Me a Coffee ───────────────────────────────────────────────
        coffee_title = QLabel("☕  Ce logiciel est <b>entièrement gratuit</b> et le restera.")
        coffee_title.setFont(QFont("Segoe UI", 9))
        coffee_title.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        coffee_title.setAlignment(Qt.AlignCenter)
        root.addWidget(coffee_title)

        coffee_sub = QLabel("Si vous souhaitez soutenir le développement :")
        coffee_sub.setFont(QFont("Segoe UI", 8))
        coffee_sub.setStyleSheet(f"color: {TEXT_LABEL}; background: transparent;")
        coffee_sub.setAlignment(Qt.AlignCenter)
        root.addWidget(coffee_sub)

        root.addSpacing(10)

        coffee_btn = QPushButton("♥   Me soutenir sur Buy Me a Coffee")
        coffee_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        coffee_btn.setFixedHeight(36)
        coffee_btn.setCursor(Qt.PointingHandCursor)
        coffee_btn.setStyleSheet("""
            QPushButton {
                background: #FFDD00;
                color: #1A1A1A;
                border: none;
                border-radius: 4px;
                padding: 0 20px;
            }
            QPushButton:hover { background: #FFE840; }
            QPushButton:pressed { background: #F0CE00; }
        """)
        coffee_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_COFFEE_URL))
        )
        root.addWidget(coffee_btn)

        root.addSpacing(18)
        root.addWidget(self._sep())
        root.addSpacing(14)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self._skip_check = QCheckBox("Ne plus afficher ce message")
        self._skip_check.setFont(QFont("Segoe UI", 8))
        self._skip_check.setStyleSheet(f"""
            QCheckBox {{
                color: {TEXT_LABEL};
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {INACTIVE};
                border-radius: 2px;
                background: {BG_SURFACE};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border-color: {ACCENT};
                image: none;
            }}
            QCheckBox::indicator:hover {{ border-color: {ACCENT_BRIGHT}; }}
        """)
        footer.addWidget(self._skip_check)
        footer.addStretch()

        close_btn = QPushButton("Commencer →")
        close_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        close_btn.setFixedHeight(34)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setDefault(True)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #020408;
                border: none;
                border-radius: 4px;
                padding: 0 22px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
        """)
        close_btn.clicked.connect(self._on_close)
        footer.addWidget(close_btn)

        root.addLayout(footer)

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {INACTIVE};")
        return f

    def _on_close(self):
        if self._skip_check.isChecked():
            prefs = _load_prefs()
            prefs["skip_welcome"] = True
            _save_prefs(prefs)
        self.accept()
