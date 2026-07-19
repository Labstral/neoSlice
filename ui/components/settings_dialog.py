"""Fenêtre paramètres neoSlice — modale, sans chrome OS, thème-aware."""
from __future__ import annotations

import os
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
    """Analyse COMPLÈTE de la configuration, en arrière-plan.

    Ne se limite plus au couple « vitesse CPU + RAM » (qui ne jugeait que
    l'analyse de pièces) : relève aussi le GPU (+ VRAM si NVIDIA), la RAM
    disponible et l'espace disque libre — nécessaires pour évaluer les modules
    gourmands (Oen = modèle 8B ~5 Go, neoGen = modèle ~12B ~9 Go, installés
    sous ~/.neoslice). Émet un dict complet."""
    result_ready = Signal(object)

    @staticmethod
    def _detect_gpu() -> tuple[str, float, bool]:
        """(nom, vram_gb, dédié). VRAM fiable seulement via nvidia-smi ;
        sinon nom via CIM et VRAM 0 (les modèles locaux tourneront sur CPU —
        Ollama sous Windows n'accélère en pratique que sur NVIDIA)."""
        import subprocess as _sp
        _NOWIN = 0x08000000 if sys.platform == "win32" else 0
        try:
            r = _sp.run(["nvidia-smi", "--query-gpu=name,memory.total",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=6,
                        creationflags=_NOWIN)
            line = (r.stdout or "").strip().splitlines()
            if r.returncode == 0 and line:
                nom, mem = line[0].rsplit(",", 1)
                return nom.strip(), float(mem.strip()) / 1024.0, True
        except Exception:
            pass
        try:
            if sys.platform == "win32":
                r = _sp.run(["powershell", "-NoProfile", "-Command",
                             "(Get-CimInstance Win32_VideoController).Name"],
                            capture_output=True, text=True, timeout=10,
                            creationflags=_NOWIN)
                noms = [n.strip() for n in (r.stdout or "").splitlines()
                        if n.strip() and "Basic Display" not in n]
                if noms:
                    nom = noms[0]
                    low = nom.lower()
                    integre = any(k in low for k in (
                        "intel", "uhd", "iris", "radeon(tm) graphics", "vega"))
                    return nom, 0.0, not integre
        except Exception:
            pass
        return "", 0.0, False

    def run(self):
        reps = 3
        a = np.random.rand(512, 512).astype(np.float32)
        b = np.random.rand(512, 512).astype(np.float32)
        t0 = time.perf_counter()
        for _ in range(reps):
            np.dot(a, b)
        elapsed_ms = (time.perf_counter() - t0) * 1000 / reps

        ram_gb = avail_gb = 0.0
        try:
            if sys.platform == "win32":
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
                avail_gb = ms.ullAvailPhys / (1024 ** 3)
            else:
                import psutil
                vm = psutil.virtual_memory()
                ram_gb, avail_gb = vm.total / (1024 ** 3), vm.available / (1024 ** 3)
        except Exception:
            pass

        gpu_name, vram_gb, gpu_dedie = self._detect_gpu()

        disk_free_gb = 0.0
        try:
            import shutil as _sh
            from pathlib import Path as _P
            disk_free_gb = _sh.disk_usage(_P.home()).free / (1024 ** 3)
        except Exception:
            pass

        if elapsed_ms < 10.0:
            tier = "full"
        elif elapsed_ms < 40.0:
            tier = "balanced"
        else:
            tier = "lite"

        self.result_ready.emit({
            "tier": tier, "elapsed_ms": elapsed_ms,
            "ram_gb": ram_gb, "avail_gb": avail_gb,
            "cores": os.cpu_count() or 0,
            "gpu_name": gpu_name, "vram_gb": vram_gb, "gpu_dedie": gpu_dedie,
            "disk_free_gb": disk_free_gb,
        })


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
        # Hauteur PLAFONNÉE + corps scrollable : la fenêtre était devenue plus
        # haute que l'écran (le lien Licences en bas était inatteignable).
        from PySide6.QtGui import QGuiApplication
        ecran = QGuiApplication.primaryScreen()
        h_dispo = ecran.availableGeometry().height() if ecran else 800
        self.setFixedHeight(min(700, h_dispo - 80))
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

        # ── Corps SCROLLABLE : tout le contenu défile, barre de titre fixe ────
        from PySide6.QtWidgets import QScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        _corps = QWidget()
        _corps.setObjectName("settings_body")
        self._scroll.setWidget(_corps)
        lay.addWidget(self._scroll, 1)
        lay = QVBoxLayout(_corps)      # tout ce qui suit va dans le corps
        lay.setContentsMargins(0, 16, 8, 4)
        lay.setSpacing(0)

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
            _("settings.scanbar_anim"), bool(PREFS.get("scanbar_anim", False)))
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
        self._slicer_combo.addItem(_("settings.slicer_anycubic"), "anycubic")
        self._slicer_combo.addItem(_("settings.slicer_snapmaker"), "snapmaker")
        self._slicer_combo.addItem(_("settings.slicer_cura"), "cura")
        _saved_slicer = PREFS.get("slicer_output", "bambu")
        _slicer_idx = {"bambu": 0, "orca": 1, "prusa": 2, "creality": 3,
                       "elegoo": 4, "anycubic": 5, "snapmaker": 6,
                       "cura": 7}.get(_saved_slicer, 0)
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

        # ── Sections Pro (Diagnostic IA + Oen) : masquées en version non-Pro ──
        self._pro_features_section = QWidget()
        _pflay = QVBoxLayout(self._pro_features_section)
        _pflay.setContentsMargins(0, 0, 0, 0)
        _pflay.setSpacing(0)
        # ── Section DIAGNOSTIC IA ─────────────────────────────────────────────
        _pflay.addSpacing(10)
        self._sep_diag = self._make_sep()
        _pflay.addWidget(self._sep_diag)
        _pflay.addSpacing(14)

        self._lbl_diag = self._make_section_label("DIAGNOSTIC IA")
        _pflay.addWidget(self._lbl_diag)
        _pflay.addSpacing(10)

        # Statut (pleine largeur)
        self._diag_status_lbl = QLabel()
        self._diag_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._diag_status_lbl.setWordWrap(True)
        _pflay.addWidget(self._diag_status_lbl)
        _pflay.addSpacing(6)

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
        _pflay.addLayout(btn_row)
        _pflay.addSpacing(4)

        # ── Section MODULES (Oen, neoGen, ... — briques optionnelles) ────────
        _pflay.addSpacing(10)
        self._sep_modules = self._make_sep()
        _pflay.addWidget(self._sep_modules)
        _pflay.addSpacing(14)

        self._lbl_modules = self._make_section_label(_("modules.section"))
        _pflay.addWidget(self._lbl_modules)
        _pflay.addSpacing(10)

        self._modules_status_lbl = QLabel()
        self._modules_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._modules_status_lbl.setWordWrap(True)
        _pflay.addWidget(self._modules_status_lbl)
        _pflay.addSpacing(6)

        modules_row = QHBoxLayout()
        modules_row.setContentsMargins(0, 0, 0, 0)
        self._modules_btn = QPushButton(_("modules.manage_btn"))
        self._modules_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._modules_btn.setFixedHeight(28)
        self._modules_btn.setCursor(Qt.PointingHandCursor)
        self._modules_btn.clicked.connect(self._open_modules)
        modules_row.addStretch()
        modules_row.addWidget(self._modules_btn)
        _pflay.addLayout(modules_row)
        self._refresh_modules_summary()
        _pflay.addSpacing(4)

        lay.addWidget(self._pro_features_section)

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
    # ── MODULES : resume + ouverture du gestionnaire ─────────────────────────
    def _refresh_modules_summary(self):
        pal = _T.palette()
        try:
            from ui.components.modules_dialog import resume_etat
            self._modules_status_lbl.setTextFormat(Qt.RichText)
            self._modules_status_lbl.setText(resume_etat())   # noms en vert si installés
        except Exception:
            self._modules_status_lbl.setText("")
        self._modules_status_lbl.setStyleSheet("background: transparent;")
        self._modules_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']}; color: #ffffff; border: none;
                border-radius: 4px; padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
        """)

    def _open_modules(self):
        from ui.components.modules_dialog import ModulesDialog
        dlg = ModulesDialog(self)
        dlg.exec()
        self._refresh_modules_summary()   # l'etat a pu changer (install/desinstall)

    def _refresh_pro_status(self):
        from core import licensing
        pal = _T.palette()
        # Sections Diagnostic IA + Oen : réservées au Pro → masquées en version non-Pro
        # (la section NEOSLICE PRO ci-dessous indique déjà qu'elles sont réservées).
        if hasattr(self, "_pro_features_section"):
            self._pro_features_section.setVisible(licensing.est_pro())
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

    def _on_bench_result(self, info: dict):
        """Affiche l'analyse COMPLÈTE : un verdict par domaine (pièces, diagnostic
        photo, Oen, neoGen) + résumé matériel — et plus seulement le mode
        d'affichage. Les modèles locaux des modules sont ce qui exige le plus
        (Oen 8B ≈ 5 Go, neoGen ~12B ≈ 9 Go) : c'est dit clairement, avec la
        raison (GPU/RAM/disque) quand la config n'est pas optimale."""
        self._perf_test_btn.setEnabled(True)
        self._perf_test_btn.setText(_("settings.perf_test_btn"))

        tier = info.get("tier", "full")
        ram, avail = info.get("ram_gb", 0.0), info.get("avail_gb", 0.0)
        vram, gpu_dedie = info.get("vram_gb", 0.0), info.get("gpu_dedie", False)
        gpu_name = info.get("gpu_name") or _("settings.cfg_gpu_none")
        disk = info.get("disk_free_gb", 0.0)
        pal = _T.palette()
        V, A, R = pal["TELE_GREEN"], pal["AMBER"], pal["ERROR_RED"]

        # ── Verdicts par domaine : (couleur, icône, texte) ───────────────────
        lignes: list[tuple[str, str, str, str]] = []   # (titre, couleur, icône, verdict)

        piece_txt = _({"full": "settings.perf_result_full",
                       "balanced": "settings.perf_result_balanced",
                       "lite": "settings.perf_result_lite"}[tier])
        piece_col = {"full": V, "balanced": A, "lite": R}[tier]
        lignes.append((_("settings.cfg_line_pieces"), piece_col,
                       {"full": "✓", "balanced": "△", "lite": "△"}[tier], piece_txt))

        # Diagnostic IA photo : modèle ONNX léger, tourne partout — juste lent
        # sur CPU vraiment faible.
        if tier == "lite":
            lignes.append((_("settings.cfg_line_diag"), A, "△", _("settings.cfg_diag_slow")))
        else:
            lignes.append((_("settings.cfg_line_diag"), V, "✓", _("settings.cfg_diag_ok")))

        # Oen (qwen3:8b ≈ 5 Go) : GPU NVIDIA ≥ 6 Go = rapide ; sinon CPU = lent.
        if vram >= 6.0:
            lignes.append((_("settings.cfg_line_oen"), V, "✓",
                           _("settings.cfg_oen_gpu", vram=f"{vram:.0f}")))
        elif ram >= 16.0:
            lignes.append((_("settings.cfg_line_oen"), A, "△", _("settings.cfg_oen_cpu")))
        elif ram >= 8.0:
            lignes.append((_("settings.cfg_line_oen"), A, "△",
                           _("settings.cfg_oen_limit", ram=f"{ram:.0f}")))
        else:
            lignes.append((_("settings.cfg_line_oen"), R, "✗", _("settings.cfg_oen_no")))

        # neoGen (modèle local ~12B ≈ 9 Go) : plus lourd qu'Oen.
        if vram >= 10.0:
            lignes.append((_("settings.cfg_line_neogen"), V, "✓", _("settings.cfg_neogen_gpu")))
        elif ram >= 16.0:
            lignes.append((_("settings.cfg_line_neogen"), A, "△", _("settings.cfg_neogen_cpu")))
        elif ram >= 12.0:
            lignes.append((_("settings.cfg_line_neogen"), A, "△",
                           _("settings.cfg_neogen_limit", ram=f"{ram:.0f}")))
        else:
            lignes.append((_("settings.cfg_line_neogen"), R, "✗", _("settings.cfg_neogen_no")))

        # ── Rendu HTML (thème-aware : couleurs de la palette active) ─────────
        sec = pal["TEXT_SECONDARY"]
        html = [f'<span style="color:{sec};">'
                + _("settings.cfg_summary", cores=info.get("cores", 0),
                    ram=f"{ram:.0f}", avail=f"{avail:.0f}", gpu=gpu_name,
                    disk=f"{disk:.0f}")
                + "</span>"]
        prim = pal["TEXT_PRIMARY"]        # couleur EXPLICITE : sans elle, les titres
        for titre, col, ico, verdict in lignes:   # héritaient d'un gris illisible en sombre
            html.append(f'<span style="color:{col};">{ico}</span> '
                        f'<b><span style="color:{prim};">{titre}</span></b><br/>'
                        f'<span style="color:{sec};">&nbsp;&nbsp;&nbsp;{verdict}</span>')
        if 0 < disk < 15.0:
            html.append(f'<span style="color:{A};">'
                        + _("settings.cfg_disk_warn", disk=f"{disk:.0f}") + "</span>")
        self._perf_result_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._perf_result_lbl.setWordWrap(True)
        self._perf_result_lbl.setText("<br/>".join(html))
        self._perf_result_lbl.setStyleSheet("background: transparent;")
        self._perf_result_lbl.show()

        # Auto-application du mode d'affichage suggéré (comportement historique)
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
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QWidget#settings_body {{ background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 0; }}
            QScrollBar::handle:vertical {{
                background: {pal['INACTIVE']}; border-radius: 5px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {pal['ACCENT']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
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
                    self._sep_updates, self._sep_diag, self._sep_modules, self._sep_pro):
            sep.setStyleSheet(sep_style)

        section_style = f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 1px;"
        for lbl in (self._lbl_apparence, self._lbl_print, self._lbl_export,
                    self._lbl_perf, self._lbl_updates, self._lbl_diag,
                    self._lbl_modules, self._lbl_pro):
            lbl.setStyleSheet(section_style)

        # Résumé Modules (couleurs dépendantes du thème)
        if hasattr(self, "_modules_status_lbl"):
            self._refresh_modules_summary()

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
