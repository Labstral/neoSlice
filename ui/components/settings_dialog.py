"""Fenêtre paramètres neoSlice — modale, sans chrome OS, thème-aware."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QPoint, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from core.i18n import _
from core.prefs import PREFS
from data.printers import PRINTERS, SERIES_ORDRE
from ui.components.brand_menu_button import BrandMenuButton
from ui.styles.theme import MANAGER as _T, FONT_MAIN


class _BenchmarkWorker(QThread):
    """Benchmark CPU/RAM in background, emits (tier, elapsed_ms, ram_gb)."""
    result_ready = Signal(str, float, float)

    def run(self):
        reps = 3
        a = np.random.rand(512, 512).astype(np.float32)
        b = np.random.rand(512, 512).astype(np.float32)
        t0 = time.perf_counter()
        for _ in range(reps):
            np.dot(a, b)
        elapsed_ms = (time.perf_counter() - t0) * 1000 / reps

        ram_gb = 0.0
        try:
            import sys as _sys
            if _sys.platform == "win32":
                import ctypes
                class _MEMSTATUS(ctypes.Structure):
                    _fields_ = [
                        ("dwLength",               ctypes.c_ulong),
                        ("dwMemoryLoad",           ctypes.c_ulong),
                        ("ullTotalPhys",           ctypes.c_ulonglong),
                        ("ullAvailPhys",           ctypes.c_ulonglong),
                        ("ullTotalPageFile",       ctypes.c_ulonglong),
                        ("ullAvailPageFile",       ctypes.c_ulonglong),
                        ("ullTotalVirtual",        ctypes.c_ulonglong),
                        ("ullAvailVirtual",        ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                ms = _MEMSTATUS()
                ms.dwLength = ctypes.sizeof(_MEMSTATUS)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
                ram_gb = ms.ullTotalPhys / (1024 ** 3)
            else:
                import psutil
                ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            pass

        if elapsed_ms < 10.0:
            tier = "full"
        elif elapsed_ms < 40.0:
            tier = "balanced"
        else:
            tier = "lite"

        self.result_ready.emit(tier, elapsed_ms, ram_gb)


class _InstallWorker(QThread):
    """Installe l'assistant IA (Ollama + modeles + base) en arriere-plan."""
    progress = Signal(str, float)   # (etape, fraction 0..1)
    log = Signal(str)
    done = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.assistant.installer import AssistantInstaller
        self._inst = AssistantInstaller(
            progress=lambda s, f: self.progress.emit(s, f),
            log=lambda m: self.log.emit(m))

    def cancel(self):
        self._inst.cancel()

    def run(self):
        try:
            self._inst.install()
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class _UninstallWorker(QThread):
    """Desinstalle l'assistant IA en arriere-plan (suppression des fichiers)."""
    done = Signal()
    failed = Signal(str)

    def run(self):
        try:
            from core.assistant.installer import uninstall
            uninstall()
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class _KBCheckWorker(QThread):
    """Verifie (en arriere-plan, appel reseau) si une nouvelle base d'Oen existe."""
    result = Signal(object)   # dict d'info, ou None

    def run(self):
        try:
            from core.assistant.kb_update import KBUpdater
            self.result.emit(KBUpdater().check())
        except Exception:
            self.result.emit(None)


