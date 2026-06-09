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

        title = QLabel("DIAGNOSTIC PHOTO IA")
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

        note = QLabel("Vous pouvez révoquer votre accord à tout moment dans les paramètres.")
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

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self._path = image_path

    def run(self):
        try:
            from core.defect_detection.detector import DefectDetector
            from core.defect_detection.dataset_manager import DatasetManager

            det = DefectDetector()
            if not det.load():
                self.error.emit("Modèle non disponible — téléchargement requis.")
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(460)
        self._drag_pos: QPoint | None = None
        self._worker: _AnalysisWorker | None = None
        self._result = None          # DiagnosticResult courant
        self._image_path: Path | None = None
        self._image_hash = ""

        self._setup_ui()
        self._apply_theme()
        _T.register(self._apply_theme)

    def closeEvent(self, event):
        _T.unregister(self._apply_theme)
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

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("diag_card")
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(20, 14, 20, 20)
        lay.setSpacing(0)
        root.addWidget(self._card)

        # ── Titre ─────────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 12)

        self._title_lbl = QLabel("DIAGNOSTIC PHOTO")
        self._title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Bold))
        self._title_lbl.setAutoFillBackground(False)

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

        # ── Drop zone ─────────────────────────────────────────────────────────
        self._drop = _PhotoDrop()
        self._drop.photo_selected.connect(self._on_photo_selected)
        lay.addWidget(self._drop)
        lay.addSpacing(12)

        # ── Bouton analyser ───────────────────────────────────────────────────
        self._analyze_btn = QPushButton("ANALYSER LA PHOTO")
        self._analyze_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._analyze_btn.setFixedHeight(32)
        self._analyze_btn.setCursor(Qt.PointingHandCursor)
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.clicked.connect(self._start_analysis)
        lay.addWidget(self._analyze_btn)
        lay.addSpacing(4)

        # ── Barre de progression ──────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.hide()
        lay.addWidget(self._progress)

        # ── Zone résultats (cachée par défaut) ────────────────────────────────
        self._result_widget = QWidget()
        self._result_widget.setAutoFillBackground(False)
        self._result_widget.setStyleSheet("background: transparent;")
        result_lay = QVBoxLayout(self._result_widget)
        result_lay.setContentsMargins(0, 14, 0, 0)
        result_lay.setSpacing(10)

        # Séparateur
        result_lay.addWidget(_make_sep())
        result_lay.addSpacing(4)

        # Bandeau défaut
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
        result_lay.addLayout(badge_row)

        # Description
        self._desc_lbl = QLabel()
        self._desc_lbl.setFont(QFont(FONT_MAIN, 8))
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setAutoFillBackground(False)
        result_lay.addWidget(self._desc_lbl)

        # Corrections
        self._corrections_widget = QWidget()
        self._corrections_widget.setAutoFillBackground(False)
        self._corrections_widget.setStyleSheet("background: transparent;")
        self._corrections_lay = QVBoxLayout(self._corrections_widget)
        self._corrections_lay.setContentsMargins(0, 6, 0, 0)
        self._corrections_lay.setSpacing(3)
        result_lay.addWidget(self._corrections_widget)

        # Conseil (hint)
        self._hint_lbl = QLabel()
        self._hint_lbl.setFont(QFont(FONT_MAIN, 9))
        self._hint_lbl.setWordWrap(True)
        self._hint_lbl.hide()
        result_lay.addWidget(self._hint_lbl)

        result_lay.addWidget(_make_sep())
        result_lay.addSpacing(4)

        # Bouton appliquer
        self._apply_btn = QPushButton("APPLIQUER LES CORRECTIONS")
        self._apply_btn.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._apply_btn.setFixedHeight(30)
        self._apply_btn.setCursor(Qt.PointingHandCursor)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_corrections)
        result_lay.addWidget(self._apply_btn)

        # Feedback confirmation
        feedback_row = QHBoxLayout()
        feedback_row.setSpacing(6)
        feedback_lbl = QLabel("Ce résultat est-il correct ?")
        feedback_lbl.setFont(QFont(FONT_MAIN, 9))
        self._feedback_lbl = feedback_lbl

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

        feedback_row.addWidget(feedback_lbl)
        feedback_row.addStretch()
        feedback_row.addWidget(self._confirm_btn)
        feedback_row.addWidget(self._correct_btn)
        result_lay.addLayout(feedback_row)

        # Picker correction (caché par défaut)
        self._correction_picker = QWidget()
        self._correction_picker.setAutoFillBackground(False)
        self._correction_picker.setStyleSheet("background: transparent;")
        picker_row = QHBoxLayout(self._correction_picker)
        picker_row.setContentsMargins(0, 0, 0, 0)
        picker_row.setSpacing(6)
        self._correction_combo = QComboBox()
        self._correction_combo.setFont(QFont(FONT_MAIN, 7))
        from core.defect_detection.defect_classes import DEFECT_LABELS_FR, DefectClass
        for cls in DefectClass:
            self._correction_combo.addItem(DEFECT_LABELS_FR[cls], cls.value)
        self._correction_ok_btn = QPushButton("Valider")
        self._correction_ok_btn.setFixedHeight(22)
        self._correction_ok_btn.setFont(QFont(FONT_MAIN, 7))
        self._correction_ok_btn.setCursor(Qt.PointingHandCursor)
        self._correction_ok_btn.clicked.connect(self._save_correction)
        _picker_lbl = QLabel("Défaut réel :")
        _picker_lbl.setAutoFillBackground(False)
        picker_row.addWidget(_picker_lbl)
        picker_row.addWidget(self._correction_combo, 1)
        picker_row.addWidget(self._correction_ok_btn)
        self._correction_picker.hide()
        result_lay.addWidget(self._correction_picker)

        self._result_widget.hide()
        lay.addWidget(self._result_widget)

    # ── Logique ───────────────────────────────────────────────────────────────

    def _on_photo_selected(self, path: Path):
        self._image_path = path
        self._result_widget.hide()
        self._result = None
        self._analyze_btn.setEnabled(True)
        self.adjustSize()

    def _start_analysis(self):
        if not self._image_path:
            return
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.setText("Analyse en cours...")
        self._progress.show()
        self._result_widget.hide()

        self._worker = _AnalysisWorker(self._image_path, self)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: Any, image_hash: str):
        self._progress.hide()
        self._analyze_btn.setText("ANALYSER LA PHOTO")
        self._analyze_btn.setEnabled(True)
        self._result    = result
        self._image_hash = image_hash
        self._show_result(result)

    def _on_error(self, msg: str):
        self._progress.hide()
        self._analyze_btn.setText("ANALYSER LA PHOTO")
        self._analyze_btn.setEnabled(bool(self._image_path))
        self._show_error(msg)

    def _show_result(self, result: Any):
        pal = _T.palette()
        from core.defect_detection.defect_classes import (
            Severity, DEFECT_LABELS_FR, DEFECT_DESCRIPTIONS_FR,
        )

        # Couleur selon sévérité
        severity_colors = {
            Severity.NONE:     pal["TELE_GREEN"],
            Severity.LOW:      pal["ACCENT"],
            Severity.MEDIUM:   pal["AMBER"],
            Severity.HIGH:     pal["ERROR_RED"],
            Severity.CRITICAL: pal["ERROR_RED"],
        }
        dot_color = severity_colors.get(result.severity, pal["ACCENT"])

        self._badge_dot.setStyleSheet(f"color: {dot_color}; background: transparent;")
        self._badge_name.setText(DEFECT_LABELS_FR.get(result.defect, result.defect.value))
        self._badge_name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._badge_conf.setText(f"{result.confidence:.0%}")
        self._badge_conf.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")

        desc = DEFECT_DESCRIPTIONS_FR.get(result.defect, "")
        self._desc_lbl.setText(desc)
        self._desc_lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")

        # Vider les corrections
        while self._corrections_lay.count():
            item = self._corrections_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        remediation = {k: v for k, v in result.remediation.items() if not k.startswith("_")}
        hint        = result.remediation.get("_hint", "")

        has_corrections = bool(remediation) and result.defect.value != "good"

        if has_corrections:
            header = QLabel("Corrections recommandées :")
            header.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
            header.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
            self._corrections_lay.addWidget(header)

            for key, value in remediation.items():
                row = QHBoxLayout()
                row.setSpacing(6)
                dot = QLabel("•")
                dot.setFont(QFont(FONT_MAIN, 10))
                dot.setFixedWidth(10)
                dot.setStyleSheet(f"color: {pal['TELE_GREEN']}; background: transparent;")

                field = key.replace("delta_", "").replace("_", " ")
                if key.startswith("delta_"):
                    sign = "+" if isinstance(value, (int, float)) and value > 0 else ""
                    val_str = f"{sign}{value}"
                else:
                    val_str = str(value)

                lbl = QLabel(f"{field}  →  {val_str}")
                lbl.setFont(QFont(FONT_MONO, 8))
                lbl.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
                row.addWidget(dot)
                row.addWidget(lbl)
                row.addStretch()
                wrapper = QWidget()
                wrapper.setStyleSheet(f"background: {pal['BG_PANEL']};")
                wrapper.setLayout(row)
                self._corrections_lay.addWidget(wrapper)

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
        self._apply_btn.setText("APPLIQUER LES CORRECTIONS")
        self._apply_btn.setEnabled(has_corrections)

        # Feedback
        self._correction_picker.hide()
        self._result_widget.show()
        self._apply_theme()
        self.adjustSize()

    def _show_error(self, msg: str):
        pal = _T.palette()
        self._badge_dot.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        self._badge_name.setText("Erreur d'analyse")
        self._badge_name.setStyleSheet(f"color: {pal['TEXT_PRIMARY']}; background: transparent;")
        self._badge_conf.setText("")
        self._desc_lbl.setText(msg)
        self._desc_lbl.setStyleSheet(f"color: {pal['ERROR_RED']}; background: transparent;")
        while self._corrections_lay.count():
            item = self._corrections_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._apply_btn.setEnabled(False)
        self._hint_lbl.hide()
        self._result_widget.show()
        self.adjustSize()

    def _apply_corrections(self):
        if self._result:
            self.corrections_ready.emit(self._result)
            self._apply_btn.setEnabled(False)
            self._apply_btn.setText("Corrections appliquées")

    def _confirm_prediction(self):
        if self._image_hash:
            try:
                from core.defect_detection.dataset_manager import DatasetManager
                DatasetManager().confirm_prediction(self._image_hash)
            except Exception:
                pass
        self._confirm_btn.setEnabled(False)
        self._correct_btn.setEnabled(False)
        self._confirm_btn.setText("Enregistré")
        QTimer.singleShot(300, self._maybe_contribute)
        QTimer.singleShot(600, self._maybe_retrain)

    def _show_correction_picker(self):
        self._correction_picker.setVisible(not self._correction_picker.isVisible())
        self.adjustSize()

    def _save_correction(self):
        correct_class = self._correction_combo.currentData()
        if self._image_hash and correct_class:
            try:
                from core.defect_detection.dataset_manager import DatasetManager
                DatasetManager().correct_prediction(self._image_hash, correct_class)
            except Exception:
                pass
        self._correction_picker.hide()
        self._correct_btn.setEnabled(False)
        self._correct_btn.setText("Corrigé")
        self._confirm_btn.setEnabled(False)
        QTimer.singleShot(300, self._maybe_contribute)
        QTimer.singleShot(600, self._maybe_retrain)

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

        bg = pal['BG_PANEL']

        self._card.setStyleSheet(f"""
            QWidget#diag_card {{
                background: {bg};
                border: 1px solid {pal['ACCENT']};
                border-radius: 6px;
            }}
        """)

        # Tous les containers QWidget reçoivent le même fond que la card
        # (CSS transparent ne fonctionne pas sur Windows avec des layouts imbriqués)
        for w in (self._result_widget, self._corrections_widget, self._correction_picker):
            w.setStyleSheet(f"background: {bg};")

        self._title_lbl.setStyleSheet(
            f"color: {pal['TEXT_PRIMARY']}; background: {bg}; letter-spacing: 2px;"
        )

        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {pal['TEXT_SECONDARY']};
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {pal['ERROR_RED']};
                color: white;
            }}
        """)

        for sep in self.findChildren(QFrame):
            sep.setStyleSheet(f"background: {pal['INACTIVE']}; border: none;")

        self._drop.update()

        # Bouton analyser
        self._analyze_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['ACCENT']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 3px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {pal['ACCENT_BRIGHT']};
            }}
            QPushButton:disabled {{
                background: {pal['INACTIVE']};
                color: {pal['TEXT_LABEL']};
            }}
        """)

        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {pal['BG_SURFACE']};
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background: {pal['ACCENT']};
                border-radius: 1px;
            }}
        """)

        # Bouton appliquer
        self._apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pal['TELE_GREEN']};
                color: {pal['EXPORT_FG']};
                border: none;
                border-radius: 3px;
                letter-spacing: 1px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background: #00D080;
            }}
            QPushButton:disabled {{
                background: {pal['INACTIVE']};
                color: {pal['TEXT_LABEL']};
            }}
        """)

        small_btn_style = f"""
            QPushButton {{
                background: {pal['BG_ELEVATED']};
                color: {pal['TEXT_SECONDARY']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 3px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                border-color: {pal['ACCENT']};
                color: {pal['ACCENT']};
            }}
            QPushButton:disabled {{
                color: {pal['TEXT_LABEL']};
                border-color: {pal['INACTIVE']};
            }}
        """
        for btn in (self._confirm_btn, self._correct_btn,
                    self._correction_ok_btn):
            btn.setStyleSheet(small_btn_style)

        self._feedback_lbl.setStyleSheet(
            f"color: {pal['TEXT_LABEL']}; background: transparent;"
        )

        self._correction_combo.setStyleSheet(f"""
            QComboBox {{
                background: {pal['BG_INPUT']};
                color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']};
                border-radius: 3px;
                padding: 2px 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {pal['BG_ELEVATED']};
                color: {pal['TEXT_PRIMARY']};
                border: 1px solid {pal['INACTIVE']};
                selection-background-color: {pal['ACCENT']};
            }}
        """)

        for lbl in self._correction_picker.findChildren(QLabel):
            lbl.setStyleSheet(f"color: {pal['TEXT_SECONDARY']}; background: transparent;")

