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
                    stop:0 #22D3EE, stop:0.5 #6594F3, stop:1 #A855F7
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
        from PySide6.QtGui import QPainter, QColor
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        if self._bg_pixmap:
            p.drawPixmap(0, 0, self._bg_pixmap)
        else:
            super().paintEvent(event)

        # « Chargement… » sous le slogan (incrusté dans l'image), au-dessus de la barre
        try:
            from core.i18n import _ as _t
            txt = _t("app.loading")
        except Exception:
            txt = "Chargement…"
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(FONT_MAIN, 10)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 205))
        p.drawText(QRectF(0, self.height() - 35, self.width(), 22),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, txt)
        p.end()

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )


def main():
    _configure_logging()
    logger.info("Démarrage de neoSlice")

    # Certificats SSL — CRITIQUE pour macOS : une app gelée (PyInstaller) n'a pas
    # le magasin de certificats système → tout HTTPS (activation Pro, mises à jour,
    # modèle IA) échouait avec « Pas de connexion Internet ». On pointe le contexte
    # SSL par défaut vers le bundle certifi embarqué. Inoffensif sur Windows.
    try:
        import certifi
        _ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", _ca)
        os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(_ca))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
        logger.info(f"Certificats SSL : {_ca}")
    except Exception as _e:
        logger.warning(f"certifi indisponible : {_e}")

    # AppUserModelID — requis pour que Windows affiche la bonne icône dans la barre des tâches
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("neoSlice.app")
        except Exception:
            pass

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("VTK_SILENCE_GET_VOID_POINTER_WARNINGS", "1")
    os.environ.setdefault("VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN", "0")

    # Mise à l'échelle fractionnaire (125 %/150 %) : sans politique d'arrondi, Qt
    # accumule des erreurs entre la zone cliquable et le rendu sur les fenêtres
    # hautes → boutons décalés. PassThrough = échelle exacte, zéro arrondi.
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Mode compatibilité : rendu OpenGL LOGICIEL (Mesa, livré par PySide6). Pour les
    # machines dont la carte graphique ne gère pas l'affichage 3D. Le viewer VTK passe
    # par un QOpenGLWidget, donc forcer Qt en logiciel force aussi le rendu 3D en
    # logiciel. À activer AVANT QApplication.
    try:
        from core.prefs import PREFS
        if PREFS.get("viewer_software_gl", False):
            os.environ["QT_OPENGL"] = "software"
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
            logger.info("Rendu OpenGL logiciel activé (mode compatibilité).")
    except Exception as _e:
        logger.warning(f"mode compatibilité OpenGL : {_e}")

    app = QApplication(sys.argv)
    app.setApplicationName("neoSlice")
    # Barre de titre native sombre/claire AU PLUS TÔT (avant tout affichage, splash
    # compris) → pas de flash clair au démarrage. Qt gère ensuite nativement la
    # couleur de la barre de titre sur toutes les fenêtres, y compris au retour de
    # réduction d'une fenêtre maximisée. Voir theme.apply_title_bar_theme.
    try:
        from ui.styles.theme import apply_title_bar_theme as _tb_early
        _tb_early(None)
    except Exception:
        pass
    # Pas de setApplicationDisplayName : Qt l'ajoute en suffixe « - neoSlice » à tous
    # les titres de fenêtres (redondant). Le nom reste via setApplicationName.
    app.setApplicationVersion(__version__)
    app.setOrganizationName("neoSlice")

    font = QFont(FONT_MAIN, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # Traduire les dialogues natifs Qt (sélecteur de couleur, OK/Annuler, Oui/Non,
    # dialogue de fichiers…) dans la langue de l'app.
    try:
        from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
        from core.prefs import PREFS as _PREFS_LANG
        _lang = _PREFS_LANG.get("lang", "fr")
        if _lang and _lang != "en":
            _qt_tr = QTranslator(app)
            _tr_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
            for _mod in ("qtbase", "qt"):
                if _qt_tr.load(QLocale(_lang), _mod, "_", _tr_path):
                    app.installTranslator(_qt_tr)
                    globals()["_QT_TRANSLATOR"] = _qt_tr  # référence anti-GC
                    break
    except Exception:
        pass

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
    # Infobulles : le style natif Windows respecte ces rôles de palette (le
    # stylesheet app QToolTip est parfois ignoré → tooltip noir système).
    _qp.setColor(QPalette.ColorRole.ToolTipBase,   _QC(_tp["BG_ELEVATED"]))
    _qp.setColor(QPalette.ColorRole.ToolTipText,   _QC(_tp["TEXT_PRIMARY"]))
    app.setPalette(_qp)

    # Style global des infobulles (lisible en thème clair ET sombre) + maj au switch
    from ui.styles.theme import apply_tooltip_style as _tt_style, install_themed_tooltips
    _tt_style()
    _THEME_MGR.register(_tt_style)
    # Infobulles maison garanties (le tooltip natif reste sombre sous Windows)
    install_themed_tooltips(app)

    # Barre de titre Windows cohérente avec le thème pour TOUTES les fenêtres
    # (fenêtre principale, dialogues, avertissements, sélecteurs natifs…).
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtWidgets import QWidget as _QWidget
    from ui.styles.theme import apply_title_bar_theme as _tb

    class _TitleBarFilter(QObject):
        # Show : chaque nouvelle fenêtre naît au bon thème. ThemeChange /
        # PaletteChange (fenêtres seulement) : Qt vient de repeindre la frame
        # selon SON idée du thème -> on repasse derrière lui immédiatement.
        _TYPES = (QEvent.Type.Show, QEvent.Type.ThemeChange,
                  QEvent.Type.ApplicationPaletteChange)

        def eventFilter(self, obj, event):
            if (event.type() in self._TYPES
                    and isinstance(obj, _QWidget) and obj.isWindow()):
                _tb(obj)
            return False

    _tb_filter = _TitleBarFilter()
    app.installEventFilter(_tb_filter)
    globals()["_TB_FILTER"] = _tb_filter  # anti-GC

    # Molette : empeche un simple scroll EN SURVOL de changer la valeur d'un menu
    # deroulant / champ numerique / curseur (couvre TOUTE l'app). Voir ui/wheel_guard.
    from ui.wheel_guard import install as _install_wheel_guard
    globals()["_WHEEL_GUARD"] = _install_wheel_guard(app)

    def _retheme_titlebars():
        for w in app.topLevelWidgets():
            if w.isWindow():
                _tb(w)

    def _retheme_cascade():
        # Au switch de thème, Qt (6.8+) repeint parfois la frame APRÈS nous
        # (setColorScheme et palette sont traités en différé) -> la barre
        # « redevenait » claire. On repasse derrière lui à plusieurs horizons ;
        # le DWM n'émet aucun signal Qt, donc aucune boucle possible.
        from PySide6.QtCore import QTimer as _QT3
        _retheme_titlebars()
        for _ms in (120, 400, 900):
            _QT3.singleShot(_ms, _retheme_titlebars)
    _THEME_MGR.register(_retheme_cascade)

    # CORRECTIF DE FOND barre de titre : Qt 6.8+ SUIT le thème de l'OS et ré-aligne la
    # couleur de la barre de titre native sur celui de l'OS — sur un changement de thème
    # Windows, un réveil, etc. En thème sombre (app) + OS clair, la barre « revient » en
    # clair. On écoute colorSchemeChanged pour RE-PEINDRE nos barres de titre (DWM) au
    # thème de l'app. On NE re-touche PAS le colorScheme (éviterait une boucle).
    def _on_os_scheme_changed(*_a):
        # Qt/OS vient de changer le colorScheme (souvent la barre de titre suit l'OS).
        # On NE re-touche PAS le colorScheme (sinon boucle de ré-émission) : on se
        # contente de re-peindre le DWM des barres de titre pour REVENIR à notre thème.
        # Le DWM n'émet pas colorSchemeChanged -> pas de boucle. Un léger différé pour
        # passer APRÈS le repaint de Qt.
        try:
            _retheme_titlebars()
            from PySide6.QtCore import QTimer as _QT2
            _QT2.singleShot(60, _retheme_titlebars)
        except Exception:
            pass
    try:
        app.styleHints().colorSchemeChanged.connect(_on_os_scheme_changed)
    except Exception:
        pass

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
            from ui.styles.theme import apply_title_bar_theme
            # AVANT l'affichage → barre de titre dessinée au bon thème dès le départ
            apply_title_bar_theme(window)
            window.showMaximized()
            apply_title_bar_theme(window)   # + après (repaint forcé, ceinture-bretelles)
            # La frame d'une fenêtre MAXIMISÉE n'est totalement réalisée qu'après
            # quelques tours de boucle → on ré-applique en différé, sinon la barre
            # de titre peut rester claire au tout premier affichage.
            from PySide6.QtCore import QTimer as _QT
            for _ms in (0, 60, 200):
                _QT.singleShot(_ms, lambda w=window: apply_title_bar_theme(w))
            # Niveau 2 anti-fraude : re-valide le Pro en ligne en arrière-plan
            # (révoque un Pro sans clé valide ; ne punit pas l'utilisateur hors-ligne).
            from core import licensing
            licensing.revalidate_pro_async()
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
 