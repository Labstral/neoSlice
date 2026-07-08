"""Fenêtre de diagnostic photo — détection de défauts d'impression IA.

Drag & drop d'une photo → analyse ONNX locale → affichage du défaut,
de la confiance et des corrections à appliquer au PrintConfig courant.

Flux de consentement obligatoire :
  DiagnosticConsentDialog → accepté → DefectDiagnosticDialog
                          → refusé  → fonctionnalité inaccessible
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QPoint, QThread, Signal, QSize, QTimer
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QFont,
    QMouseEvent, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
    QFileDialog, QProgressBar,
)

from ui.styles.theme import MANAGER as _T, FONT_MAIN, FONT_MONO
from core.i18n import _


# ── Dialog de consentement ─────────────────────────────────────────────────────

class DiagnosticConsentDialog(QDialog):
    """Demande le consentement au partage de photos avant d'activer le diagnostic.

    Retourne QDialog.Accepted si l'utilisateur accepte, Rejected sinon.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(480)
        self._drag_pos: QPoint | None = None
        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
        super().closeEvent(event)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _ev):
        self._drag_pos = None

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("consent_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(28, 22, 28, 24)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # Icone + titre
        icon_lbl = QLabel("⬡")
        icon_lbl.setFont(QFont(FONT_MAIN, 32))
        icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl = icon_lbl
        lay.addWidget(icon_lbl)
        lay.addSpacing(10)

        title = QLabel("DIAGNOSTIC IA")
        title.setFont(QFont(FONT_MAIN, 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        self._title_lbl = title
        lay.addWidget(title)
        lay.addSpacing(6)

        subtitle = QLabel("Détectez les défauts d'impression et obtenez\nles corrections automatiquement")
        subtitle.setFont(QFont(FONT_MAIN, 8))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        self._subtitle_lbl = subtitle
        lay.addWidget(subtitle)
        lay.addSpacing(20)

        sep1 = _make_sep()
        lay.addWidget(sep1)
        lay.addSpacing(16)
        self._sep1 = sep1

        # Explication fonctionnement
        how_title = QLabel("Comment ça fonctionne")
        how_title.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._how_title = how_title
        lay.addWidget(how_title)
        lay.addSpacing(8)

        steps = [
            ("1", "Vous glissez une photo de votre impression"),
            ("2", "Le modèle IA analyse la photo en local sur votre PC"),
            ("3", "neoSlice identifie le défaut et vous propose des corrections"),
        ]
        self._step_widgets = []
        for num, text in steps:
            row = QHBoxLayout()
            row.setSpacing(10)
            num_lbl = QLabel(num)
            num_lbl.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            num_lbl.setFixedSize(20, 20)
            num_lbl.setAlignment(Qt.AlignCenter)
            text_lbl = QLabel(text)
            text_lbl.setFont(QFont(FONT_MAIN, 8))
            text_lbl.setWordWrap(True)
            row.addWidget(num_lbl)
            row.addWidget(text_lbl, 1)
            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent;")
            wrapper.setLayout(row)
            lay.addWidget(wrapper)
            lay.addSpacing(4)
            self._step_widgets.append((num_lbl, text_lbl))

        lay.addSpacing(16)

        sep2 = _make_sep()
        lay.addWidget(sep2)
        lay.addSpacing(14)
        self._sep2 = sep2

        # Section partage — la condition
        share_title = QLabel("Pourquoi le partage est nécessaire")
        share_title.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._share_title = share_title
        lay.addWidget(share_title)
        lay.addSpacing(8)

        share_text = QLabel(
            "Ce service repose sur un modèle IA entraîné sur des photos d'impressions réelles. "
            "Pour que le modèle s'améliore avec le temps et détecte de mieux en mieux les défauts, "
            "il a besoin de nouvelles photos annotées.\n\n"
            "Lorsque vous confirmez un résultat, votre photo et le label correspondant "
            "(ex: \"warping\") sont envoyés de façon anonyme — sans aucune donnée personnelle. "
            "Ces contributions permettent de réentraîner régulièrement le modèle et "
            "d'en faire profiter tous les utilisateurs.\n\n"
            "Sans ce partage, le modèle restera figé. Avec lui, il progresse à chaque photo."
        )
        share_text.setFont(QFont(FONT_MAIN, 8))
        share_text.setWordWrap(True)
        self._share_text = share_text
        lay.addWidget(share_text)
        lay.addSpacing(16)

        sep3 = _make_sep()
        lay.addWidget(sep3)
        lay.addSpacing(16)
        self._sep3 = sep3

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._refuse_btn = QPushButton("Non merci")
        self._refuse_btn.setFont(QFont(FONT_MAIN, 8))
        self._refuse_btn.setFixedHeight(34)
        self._refuse_btn.setCursor(Qt.PointingHandCursor)
        self._refuse_btn.clicked.connect(self._on_refuse)

        self._accept_btn = QPushButton("Participer et utiliser le diagnostic")
        self._accept_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._accept_btn.setFixedHeight(34)
        self._accept_btn.setCursor(Qt.PointingHandCursor)
        self._accept_btn.clicked.connect(self._on_accept)

        btn_row.addWidget(self._refuse_btn)
        btn_row.addWidget(self._accept_btn, 2)
        lay.addLayout(btn_row)
        lay.addSpacing(6)

        note = QLabel(_("diag.consent_revoke_note"))
        note.setFont(QFont(FONT_MAIN, 7))
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        self._note_lbl = note
        lay.addWidget(note)

    def _on_accept(self):
        from core.prefs import PREFS
        PREFS.set("defect_consent", True)
        PREFS.set("defect_contribute", True)
        self.accept()

    def _on_refuse(self):
        from core.prefs import PREFS
        PREFS.set("defect_consent", False)
        self.reject()

    def _apply_theme(self):
        pal = _T.palette()
        self._card.setStyleSheet(f"""
            QWidget#consent_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['ACCENT']};
                border-radius: 8px;
            }}
        """)
        self._icon_lbl.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        self._title_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 2px;"
        )
        self._subtitle_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._how_title.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._share_title.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
        self._share_text.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")
        self._note_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")

        for sep in (self._sep1, self._sep2, self._sep3):
            sep.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")

        for num_lbl, text_lbl in self._step_widgets:
            num_lbl.setStyleSheet(
                f"background: {pal['BG_ELEVATED']}; color: {pal['ACCENT']}; "
                f"border: 1px solid {pal['ACCENT']}; border-radius: 10px;"
            )
            text_lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")

        self._accept_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['TELE_GREEN']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 4px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: #00D080; }}
        """)
        self._refuse_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {pal['ERROR_RED']};
                color: {pal['ERROR_RED']};
            }}
        """)


# ── Worker thread ──────────────────────────────────────────────────────────────

class _AnalysisWorker(QThread):
    result_ready = Signal(object, str)   # DiagnosticResult, image_hash
    error        = Signal(str)
    dl_progress  = Signal(int)           # % de téléchargement du modèle
    dl_started   = Signal()              # un téléchargement de modèle commence

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self._path = image_path

    def run(self):
        try:
            from core.defect_detection.detector import DefectDetector
            from core.defect_detection.dataset_manager import DatasetManager
            from core.defect_detection.model_manager import ModelManager

            # Télécharge / met à jour le modèle si nécessaire (1er lancement ou
            # nouvelle version publiée). Bloquant ici — on est déjà dans un thread.
            mgr = ModelManager()
            self._dl_announced = False

            def _on_dl(done: int, total: int):
                if not self._dl_announced:
                    self._dl_announced = True
                    self.dl_started.emit()
                if total > 0:
                    self.dl_progress.emit(int(done * 100 / total))

            mgr.ensure_latest_sync(on_progress=_on_dl)

            det = DefectDetector(mgr)
            if not det.load():
                self.error.emit(_("diag.model_unavailable"))
                return

            result = det.analyze(self._path)

            # Enregistre la prédiction pour l'apprentissage local
            img_hash = ""
            try:
                dm = DatasetManager()
                img_hash = dm.record_prediction(
                    self._path,
                    result.defect.value,
                    result.confidence,
                    result.embedding,
                )
            except Exception:
                pass

            self.result_ready.emit(result, img_hash)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Zone drop photo ────────────────────────────────────────────────────────────

class _PhotoDrop(QWidget):
    """Zone drag-and-drop pour une image (.jpg / .png / .webp / .bmp)."""

    photo_selected = Signal(Path)

    _ACCEPTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hovered = False
        self._pixmap: QPixmap | None = None
        self._filename = ""

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, ev: QDragEnterEvent):
        if ev.mimeData().hasUrls():
            for url in ev.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in self._ACCEPTED:
                    ev.acceptProposedAction()
                    self._hovered = True
                    self.update()
                    return
        ev.ignore()

    def dragLeaveEvent(self, _ev):
        self._hovered = False
        self.update()

    def dropEvent(self, ev: QDropEvent):
        self._hovered = False
        for url in ev.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() in self._ACCEPTED:
                self._load(p)
                ev.acceptProposedAction()
                return
        ev.ignore()

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "Sélectionner une photo",
                str(Path.home()),
                "Images (*.jpg *.jpeg *.png *.webp *.bmp)",
            )
            if path:
                self._load(Path(path))

    def _load(self, path: Path):
        pix = QPixmap(str(path))
        if not pix.isNull():
            self._pixmap = pix.scaled(
                QSize(200, 130), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._filename = path.name
            self.update()
            self.photo_selected.emit(path)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        pal = _T.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        border_color = QColor(pal["ACCENT"] if self._hovered else pal["INACTIVE"])
        bg_color     = QColor(pal["BG_SURFACE"])
        bg_color.setAlpha(200)

        p.setBrush(bg_color)
        pen = QPen(border_color, 1, Qt.DashLine if not self._pixmap else Qt.SolidLine)
        p.setPen(pen)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)

        if self._pixmap:
            x = (self.width()  - self._pixmap.width())  // 2
            y = (self.height() - self._pixmap.height()) // 2
            p.drawPixmap(x, y, self._pixmap)
        else:
            icon_color = QColor(pal["ACCENT"] if self._hovered else pal["TEXT_LABEL"])
            p.setPen(icon_color)
            p.setFont(QFont(FONT_MAIN, 22))
            p.drawText(self.rect().adjusted(0, -20, 0, 0),
                       Qt.AlignCenter, "⬡")
            p.setFont(QFont(FONT_MAIN, 8))
            p.setPen(QColor(pal["TEXT_SECONDARY"]))
            p.drawText(self.rect().adjusted(0, 30, 0, 0),
                       Qt.AlignCenter, "Glissez une photo ici  ou  cliquez pour parcourir")
            p.setFont(QFont(FONT_MONO, 8))
            p.setPen(QColor(pal["TEXT_LABEL"]))
            p.drawText(self.rect().adjusted(0, 64, 0, 0),
                       Qt.AlignCenter, "JPG  ·  PNG  ·  WEBP  ·  BMP")

    def reset(self):
        self._pixmap = None
        self._filename = ""
        self.update()


