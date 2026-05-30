"""
Exemple autonome — fenêtre de mise à jour neoSlice (thème clair).
Lancer directement : python ui/update_dialog_example.py
"""
from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import (
    QPixmap, QFont, QColor, QPalette, QPainter, QLinearGradient,
    QBrush, QPen, QIcon,
)

# ── Palette thème clair ────────────────────────────────────────────────────

_L = {
    "BG":          "#f5f6f8",
    "PANEL":       "#ffffff",
    "BORDER":      "#e0e4ea",
    "ACCENT":      "#2d8a4e",
    "ACCENT_DARK": "#1f6b3a",
    "TEXT_H":      "#1a1a2e",
    "TEXT":        "#3a3a4a",
    "TEXT_MUTED":  "#7a8290",
    "TAG_BG":      "#e8f5ee",
    "TAG_FG":      "#1f7a42",
    "WARN_BG":     "#fff8e8",
    "WARN_FG":     "#b06000",
    "INFO_BG":     "#eaf3ff",
    "INFO_FG":     "#1a5fb4",
    "RED_BG":      "#fdecea",
    "RED_FG":      "#c0392b",
    "SHADOW":      QColor(0, 0, 0, 28),
}

_CHANGELOG = [
    {
        "version": "v0.2.0",
        "date": "30 mai 2026",
        "tag": "Nouveauté",
        "tag_style": "new",
        "items": [
            "Rendu 3D studio — PBR haute qualité, fond dégradé, éclairage cinématique",
            "Détection surplombs ultra-poly (> 500 k faces) via numpy vectorisé",
            "Correction crash au 3ᵉ glisser-déposer (thread zombie)",
            "Logo PDF corrigé — ratio d'aspect préservé",
        ],
    },
    {
        "version": "v0.1.1",
        "date": "12 mai 2026",
        "tag": "Correctif",
        "tag_style": "fix",
        "items": [
            "Grille invisible en mode sombre — corrigée",
            "Faces rouges au bas de la pièce (surplomb faux positif) — corrigées",
            "VOL.SUPPORT = 0 % pour meshes moyens (KingKong 484 k faces) — corrigé",
        ],
    },
    {
        "version": "v0.1.0",
        "date": "1ᵉʳ mai 2026",
        "tag": "Initial",
        "tag_style": "info",
        "items": [
            "Première version publique",
            "Chargement STL / OBJ / 3MF, analyse surplombs, export PDF",
        ],
    },
]

_TAG_STYLES = {
    "new":  (_L["TAG_BG"],  _L["TAG_FG"]),
    "fix":  (_L["WARN_BG"], _L["WARN_FG"]),
    "info": (_L["INFO_BG"], _L["INFO_FG"]),
}


def _shadow(widget, blur=18, dy=4, color=None):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(color or _L["SHADOW"])
    widget.setGraphicsEffect(fx)
    return fx