class _KBUpdateWorker(QThread):
    """Telecharge et applique la mise a jour de la base d'Oen (integrite + swap
    atomique + rollback geres par KBUpdater). L'index actuel reste intact si echec."""
    progress = Signal(str, float)
    done = Signal(str)        # version installee
    failed = Signal(str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self._info = info
        from core.assistant.kb_update import KBUpdater
        self._up = KBUpdater(progress=lambda s, f: self.progress.emit(s, f))

    def cancel(self):
        self._up.cancel()

    def run(self):
        try:
            self._up.update(self._info)
            self.done.emit(str(self._info.get("kb_version", "")))
        except Exception as e:
            self.failed.emit(str(e))


class SettingsDialog(QDialog):
    update_request = Signal(str, str, str)   # version, download_url, notes
    _update_result = Signal(str, str, str)   # résultat du thread → main thread
    pro_activated = Signal()                 # émis quand neoSlice Pro vient d'être activé ici
    scanbar_anim_changed = Signal(bool)      # animation de la scan-line on/off

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(400)
        self._drag_pos: QPoint | None = None
        self._bench_worker: _BenchmarkWorker | None = None
        # Valeurs au moment de l'ouverture — sert à ne suggérer le redémarrage
        # que si quelque chose a vraiment changé par rapport à la session active.
        self._orig_lang = PREFS.get("lang", "fr")
        self._orig_perf = PREFS.get("perf_mode", "full")
        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("settings_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(22, 16, 22, 22)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # ── Barre titre ───────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 14)
        self._title_lbl = QLabel(_("settings.title"))
        self._title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setFont(QFont(FONT_MAIN, 9))
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.close)
        title_row.addWidget(self._title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._close_btn)
        lay.addLayout(title_row)

        self._sep_top = self._make_sep()
        lay.addWidget(self._sep_top)
        lay.addSpacing(16)

        # ── Section APPARENCE ─────────────────────────────────────────────────
        self._lbl_apparence = self._make_section_label(_("settings.sec_appearance"))
        lay.addWidget(self._lbl_apparence)
        lay.addSpacing(10)

        self._dark_lbl, self._dark_cb = self._make_checkbox_row(_("settings.dark_theme"), _T.is_dark())
        self._dark_cb.toggled.connect(self._on_theme_toggled)
        dark_row = QHBoxLayout()
        dark_row.setContentsMargins(0, 0, 0, 0)
        dark_row.addWidget(self._dark_lbl)
        dark_row.addStretch()
        dark_row.addWidget(self._dark_cb)
        lay.addLayout(dark_row)
        lay.addSpacing(8)

        # Animation de la barre de scan (en-tête) — figée si décochée
        self._scan_lbl, self._scan_cb = self._make_checkbox_row(
            _("settings.scanbar_anim"), bool(PREFS.get("scanbar_anim", True)))
        self._scan_cb.toggled.connect(self._on_scanbar_toggled)
        scan_row = QHBoxLayout()
        scan_row.setContentsMargins(0, 0, 0, 0)
        scan_row.addWidget(self._scan_lbl)
        scan_row.addStretch()
        scan_row.addWidget(self._scan_cb)
        lay.addLayout(scan_row)
        lay.addSpacing(8)

        # Langue
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        self._lang_lbl = QLabel(_("settings.language"))
        self._lang_lbl.setFont(QFont(FONT_MAIN, 9))
        self._lang_combo = QComboBox()
        self._lang_combo.setFixedWidth(120)
        self._lang_combo.addItem("Français", "fr")
        self._lang_combo.addItem("English", "en")
        _saved_lang = PREFS.get("lang", "fr")
        self._lang_combo.setCurrentIndex(0 if _saved_lang == "fr" else 1)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self._lang_lbl)
        lang_row.addStretch()
        lang_row.addWidget(self._lang_combo)
        lay.addLayout(lang_row)

        lay.addSpacing(12)
        self._sep_print = self._make_sep()
        lay.addWidget(self._sep_print)
        lay.addSpacing(16)

        # ── Section IMPRESSION 3D ─────────────────────────────────────────────
        self._lbl_print = self._make_section_label(_("settings.sec_print"))
        lay.addWidget(self._lbl_print)
        lay.addSpacing(10)

        printer_row = QHBoxLayout()
        printer_row.setContentsMargins(0, 0, 0, 0)
        self._printer_lbl = QLabel(_("settings.printer_default"))
        self._printer_lbl.setFont(QFont(FONT_MAIN, 9))
        self._printer_combo = BrandMenuButton(placeholder=_("settings.printer_none"))
        self._printer_combo.setFixedWidth(160)
        self._populate_printers()
        self._printer_combo.selectionChanged.connect(self._on_printer_changed)
        printer_row.addWidget(self._printer_lbl)
        printer_row.addStretch()
        printer_row.addWidget(self._printer_combo)
        lay.addLayout(printer_row)
        lay.addSpacing(8)

        # Slicer de sortie (Bambu/Orca par défaut | PrusaSlicer)
        slicer_row = QHBoxLayout()
        slicer_row.setContentsMargins(0, 0, 0, 0)
        self._slicer_lbl = QLabel(_("settings.slicer_output"))
        self._slicer_lbl.setFont(QFont(FONT_MAIN, 9))
        self._slicer_combo = QComboBox()
        self._slicer_combo.setFixedWidth(160)
        self._slicer_combo.addItem(_("settings.slicer_bambu"), "bambu")
        self._slicer_combo.addItem(_("settings.slicer_orca"), "orca")
        self._slicer_combo.addItem(_("settings.slicer_prusa"), "prusa")
        self._slicer_combo.addItem(_("settings.slicer_creality"), "creality")
        self._slicer_combo.addItem(_("settings.slicer_elegoo"), "elegoo")
        _saved_slicer = PREFS.get("slicer_output", "bambu")
        _slicer_idx = {"bambu": 0, "orca": 1, "prusa": 2, "creality": 3,
                       "elegoo": 4}.get(_saved_slicer, 0)
        self._slicer_combo.setCurrentIndex(_slicer_idx)
        self._slicer_combo.currentIndexChanged.connect(self._on_slicer_changed)
        slicer_row.addWidget(self._slicer_lbl)
        slicer_row.addStretch()
        slicer_row.addWidget(self._slicer_combo)
        lay.addLayout(slicer_row)
        lay.addSpacing(8)

        lay.addSpacing(18)
        self._sep_export = self._make_sep()
        lay.addWidget(self._sep_export)
        lay.addSpacing(16)

        # ── Section EXPORT ────────────────────────────────────────────────────
        self._lbl_export = self._make_section_label(_("settings.sec_export"))
        lay.addWidget(self._lbl_export)
        lay.addSpacing(10)

        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(6)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText(_("settings.folder_ph"))
        self._folder_edit.setReadOnly(True)
        saved_folder = PREFS.get("export_folder", "")
        if saved_folder:
            self._folder_edit.setText(saved_folder)
        self._folder_edit.setFont(QFont(FONT_MAIN, 8))
        self._browse_btn = QPushButton("📂")
        self._browse_btn.setFixedSize(28, 28)
        self._browse_btn.setCursor(Qt.PointingHandCursor)
        self._browse_btn.setFont(QFont(FONT_MAIN, 11))
        self._browse_btn.clicked.connect(self._on_browse_folder)
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(self._browse_btn)
        lay.addLayout(folder_row)

        lay.addSpacing(18)
        self._sep_perf = self._make_sep()
        lay.addWidget(self._sep_perf)
        lay.addSpacing(16)

        # ── Section PERFORMANCE ───────────────────────────────────────────────
        self._lbl_perf = self._make_section_label(_("settings.sec_performance"))
        lay.addWidget(self._lbl_perf)
        lay.addSpacing(10)

        perf_mode_row = QHBoxLayout()
        perf_mode_row.setContentsMargins(0, 0, 0, 0)
        self._perf_lbl = QLabel(_("settings.perf_mode"))
        self._perf_lbl.setFont(QFont(FONT_MAIN, 9))
        self._perf_combo = QComboBox()
        self._perf_combo.setFixedWidth(130)
        self._perf_combo.addItem(_("settings.perf_full"),     "full")
        self._perf_combo.addItem(_("settings.perf_balanced"), "balanced")
        self._perf_combo.addItem(_("settings.perf_lite"),     "lite")
        _perf_idx = {"full": 0, "balanced": 1, "lite": 2}.get(PREFS.get("perf_mode", "full"), 0)
        self._perf_combo.setCurrentIndex(_perf_idx)
        self._perf_combo.currentIndexChanged.connect(self._on_perf_mode_changed)
        perf_mode_row.addWidget(self._perf_lbl)
        perf_mode_row.addStretch()
        perf_mode_row.addWidget(self._perf_combo)
        lay.addLayout(perf_mode_row)
        lay.addSpacing(4)

        self._perf_desc_lbl = QLabel(self._perf_mode_desc(PREFS.get("perf_mode", "full")))
        self._perf_desc_lbl.setFont(QFont(FONT_MAIN, 8))
        self._perf_desc_lbl.setWordWrap(True)
        lay.addWidget(self._perf_desc_lbl)
        lay.addSpacing(6)

        self._perf_test_btn = QPushButton(_("settings.perf_test_btn"))
        self._perf_test_btn.setCursor(Qt.PointingHandCursor)
        self._perf_test_btn.setFont(QFont(FONT_MAIN, 10))
        self._perf_test_btn.setFixedHeight(28)
        self._perf_test_btn.clicked.connect(self._on_test_config)
        lay.addWidget(self._perf_test_btn)
        lay.addSpacing(6)

        self._perf_result_lbl = QLabel("")
        # Même police/style que les autres états verts (ex. statut diagnostic)
        self._perf_result_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._perf_result_lbl.setWordWrap(True)
        self._perf_result_lbl.hide()
        lay.addWidget(self._perf_result_lbl)

        # Notice de redémarrage — commune à langue ET mode perf (cachée par défaut)
        lay.addSpacing(10)
        restart_row = QHBoxLayout()
        restart_row.setContentsMargins(0, 0, 0, 0)
        self._restart_lbl = QLabel(_("settings.restart_notice"))
        self._restart_lbl.setFont(QFont(FONT_MAIN, 9))
        self._restart_lbl.setWordWrap(True)
        self._restart_lbl.hide()
        self._restart_btn = QPushButton(_("settings.restart_btn"))
        self._restart_btn.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        self._restart_btn.setCursor(Qt.PointingHandCursor)
        self._restart_btn.setFixedHeight(32)
        self._restart_btn.clicked.connect(self._do_restart)
        self._restart_btn.hide()
        restart_row.addWidget(self._restart_lbl, 1)
        restart_row.addSpacing(6)
        restart_row.addWidget(self._restart_btn)
        lay.addLayout(restart_row)

        lay.addSpacing(18)
        self._sep_updates = self._make_sep()
        lay.addWidget(self._sep_updates)
        lay.addSpacing(16)

        # ── Section MISES À JOUR ──────────────────────────────────────────────
        self._lbl_updates = self._make_section_label(_("settings.sec_updates"))
        lay.addWidget(self._lbl_updates)
        lay.addSpacing(10)

        update_row = QHBoxLayout()
        update_row.setContentsMargins(0, 0, 0, 0)
        self._update_check_btn = QPushButton(_("settings.update_check_btn"))
        self._update_check_btn.setCursor(Qt.PointingHandCursor)
        self._update_check_btn.setFont(QFont(FONT_MAIN, 9))
        self._update_check_btn.setFixedHeight(28)
        self._update_check_btn.clicked.connect(self._on_check_update)
        self._update_status_lbl = QLabel("")
        self._update_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._update_status_lbl.hide()
        update_row.addWidget(self._update_check_btn)
        update_row.addSpacing(10)
        update_row.addWidget(self._update_status_lbl)
        update_row.addStretch()
        lay.addLayout(update_row)
        lay.addSpacing(8)

        # ── Section DIAGNOSTIC IA ─────────────────────────────────────────────
        lay.addSpacing(10)
        self._sep_diag = self._make_sep()
        lay.addWidget(self._sep_diag)
        lay.addSpacing(14)

        self._lbl_diag = self._make_section_label("DIAGNOSTIC IA")
        lay.addWidget(self._lbl_diag)
        lay.addSpacing(10)

        # Statut (pleine largeur)
        self._diag_status_lbl = QLabel()
        self._diag_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._diag_status_lbl.setWordWrap(True)
        lay.addWidget(self._diag_status_lbl)
        lay.addSpacing(6)

        # Bouton sur sa propre ligne, aligné à droite
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        self._revoke_btn = QPushButton()
        self._revoke_btn.setFont(QFont(FONT_MAIN, 8))
        self._revoke_btn.setFixedHeight(24)
        self._revoke_btn.setCursor(Qt.PointingHandCursor)
        self._revoke_btn.clicked.connect(self._revoke_diagnostic_consent)
        self._refresh_diag_status()
        btn_row.addStretch()
        btn_row.addWidget(self._revoke_btn)
        lay.addLayout(btn_row)
        lay.addSpacing(4)

        # ── Section ASSISTANT IA ──────────────────────────────────────────────
        lay.addSpacing(10)
        self._sep_assist = self._make_sep()
        lay.addWidget(self._sep_assist)
        lay.addSpacing(14)

        self._lbl_assist = self._make_section_label(_("oen.section"))
        lay.addWidget(self._lbl_assist)
        lay.addSpacing(10)

        self._assist_status_lbl = QLabel()
        self._assist_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._assist_status_lbl.setWordWrap(True)
        lay.addWidget(self._assist_status_lbl)
        lay.addSpacing(6)

        self._assist_progress = QProgressBar()
        self._assist_progress.setRange(0, 100)
        self._assist_progress.setValue(0)
        self._assist_progress.setTextVisible(True)
        self._assist_progress.setFixedHeight(16)
        self._assist_progress.hide()
        lay.addWidget(self._assist_progress)
        lay.addSpacing(6)

        assist_btn_row = QHBoxLayout()
        assist_btn_row.setContentsMargins(0, 0, 0, 0)
        self._assist_btn = QPushButton()
        self._assist_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._assist_btn.setFixedHeight(28)
        self._assist_btn.setCursor(Qt.PointingHandCursor)
        self._assist_btn.clicked.connect(self._on_assist_btn)
        # Bouton secondaire : mettre a jour la base de connaissances d'Oen sans
        # reinstaller ni ressortir l'app. SUR LA MEME LIGNE que installer/desinstaller
        # (n'ajoute aucune hauteur a la fenetre). Visible seulement si Oen est installe.
        self._kb_btn = QPushButton(_("oen.kb_update"))
        self._kb_btn.setFont(QFont(FONT_MAIN, 8))
        self._kb_btn.setFixedHeight(28)
        self._kb_btn.setCursor(Qt.PointingHandCursor)
        self._kb_btn.clicked.connect(self._on_kb_update_btn)
        self._kb_btn.hide()
        assist_btn_row.addStretch()
        assist_btn_row.addWidget(self._kb_btn)
        assist_btn_row.addSpacing(6)
        assist_btn_row.addWidget(self._assist_btn)
        lay.addLayout(assist_btn_row)

        self._assist_worker = None
        self._uninstall_worker = None
        self._kb_check_worker = None
        self._kb_update_worker = None
        self._refresh_assistant_status()
        lay.addSpacing(4)

        # ── Section NEOSLICE PRO ──────────────────────────────────────────────
        lay.addSpacing(10)
        self._sep_pro = self._make_sep()
        lay.addWidget(self._sep_pro)
        lay.addSpacing(14)

        from ui.components.pro_badge import ProBadge
        pro_title_row = QHBoxLayout()
        pro_title_row.setContentsMargins(0, 0, 0, 0)
        pro_title_row.setSpacing(5)
        self._lbl_pro = self._make_section_label("NEOSLICE")
        pro_title_row.addWidget(self._lbl_pro)
        self._pro_title_badge = ProBadge("PRO", point_size=8, letter_spacing=1.0)
        pro_title_row.addWidget(self._pro_title_badge)
        pro_title_row.addStretch()
        lay.addLayout(pro_title_row)
        lay.addSpacing(10)

        self._pro_status_lbl = QLabel()
        self._pro_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._pro_status_lbl.setWordWrap(True)
        lay.addWidget(self._pro_status_lbl)
        lay.addSpacing(6)

        pro_btn_row = QHBoxLayout()
        pro_btn_row.setContentsMargins(0, 0, 0, 0)
        self._pro_btn = QPushButton(_("pro.settings_btn_upgrade"))
        self._pro_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._pro_btn.setFixedHeight(28)
        self._pro_btn.setCursor(Qt.PointingHandCursor)
        self._pro_btn.clicked.connect(self._on_pro_btn)
        pro_btn_row.addStretch()
        pro_btn_row.addWidget(self._pro_btn)
        lay.addLayout(pro_btn_row)
        self._refresh_pro_status()
        lay.addSpacing(4)

        # ── Lien « Licences et mentions » ─────────────────────────────────────
        lay.addSpacing(10)
        lic_row = QHBoxLayout()
        lic_row.setContentsMargins(0, 0, 0, 0)
        lic_row.addStretch()
        self._licenses_lbl = QLabel(
            f"<a href='#'>{_('settings.licenses_link')}</a>")
        self._licenses_lbl.setFont(QFont(FONT_MAIN, 8))
        self._licenses_lbl.setCursor(Qt.PointingHandCursor)
        self._licenses_lbl.setOpenExternalLinks(False)
        self._licenses_lbl.linkActivated.connect(self._open_licenses)
        lic_row.addWidget(self._licenses_lbl)
        lic_row.addStretch()
        lay.addLayout(lic_row)

    def _open_licenses(self):
        from ui.components.licenses_dialog import LicensesDialog
        dlg = LicensesDialog(self)
        dlg.move(
            self.geometry().center().x() - dlg.width() // 2,
            max(0, self.geometry().center().y() - dlg.height() // 2))
        dlg.exec()

    # ── Assistant IA : installation optionnelle ──────────────────────────────
    def _refresh_assistant_status(self):
        from core.assistant.engine import AssistantEngine
        from core.assistant.installer import is_installed
        from core import licensing
        pal = _T.palette()
        installed = is_installed() or AssistantEngine.available()
        # Le bouton de mise a jour de la base n'a de sens qu'une fois Oen installe.
        if hasattr(self, "_kb_btn"):
            busy = bool(self._kb_check_worker or self._kb_update_worker)
            self._kb_btn.setVisible(installed)
            if installed and not busy:
                self._kb_btn.setEnabled(True)
                self._kb_btn.setText(_("oen.kb_update"))
            self._kb_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {pal['TEXT_SECONDARY']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 3px 10px;
                }}
                QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT_BRIGHT']}; }}
                QPushButton:disabled {{ color: {pal['INACTIVE']}; border-color: {pal['INACTIVE']}; }}
            """)
        if installed:
            self._assist_status_lbl.setText(_("oen.ready"))
            self._assist_status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
            self._assist_btn.setText(_("oen.uninstall"))
            self._assist_btn.setFont(QFont(FONT_MAIN, 8))
            self._assist_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {pal['TEXT_SECONDARY']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 4px 12px;
                }}
                QPushButton:hover {{ border-color: {pal['ERROR_RED']}; color: {pal['ERROR_RED']}; }}
            """)
            self._assist_btn.setEnabled(True)
            self._assist_btn.show()
            return
        if not licensing.est_pro():
            self._assist_status_lbl.setText(_("oen.pro_only"))
            self._assist_status_lbl.setStyleSheet(
                f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
            self._assist_btn.hide()
            return
        self._assist_status_lbl.setText(_("oen.install_pitch"))
        self._assist_status_lbl.setStyleSheet(
            f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._assist_btn.setText(_("oen.install"))
        self._assist_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._assist_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']}; color: #ffffff; border: none;
                border-radius: 4px; padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['BG_PANEL']}; }}
        """)
        self._assist_btn.setEnabled(True)
        self._assist_btn.show()

    def _on_assist_btn(self):
        """Le bouton sert selon l'etat : installer si absent, desinstaller si present."""
        from core.assistant.installer import is_installed
        from core.assistant.engine import AssistantEngine
        if is_installed() or AssistantEngine.available():
            self._uninstall_assistant()
        else:
            self._on_install_assistant()

    def _on_install_assistant(self):
        if self._assist_worker is not None:
            return
        self._assist_btn.setEnabled(False)
        self._assist_btn.setText(_("oen.installing"))
        self._assist_progress.setValue(0)
        self._assist_progress.show()
        self._assist_worker = _InstallWorker(self)
        self._assist_worker.progress.connect(self._on_install_progress)
        self._assist_worker.done.connect(self._on_install_done)
        self._assist_worker.failed.connect(self._on_install_failed)
        self._assist_worker.start()

    def _uninstall_assistant(self):
        if self._uninstall_worker is not None:
            return
        rep = QMessageBox.question(
            self, _("oen.uninstall_title"), _("oen.uninstall_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if rep != QMessageBox.Yes:
            return
        pal = _T.palette()
        self._assist_btn.setEnabled(False)
        self._assist_btn.setText(_("oen.uninstalling_btn"))
        self._assist_status_lbl.setText(_("oen.uninstalling"))
        self._assist_status_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._uninstall_worker = _UninstallWorker(self)
        self._uninstall_worker.done.connect(self._on_uninstall_done)
        self._uninstall_worker.failed.connect(self._on_uninstall_failed)
        self._uninstall_worker.start()

    def _on_uninstall_done(self):
        self._uninstall_worker = None
        self._refresh_assistant_status()

    def _on_uninstall_failed(self, err: str):
        self._uninstall_worker = None
        pal = _T.palette()
        self._assist_status_lbl.setText(_("oen.uninstall_failed", err=err[:140]))
        self._assist_status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        self._assist_btn.setEnabled(True)
        self._refresh_assistant_status()

    def _on_install_progress(self, label: str, frac: float):
        self._assist_progress.setValue(int(frac * 100))
        self._assist_progress.setFormat(f"{label}  %p%")

    def _on_install_done(self):
        self._assist_worker = None
        self._assist_progress.setValue(100)
        self._assist_progress.hide()
        self._refresh_assistant_status()

    def _on_install_failed(self, err: str):
        self._assist_worker = None
        self._assist_progress.hide()
        pal = _T.palette()
        self._assist_status_lbl.setText(_("oen.install_failed", err=err[:140]))
        self._assist_status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        self._assist_btn.setText(_("oen.retry"))
        self._assist_btn.setEnabled(True)
        self._assist_btn.show()

    # ── Oen : mise a jour de la base de connaissances (sans reinstaller) ───────
    def _on_kb_update_btn(self):
        if self._kb_check_worker is not None or self._kb_update_worker is not None:
            return
        self._kb_btn.setEnabled(False)
        self._kb_btn.setText(_("oen.kb_checking"))
        self._kb_check_worker = _KBCheckWorker(self)
        self._kb_check_worker.result.connect(self._on_kb_checked)
        self._kb_check_worker.start()

    def _on_kb_checked(self, info):
        self._kb_check_worker = None
        pal = _T.palette()
        self._kb_btn.setEnabled(True)
        self._kb_btn.setText(_("oen.kb_update"))
        if not info:
            self._assist_status_lbl.setText(_("oen.kb_uptodate"))
            self._assist_status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
            return
        if info.get("incompatible_app"):
            self._assist_status_lbl.setText(
                _("oen.kb_needs_app", min=info.get("min_app_version")))
            self._assist_status_lbl.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
            return
        mo = float(info.get("download_size", 0)) / 1e6
        notes = info.get("notes", "")
        msg = (_("oen.kb_available", version=info.get("kb_version")) + "\n\n"
               + _("oen.kb_download_size", mo=f"{mo:.0f}") + "\n")
        if notes:
            msg += f"\n{notes}\n"
        msg += "\n" + _("oen.kb_reassure")
        rep = QMessageBox.question(
            self, _("oen.kb_update_title"), msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if rep != QMessageBox.Yes:
            return
        self._kb_btn.setEnabled(False)
        self._assist_progress.setValue(0)
        self._assist_progress.show()
        self._kb_update_worker = _KBUpdateWorker(info, self)
        self._kb_update_worker.progress.connect(self._on_install_progress)  # meme barre
        self._kb_update_worker.done.connect(self._on_kb_update_done)
        self._kb_update_worker.failed.connect(self._on_kb_update_failed)
        self._kb_update_worker.start()

    def _on_kb_update_done(self, version: str):
        self._kb_update_worker = None
        self._assist_progress.setValue(100)
        self._assist_progress.hide()
        pal = _T.palette()
        self._assist_status_lbl.setText(_("oen.kb_done", version=version))
        self._assist_status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        self._kb_btn.setEnabled(True)

    def _on_kb_update_failed(self, err: str):
        self._kb_update_worker = None
        self._assist_progress.hide()
        pal = _T.palette()
        self._assist_status_lbl.setText(_("oen.kb_failed", err=err[:140]))
        self._assist_status_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        self._kb_btn.setEnabled(True)

    def _refresh_pro_status(self):
        from core import licensing
        pal = _T.palette()
        # Pré-lancement : pas d'activation possible, juste « bientôt disponible ».
        if not licensing.est_pro() and getattr(licensing, "PRO_COMING_SOON", False):
            self._pro_status_lbl.setText(_("pro.coming_soon_short"))
            self._pro_status_lbl.setStyleSheet(f"color: {pal['ACCENT']}; background: transparent;")
            self._pro_btn.hide()
            return
        if licensing.est_pro():
            self._pro_status_lbl.setText(_("pro.settings_status_pro"))
            self._pro_status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
            self._pro_btn.setText(_("pro.settings_btn_deactivate"))
            # Mode désactivation = action secondaire → police NON grasse, identique
            # au bouton « Désactiver » du diagnostic (sinon il paraît plus foncé).
            self._pro_btn.setFont(QFont(FONT_MAIN, 8))
            self._pro_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {pal['TEXT_SECONDARY']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 4px 12px;
                }}
                QPushButton:hover {{ border-color: {pal['ERROR_RED']}; color: {pal['ERROR_RED']}; }}
            """)
        else:
            self._pro_status_lbl.setText(_("pro.settings_status_locked"))
            self._pro_status_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
            self._pro_btn.setText(_("pro.settings_btn_upgrade"))
            # Mode achat = CTA principal plein → gras assumé.
            self._pro_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            self._pro_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                    border: none; border-radius: 4px; padding: 4px 14px;
                    font-weight: bold; letter-spacing: 0.5px;
                }}
                QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
            """)
        self._pro_btn.show()

    def _on_pro_btn(self):
        from core import licensing
        if licensing.est_pro():
            self._deactivate_device()
        else:
            self._open_paywall()

    def _open_paywall(self):
        from ui.components.paywall_dialog import PaywallDialog
        from core import licensing
        wall = PaywallDialog(self)
        wall.exec()
        if licensing.est_pro():
            self.pro_activated.emit()
        self._refresh_pro_status()

    def _deactivate_device(self):
        from core import licensing
        ok, message = licensing.desactiver_appareil()
        self._pro_status_lbl.setText(message)
        pal = _T.palette()
        self._pro_status_lbl.setStyleSheet(
            f"color: {pal['TELE_GREEN'] if ok else pal['ERROR_RED']}; background: transparent;"
        )
        if ok:
            self.pro_activated.emit()   # le badge de la barre se met à jour (disparaît)
            self._refresh_pro_status()

    def _refresh_diag_status(self):
        from core import licensing
        # Pré-lancement : on masque toute la section diagnostic (rien d'accessible).
        if getattr(licensing, "PRO_COMING_SOON", False):
            for w in (self._sep_diag, self._lbl_diag, self._diag_status_lbl, self._revoke_btn):
                w.hide()
            return
        consented = bool(PREFS.get("defect_consent", False))
        if consented:
            self._diag_status_lbl.setText("Actif ✓ — photos confirmées partagées automatiquement")
            self._revoke_btn.setText("Désactiver")
            self._revoke_btn.setEnabled(True)
        else:
            self._diag_status_lbl.setText("Inactif — cliquez sur le bouton pour activer")
            self._revoke_btn.setText("Désactivé")
            self._revoke_btn.setEnabled(False)

    def _revoke_diagnostic_consent(self):
        PREFS.set("defect_consent", False)
        PREFS.set("defect_contribute", False)
        self._refresh_diag_status()

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        return sep

    def _make_section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_MAIN, 7, QFont.Weight.Bold))
        return lbl

    def _make_checkbox_row(self, label: str, checked: bool):
        lbl = QLabel(label)
        lbl.setFont(QFont(FONT_MAIN, 9))
        cb = QCheckBox()
        cb.setChecked(checked)
        return lbl, cb

    def _populate_printers(self):
        from data.printers import (
            catalogue_brands, models_for_brand,
            prusa_brands, prusa_models_for_brand, split_popular,
        )
        groups: list = [(_("settings.printer_none"), [(_("settings.printer_none"), "")])]
        slicer = PREFS.get("slicer_output", "bambu")
        if slicer == "prusa":
            brands = prusa_brands()
            models = prusa_models_for_brand
        else:
            brands = catalogue_brands(slicer)
            models = lambda b: models_for_brand(b, slicer)
            by_serie: dict[str, list[str]] = {}
            for name, data in PRINTERS.items():
                by_serie.setdefault(data.get("serie", "Autre"), []).append(name)
            bambu = [(name, name) for serie in SERIES_ORDRE
                     for name in by_serie.get(serie, [])]
            groups.append(("Bambu Lab", bambu))

        popular, others = split_popular(brands)
        for b in popular:
            groups.append((b, models(b)))
        if others:
            groups.append(("Autres marques", [(b, models(b)) for b in others]))

        self._printer_combo.set_groups(groups)
        saved = PREFS.get("printer_default", "")
        if saved:
            self._printer_combo.set_current_key(saved, emit=False)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_theme_toggled(self, checked: bool):
        _T.switch("dark" if checked else "light")
        self._dark_cb.blockSignals(True)
        self._dark_cb.setChecked(_T.is_dark())
        self._dark_cb.blockSignals(False)

    def _on_scanbar_toggled(self, checked: bool):
        PREFS.set("scanbar_anim", bool(checked))
        self.scanbar_anim_changed.emit(bool(checked))

    def _on_lang_changed(self):
        PREFS.set("lang", self._lang_combo.currentData())
        self._show_restart_notice()

    def _show_restart_notice(self):
        lang_changed = PREFS.get("lang", "fr") != self._orig_lang
        perf_changed = PREFS.get("perf_mode", "full") != self._orig_perf
        if lang_changed or perf_changed:
            self._restart_lbl.show()
            self._restart_btn.show()
        else:
            self._restart_lbl.hide()
            self._restart_btn.hide()

    def _on_printer_changed(self, key: str = ""):
        PREFS.set("printer_default", self._printer_combo.current_key() or "")

    def _on_slicer_changed(self):
        PREFS.set("slicer_output", self._slicer_combo.currentData() or "bambu")
        # Le catalogue d'imprimantes dépend du slicer → reconstruire la liste
        # « imprimante par défaut » immédiatement (sinon elle garde l'ancien slicer).
        self._populate_printers()

    def _on_browse_folder(self):
        current = self._folder_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, _("settings.browse_title"), current)
        if folder:
            self._folder_edit.setText(folder)
            PREFS.set("export_folder", folder)

    @staticmethod
    def _perf_mode_desc(mode: str) -> str:
        key = {
            "full":     "settings.perf_full_desc",
            "balanced": "settings.perf_balanced_desc",
            "lite":     "settings.perf_lite_desc",
        }.get(mode, "settings.perf_full_desc")
        return _(key)

    def _on_perf_mode_changed(self):
        mode = self._perf_combo.currentData()
        PREFS.set("perf_mode", mode)
        self._perf_desc_lbl.setText(self._perf_mode_desc(mode))
        self._show_restart_notice()


    def _on_check_update(self):
        from core.updater import check_for_update
        self._update_check_btn.setEnabled(False)
        self._update_status_lbl.setText(_("settings.update_checking"))
        self._update_status_lbl.setStyleSheet(f"color: {_T.palette()['TEXT_SECONDARY']}; background: transparent;")
        self._update_status_lbl.show()
        # Connexion unique — on déconnecte d'abord pour éviter les doublons
        try:
            self._update_result.disconnect()
        except RuntimeError:
            pass
        self._update_result.connect(self._on_update_result)
        check_for_update(lambda v, u, n: self._update_result.emit(v or "", u, n))

    def _on_update_result(self, version: str, url: str, notes: str):
        try:
            self._update_result.disconnect()
        except RuntimeError:
            pass
        self._update_check_btn.setEnabled(True)
        pal = _T.palette()
        if version:
            self._update_status_lbl.setText(_("settings.update_found"))
            self._update_status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
            self.close()
            self.update_request.emit(version, url, notes)
        else:
            self._update_status_lbl.setText(_("settings.update_uptodate"))
            self._update_status_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")

    def _on_test_config(self):
        if self._bench_worker and self._bench_worker.isRunning():
            return
        self._perf_test_btn.setEnabled(False)
        self._perf_test_btn.setText(_("settings.perf_testing"))
        self._perf_result_lbl.hide()
        self._bench_worker = _BenchmarkWorker(self)
        self._bench_worker.result_ready.connect(self._on_bench_result)
        self._bench_worker.start()

    def _on_bench_result(self, tier: str, elapsed_ms: float, ram_gb: float):
        self._perf_test_btn.setEnabled(True)
        self._perf_test_btn.setText(_("settings.perf_test_btn"))

        result_key = {
            "full":     "settings.perf_result_full",
            "balanced": "settings.perf_result_balanced",
            "lite":     "settings.perf_result_lite",
        }.get(tier, "settings.perf_result_full")
        result_text = _(result_key)
        if ram_gb > 0:
            result_text += f"  ({elapsed_ms:.1f} ms · {ram_gb:.1f} GB RAM)"

        pal = _T.palette()
        color = {
            "full":     pal["TELE_GREEN"],
            "balanced": pal["AMBER"],
            "lite":     pal["ERROR_RED"],
        }.get(tier, pal["TEXT_PRIMARY"])

        self._perf_result_lbl.setText(result_text)
        self._perf_result_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self._perf_result_lbl.show()

        # Auto-apply the suggested mode
        idx = {"full": 0, "balanced": 1, "lite": 2}.get(tier, 0)
        self._perf_combo.blockSignals(True)
        self._perf_combo.setCurrentIndex(idx)
        self._perf_combo.blockSignals(False)
        PREFS.set("perf_mode", tier)
        self._perf_desc_lbl.setText(self._perf_mode_desc(tier))
        self._show_restart_notice()

    @staticmethod
    def _do_restart():
        if getattr(sys, "frozen", False):
            args = [sys.executable] + sys.argv[1:]
        else:
            args = [sys.executable] + sys.argv
        subprocess.Popen(args)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    # ── Thème ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        pal = _T.palette()

        self._card.setStyleSheet(f"""
            QWidget#settings_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 8px;
            }}
        """)
        self._title_lbl.setStyleSheet(
            f"color: {pal['ACCENT_BRIGHT']}; background: transparent; letter-spacing: 2px;"
        )
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: none; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {pal['ERROR_RED']}; color: #ffffff; }}
        """)

        sep_style = f"background: {pal['INACTIVE']}; border: none;"
        for sep in (self._sep_top, self._sep_print, self._sep_export, self._sep_perf,
                    self._sep_updates, self._sep_diag, self._sep_assist, self._sep_pro):
            sep.setStyleSheet(sep_style)

        section_style = f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 1px;"
        for lbl in (self._lbl_apparence, self._lbl_print, self._lbl_export,
                    self._lbl_perf, self._lbl_updates, self._lbl_diag,
                    self._lbl_assist, self._lbl_pro):
            lbl.setStyleSheet(section_style)

        # Section neoSlice Pro (le bouton est stylé selon l'état dans _refresh_pro_status)
        self._refresh_pro_status()

        # Section diagnostic
        consented = bool(PREFS.get("defect_consent", False))
        self._diag_status_lbl.setStyleSheet(
            f"color: {pal['TELE_GREEN'] if consented else pal['TEXT_LABEL']}; background: transparent;"
        )
        self._revoke_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ border-color: {pal['ERROR_RED']}; color: {pal['ERROR_RED']}; }}
            QPushButton:disabled {{ color: {pal['TEXT_LABEL']}; border-color: {pal['INACTIVE']}; }}
        """)

        self._update_check_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
                font-family: {FONT_MAIN}; font-size: 11px;
                padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {pal['BG_SURFACE']}; border-color: {pal['ACCENT']}; }}
            QPushButton:disabled {{ color: {pal['TEXT_SECONDARY']}; }}
        """)

        row_lbl_style = f"color: {pal['TEXT_PRIMARY']}; background: transparent;"
        for lbl in (self._dark_lbl, self._scan_lbl, self._lang_lbl, self._slicer_lbl,
                    self._printer_lbl, self._perf_lbl):
            lbl.setStyleSheet(row_lbl_style)

        self._perf_desc_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._licenses_lbl.setText(f"<a href='#'>{_('settings.licenses_link')}</a>")
        self._licenses_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; }} "
            f"QLabel a {{ color: {pal['TEXT_SECONDARY']}; text-decoration: none; }}")
        self._restart_lbl.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        self._restart_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['AMBER']}; color: #000000;
                border: none; border-radius: 4px; padding: 4px 14px;
                font-family: {FONT_MAIN}; font-size: 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; color: #ffffff; }}
        """)

        cb_style = f"""
            QCheckBox {{ background: transparent; }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {pal['INACTIVE']};
                border-radius: 3px;
                background: {pal['BG_INPUT']};
            }}
            QCheckBox::indicator:checked {{
                background: {pal['ACCENT']}; border-color: {pal['ACCENT']};
            }}
            QCheckBox::indicator:hover {{ border-color: {pal['ACCENT_BRIGHT']}; }}
        """
        for cb in (self._dark_cb, self._scan_cb):
            cb.setStyleSheet(cb_style)

        self._dark_cb.blockSignals(True)
        self._dark_cb.setChecked(_T.is_dark())
        self._dark_cb.blockSignals(False)

        combo_style = f"""
            QComboBox {{
                background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
                padding: 2px 8px; font-family: {FONT_MAIN}; font-size: 11px;
            }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                selection-background-color: {pal['ACCENT']};
                selection-color: {pal['EXPORT_FG']};
                border: 1px solid {pal['INACTIVE']};
            }}
        """
        for combo in (self._lang_combo, self._printer_combo, self._slicer_combo, self._perf_combo):
            combo.setStyleSheet(combo_style)
        self._printer_combo.apply_theme()   # style du menu déroulant en cascade

        self._folder_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
                padding: 2px 6px; font-family: {FONT_MAIN};
            }}
        """)
        self._browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['BG_SURFACE']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {pal['BG_ELEVATED']}; }}
        """)
        self._perf_test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px;
                font-family: {FONT_MAIN}; font-size: 11px;
            }}
            QPushButton:hover {{ background: {pal['BG_SURFACE']}; border-color: {pal['ACCENT']}; }}
            QPushButton:disabled {{ color: {pal['TEXT_SECONDARY']}; }}
        """)
