"""neoSlice — Point d'entrée principal."""
from __future__ import annotations
import sys
import os
import ctypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QProgressBar
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from loguru import logger
from version import __version__
from ui.styles.theme import FONT_MAIN


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

        self.setFixedSize(740, 416)
        self._bg_pixmap = None
        bg_path = _assets_dir() / "splash_bg.png"
        if bg_path.exists():
            self._bg_pixmap = QPixmap(str(bg_path)).scaled(
                740, 416,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self.setStyleSheet("QWidget { background-color: #070D14; }")

        # Barre de chargement infinie tout en bas
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()

        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.15);
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4A9EFF, stop:1 #FFFFFF
                );
            }
        """)
        layout.addWidget(bar)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

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

    # AppUserModelID — requis pour que Windows affiche la bonne icône dans la barre des tâches
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("neoSlice.app")
        except Exception:
            pass

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("VTK_SILENCE_GET_VOID_POINTER_WARNINGS", "1")
    os.environ.setdefault("VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN", "0")

    app = QApplication(sys.argv)
    app.setApplicationName("neoSlice")
    app.setApplicationDisplayName("neoSlice")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("neoSlice")

    font = QFont(FONT_MAIN, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # Appliquer la palette Qt dès le départ pour éviter le flash blanc en mode sombre.
    # QPalette fixe la couleur de fond système avant tout rendu — sans ça, Qt peint
    # le fond par défaut (blanc) pendant les ~80 ms avant l'application du stylesheet.
    from PySide6.QtGui import QPalette, QColor as _QC
    from ui.styles.theme import MANAGER as _THEME_MGR
    _tp = _THEME_MGR.palette()
    _qp = QPalette()
    _qp.setColor(QPalette.ColorRole.Window,        _QC(_tp["BG_VOID"]))
    _qp.setColor(QPalette.ColorRole.Base,          _QC(_tp["BG_SURFACE"]))
    _qp.setColor(QPalette.ColorRole.AlternateBase, _QC(_tp["BG_ELEVATED"]))
    _qp.setColor(QPalette.ColorRole.WindowText,    _QC(_tp["TEXT_PRIMARY"]))
    _qp.setColor(QPalette.ColorRole.Text,          _QC(_tp["TEXT_PRIMARY"]))
    _qp.setColor(QPalette.ColorRole.Button,        _QC(_tp["BG_PANEL"]))
    _qp.setColor(QPalette.ColorRole.ButtonText,    _QC(_tp["TEXT_PRIMARY"]))
    app.setPalette(_qp)

    # Icône sur QApplication avant tout affichage — garantit la barre des tâches
    _icon_path = _assets_dir() / "neoSlice.ico"
    if not _icon_path.exists():
        _icon_path = _assets_dir() / "neoSlice.png"
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # Liste utilisée comme conteneur pour éviter la destruction par le GC
    _keep_alive: list = []

    def _on_imports_ready():
        try:
            from ui.main_window import MainWindow
            window = MainWindow()
            _keep_alive.append(window)
            window.showMaximized()
            from ui.styles.theme import apply_title_bar_theme
            apply_title_bar_theme(window)
            logger.info("Interface prête")
        except Exception as e:
            logger.exception(f"Erreur critique au démarrage : {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "neoSlice — Erreur", f"Impossible de démarrer :\n{e}")
        finally:
            splash.close()

    loader = _ImportThread()
    loader.ready.connect(_on_imports_ready)
    loader.start()

    return sys.exit(app.exec())


if __name__ == "__main__":
    main()
 