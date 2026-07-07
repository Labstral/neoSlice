"""Fenêtre de configuration de la sauvegarde automatique de l'Espace Pro.

Sauvegarde auto = export ZIP de toutes les données métier (clients, devis,
factures, bobines…) dans un dossier choisi par l'utilisateur, à la fréquence
choisie. Modale, sans chrome OS, thème-aware (cohérente avec settings_dialog).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import _
from core.prefs import PREFS
from ui.styles.theme import MANAGER as _T, FONT_MAIN


class AutoBackupDialog(QDialog):
    """Configure la sauvegarde automatique (dossier + fréquence)."""

    configured = Signal()   # émis après enregistrement (pour rafraîchir le statut)

    _FREQS = ("open", "daily", "weekly", "monthly")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self._drag_pos: QPoint | None = None
        self._setup_ui()
        self._load()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    # ── Drag ────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ── UI ──────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("abk_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(24, 18, 24, 22)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # Titre + fermer
        trow = QHBoxLayout()
        self._title = QLabel(_("pro.autobk_title"))
        self._title.setFont(QFont(FONT_MAIN, 11, QFont.Bold))
        self._close = QPushButton("✕")
        self._close.setFixedSize(22, 22)
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.clicked.connect(self.reject)
        trow.addWidget(self._title); trow.addStretch(); trow.addWidget(self._close)
        lay.addLayout(trow)

        self._sep = QFrame(); self._sep.setFixedHeight(1)
        lay.addSpacing(12); lay.addWidget(self._sep); lay.addSpacing(14)

        # Intro
        self._intro = QLabel(_("pro.autobk_intro"))
        self._intro.setFont(QFont(FONT_MAIN, 9)); self._intro.setWordWrap(True)
        lay.addWidget(self._intro)
        lay.addSpacing(16)

        # Activer
        en_row = QHBoxLayout()
        self._enable_lbl = QLabel(_("pro.autobk_enable"))
        self._enable_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._enable_cb = QCheckBox()
        self._enable_cb.toggled.connect(self._sync_enabled)
        en_row.addWidget(self._enable_lbl); en_row.addStretch(); en_row.addWidget(self._enable_cb)
        lay.addLayout(en_row)
        lay.addSpacing(12)

        # Dossier
        self._folder_lbl = QLabel(_("pro.autobk_folder"))
        self._folder_lbl.setFont(QFont(FONT_MAIN, 9))
        lay.addWidget(self._folder_lbl)
        lay.addSpacing(4)
        f_row = QHBoxLayout(); f_row.setSpacing(6)
        self._folder_edit = QLineEdit(); self._folder_edit.setReadOnly(True)
        self._folder_edit.setFont(QFont(FONT_MAIN, 9))
        self._folder_edit.setPlaceholderText(_("pro.autobk_folder_none"))
        self._browse_btn = QPushButton(_("pro.autobk_browse"))
        self._browse_btn.setCursor(Qt.PointingHandCursor); self._browse_btn.setFixedHeight(30)
        self._browse_btn.clicked.connect(self._browse)
        f_row.addWidget(self._folder_edit, 1); f_row.addWidget(self._browse_btn)
        lay.addLayout(f_row)
        lay.addSpacing(12)

        # Fréquence
        fq_row = QHBoxLayout()
        self._freq_lbl = QLabel(_("pro.autobk_freq"))
        self._freq_lbl.setFont(QFont(FONT_MAIN, 9))
        self._freq_combo = QComboBox(); self._freq_combo.setFixedWidth(190)
        for fq in self._FREQS:
            self._freq_combo.addItem(_(f"pro.autobk_freq_{fq}"), fq)
        fq_row.addWidget(self._freq_lbl); fq_row.addStretch(); fq_row.addWidget(self._freq_combo)
        lay.addLayout(fq_row)
        lay.addSpacing(14)

        # Dernière sauvegarde
        self._last_lbl = QLabel("")
        self._last_lbl.setFont(QFont(FONT_MAIN, 8))
        lay.addWidget(self._last_lbl)
        lay.addSpacing(10)

        # Astuce
        self._hint = QLabel(_("pro.autobk_hint"))
        self._hint.setFont(QFont(FONT_MAIN, 8)); self._hint.setWordWrap(True)
        lay.addWidget(self._hint)
        lay.addSpacing(18)

        # Boutons
        b_row = QHBoxLayout(); b_row.addStretch()
        self._cancel_btn = QPushButton(_("pro.autobk_cancel"))
        self._cancel_btn.setCursor(Qt.PointingHandCursor); self._cancel_btn.setFixedHeight(32)
        self._cancel_btn.clicked.connect(self.reject)
        self._save_btn = QPushButton(_("pro.autobk_save"))
        self._save_btn.setCursor(Qt.PointingHandCursor); self._save_btn.setFixedHeight(32)
        self._save_btn.clicked.connect(self._save)
        b_row.addWidget(self._cancel_btn); b_row.addWidget(self._save_btn)
        lay.addLayout(b_row)

    # ── Données ─────────────────────────────────────────────────────────────
    def _load(self):
        self._enable_cb.setChecked(bool(PREFS.get("autobk_enabled", False)))
        self._folder_edit.setText(str(PREFS.get("autobk_dir", "") or ""))
        fq = PREFS.get("autobk_freq", "weekly")
        i = self._freq_combo.findData(fq)
        self._freq_combo.setCurrentIndex(max(0, i))
        last = PREFS.get("autobk_last", "")
        shown = last if last else _("pro.autobk_last_never")
        self._last_lbl.setText(_("pro.autobk_last", date=shown))
        self._sync_enabled()

    def _sync_enabled(self):
        on = self._enable_cb.isChecked()
        for w in (self._folder_lbl, self._folder_edit, self._browse_btn,
                  self._freq_lbl, self._freq_combo):
            w.setEnabled(on)

    def _browse(self):
        start = self._folder_edit.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, _("pro.autobk_folder"), start)
        if d:
            self._folder_edit.setText(d)

    def _save(self):
        enabled = self._enable_cb.isChecked()
        folder = self._folder_edit.text().strip()
        if enabled and not folder:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, _("pro.autobk_title"), _("pro.autobk_need_folder"))
            return
        PREFS.set("autobk_enabled", enabled)
        PREFS.set("autobk_dir", folder)
        PREFS.set("autobk_freq", self._freq_combo.currentData())
        self.configured.emit()
        self.accept()

    # ── Thème ───────────────────────────────────────────────────────────────
    def _apply_theme(self):
        p = _T.palette()
        self._card.setStyleSheet(
            f"QWidget#abk_card {{ background: {p['BG_PANEL']}; "
            f"border: 1px solid {p['ACCENT']}; border-radius: 8px; }}")
        self._title.setStyleSheet(f"color: {p['TEXT_PRIMARY']}; background: transparent;")
        self._sep.setStyleSheet(f"background: {p['INACTIVE']}; border: none;")
        self._intro.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; background: transparent;")
        self._enable_lbl.setStyleSheet(f"color: {p['TEXT_PRIMARY']}; background: transparent;")
        for l in (self._folder_lbl, self._freq_lbl):
            l.setStyleSheet(f"color: {p['TEXT_SECONDARY']}; background: transparent;")
        self._last_lbl.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;")
        self._hint.setStyleSheet(f"color: {p['TEXT_LABEL']}; background: transparent;")
        self._close.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {p['TEXT_SECONDARY']}; border: none; }}"
            f"QPushButton:hover {{ background: {p['ERROR_RED']}; color: #fff; border-radius: 4px; }}")
        field = (f"QLineEdit, QComboBox {{ background: {p['BG_INPUT']}; color: {p['TEXT_PRIMARY']}; "
                 f"border: 1px solid {p['INACTIVE']}; border-radius: 4px; padding: 4px 8px; }}"
                 f"QLineEdit:disabled, QComboBox:disabled {{ color: {p['TEXT_LABEL']}; }}")
        self._folder_edit.setStyleSheet(field)
        self._freq_combo.setStyleSheet(field)
        soft = (f"QPushButton {{ background: transparent; color: {p['TEXT_SECONDARY']}; "
                f"border: 1px solid {p['INACTIVE']}; border-radius: 4px; padding: 0 16px; }}"
                f"QPushButton:hover {{ border-color: {p['ACCENT']}; color: {p['ACCENT']}; }}"
                f"QPushButton:disabled {{ color: {p['TEXT_LABEL']}; border-color: {p['INACTIVE']}; }}")
        self._browse_btn.setStyleSheet(soft)
        self._cancel_btn.setStyleSheet(soft)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {p['ACCENT']}; color: #fff; border: none; "
            f"border-radius: 4px; padding: 0 20px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {p['ACCENT_BRIGHT']}; }}")
        self._enable_cb.setStyleSheet(
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
            f"QCheckBox::indicator:unchecked {{ border: 1px solid {p['INACTIVE']}; "
            f"background: {p['BG_INPUT']}; border-radius: 4px; }}"
            f"QCheckBox::indicator:checked {{ border: 1px solid {p['TELE_GREEN']}; "
            f"background: {p['TELE_GREEN']}; border-radius: 4px; }}")
