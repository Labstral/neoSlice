# -*- coding: utf-8 -*-
"""Gestionnaire de MODULES — les briques optionnelles de neoSlice (Pro).

Chaque module s'installe/se désinstalle librement, comme les extensions d'un
navigateur ou les plugins d'un slicer :
  🤖 Oen    — assistant IA local (Ollama + Qwen3 8B + base de connaissances)
  🛠 neoGen — génération d'objets 3D par texte (modèle dédié qwen3:14b)

La fenêtre Paramètres n'affiche plus qu'un résumé compact + « Gérer les
modules… » qui ouvre ce dialogue. Ajouter un futur module = une carte de plus
ici. Toute la logique d'installation vit dans ce fichier (workers QThread).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QFrame, QMessageBox,
)

from core.i18n import _
from ui.styles.theme import MANAGER as _T

FONT_MAIN = "Segoe UI"
PRO_CYAN, PRO_VIOLET = "#22D3EE", "#A855F7"


# ═══════════════════════════════ Workers ════════════════════════════════════
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


class _NeoGenInstallWorker(QThread):
    """Installe neoGen : telecharge son modele dedie (qwen3:14b, ~9 Go)."""
    progress = Signal(int, str)
    done = Signal()
    failed = Signal(str)

    def run(self):
        try:
            from core.neogen.installation import installer
            installer(progress_cb=lambda p, s: self.progress.emit(p, s))
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class _NeoGenUninstallWorker(QThread):
    """Desinstalle neoGen (supprime le modele 14b, libere ~9 Go)."""
    done = Signal()
    failed = Signal(str)

    def run(self):
        try:
            from core.neogen.installation import desinstaller
            desinstaller()
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class _KBCheckWorker(QThread):
    """Verifie (appel reseau) si une nouvelle base d'Oen existe."""
    result = Signal(object)

    def run(self):
        try:
            from core.assistant.kb_update import KBUpdater
            self.result.emit(KBUpdater().check())
        except Exception:
            self.result.emit(None)


class _KBUpdateWorker(QThread):
    """Telecharge/applique la mise a jour de la base d'Oen (swap atomique)."""
    progress = Signal(str, float)
    done = Signal(str)
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


# ═══════════════════════════ État (résumé réglages) ═════════════════════════
def etat_modules() -> list[tuple[str, bool]]:
    """[(nom, installé), ...] — pour le résumé coloré des Paramètres."""
    from core.assistant.engine import AssistantEngine
    from core.assistant.installer import is_installed
    from core.neogen import installation
    return [("Oen", is_installed() or AssistantEngine.available()),
            ("neoGen", installation.est_installe())]


def resume_etat() -> str:
    """Résumé compact en texte riche : modules installés en VERT."""
    pal = _T.palette()
    morceaux = []
    for nom, ok in etat_modules():
        coul = pal["TELE_GREEN"] if ok else pal["TEXT_SECONDARY"]
        marque = "✓" if ok else "—"
        morceaux.append(f"<span style='color:{coul};'>{nom} {marque}</span>")
    return "&nbsp;&nbsp;·&nbsp;&nbsp;".join(morceaux)


