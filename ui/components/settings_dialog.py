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
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import _
from core.prefs import PREFS
from data.printers import PRINTERS, SERIES_ORDRE
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


class SettingsDialog(QDialog):
    update_request = Signal(str, str, str)   # version, download_url, notes
    _update_result = Signal(str, str, str)   # résultat du thread → main thread

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
        self._printer_combo = QComboBox()
        self._printer_combo.setFixedWidth(160)
        self._populate_printers()
        self._printer_combo.currentIndexChanged.connect(self._on_printer_changed)
        printer_row.addWidget(self._printer_lbl)
        printer_row.addStretch()
        printer_row.addWidget(self._printer_combo)
        lay.addLayout(printer_row)
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
        self._perf_result_lbl.setFont(QFont(FONT_MAIN, 8))
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
        self._update_status_lbl.setFont(QFont(FONT_MAIN, 9))
        self._update_status_lbl.hide()
        update_row.addWidget(self._update_check_btn)
        update_row.addSpacing(10)
        update_row.addWidget(self._update_status_lbl)
        update_row.addStretch()
        lay.addLayout(update_row)
        lay.addSpacing(8)

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
        model = QStandardItemModel()
        none_item = QStandardItem(_("settings.printer_none"))
        none_item.setData("", Qt.UserRole)
        none_item.setFont(QFont(FONT_MAIN, 10))
        model.appendRow(none_item)

        by_serie: dict[str, list[str]] = {}
        for name, data in PRINTERS.items():
            by_serie.setdefault(data.get("serie", "Autre"), []).append(name)

        from PySide6.QtGui import QColor
        for serie in SERIES_ORDRE:
            if serie not in by_serie:
                continue
            sep = QStandardItem(f"── {serie.upper()} ──")
            sep.setEnabled(False)
            sep.setForeground(QColor(_T.palette()["TEXT_LABEL"]))
            sep.setFont(QFont(FONT_MAIN, 7, QFont.Weight.Bold))
            model.appendRow(sep)
            for name in by_serie[serie]:
                item = QStandardItem(f"  {name}")
                item.setData(name, Qt.UserRole)
                item.setFont(QFont(FONT_MAIN, 10))
                model.appendRow(item)

        self._printer_combo.setModel(model)

        saved = PREFS.get("printer_default", "")
        if saved:
            for i in range(model.rowCount()):
                it = model.item(i)
                if it and it.data(Qt.UserRole) == saved:
                    self._printer_combo.setCurrentIndex(i)
                    return
        self._printer_combo.setCurrentIndex(0)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_theme_toggled(self, checked: bool):
        _T.switch("dark" if checked else "light")
        self._dark_cb.blockSignals(True)
        self._dark_cb.setChecked(_T.is_dark())
        self._dark_cb.blockSignals(False)

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

    def _on_printer_changed(self):
        model = self._printer_combo.model()
        idx = self._printer_combo.currentIndex()
        item = model.item(idx)
        if item and item.isEnabled():
            PREFS.set("printer_default", item.data(Qt.UserRole) or "")

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
        for sep in (self._sep_top, self._sep_print, self._sep_export, self._sep_perf, self._sep_updates):
            sep.setStyleSheet(sep_style)

        section_style = f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 1px;"
        for lbl in (self._lbl_apparence, self._lbl_print, self._lbl_export, self._lbl_perf, self._lbl_updates):
            lbl.setStyleSheet(section_style)

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
        for lbl in (self._dark_lbl, self._lang_lbl, self._printer_lbl, self._perf_lbl):
            lbl.setStyleSheet(row_lbl_style)

        self._perf_desc_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
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
        for cb in (self._dark_cb,):
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
        for combo in (self._lang_combo, self._printer_combo, self._perf_combo):
            combo.setStyleSheet(combo_style)

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
