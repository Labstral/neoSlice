from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QPixmap,
    QDragEnterEvent, QDropEvent, QMouseEvent,
)

from core.i18n import _
from ui.styles.theme import (
    BG_SURFACE, ACCENT, ACCENT_BRIGHT, TELE_GREEN,
    TEXT_SECONDARY, TEXT_LABEL, INACTIVE, FONT_MONO, MANAGER as _T,
    FONT_MAIN,)

_SUPPORTED = {".stl", ".obj", ".3mf"}


class DropZone(QWidget):
    """Zone drag-and-drop STL — style Mission Control avec coins HUD."""

    file_dropped = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(False)
        self.setCursor(Qt.ForbiddenCursor)
        self.setMinimumHeight(160)
        self._hovered = False
        self._loaded = False
        self._locked = True
        self._current_file: Path | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)
        layout.setContentsMargins(16, 16, 16, 16)

        # Miniature d'aperçu du modèle chargé (masquée tant qu'aucun fichier)
        self._thumb = QLabel()
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setStyleSheet("background: transparent;")
        self._thumb.hide()
        layout.addWidget(self._thumb)

        self._icon = QLabel("⊘")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet(f"font-size: 22px; color: {INACTIVE}; background: transparent;")
        layout.addWidget(self._icon)

        self._main_label = QLabel(_("drop.main_locked"))
        self._main_label.setAlignment(Qt.AlignCenter)
        self._main_label.setFont(QFont(FONT_MAIN, 8, QFont.Bold))
        self._main_label.setStyleSheet(f"color: {INACTIVE}; background: transparent; letter-spacing: 1px;")
        layout.addWidget(self._main_label)

        self._sub_label = QLabel(_("drop.sub_locked"))
        self._sub_label.setAlignment(Qt.AlignCenter)
        self._sub_label.setWordWrap(True)
        self._sub_label.setFont(QFont(FONT_MONO, 9))
        self._sub_label.setStyleSheet(f"color: {INACTIVE}; background: transparent;")
        layout.addWidget(self._sub_label)

        self._recent_path: "Path | None" = None
        self._recent_btn = QPushButton()
        self._recent_btn.setFont(QFont(FONT_MONO, 9))
        self._recent_btn.setStyleSheet(f"""
            QPushButton {{ color: {ACCENT}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {ACCENT_BRIGHT}; text-decoration: underline; }}
        """)
        self._recent_btn.setCursor(Qt.PointingHandCursor)
        self._recent_btn.hide()
        self._recent_btn.clicked.connect(self._on_recent_clicked)
        layout.addWidget(self._recent_btn)

    # ── État verrouillé / déverrouillé ────────────────────────────────────

    def set_locked(self, locked: bool):
        self._locked = locked
        self.setAcceptDrops(not locked)
        self.setCursor(Qt.ForbiddenCursor if locked else Qt.PointingHandCursor)
        self._refresh_labels()
        self.update()

    def _refresh_labels(self):
        _p = _T.palette()
        inc = _p["INACTIVE"]; ts = _p["TEXT_SECONDARY"]; tl = _p["TEXT_LABEL"]
        if self._locked:
            self._icon.setText("⊘")
            self._icon.setStyleSheet(f"font-size: 22px; color: {inc}; background: transparent;")
            self._main_label.setText(_("drop.main_locked"))
            self._main_label.setStyleSheet(f"color: {ts}; background: transparent; letter-spacing: 1px;")
            self._sub_label.setText(_("drop.sub_locked"))
            self._sub_label.setStyleSheet(f"color: {tl}; background: transparent;")
        elif self._loaded:
            if hasattr(self, "_recent_btn"):
                self._recent_btn.hide()
        else:
            self._icon.setText("⬆")
            self._icon.setStyleSheet(f"font-size: 24px; color: {inc}; background: transparent;")
            self._main_label.setText(_("drop.main"))
            self._main_label.setStyleSheet(f"color: {ts}; background: transparent; letter-spacing: 2px;")
            self._sub_label.setText(_("drop.sub"))
            self._sub_label.setStyleSheet(f"color: {tl}; background: transparent;")
            if hasattr(self, "_recent_btn") and hasattr(self, "_recent_path") and self._recent_path:
                self._recent_btn.setText(_("drop.reopen", name=self._recent_path.name))
                self._recent_btn.show()

    # ── Drag & Drop ────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._locked:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            if any(Path(u.toLocalFile()).suffix.lower() in _SUPPORTED
                   for u in event.mimeData().urls()):
                self._hovered = True
                self.update()
                event.acceptProposedAction()
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._hovered = False
        self.update()

    def dropEvent(self, event: QDropEvent):
        if self._locked:
            return
        self._hovered = False
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile()).resolve()
            if path.suffix.lower() in _SUPPORTED and path.is_file():
                self._set_file(path)
                break

    def mousePressEvent(self, event: QMouseEvent):
        if self._locked:
            return
        if event.button() == Qt.LeftButton:
            _title  = _("drop.dialog_title")
            _filter = _("drop.dialog_filter")
            path, _ext = QFileDialog.getOpenFileName(
                self.window(), _title, "", _filter,
            )
            if path:
                self._set_file(Path(path))

    # ── État chargé ────────────────────────────────────────────────────────

    def set_thumbnail(self, png_bytes: "bytes | None"):
        """Affiche une miniature d'aperçu (octets PNG) à la place de l'icône ✓."""
        if not png_bytes:
            return
        pix = QPixmap()
        if pix.loadFromData(png_bytes):
            self._thumb.setPixmap(pix.scaledToHeight(96, Qt.SmoothTransformation))
            self._thumb.show()
            self._icon.hide()

    def _set_file(self, path: Path):
        self._current_file = path
        self._loaded = True
        # Nouvelle pièce → on repart de l'icône ✓ ; la miniature arrive ensuite.
        self._thumb.hide()
        self._thumb.clear()
        self._icon.show()
        self._icon.setText("✓")
        self._icon.setStyleSheet(
            f"font-size: 22px; color: {_T.palette()['TELE_GREEN']}; background: transparent;"
        )
        self._main_label.setText(path.name)
        self._main_label.setStyleSheet(
            f"color: {_T.palette()['TELE_GREEN']}; background: transparent; font-size: 11px;"
        )
        self._sub_label.setText(_("drop.sub_loaded"))
        self._sub_label.setFont(QFont(FONT_MONO, 9))
        self._sub_label.setStyleSheet(f"color: {_T.palette()['TEXT_LABEL']}; background: transparent;")
        self.update()
        self.file_dropped.emit(path)

    def reset(self):
        self._hovered = False
        self._loaded = False
        self._current_file = None
        self._thumb.hide()
        self._thumb.clear()
        self._icon.show()
        self._refresh_labels()
        if hasattr(self, "_recent_path") and self._recent_path and not self._locked:
            self._recent_btn.setText(_("drop.reopen", name=self._recent_path.name))
            self._recent_btn.show()
        self.update()

    def set_recent_file(self, path: "Path | None"):
        self._recent_path = path
        if path and not self._locked and not self._loaded:
            self._recent_btn.setText(_("drop.reopen", name=path.name))
            self._recent_btn.show()
        else:
            self._recent_btn.hide()

    def _on_recent_clicked(self):
        if self._recent_path and self._recent_path.exists() and not self._locked:
            self._set_file(self._recent_path)

    # ── Rendu NASA ─────────────────────────────────────────────────────────

    def refresh_theme(self):
        _p = _T.palette()
        self._recent_btn.setStyleSheet(f"""
            QPushButton {{ color: {_p["ACCENT"]}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {_p["ACCENT_BRIGHT"]}; text-decoration: underline; }}
        """)
        if self._loaded:
            self._sub_label.setStyleSheet(f"color: {_p['TEXT_LABEL']}; background: transparent;")
        self._refresh_labels()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(3, 3, -3, -3)
        pal = _T.palette()

        bg = QColor(pal["BG_SURFACE"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRect(rect)

        if self._locked:
            pen_color = QColor(pal["INACTIVE"])
            pen_color.setAlpha(80)
        elif self._hovered:
            pen_color = QColor(pal["ACCENT_BRIGHT"])
        elif self._loaded:
            pen_color = QColor(pal["TELE_GREEN"])
        else:
            pen_color = QColor(pal["INACTIVE"])

        pen = QPen(pen_color, 1, Qt.DashLine)
        pen.setDashPattern([6, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        if not self._locked:
            hud_color = QColor(
                pal["ACCENT_BRIGHT"] if (self._hovered or self._loaded) else pal["INACTIVE"]
            )
            painter.setPen(QPen(hud_color, 1.5))
            size = 10
            r = rect
            for x1, y1, x2, y2 in [
                (r.left(),        r.top(),          r.left()+size,    r.top()),
                (r.left(),        r.top(),          r.left(),         r.top()+size),
                (r.right()-size,  r.top(),          r.right(),        r.top()),
                (r.right(),       r.top(),          r.right(),        r.top()+size),
                (r.left(),        r.bottom()-size,  r.left(),         r.bottom()),
                (r.left(),        r.bottom(),       r.left()+size,    r.bottom()),
                (r.right()-size,  r.bottom(),       r.right(),        r.bottom()),
                (r.right(),       r.bottom()-size,  r.right(),        r.bottom()),
            ]:
                painter.drawLine(x1, y1, x2, y2)

            if self._hovered:
                glow_col = (30, 144, 255) if _T.is_dark() else (45, 138, 78)
                glow_pen = QPen(QColor(*glow_col, 35), 6)
                painter.setPen(glow_pen)
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