class _UpdateDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mise à jour disponible — neoSlice")
        self.setFixedSize(520, 620)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag_pos = None
        self._build_ui()

    # ── Drag ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)

        # Carte principale
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(f"""
            QFrame#card {{
                background: {_L['PANEL']};
                border-radius: 16px;
                border: 1px solid {_L['BORDER']};
            }}
        """)
        _shadow(card, blur=32, dy=8)
        root.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_header())
        lay.addWidget(self._build_version_banner())
        lay.addWidget(self._build_changelog(), stretch=1)
        lay.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(64)
        w.setStyleSheet(f"""
            background: {_L['PANEL']};
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
            border-bottom: 1px solid {_L['BORDER']};
        """)
        h = QHBoxLayout(w)
        h.setContentsMargins(20, 0, 16, 0)

        # Logo
        logo_path = Path(__file__).parent.parent / "assets" / "neoSlice.png"
        lbl_logo = QLabel()
        if logo_path.exists():
            px = QPixmap(str(logo_path)).scaled(
                34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            lbl_logo.setPixmap(px)
            lbl_logo.setFixedSize(34, 34)
        h.addWidget(lbl_logo)
        h.addSpacing(10)

        # Titre
        title = QLabel("neoSlice")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {_L['TEXT_H']}; letter-spacing: 2px;")
        h.addWidget(title)
        h.addStretch()

        # Bouton fermer
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_L['TEXT_MUTED']};
                border: none;
                font-size: 14px;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {_L['BORDER']};
                color: {_L['TEXT_H']};
            }}
        """)
        btn_close.clicked.connect(self.reject)
        h.addWidget(btn_close)
        return w

    def _build_version_banner(self) -> QWidget:
        """Bandeau coloré : version actuelle → nouvelle version."""
        w = QWidget()
        w.setFixedHeight(88)
        w.setStyleSheet(f"background: {_L['BG']};")
        h = QHBoxLayout(w)
        h.setContentsMargins(24, 0, 24, 0)

        def _ver_block(label, version, muted=False):
            col = QWidget()
            v = QVBoxLayout(col)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {_L['TEXT_MUTED']};")
            ver = QLabel(version)
            ver.setFont(QFont("Segoe UI", 18, QFont.Bold))
            ver.setStyleSheet(
                f"color: {_L['TEXT_MUTED']};" if muted
                else f"color: {_L['ACCENT_DARK']};"
            )
            v.addWidget(lbl)
            v.addWidget(ver)
            return col

        h.addWidget(_ver_block("Version installée", "v0.1.1", muted=True))
        h.addStretch()

        # Flèche
        arr = QLabel("→")
        arr.setFont(QFont("Segoe UI", 22))
        arr.setStyleSheet(f"color: {_L['BORDER']};")
        h.addWidget(arr)

        h.addStretch()
        h.addWidget(_ver_block("Nouvelle version", "v0.2.0"))
        return w

    def _build_changelog(self) -> QWidget:
        """Zone scrollable des notes de version."""
        outer = QFrame()
        outer.setStyleSheet(f"""
            QFrame {{
                background: {_L['BG']};
                border-top: 1px solid {_L['BORDER']};
                border-bottom: 1px solid {_L['BORDER']};
            }}
        """)
        v = QVBoxLayout(outer)
        v.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #eef0f3; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #c0c8d0; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(16)

        for entry in _CHANGELOG:
            cl.addWidget(self._build_entry(entry))

        cl.addStretch()
        scroll.setWidget(content)
        v.addWidget(scroll)
        return outer

    def _build_entry(self, entry: dict) -> QWidget:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_L['PANEL']};
                border-radius: 10px;
                border: 1px solid {_L['BORDER']};
            }}
        """)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 14)
        v.setSpacing(8)

        # En-tête de version
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        ver_lbl = QLabel(entry["version"])
        ver_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        ver_lbl.setStyleSheet(f"color: {_L['TEXT_H']};")
        hdr.addWidget(ver_lbl)

        # Tag coloré
        tag_bg, tag_fg = _TAG_STYLES.get(entry["tag_style"], (_L["INFO_BG"], _L["INFO_FG"]))
        tag = QLabel(entry["tag"])
        tag.setFont(QFont("Segoe UI", 8, QFont.Bold))
        tag.setStyleSheet(f"""
            color: {tag_fg};
            background: {tag_bg};
            border-radius: 8px;
            padding: 2px 8px;
        """)
        tag.setFixedHeight(20)
        hdr.addWidget(tag)
        hdr.addStretch()

        date_lbl = QLabel(entry["date"])
        date_lbl.setFont(QFont("Segoe UI", 8))
        date_lbl.setStyleSheet(f"color: {_L['TEXT_MUTED']};")
        hdr.addWidget(date_lbl)
        v.addLayout(hdr)

        # Séparateur
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_L['BORDER']}; margin: 0;")
        sep.setFixedHeight(1)
        v.addWidget(sep)

        # Items
        for item in entry["items"]:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)

            dot = QLabel("•")
            dot.setFont(QFont("Segoe UI", 12))
            dot.setStyleSheet(f"color: {_L['ACCENT']};")
            dot.setFixedWidth(14)
            row.addWidget(dot, 0, Qt.AlignTop)

            txt = QLabel(item)
            txt.setFont(QFont("Segoe UI", 9))
            txt.setStyleSheet(f"color: {_L['TEXT']};")
            txt.setWordWrap(True)
            row.addWidget(txt, 1)
            v.addLayout(row)

        return card

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(72)
        w.setStyleSheet(f"""
            background: {_L['PANEL']};
            border-bottom-left-radius: 16px;
            border-bottom-right-radius: 16px;
        """)
        h = QHBoxLayout(w)
        h.setContentsMargins(20, 0, 20, 0)
        h.setSpacing(10)

        # Note de taille
        note = QLabel("Taille : 42 MB  ·  Redémarrage requis")
        note.setFont(QFont("Segoe UI", 8))
        note.setStyleSheet(f"color: {_L['TEXT_MUTED']};")
        h.addWidget(note)
        h.addStretch()

        btn_later = QPushButton("Plus tard")
        btn_later.setFixedSize(100, 38)
        btn_later.setCursor(Qt.PointingHandCursor)
        btn_later.setFont(QFont("Segoe UI", 9))
        btn_later.setStyleSheet(f"""
            QPushButton {{
                background: {_L['BG']};
                color: {_L['TEXT']};
                border: 1px solid {_L['BORDER']};
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background: {_L['BORDER']};
            }}
        """)
        btn_later.clicked.connect(self.reject)
        h.addWidget(btn_later)

        btn_update = QPushButton("⬇  Mettre à jour")
        btn_update.setFixedSize(148, 38)
        btn_update.setCursor(Qt.PointingHandCursor)
        btn_update.setFont(QFont("Segoe UI", 9, QFont.Bold))
        btn_update.setStyleSheet(f"""
            QPushButton {{
                background: {_L['ACCENT']};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {_L['ACCENT_DARK']};
            }}
            QPushButton:pressed {{
                background: #185a30;
            }}
        """)
        _shadow(btn_update, blur=12, dy=3, color=QColor(45, 138, 78, 60))
        btn_update.clicked.connect(self.accept)
        h.addWidget(btn_update)

        return w


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Fond neutre pour voir la fenêtre flottante
    bg = QWidget()
    bg.setFixedSize(700, 750)
    bg.setStyleSheet("background: #d8dce4;")
    bg.show()

    dlg = _UpdateDialog(bg)
    # Centrer sur le fond
    dlg.move(
        bg.x() + (bg.width()  - dlg.width())  // 2,
        bg.y() + (bg.height() - dlg.height()) // 2,
    )
    dlg.show()

    sys.exit(app.exec())
