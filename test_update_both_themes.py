"""Affiche la popup de mise à jour en thème sombre ET clair côte à côte."""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from ui.styles.theme import MANAGER as _THEME
from core.i18n import _
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QPoint

NEW_VER = "0.1.3"
CUR_VER = "0.1.2"
NOTES   = "Nouveau moteur d'analyse, support nozzle 0.2 mm, corrections d'interface."


def _make_dialog(theme: str, offset_x: int) -> QDialog:
    _THEME.switch(theme)
    pal = _THEME.palette()

    dlg = QDialog()
    dlg.setWindowTitle(f"{_('update.title')}  [{theme}]")
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dlg.setFixedWidth(420)
    dlg.setStyleSheet(f"""
        QDialog {{ background: {pal['BG_PANEL']}; }}
        QLabel  {{ background: transparent; color: {pal['TEXT_PRIMARY']}; }}
        QProgressBar {{
            background: {pal['BG_SURFACE']}; border: 1px solid {pal['INACTIVE']};
            border-radius: 4px; height: 8px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {pal['ACCENT']}; border-radius: 3px; }}
    """)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(28, 24, 28, 20)
    lay.setSpacing(14)

    title_lbl = QLabel(_("update.title"))
    title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
    title_lbl.setStyleSheet(f"color: {pal['ACCENT_BRIGHT']};")
    lay.addWidget(title_lbl)

    body_lbl = QLabel(_("update.body", new=NEW_VER, cur=CUR_VER))
    body_lbl.setFont(QFont("Segoe UI", 10))
    body_lbl.setTextFormat(Qt.RichText)
    body_lbl.setWordWrap(True)
    lay.addWidget(body_lbl)

    notes_title = QLabel(_("update.notes_label"))
    notes_title.setFont(QFont("Segoe UI", 8, QFont.Bold))
    notes_title.setStyleSheet(f"color: {pal['TEXT_LABEL']};")
    lay.addWidget(notes_title)

    notes_lbl = QLabel(NOTES)
    notes_lbl.setFont(QFont("Segoe UI", 9))
    notes_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
    notes_lbl.setWordWrap(True)
    lay.addWidget(notes_lbl)

    lay.addSpacing(4)

    progress_bar = QProgressBar()
    progress_bar.setRange(0, 100)
    progress_bar.setValue(60)
    progress_bar.setFixedHeight(8)
    progress_bar.setTextVisible(False)
    progress_bar.show()
    lay.addWidget(progress_bar)

    status_lbl = QLabel(_("update.downloading", pct=60))
    status_lbl.setFont(QFont("Segoe UI", 9))
    status_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
    status_lbl.setAlignment(Qt.AlignCenter)
    status_lbl.show()
    lay.addWidget(status_lbl)

    lay.addSpacing(2)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    later_btn = QPushButton(_("update.btn_later"))
    later_btn.setFont(QFont("Segoe UI", 9))
    later_btn.setFixedHeight(32)
    later_btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {pal['TEXT_SECONDARY']};
            border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 0 14px;
        }}
        QPushButton:hover {{ color: {pal['TEXT_PRIMARY']}; border-color: {pal['TEXT_SECONDARY']}; }}
    """)
    later_btn.clicked.connect(dlg.reject)

    install_btn = QPushButton(_("update.btn_install"))
    install_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
    install_btn.setFixedHeight(32)
    install_btn.setEnabled(False)
    install_btn.setStyleSheet(f"""
        QPushButton {{
            background: {pal['ACCENT']}; color: #ffffff;
            border: none; border-radius: 4px; padding: 0 18px;
        }}
        QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
        QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['TEXT_LABEL']}; }}
    """)

    btn_row.addWidget(later_btn)
    btn_row.addStretch()
    btn_row.addWidget(install_btn)
    lay.addLayout(btn_row)

    dlg.adjustSize()
    dlg.move(offset_x, 200)
    return dlg


dlg_dark  = _make_dialog("dark",  100)
dlg_light = _make_dialog("light", 560)

dlg_dark.show()
dlg_light.show()

sys.exit(app.exec())