# ── Séparateur ─────────────────────────────────────────────────────────────────

def _make_sep(parent=None) -> QFrame:
    sep = QFrame(parent)
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    return sep


# ── Dialog principal ───────────────────────────────────────────────────────────

class DefectDiagnosticDialog(QDialog):
    """Fenêtre de diagnostic défaut d'impression par photo.

    Signaux :
        corrections_ready(object) — émet un DiagnosticResult validé pour
                                    application au PrintConfig courant.
    """

    corrections_ready = Signal(object)   # DiagnosticResult
    pro_state_changed = Signal()         # émis quand neoSlice Pro vient d'être activé

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("diag_dialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        # PAS de WA_TranslucentBackground ici : ce dialog se REDIMENSIONNE après
        # affichage (résultats variables). Une fenêtre translucide ("layered
        # window" Windows) redimensionnée garde son ancien rendu à l'écran →
        # les boutons visibles ne correspondent plus à leur vraie position
        # (zone cliquable décalée vers le haut). Fenêtre opaque = rendu toujours
        # synchronisé avec la géométrie réelle.
        self._drag_pos: QPoint | None = None
        self._worker: _AnalysisWorker | None = None
        self._result = None          # DiagnosticResult courant
        self._image_path: Path | None = None
        self._image_hash = ""
        self._manual_mode = False    # True quand le défaut est choisi à la main

        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        # Dialog réutilisé (singleton) : on NE désenregistre PAS le thème pour
        # qu'il continue de se mettre à jour, et on conserve l'image + le résultat.
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)
        super().closeEvent(event)

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _ev):
        self._drag_pos = None

    # ── Construction UI ───────────────────────────────────────────────────────
    # Structure identique à SettingsDialog : tout en enfants directs de la card,
    # pas de QWidget containers intermédiaires (cause du fond gris Windows).

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("diag_card")
        self._card.setFixedWidth(460)   # ancre la largeur (SetFixedSize gère la hauteur)
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(20, 14, 20, 20)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # ── Titre ─────────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 12)
        self._title_lbl = QLabel("DIAGNOSTIC IA")
        self._title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._close_btn = QPushButton("X")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.close)
        title_row.addWidget(self._title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._close_btn)
        lay.addLayout(title_row)

        self._sep_top = _make_sep()
        lay.addWidget(self._sep_top)
        lay.addSpacing(14)

        # ── Sélecteur de mode : photo  /  je connais le problème ──────────────
        from core.i18n import _ as _t
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        self._mode_photo_btn  = QPushButton(_t("diag.mode_photo"))
        self._mode_manual_btn = QPushButton(_t("diag.mode_manual"))
        for b in (self._mode_photo_btn, self._mode_manual_btn):
            b.setCheckable(True)
            b.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
            b.setFixedHeight(30)
            b.setCursor(Qt.PointingHandCursor)
        self._mode_photo_btn.setChecked(True)
        self._mode_photo_btn.clicked.connect(lambda: self._set_mode(False))
        self._mode_manual_btn.clicked.connect(lambda: self._set_mode(True))
        mode_row.addWidget(self._mode_photo_btn, 1)
        mode_row.addWidget(self._mode_manual_btn, 1)
        lay.addLayout(mode_row)
        lay.addSpacing(12)

        # ── Panneau MODE PHOTO ────────────────────────────────────────────────
        self._photo_panel = QWidget()
        self._photo_panel.setObjectName("diag_photo_panel")
        play = QVBoxLayout(self._photo_panel)
        play.setContentsMargins(0, 0, 0, 0)
        play.setSpacing(0)
        lay.addWidget(self._photo_panel)

        # Drop zone
        self._drop = _PhotoDrop()
        self._drop.photo_selected.connect(self._on_photo_selected)
        play.addWidget(self._drop)
        play.addSpacing(6)

        # Conseils de prise de vue (meilleure précision)
        self._tips_lbl = QLabel(
            "💡 Pour une analyse fiable : cadrez la zone du défaut, bonne lumière, "
            "fond neutre, photo nette."
        )
        self._tips_lbl.setFont(QFont(FONT_MAIN, 9))
        self._tips_lbl.setWordWrap(True)
        play.addWidget(self._tips_lbl)
        play.addSpacing(10)

        # Boutons analyser + nouvelle photo
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self._analyze_btn = QPushButton("ANALYSER LA PHOTO")
        self._analyze_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._analyze_btn.setFixedHeight(32)
        self._analyze_btn.setCursor(Qt.PointingHandCursor)
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.clicked.connect(self._start_analysis)
        action_row.addWidget(self._analyze_btn, 1)

        self._reset_btn = QPushButton("Nouvelle photo")
        self._reset_btn.setFont(QFont(FONT_MAIN, 8))
        self._reset_btn.setFixedHeight(32)
        self._reset_btn.setCursor(Qt.PointingHandCursor)
        self._reset_btn.clicked.connect(self._reset_photo)
        self._reset_btn.hide()   # visible seulement quand une photo est chargée
        action_row.addWidget(self._reset_btn)

        play.addLayout(action_row)
        play.addSpacing(4)

        # Barre de progression
        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)
        self._progress.hide()
        play.addWidget(self._progress)

        # ── Panneau MODE MANUEL ───────────────────────────────────────────────
        # Choix direct du défaut → mêmes corrections, sans photo ni analyse IA.
        self._manual_panel = QWidget()
        self._manual_panel.setObjectName("diag_manual_panel")
        mlay = QVBoxLayout(self._manual_panel)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(0)
        lay.addWidget(self._manual_panel)

        self._manual_pick_lbl = QLabel(_t("diag.manual_pick"))
        self._manual_pick_lbl.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        mlay.addWidget(self._manual_pick_lbl)
        mlay.addSpacing(8)

        from core.defect_detection.defect_classes import (
            defect_label as _dl, DefectClass as _DC,
        )
        self._manual_combo = QComboBox()
        self._manual_combo.setFont(QFont(FONT_MAIN, 9))
        for cls in _DC:
            if cls == _DC.GOOD:
                continue   # « Bonne impression » n'a aucune correction à proposer
            self._manual_combo.addItem(_dl(cls), cls.value)
        self._manual_combo.currentIndexChanged.connect(self._on_manual_pick)
        mlay.addWidget(self._manual_combo)
        mlay.addSpacing(8)

        self._manual_desc_lbl = QLabel()
        self._manual_desc_lbl.setFont(QFont(FONT_MAIN, 8))
        self._manual_desc_lbl.setWordWrap(True)
        mlay.addWidget(self._manual_desc_lbl)
        mlay.addSpacing(10)

        self._manual_btn = QPushButton(_t("diag.manual_show"))
        self._manual_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._manual_btn.setFixedHeight(32)
        self._manual_btn.setCursor(Qt.PointingHandCursor)
        self._manual_btn.clicked.connect(self._show_manual)
        mlay.addWidget(self._manual_btn)

        self._manual_panel.hide()   # mode photo par défaut
        # NB : la description du mode manuel est remplie au 1er passage en mode
        # manuel (_set_mode) — _fix_wrap_heights a besoin que toute l'UI existe.

        # ── Compteur d'essais gratuits — PARTAGÉ photo + manuel (masqué si Pro) ──
        # Hors des panneaux pour rester visible quel que soit le mode actif.
        self._trial_lbl = QLabel("")
        self._trial_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._trial_lbl.setAlignment(Qt.AlignCenter)
        lay.addSpacing(8)
        lay.addWidget(self._trial_lbl)
        self.refresh_trial_label()

        # ── Résultats — TOUT dans un conteneur unique masquable d'un bloc ────
        # Quand aucune analyse n'a tourné, le conteneur est masqué et la fenêtre
        # retrouve sa taille d'origine (pas d'espace vide résiduel).
        self._result_box = QWidget()
        self._result_box.setObjectName("diag_result_box")
        rlay = QVBoxLayout(self._result_box)
        rlay.setContentsMargins(0, 6, 0, 0)
        rlay.setSpacing(0)
        lay.addWidget(self._result_box)

        self._sep_result = _make_sep()
        rlay.addWidget(self._sep_result)
        rlay.addSpacing(10)

        # ── Section RÉSULTAT D'ANALYSE ────────────────────────────────────────
        self._section_result_lbl = QLabel("RÉSULTAT D'ANALYSE")
        self._section_result_lbl.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        rlay.addWidget(self._section_result_lbl)
        rlay.addSpacing(8)

        # Badge défaut (dot + nom + confiance)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(10)
        self._badge_dot = QLabel("●")
        self._badge_dot.setFont(QFont(FONT_MAIN, 14))
        self._badge_name = QLabel()
        self._badge_name.setFont(QFont(FONT_MAIN, 10, QFont.Bold))
        self._badge_conf = QLabel()
        self._badge_conf.setFont(QFont(FONT_MONO, 8))
        badge_row.addWidget(self._badge_dot)
        badge_row.addWidget(self._badge_name)
        badge_row.addStretch()
        badge_row.addWidget(self._badge_conf)
        rlay.addLayout(badge_row)
        rlay.addSpacing(6)

        # Description
        self._desc_lbl = QLabel()
        self._desc_lbl.setFont(QFont(FONT_MAIN, 8))
        self._desc_lbl.setWordWrap(True)
        rlay.addWidget(self._desc_lbl)
        rlay.addSpacing(12)

        # ── Section CORRECTIONS RECOMMANDÉES (sous-conteneur) ────────────────
        self._corrections_box = QWidget()
        self._corrections_box.setObjectName("diag_corrections_box")
        clay = QVBoxLayout(self._corrections_box)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)
        rlay.addWidget(self._corrections_box)

        self._sep_corrections = _make_sep()
        clay.addWidget(self._sep_corrections)
        clay.addSpacing(10)

        self._corrections_header = QLabel("CORRECTIONS RECOMMANDÉES")
        self._corrections_header.setFont(QFont(FONT_MAIN, 7, QFont.Bold))
        clay.addWidget(self._corrections_header)
        clay.addSpacing(8)

        self._corrections_lay = QVBoxLayout()
        self._corrections_lay.setContentsMargins(0, 0, 0, 0)
        self._corrections_lay.setSpacing(3)
        clay.addLayout(self._corrections_lay)
        clay.addSpacing(10)

        self._sep_result2 = _make_sep()
        clay.addWidget(self._sep_result2)
        clay.addSpacing(8)

        # Bouton appliquer (= confirmer les réglages pour la barre du bas)
        self._apply_btn = QPushButton("UTILISER CES CORRECTIONS")
        self._apply_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._apply_btn.setFixedHeight(30)
        self._apply_btn.setCursor(Qt.PointingHandCursor)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_corrections)
        clay.addWidget(self._apply_btn)

        self._apply_hint = QLabel(
            "Facultatif : si vous avez généré une configuration, le bouton "
            "« Appliquer corrections » apparaîtra en bas, à gauche de l'export. "
            "Sinon, vous pouvez simplement fermer cette fenêtre."
        )
        self._apply_hint.setFont(QFont(FONT_MAIN, 9))
        self._apply_hint.setWordWrap(True)
        clay.addWidget(self._apply_hint)

        # Conseil (hint général) — sous le badge, hors corrections
        self._hint_lbl = QLabel()
        self._hint_lbl.setFont(QFont(FONT_MAIN, 9))
        self._hint_lbl.setWordWrap(True)
        rlay.addWidget(self._hint_lbl)
        rlay.addSpacing(10)

        # ── Feedback (toujours dans le conteneur résultat) ───────────────────
        self._sep_feedback = _make_sep()
        rlay.addWidget(self._sep_feedback)
        rlay.addSpacing(8)

        feedback_row = QHBoxLayout()
        feedback_row.setSpacing(6)
        self._feedback_lbl = QLabel("Ce résultat est-il correct ?")
        self._feedback_lbl.setFont(QFont(FONT_MAIN, 9))
        self._confirm_btn = QPushButton("Oui")
        self._confirm_btn.setFixedHeight(28)
        self._confirm_btn.setFont(QFont(FONT_MAIN, 9))
        self._confirm_btn.setCursor(Qt.PointingHandCursor)
        self._confirm_btn.clicked.connect(self._confirm_prediction)
        self._correct_btn = QPushButton("Non, corriger")
        self._correct_btn.setFixedHeight(28)
        self._correct_btn.setFont(QFont(FONT_MAIN, 9))
        self._correct_btn.setCursor(Qt.PointingHandCursor)
        self._correct_btn.clicked.connect(self._show_correction_picker)
        feedback_row.addWidget(self._feedback_lbl)
        feedback_row.addStretch()
        feedback_row.addWidget(self._confirm_btn)
        feedback_row.addWidget(self._correct_btn)
        rlay.addLayout(feedback_row)

        # Picker correction (sous-conteneur masquable)
        self._picker_box = QWidget()
        self._picker_box.setObjectName("diag_picker_box")
        picker_row = QHBoxLayout(self._picker_box)
        picker_row.setContentsMargins(0, 6, 0, 0)
        picker_row.setSpacing(6)
        self._picker_lbl = QLabel("Défaut réel :")
        self._picker_lbl.setFont(QFont(FONT_MAIN, 8))
        self._correction_combo = QComboBox()
        self._correction_combo.setFont(QFont(FONT_MAIN, 8))
        from core.defect_detection.defect_classes import defect_label, DefectClass
        for cls in DefectClass:
            self._correction_combo.addItem(defect_label(cls), cls.value)
        self._correction_ok_btn = QPushButton("Valider")
        self._correction_ok_btn.setFixedHeight(24)
        self._correction_ok_btn.setFont(QFont(FONT_MAIN, 8))
        self._correction_ok_btn.setCursor(Qt.PointingHandCursor)
        self._correction_ok_btn.clicked.connect(self._save_correction)
        picker_row.addWidget(self._picker_lbl)
        picker_row.addWidget(self._correction_combo, 1)
        picker_row.addWidget(self._correction_ok_btn)
        rlay.addWidget(self._picker_box)

        self._result_box.hide()
        self._picker_box.hide()

    def _set_result_visible(self, visible: bool):
        self._result_box.setVisible(visible)
        if not visible:
            self._picker_box.hide()

    def _set_picker_visible(self, visible: bool):
        self._picker_box.setVisible(visible)

    def _refit(self):
        """Recalcule la taille pour coller au contenu.

        DOUBLE PASSE volontaire : les QLabel word-wrap (description) ne calculent
        leur vraie hauteur qu'une fois leur largeur connue. Sans 2e passe, Qt
        sous-estime la hauteur → le texte déborde sur les boutons et leur zone
        cliquable se retrouve décalée vers le haut. Ensuite on garde la fenêtre
        entièrement visible à l'écran (boutons du bas atteignables)."""
        self._fix_wrap_heights()   # hauteurs word-wrap correctes AVANT de mesurer
        lay = self._card.layout()
        lay.activate()
        self.adjustSize()
        lay.activate()          # 2e passe : hauteurs word-wrap correctes
        self.adjustSize()
        # NB : on ne déplace PLUS la fenêtre ici. Déplacer une fenêtre translucide
        # déjà affichée laisse Windows désynchronisé (géométrie ≠ rendu) → la zone
        # cliquable des boutons se décalait. Le placement à l'écran est géré une
        # seule fois à l'ouverture (main_window._open_diagnostic).

    def _clear_corrections(self):
        """Supprime toutes les lignes de correction. Chaque ligne est un
        sous-layout (QHBoxLayout) contenant des QLabel : il faut supprimer
        récursivement les widgets, sinon ils persistent et se superposent."""
        while self._corrections_lay.count():
            item = self._corrections_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()               # retire de l'affichage immédiatement
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    sitem = sub.takeAt(0)
                    sw = sitem.widget()
                    if sw is not None:
                        sw.hide()      # idem : pas de superposition en attendant la suppression
                        sw.deleteLater()
                sub.deleteLater()
        self._corr_dots = []
        self._corr_lbls = []

    def _recolor_corrections(self):
        """Recolore les lignes de correction selon le thème courant
        (elles sont créées dynamiquement → à rafraîchir au switch de thème)."""
        pal = _T.palette()
        for dot in getattr(self, "_corr_dots", []):
            dot.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")
        for lbl in getattr(self, "_corr_lbls", []):
            lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")

    # ── Logique ───────────────────────────────────────────────────────────────

    def _on_photo_selected(self, path: Path):
        self._image_path = path
        self._set_result_visible(False)
        self._result = None
        self._analyze_btn.setEnabled(True)
        self._reset_btn.show()
        QTimer.singleShot(0, self._refit)

    def _reset_photo(self):
        """Efface la photo et le résultat pour en analyser une nouvelle."""
        self._image_path = None
        self._result = None
        self._image_hash = ""
        self._drop.reset()
        self._set_result_visible(False)
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.setText("ANALYSER LA PHOTO")
        self._reset_btn.hide()
        QTimer.singleShot(0, self._refit)

    def _set_mode(self, manual: bool):
        """Bascule entre mode photo et mode manuel (choix direct du défaut)."""
        self._manual_mode = manual
        self._mode_photo_btn.setChecked(not manual)
        self._mode_manual_btn.setChecked(manual)
        self._photo_panel.setVisible(not manual)
        self._manual_panel.setVisible(manual)
        # Changer de mode efface le résultat affiché (on repart propre)
        self._set_result_visible(False)
        self._result = None
        if manual:
            self._on_manual_pick()
        self._apply_theme()                 # boutons toggle recolorés selon l'état
        QTimer.singleShot(0, self._refit)

    def _on_manual_pick(self):
        """Met à jour la description sous la liste déroulante du mode manuel."""
        from core.defect_detection.defect_classes import DefectClass, defect_description
        val = self._manual_combo.currentData()
        if val is None:
            return
        try:
            cls = DefectClass(val)
        except ValueError:
            return
        self._manual_desc_lbl.setText(defect_description(cls))
        self._fix_wrap_heights()

    def _show_manual(self):
        """Affiche les corrections du défaut choisi à la main (mode manuel).

        Même barrière que l'analyse photo : fonctionnalité Pro (activation requise, plus
        d'essais gratuits). On construit un DiagnosticResult synthétique depuis les mêmes
        règles de remédiation, puis _show_result."""
        from core import licensing
        if not licensing.peut_analyser():
            from ui.components.paywall_dialog import PaywallDialog
            wall = PaywallDialog(self)
            wall.exec()
            if not licensing.peut_analyser():
                self.refresh_trial_label()
                return   # toujours pas débloqué → on n'affiche rien
            self.pro_state_changed.emit()
            self.refresh_trial_label()

        from core.defect_detection.defect_classes import (
            DefectClass, DiagnosticResult, REMEDIATION_RULES,
            DEFECT_DEFAULT_SEVERITY, Severity,
        )
        from core.i18n import lang
        val = self._manual_combo.currentData()
        cls = DefectClass(val)

        rem = dict(REMEDIATION_RULES.get(cls, {}))
        # Résolution du hint selon la langue (même logique que le detector)
        hint_en = rem.pop("_hint_en", None)
        if lang() == "en" and hint_en:
            rem["_hint"] = hint_en
        rem.pop("_stop_print", None)   # aucune impression en cours en mode manuel

        result = DiagnosticResult(
            defect=cls,
            confidence=1.0,
            severity=DEFECT_DEFAULT_SEVERITY.get(cls, Severity.MEDIUM),
            all_probs={},
            remediation=rem,
            message_fr="",
            uncertain=False,
        )
        self._manual_mode = True
        self._result = result
        self._image_hash = ""          # pas de photo → rien à confirmer/envoyer
        self._show_result(result)

    def refresh_trial_label(self):
        """Essais gratuits supprimés : le Diagnostic IA est une fonctionnalité Pro pure
        → aucun compteur d'essais, le libellé reste masqué."""
        self._trial_lbl.hide()

    def _start_analysis(self):
        if not self._image_path:
            return
        self._manual_mode = False   # analyse photo réelle → pas le mode manuel

        # ── Consentement au partage de photos — demandé à la 1re analyse réelle ──
        # (déplacé ici : il ne concerne QUE l'envoi de photos, donc inutile en
        # mode manuel ou tant qu'on n'a pas lancé d'analyse).
        from core.prefs import PREFS
        if not PREFS.get("defect_consent", False):
            from ui.styles.theme import apply_title_bar_theme
            consent = DiagnosticConsentDialog(self)
            apply_title_bar_theme(consent)
            consent.move(
                self.x() + (self.width() - consent.width()) // 2,
                self.y() + 40,
            )
            if consent.exec() != QDialog.Accepted:
                return   # refusé → pas d'analyse

        # ── Barrière neoSlice Pro : activation requise (plus d'essais gratuits) ──
        from core import licensing
        if not licensing.peut_analyser():
            from ui.components.paywall_dialog import PaywallDialog
            wall = PaywallDialog(self)
            wall.exec()
            if not licensing.peut_analyser():
                self.refresh_trial_label()
                return   # toujours pas débloqué → on annule l'analyse
            # Activation réussie pendant le paywall → MAJ badge Pro + compteur
            self.pro_state_changed.emit()
            self.refresh_trial_label()

        self._analyze_btn.setEnabled(False)
        self._analyze_btn.setText(_("diag.analyzing"))
        self._progress.show()
        self._set_result_visible(False)
        # Ré-analyse d'une photo déjà analysée : le résultat masqué laissait un
        # grand vide → on recalcule la taille de la fenêtre.
        QTimer.singleShot(0, self._refit)

        self._worker = _AnalysisWorker(self._image_path, self)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.dl_started.connect(self._on_dl_started)
        self._worker.dl_progress.connect(self._on_dl_progress)
        self._worker.start()

    def _on_dl_started(self):
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._analyze_btn.setText(_("diag.downloading_model", pct=0))

    def _on_dl_progress(self, pct: int):
        self._progress.setValue(pct)
        self._analyze_btn.setText(_("diag.downloading_model", pct=pct))
        if pct >= 100:
            # Téléchargement fini → on repasse en mode analyse
            self._progress.setRange(0, 0)
            self._analyze_btn.setText(_("diag.analyzing"))

    def _on_result(self, result: Any, image_hash: str):
        # Ignore un résultat tardif : analyse annulée (Nouvelle photo / fermeture)
        # ou worker périmé remplacé par une nouvelle analyse.
        if self._image_path is None or self.sender() is not self._worker:
            return
        self._progress.hide()
        self._analyze_btn.setText("ANALYSER LA PHOTO")
        self._analyze_btn.setEnabled(True)
        self._result    = result
        self._image_hash = image_hash
        self._show_result(result)

    def _on_error(self, msg: str):
        if self._image_path is None or self.sender() is not self._worker:
            return
        self._progress.hide()
        self._analyze_btn.setText("ANALYSER LA PHOTO")
        self._analyze_btn.setEnabled(bool(self._image_path))
        self._show_error(msg)

    def _fix_wrap_heights(self):
        """Fige la hauteur réelle de TOUS les QLabel word-wrap avant adjustSize.

        Tant que la largeur d'un label multi-lignes n'est pas connue, Qt
        sous-estime sa hauteur → les widgets suivants se chevauchent (le texte
        « Facultatif… » passait par-dessus le bouton vert et l'encadré du
        dessous). On force hauteur mini = heightForWidth(largeur utile).
        Surestimer légèrement est sans danger (petit espace) ; sous-estimer crée
        le chevauchement — donc on retranche le padding CSS pour les labels qui
        en ont, afin de toujours majorer la hauteur."""
        w = max(self._card.width() - 40, 200)   # largeur utile = 460 - marges (20+20)
        # (label, padding horizontal CSS total) : _hint_lbl a padding 10 px × 2
        for lbl, pad in (
            (self._tips_lbl, 0),
            (self._manual_desc_lbl, 0),
            (self._desc_lbl, 0),
            (self._apply_hint, 0),
            (self._hint_lbl, 22),
        ):
            if not lbl.isHidden():
                lbl.setMinimumHeight(lbl.heightForWidth(max(w - pad, 120)))

    def _show_result(self, result: Any):
        pal = _T.palette()
        from core.defect_detection.defect_classes import (
            Severity, defect_label, defect_description,
        )
        from core.i18n import _

        # ── Cas incertain : on n'affiche pas de diagnostic, on demande mieux ──
        if getattr(result, "uncertain", False):
            self._clear_corrections()
            self._badge_dot.setStyleSheet(f"color: {pal['AMBER']}; background: transparent;")
            self._badge_name.setText(_("diag.uncertain_title"))
            self._badge_conf.setText("")
            self._desc_lbl.setText(_("diag.uncertain_desc"))
            self._fix_wrap_heights()
            self._corrections_box.hide()
            for w in (self._sep_feedback, self._feedback_lbl,
                      self._confirm_btn, self._correct_btn):
                w.hide()
            self._set_picker_visible(False)
            self._set_result_visible(True)
            self._apply_theme()
            QTimer.singleShot(0, self._refit)
            return

        # Couleur selon sévérité
        severity_colors = {
            Severity.NONE:     pal["TELE_GREEN"],
            Severity.LOW:      pal["ACCENT"],
            Severity.MEDIUM:   pal["AMBER"],
            Severity.HIGH:     pal["ERROR_RED"],
            Severity.CRITICAL: pal["ERROR_RED"],
        }
        dot_color = severity_colors.get(result.severity, pal["ACCENT"])

        manual = getattr(self, "_manual_mode", False)
        self._badge_dot.setStyleSheet(f"color: {dot_color}; background: transparent;")
        self._badge_name.setText(defect_label(result.defect))
        # En mode manuel il n'y a pas de % de confiance → on l'indique
        self._badge_conf.setText(_("diag.manual_badge") if manual else f"{result.confidence:.0%}")
        self._desc_lbl.setText(defect_description(result.defect))
        self._fix_wrap_heights()

        # Vider les corrections (lignes = sous-layouts → suppression récursive)
        self._clear_corrections()
        # Références pour re-coloration au changement de thème
        self._corr_dots = []
        self._corr_lbls = []

        remediation = {k: v for k, v in result.remediation.items() if not k.startswith("_")}
        hint        = result.remediation.get("_hint", "")

        has_corrections = bool(remediation) and result.defect.value != "good"

        # En français on ajoute la traduction du terme entre parenthèses (les
        # noms de champs sont des termes Bambu Studio en anglais). En anglais on
        # laisse tel quel.
        from core.i18n import lang
        from core.defect_detection.defect_classes import field_translation_fr
        is_fr = lang() == "fr"

        if has_corrections:
            for key, value in remediation.items():
                row = QHBoxLayout()
                row.setSpacing(6)
                dot = QLabel("•")
                dot.setFont(QFont(FONT_MAIN, 10))
                dot.setFixedWidth(10)

                field = key.replace("delta_", "").replace("_", " ")
                if is_fr:
                    tr = field_translation_fr(field)
                    if tr:
                        field = f"{field} ({tr})"
                if key.startswith("delta_"):
                    sign = "+" if isinstance(value, (int, float)) and value > 0 else ""
                    val_str = f"{sign}{value}"
                else:
                    val_str = str(value)

                lbl = QLabel(f"{field}  →  {val_str}")
                lbl.setFont(QFont(FONT_MONO, 8))
                row.addWidget(dot)
                row.addWidget(lbl)
                row.addStretch()
                self._corrections_lay.addLayout(row)
                self._corr_dots.append(dot)
                self._corr_lbls.append(lbl)
        self._recolor_corrections()

        # Conseil
        if hint:
            self._hint_lbl.setText(hint)
            self._hint_lbl.setStyleSheet(
                f"color: {pal['TEXT_PRIMARY']}; background: {pal['BG_ELEVATED']}; "
                f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 6px 10px;"
            )
            self._hint_lbl.show()
        else:
            self._hint_lbl.hide()

        # Bouton appliquer
        self._apply_btn.setText("UTILISER CES CORRECTIONS")
        self._apply_btn.setEnabled(has_corrections)

        # Feedback « Ce résultat est-il correct ? » : seulement en mode photo.
        # En mode manuel l'utilisateur a choisi lui-même → rien à confirmer/envoyer.
        if manual:
            for w in (self._sep_feedback, self._feedback_lbl,
                      self._confirm_btn, self._correct_btn):
                w.hide()
            self._set_picker_visible(False)
        else:
            for w in (self._sep_feedback, self._feedback_lbl,
                      self._confirm_btn, self._correct_btn):
                w.show()
            self._confirm_btn.setEnabled(True)
            self._correct_btn.setEnabled(True)
            self._confirm_btn.setText("Oui")
            self._correct_btn.setText("Non, corriger")

        # Affiche le conteneur résultat ; la section corrections n'apparaît
        # que s'il y a vraiment des corrections (sinon masquée en bloc).
        self._set_picker_visible(False)
        self._corrections_box.setVisible(has_corrections)
        self._set_result_visible(True)
        self._apply_theme()
        QTimer.singleShot(0, self._refit)

    def _show_error(self, msg: str):
        pal = _T.palette()
        self._badge_dot.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        self._badge_name.setText("Erreur d'analyse")
        self._badge_name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._badge_conf.setText("")
        self._desc_lbl.setText(msg)
        self._desc_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        self._clear_corrections()
        self._apply_btn.setEnabled(False)
        self._hint_lbl.hide()
        self._corrections_box.hide()        # erreur → pas de corrections
        self._feedback_lbl.hide()
        self._confirm_btn.hide()
        self._correct_btn.hide()
        self._sep_feedback.hide()
        self._set_result_visible(True)
        QTimer.singleShot(0, self._refit)

    def _apply_corrections(self):
        if self._result:
            self.corrections_ready.emit(self._result)
            self._apply_btn.setEnabled(False)
            self._apply_btn.setText("Corrections prêtes — voir bas de l'écran")
            QTimer.singleShot(900, self.close)

    def _confirm_prediction(self):
        if self._image_hash:
            try:
                from core.defect_detection.dataset_manager import DatasetManager
                DatasetManager().confirm_prediction(self._image_hash)
            except Exception:
                pass
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setText("Enregistré")
        self._correct_btn.hide()          # résultat validé → plus besoin de corriger
        self._set_picker_visible(False)
        QTimer.singleShot(300, self._maybe_contribute)
        QTimer.singleShot(600, self._maybe_retrain)
        QTimer.singleShot(0, self._refit)

    def _show_correction_picker(self):
        visible = not self._picker_lbl.isVisible()
        self._set_picker_visible(visible)
        QTimer.singleShot(0, self._refit)

    def _save_correction(self):
        correct_class = self._correction_combo.currentData()
        if self._image_hash and correct_class:
            try:
                from core.defect_detection.dataset_manager import DatasetManager
                DatasetManager().correct_prediction(self._image_hash, correct_class)
            except Exception:
                pass
        self._set_picker_visible(False)
        self._correct_btn.setEnabled(False)
        self._correct_btn.setText("Corrigé")
        self._confirm_btn.hide()          # résultat corrigé → "Oui" inutile
        QTimer.singleShot(300, self._maybe_contribute)
        QTimer.singleShot(600, self._maybe_retrain)
        QTimer.singleShot(0, self._refit)

    def _maybe_contribute(self):
        """Contribue automatiquement si l'utilisateur a donné son accord."""
        from core.prefs import PREFS
        if not PREFS.get("defect_contribute", False):
            return
        try:
            from core.defect_detection.contribution import ContributionPipeline
            ContributionPipeline().contribute_async()
        except Exception:
            pass

    def _maybe_retrain(self):
        try:
            from core.defect_detection.adaptation import AdaptationLayer
            AdaptationLayer().retrain_if_needed()
        except Exception:
            pass

    # ── Thème ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        pal = _T.palette()

        # Fenêtre opaque (voir __init__) : on peint le fond de la fenêtre de la
        # même couleur que la card pour que les coins arrondis restent discrets.
        self.setStyleSheet(f"QDialog#diag_dialog {{ background: {pal['BG_PANEL']}; }}")

        # Card — même pattern que SettingsDialog
        self._card.setStyleSheet(f"""
            QWidget#diag_card {{
                background: {pal['BG_PANEL']};
                border: 1px solid {pal['ACCENT']};
                border-radius: 6px;
            }}
        """)

        # Titre et fermeture — style direct, comme SettingsDialog
        self._title_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent; letter-spacing: 2px;"
        )
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: none; border-radius: 3px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {pal['ERROR_RED']}; color: white; }}
        """)

        # Sélecteur de mode (segmented) — actif = accent, inactif = neutre
        seg = f"""
            QPushButton {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']};
            }}
            QPushButton:checked {{
                background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                border: 1px solid {pal['ACCENT']};
            }}
            QPushButton:hover:!checked {{ color: {pal['ACCENT']}; border-color: {pal['ACCENT']}; }}
        """
        self._mode_photo_btn.setStyleSheet(
            seg + "QPushButton { border-top-left-radius:4px; border-bottom-left-radius:4px; }"
        )
        self._mode_manual_btn.setStyleSheet(
            seg + "QPushButton { border-top-right-radius:4px; border-bottom-right-radius:4px; }"
        )

        # Panneaux photo / manuel — fond panneau (pas de gris système Windows)
        self._photo_panel.setStyleSheet(
            f"QWidget#diag_photo_panel {{ background: {pal['BG_PANEL']}; }}"
        )
        self._manual_panel.setStyleSheet(
            f"QWidget#diag_manual_panel {{ background: {pal['BG_PANEL']}; }}"
        )
        self._manual_pick_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent;"
        )
        self._manual_desc_lbl.setStyleSheet(
            f"color: {pal['TEXT_SECONDARY']}; background: transparent;"
        )

        # Conteneurs résultat — fond panneau (pas de gris système Windows)
        self._result_box.setStyleSheet(
            f"QWidget#diag_result_box {{ background: {pal['BG_PANEL']}; }}"
        )
        self._corrections_box.setStyleSheet(
            f"QWidget#diag_corrections_box {{ background: {pal['BG_PANEL']}; }}"
        )
        self._picker_box.setStyleSheet(
            f"QWidget#diag_picker_box {{ background: {pal['BG_PANEL']}; }}"
        )

        # Séparateurs
        for sep in (self._sep_top, self._sep_result, self._sep_result2,
                    self._sep_corrections, self._sep_feedback):
            sep.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")

        # En-têtes de section
        self._section_result_lbl.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 2px;"
        )
        self._corrections_header.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent; letter-spacing: 2px;"
        )

        self._drop.update()
        self._tips_lbl.setStyleSheet(f"color: {pal['TEXT_LABEL']}; background: transparent;")

        # Analyser + Voir les corrections (mode manuel) — même style accent
        accent_btn = f"""
            QPushButton {{
                background: {pal['ACCENT']}; color: {pal['EXPORT_FG']};
                border: none; border-radius: 3px; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {pal['ACCENT_BRIGHT']}; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['TEXT_LABEL']}; }}
        """
        self._analyze_btn.setStyleSheet(accent_btn)
        self._manual_btn.setStyleSheet(accent_btn)

        # Liste déroulante des défauts (mode manuel) — même style que le picker
        self._manual_combo.setStyleSheet(f"""
            QComboBox {{
                background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 4px 8px;
            }}
            QComboBox QAbstractItemView {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']};
                selection-background-color: {pal['ACCENT']};
            }}
        """)

        # Nouvelle photo (réinitialiser)
        self._reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 0 12px;
            }}
            QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}
        """)

        self._progress.setStyleSheet(f"""
            QProgressBar {{ background: {pal['BG_SURFACE']}; border: none; border-radius: 1px; }}
            QProgressBar::chunk {{ background: {pal['ACCENT']}; border-radius: 1px; }}
        """)

        # Labels résultats — tous explicitement stylés (pas de cascade)
        self._badge_dot.setStyleSheet(
            f"color: {pal['AMBER']}; background: transparent;"
        )
        self._badge_name.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent;"
        )
        self._badge_conf.setStyleSheet(
            f"color: {pal['TEXT_SECONDARY']}; background: transparent;"
        )
        self._desc_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent;"
        )
        self._corrections_header.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: transparent;"
        )
        self._recolor_corrections()
        self._hint_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: {pal['BG_ELEVATED']}; "
            f"border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 6px 10px;"
        )
        self._feedback_lbl.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent;"
        )
        self._apply_hint.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent;"
        )
        self._picker_lbl.setStyleSheet(
            f"color: {pal['TEXT_SECONDARY']}; background: transparent;"
        )

        # Appliquer
        self._apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['TELE_GREEN']}; color: {pal['EXPORT_FG']};
                border: none; border-radius: 3px; letter-spacing: 1px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #00D080; }}
            QPushButton:disabled {{ background: {pal['INACTIVE']}; color: {pal['TEXT_LABEL']}; }}
        """)

        small = f"""
            QPushButton {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 0 8px;
            }}
            QPushButton:hover {{ border-color: {pal['ACCENT']}; color: {pal['ACCENT']}; }}
            QPushButton:disabled {{ color: {pal['TEXT_LABEL']}; border-color: {pal['INACTIVE']}; }}
        """
        for btn in (self._confirm_btn, self._correct_btn, self._correction_ok_btn):
            btn.setStyleSheet(small)

        self._correction_combo.setStyleSheet(f"""
            QComboBox {{
                background: {pal['BG_INPUT']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']}; border-radius: 3px; padding: 2px 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']};
                selection-background-color: {pal['ACCENT']};
            }}
        """)