# ═══════════════════════════════ Dialogue ════════════════════════════════════
class ModulesDialog(QDialog):
    """Une carte par module : statut, description, installer/désinstaller."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("modules.title"))
        self.setMinimumWidth(560)
        pal = _T.palette()
        self.setStyleSheet(f"background: {pal['BG_PANEL']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        titre = QLabel(_("modules.title"))
        titre.setFont(QFont(FONT_MAIN, 15, QFont.Weight.Bold))
        titre.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        lay.addWidget(titre)
        sous = QLabel(_("modules.subtitle"))
        sous.setWordWrap(True)
        sous.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")
        lay.addWidget(sous)

        lay.addWidget(self._carte_oen())
        lay.addWidget(self._carte_neogen())
        lay.addStretch()

        self._assist_worker = None
        self._uninstall_worker = None
        self._kb_check_worker = None
        self._kb_update_worker = None
        self._neogen_worker = None
        self._neogen_un_worker = None
        self._refresh_assistant_status()
        self._refresh_neogen_status()

    # ── Fabrique de cartes ────────────────────────────────────────────────────
    def _cadre(self) -> tuple[QFrame, QVBoxLayout]:
        pal = _T.palette()
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{ background: {pal['BG_SURFACE']};
                      border: 1px solid {pal['INACTIVE']}; border-radius: 8px; }}
            QLabel {{ border: none; }}
        """)
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(6)
        return f, v

    def _titre_carte(self, nom: str, pitch: str) -> QLabel:
        pal = _T.palette()
        w = QLabel(f"<b>{nom}</b>  <span style='color:{pal['TEXT_LABEL']};'>— {pitch}</span>")
        w.setFont(QFont(FONT_MAIN, 10))
        w.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        w.setTextFormat(Qt.RichText)
        return w

    # ── Carte OEN ─────────────────────────────────────────────────────────────
    def _carte_oen(self) -> QFrame:
        f, v = self._cadre()
        v.addWidget(self._titre_carte("Oen", _("modules.oen_pitch")))
        self._assist_status_lbl = QLabel()
        self._assist_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._assist_status_lbl.setWordWrap(True)
        v.addWidget(self._assist_status_lbl)
        self._assist_progress = QProgressBar()
        self._assist_progress.setRange(0, 100)
        self._assist_progress.setTextVisible(True)
        self._assist_progress.setFixedHeight(16)
        self._assist_progress.hide()
        v.addWidget(self._assist_progress)
        row = QHBoxLayout()
        self._kb_btn = QPushButton(_("oen.kb_update"))
        self._kb_btn.setFont(QFont(FONT_MAIN, 8))
        self._kb_btn.setFixedHeight(26)
        self._kb_btn.setCursor(Qt.PointingHandCursor)
        self._kb_btn.clicked.connect(self._on_kb_update_btn)
        self._kb_btn.hide()
        self._assist_btn = QPushButton()
        self._assist_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._assist_btn.setFixedHeight(26)
        self._assist_btn.setCursor(Qt.PointingHandCursor)
        self._assist_btn.clicked.connect(self._on_assist_btn)
        row.addStretch()
        row.addWidget(self._kb_btn)
        row.addSpacing(6)
        row.addWidget(self._assist_btn)
        v.addLayout(row)
        return f

    # ── Carte NEOGEN ─────────────────────────────────────────────────────────
    def _carte_neogen(self) -> QFrame:
        f, v = self._cadre()
        v.addWidget(self._titre_carte("neoGen", _("modules.neogen_pitch")))
        self._neogen_status_lbl = QLabel()
        self._neogen_status_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._neogen_status_lbl.setWordWrap(True)
        v.addWidget(self._neogen_status_lbl)
        self._neogen_progress = QProgressBar()
        self._neogen_progress.setRange(0, 100)
        self._neogen_progress.setTextVisible(True)
        self._neogen_progress.setFixedHeight(16)
        self._neogen_progress.hide()
        v.addWidget(self._neogen_progress)
        row = QHBoxLayout()
        self._neogen_btn = QPushButton()
        self._neogen_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._neogen_btn.setFixedHeight(26)
        self._neogen_btn.setCursor(Qt.PointingHandCursor)
        self._neogen_btn.clicked.connect(self._on_neogen_btn)
        row.addStretch()
        row.addWidget(self._neogen_btn)
        v.addLayout(row)
        return f

    # ═══════════════ Oen : statut / installer / désinstaller / base ══════════
    def _refresh_assistant_status(self):
        from core.assistant.engine import AssistantEngine
        from core.assistant.installer import is_installed
        from core import licensing
        pal = _T.palette()
        installed = is_installed() or AssistantEngine.available()
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

    # ── Oen : mise à jour de la base de connaissances ─────────────────────────
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
        self._kb_update_worker.progress.connect(self._on_install_progress)
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

    # ═══════════════ neoGen : statut / installer / désinstaller ══════════════
    def _refresh_neogen_status(self):
        from core.neogen import installation
        from core import licensing
        pal = _T.palette()
        if installation.est_installe():
            self._neogen_status_lbl.setText(_("neogen.ready"))
            self._neogen_status_lbl.setStyleSheet(
                f"color: {pal['TELE_GREEN']}; background: transparent;")
            self._neogen_btn.setText(_("neogen.uninstall"))
            self._neogen_btn.setFont(QFont(FONT_MAIN, 8))
            self._neogen_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {pal['TEXT_SECONDARY']};
                    border: 1px solid {pal['INACTIVE']}; border-radius: 4px; padding: 4px 12px;
                }}
                QPushButton:hover {{ border-color: {pal['ERROR_RED']}; color: {pal['ERROR_RED']}; }}
            """)
            self._neogen_btn.setEnabled(True)
            self._neogen_btn.show()
            return
        if not licensing.est_pro():
            self._neogen_status_lbl.setText(_("neogen.pro_only"))
            self._neogen_status_lbl.setStyleSheet(
                f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
            self._neogen_btn.hide()
            return
        if not installation.runtime_present():
            self._neogen_status_lbl.setText(_("neogen.need_runtime"))
            self._neogen_status_lbl.setStyleSheet(
                f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
            self._neogen_btn.hide()
            return
        self._neogen_status_lbl.setText(_("neogen.install_pitch"))
        self._neogen_status_lbl.setStyleSheet(
            f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._neogen_btn.setText(_("neogen.install"))
        self._neogen_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._neogen_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']}; color: #ffffff; border: none;
                border-radius: 4px; padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['BG_PANEL']}; }}
        """)
        self._neogen_btn.setEnabled(True)
        self._neogen_btn.show()

    def _on_neogen_btn(self):
        from core.neogen import installation
        if installation.est_installe():
            rep = QMessageBox.question(
                self, _("neogen.uninstall_title"), _("neogen.uninstall_confirm"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if rep != QMessageBox.Yes:
                return
            self._neogen_btn.setEnabled(False)
            self._neogen_un_worker = _NeoGenUninstallWorker(self)
            self._neogen_un_worker.done.connect(self._on_neogen_un_done)
            self._neogen_un_worker.failed.connect(self._on_neogen_failed)
            self._neogen_un_worker.start()
            return
        if self._neogen_worker is not None:
            return
        self._neogen_btn.setEnabled(False)
        self._neogen_btn.setText(_("neogen.installing"))
        self._neogen_progress.setValue(0)
        self._neogen_progress.show()
        self._neogen_worker = _NeoGenInstallWorker(self)
        self._neogen_worker.progress.connect(
            lambda p, s: self._neogen_progress.setValue(int(p)))
        self._neogen_worker.done.connect(self._on_neogen_done)
        self._neogen_worker.failed.connect(self._on_neogen_failed)
        self._neogen_worker.start()

    def _on_neogen_done(self):
        self._neogen_worker = None
        self._neogen_progress.hide()
        self._refresh_neogen_status()

    def _on_neogen_un_done(self):
        self._neogen_un_worker = None
        self._refresh_neogen_status()

    def _on_neogen_failed(self, msg: str):
        self._neogen_worker = None
        self._neogen_un_worker = None
        self._neogen_progress.hide()
        pal = _T.palette()
        self._neogen_status_lbl.setText("⚠ " + msg)
        self._neogen_status_lbl.setStyleSheet(
            f"color: {pal['ERROR_RED']}; background: transparent;")
        self._neogen_btn.setEnabled(True)
        self._neogen_btn.setText(_("neogen.install"))
