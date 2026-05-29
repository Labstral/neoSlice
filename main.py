"""neoSlice — Point d'entrée principal."""
from __future__ import annotations
import sys
import os
import ctypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from loguru import logger
from version import __version__


def _configure_logging():
    logger.remove()
    if sys.stderr is not None:
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            level="INFO",
            colorize=True,
        )
    log_file = Path(__file__).parent / "data" / "neoslice.log"
    log_file.parent.mkdir(exist_ok=True)
    logger.add(str(log_file), rotation="5 MB", retention="7 days", level="DEBUG")


def _assets_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass) / "assets"
    return Path(__file__).parent / "assets"


class _ImportThread(QThread):
    """Pré-charge les modules lourds hors du thread principal pour garder l'animation fluide."""
    ready = Signal()

    def run(self):
        try:
            import ui.main_window  # noqa: F401
        except Exception as e:
            logger.error(f"Erreur import MainWindow : {e}")
        self.ready.emit()


class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(720, 400)

        # Fond : splash_bg.png si disponible, sinon couleur unie
        self._bg_pixmap = None
        bg_path = _assets_dir() / "splash_bg.png"
        if bg_path.exists():
            self._bg_pixmap = QPixmap(str(bg_path)).scaled(
                720, 400,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self.setStyleSheet("QWidget { background-color: #070D14; }")

        # Couche de contenu par-dessus le fond
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 60, 0, 36)
        layout.setSpacing(0)

        logo = QLabel()
        logo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        logo_path = _assets_dir() / "neoSlice.png"
        if logo_path.exists():
            px = QPixmap(str(logo_path)).scaled(
                220, 110,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(px)
        else:
            logo.setText("neoSlice")
            logo.setStyleSheet("color: #FFFFFF; font-size: 36px; font-weight: bold;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        layout.addSpacing(20)

        tagline = QLabel("Slice smarter. Print faster.")
        tagline.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        tagline.setStyleSheet("color: #FFFFFF; font-size: 13px; letter-spacing: 1px;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)

        layout.addStretch()

        bar = QProgressBar()
        bar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(3)
        bar.setContentsMargins(40, 0, 40, 0)
        bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.15);
                border: none;
                margin: 0 40px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4A9EFF, stop:1 #FFFFFF
                );
            }
        """)
        layout.addWidget(bar)

    def paintEvent(self, event):
        if self._bg_pixmap:
            from PySide6.QtGui import QPainter
            p = QPainter(self)
            p.drawPixmap(0, 0, self._bg_pixmap)
        else:
            super().paintEvent(event)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )


def main():
    _configure_logging()
    logger.info("Démarrage de neoSlice")

    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("neoSlice.app")

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("VTK_SILENCE_GET_VOID_POINTER_WARNINGS", "1")
    # Supprime les logs VTK niveau ERR (framebuffer non-critique au démarrage)
    os.environ.setdefault("VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN", "0")

    app = QApplication(sys.argv)
    app.setApplicationName("neoSlice")
    app.setApplicationDisplayName("neoSlice")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("neoSlice")

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # Liste utilisée comme conteneur pour éviter la destruction par le GC
    _keep_alive: list = []

    def _on_imports_ready():
        from ui.main_window import MainWindow
        window = MainWindow()
        _keep_alive.append(window)
        window.show()
        splash.close()
        logger.info("Interface prête")

    loader = _ImportThread()
    loader.ready.connect(_on_imports_ready)
    loader.start()

    return sys.exit(app.exec())


if __name__ == "__main__":
    main()
