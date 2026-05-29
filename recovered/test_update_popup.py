"""Simulation de la popup de mise à jour avec téléchargement automatique."""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

# Importer le thème avant tout
from ui.styles.theme import MANAGER as _THEME, apply_title_bar_theme
from core.i18n import _

import queue as _queue
import threading as _threading
import tempfile
import subprocess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QTimer

# ── Données simulées ──────────────────────────────────────────────────────────
new_version  = "0.1.3"
cur_version  = "0.1.2"
notes        = "Nouveau moteur d'analyse, support nozzle 0.2 mm, corrections d'interface."

# Utilise l'installateur local pour simuler un vrai téléchargement
_LOCAL_INSTALLER = r"C:\neoSlice\dist\installer\neoSlice_Setup_v0.1.2-beta_Windows.exe"
download_url = "file:///" + _LOCAL_INSTALLER.replace("\\", "/")

# ── Construction de la dialog (identique au code de production) ───────────────
pal = _THEME.palette()

dlg = QDialog()
dlg.setWindowTitle(_("update.title"))
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

body_lbl = QLabel(_("update.body", new=new_version, cur=cur_version))
body_lbl.setFont(QFont("Segoe UI", 10))
body_lbl.setTextFormat(Qt.RichText)
body_lbl.setWordWrap(True)
lay.addWidget(body_lbl)

notes_title = QLabel(_("update.notes_label"))
notes_title.setFont(QFont("Segoe UI", 8, QFont.Bold))
notes_title.setStyleSheet(f"color: {pal['TEXT_LABEL']};")
lay.addWidget(notes_title)

notes_lbl = QLabel(notes)
notes_lbl.setFont(QFont("Segoe UI", 9))
notes_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
notes_lbl.setWordWrap(True)
lay.addWidget(notes_lbl)

lay.addSpacing(4)

progress_bar = QProgressBar()
progress_bar.setRange(0, 100)
progress_bar.setValue(0)
progress_bar.setFixedHeight(8)
progress_bar.setTextVisible(False)
progress_bar.hide()
lay.addWidget(progress_bar)

status_lbl = QLabel("")
status_lbl.setFont(QFont("Segoe UI", 9))
status_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']};")
status_lbl.setAlignment(Qt.AlignCenter)
status_lbl.hide()
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
install_btn.setStyleSheet(f"""
    QPushButton {{
        background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
        border: none; border-radius: 4px; padding: 0 18px;
    }}
    QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
    QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['TEXT_LABEL']}; }}
""")

btn_row.addWidget(later_btn)
btn_row.addStretch()
btn_row.addWidget(install_btn)
lay.addLayout(btn_row)

# ── Logique de téléchargement (simule un téléchargement lent avec fichier local) ──
_q: _queue.Queue = _queue.Queue()
_poll_timer = QTimer(dlg)

def _download_simulated():
    """Simule un téléchargement avec progression artificielle, puis lance l'installateur local."""
    import time
    for pct in range(0, 101, 5):
        time.sleep(0.12)
        _q.put(("progress", pct))
    _q.put(("done", _LOCAL_INSTALLER))

def _on_poll():
    try:
        kind, val = _q.get_nowait()
        if kind == "progress":
            progress_bar.setRange(0, 100)
            progress_bar.setValue(val)
            status_lbl.setText(_("update.downloading", pct=val))
        elif kind == "done":
            _poll_timer.stop()
            progress_bar.setValue(100)
            status_lbl.setText(_("update.installing"))
            QTimer.singleShot(800, lambda: (subprocess.Popen([val]), dlg.accept()))
        elif kind == "error":
            _poll_timer.stop()
            status_lbl.setText(_("update.failed"))
            status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']};")
            install_btn.setText(_("update.btn_retry"))
            install_btn.setEnabled(True)
            install_btn.show()
    except _queue.Empty:
        pass

def _start():
    install_btn.setEnabled(False)
    install_btn.hide()
    later_btn.setEnabled(False)
    progress_bar.show()
    status_lbl.setText(_("update.downloading", pct=0))
    status_lbl.show()
    dlg.adjustSize()
    _poll_timer.timeout.connect(_on_poll)
    _poll_timer.start(80)
    _threading.Thread(target=_download_simulated, daemon=True).start()

install_btn.clicked.connect(_start)

apply_title_bar_theme(dlg)
dlg.exec()
sys.exit(0)
