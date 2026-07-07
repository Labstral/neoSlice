"""Palette neoSlice — thème sombre NASA et thème clair Bambu Studio.

Double palette avec ThemeManager singleton.
Persistance dans ~/.neoslice/prefs.json (clé "theme").
"""
from __future__ import annotations

import ctypes
import sys
import json
from pathlib import Path

_PREFS_FILE = Path.home() / ".neoslice" / "prefs.json"

# ── Palettes ───────────────────────────────────────────────────────────────

_DARK: dict = {
    "BG_VOID":     "#020408",
    "BG_PANEL":    "#070D14",
    "BG_SURFACE":  "#0A1628",
    "BG_ELEVATED": "#0F1F35",
    "BG_INPUT":    "#060E1A",

    "ACCENT":        "#1E90FF",
    "ACCENT_BRIGHT": "#4DAFFF",

    "TELE_GREEN": "#00B870",
    "AMBER":      "#FFB800",
    "ERROR_RED":  "#FF3B3B",

    "TEXT_PRIMARY":   "#C8DCF0",
    "TEXT_SECONDARY": "#4A7A9B",
    "TEXT_LABEL":     "#2A5F8A",
    "INACTIVE":       "#1A3550",

    "FONT_MAIN": "Segoe UI",
    "FONT_MONO": "Segoe UI",
    "RADIUS": 4,

    # Viewer 3D PyVista — fond studio sombre avec dégradé (bas → haut)
    "VIEWER_BG":     "#111520",
    "VIEWER_BG_TOP": "#2a3348",

    # paintEvent — grille fond et scan-line (RGBA composantes)
    "GRID_R": 30, "GRID_G": 144, "GRID_B": 255, "GRID_A": 8,
    "SCAN_R": 30, "SCAN_G": 144, "SCAN_B": 255, "SCAN_A": 25,

    # Export button — texte blanc sur boutons colorés (cohérent avec boutons Valider)
    "EXPORT_FG": "#ffffff",
}

_LIGHT: dict = {
    "BG_VOID":     "#e8e8e8",
    "BG_PANEL":    "#f0f0f0",
    "BG_SURFACE":  "#e4e4e4",
    "BG_ELEVATED": "#d8d8d8",
    "BG_INPUT":    "#f8f8f8",

    "ACCENT":        "#2d8a4e",
    "ACCENT_BRIGHT": "#1f6b3a",

    "TELE_GREEN": "#0A9E60",
    "AMBER":      "#e67e22",
    "ERROR_RED":  "#c0392b",

    "TEXT_PRIMARY":   "#1a1a1a",
    "TEXT_SECONDARY": "#555555",
    "TEXT_LABEL":     "#777777",
    "INACTIVE":       "#d0d0d0",

    "FONT_MAIN": "Segoe UI",
    "FONT_MONO": "Segoe UI",
    "RADIUS": 4,

    # Viewer 3D PyVista — fond studio clair avec dégradé subtil
    "VIEWER_BG":     "#8e9aa6",
    "VIEWER_BG_TOP": "#c8d0d8",

    "GRID_R": 0, "GRID_G": 0, "GRID_B": 0, "GRID_A": 12,
    "SCAN_R": 45, "SCAN_G": 138, "SCAN_B": 78, "SCAN_A": 55,

    "EXPORT_FG": "#ffffff",
}


# ── ThemeManager ───────────────────────────────────────────────────────────

class ThemeManager:
    """Singleton de gestion de thème. Persistance dans prefs.json."""

    def __init__(self):
        self._name: str = self._load_saved()
        self._palette: dict = _DARK if self._name == "dark" else _LIGHT
        self._listeners: list = []

    # ── Lecture ────────────────────────────────────────────────────────────

    def palette(self) -> dict:
        return self._palette

    def name(self) -> str:
        return self._name

    def is_dark(self) -> bool:
        return self._name == "dark"

    # ── Basculement ────────────────────────────────────────────────────────

    def switch(self, name: str) -> None:
        if name not in ("dark", "light") or name == self._name:
            return
        self._name = name
        self._palette = _DARK if name == "dark" else _LIGHT
        self._save(name)
        _sync_native_color_scheme(name == "dark")   # barre de titre native (Qt)
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    def toggle(self) -> None:
        self.switch("light" if self._name == "dark" else "dark")

    # ── Listeners ──────────────────────────────────────────────────────────

    def register(self, callback) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister(self, callback) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    # ── Persistance ────────────────────────────────────────────────────────

    def _load_saved(self) -> str:
        try:
            if _PREFS_FILE.exists():
                data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
                name = data.get("theme", "dark")
                if name in ("dark", "light"):
                    return name
        except Exception:
            pass
        return "dark"

    def _save(self, name: str) -> None:
        try:
            prefs: dict = {}
            if _PREFS_FILE.exists():
                try:
                    prefs = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            prefs["theme"] = name
            _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_FILE.write_text(
                json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass


MANAGER = ThemeManager()


def apply_tooltip_style() -> None:
    """Style global des infobulles (QToolTip), lisible dans les DEUX thèmes.

    Par défaut Qt rend le texte des tooltips quasi invisible en thème clair
    (texte très pâle sur fond pâle). On force un fond contrasté + texte primaire.
    À (ré)appeler à chaque changement de thème."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtCore import Qt
        app = QApplication.instance()
        if app is None:
            return
        pal = MANAGER.palette()
        # 0) Schéma de couleurs Qt = thème de l'app. CLÉ sous Windows : sans ça,
        #    Qt 6 suit le mode sombre de l'OS pour les éléments « système »
        #    (barre de titre, popups infobulles) même quand l'app est en clair.
        try:
            app.styleHints().setColorScheme(
                Qt.ColorScheme.Dark if MANAGER.is_dark() else Qt.ColorScheme.Light
            )
        except Exception:
            pass
        # 1) Palette DÉDIÉE aux infobulles via l'API statique QToolTip.setPalette
        #    — c'est LE moyen direct de fixer leur couleur, indépendamment du
        #    stylesheet app (souvent ignoré) et du mode sombre de l'OS.
        from PySide6.QtWidgets import QToolTip
        bg = QColor(pal["BG_ELEVATED"])
        fg = QColor(pal["TEXT_PRIMARY"])
        tip_pal = QToolTip.palette()
        for role in (QPalette.ColorRole.ToolTipBase, QPalette.ColorRole.Base,
                     QPalette.ColorRole.Window, QPalette.ColorRole.Button):
            tip_pal.setColor(role, bg)
        for role in (QPalette.ColorRole.ToolTipText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            tip_pal.setColor(role, fg)
        QToolTip.setPalette(tip_pal)
        # Palette app aussi (ceinture + bretelles)
        qpal = app.palette()
        qpal.setColor(QPalette.ColorRole.ToolTipBase, bg)
        qpal.setColor(QPalette.ColorRole.ToolTipText, fg)
        app.setPalette(qpal)
        # 2) Stylesheet : utile si le style feuille est actif (bordure accent).
        app.setStyleSheet(
            "QToolTip {"
            f" background-color: {pal['BG_ELEVATED']};"
            f" color: {pal['TEXT_PRIMARY']};"
            f" border: 1px solid {pal['ACCENT']};"
            " padding: 4px 8px; border-radius: 3px; }"
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Infobulles thématisées garanties — on remplace le tooltip natif (que Qt/Windows
# rend en sombre malgré tout) par notre propre étiquette stylée.
# ──────────────────────────────────────────────────────────────────────────────
class _ThemedTooltipFilter:
    """Filtre d'événements applicatif : intercepte les tooltips et affiche une
    étiquette à nos couleurs (indépendante du mode sombre de l'OS)."""

    def __init__(self):
        from PySide6.QtCore import QObject, QTimer

        class _Filter(QObject):
            def __init__(self, outer):
                super().__init__()
                self._o = outer

            def eventFilter(self, obj, event):
                return self._o._on_event(obj, event)

        self._qobj = _Filter(self)
        self._tip = None
        self._owner = None
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)

    def _on_event(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget
        t = event.type()
        if t == QEvent.Type.ToolTip and isinstance(obj, QWidget):
            text = obj.toolTip()
            if text:
                self._owner = obj
                self._show(event.globalPos(), text)
                return True   # bloque le tooltip natif sombre
            self._hide()
            return False
        if t in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress,
                 QEvent.Type.Wheel, QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate):
            self._hide()
        return False

    def _show(self, gpos, text):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        pal = MANAGER.palette()
        if self._tip is None:
            self._tip = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
            self._tip.setWindowFlag(Qt.WindowTransparentForInput, True)
            self._tip.setWordWrap(True)
            self._tip.setMaximumWidth(360)
        self._tip.setStyleSheet(
            f"QLabel {{ background: {pal['BG_ELEVATED']}; color: {pal['TEXT_PRIMARY']}; "
            f"border: 1px solid {pal['ACCENT']}; border-radius: 3px; "
            f"padding: 4px 8px; font-size: 12px; }}"
        )
        self._tip.setText(text)
        self._tip.adjustSize()
        self._tip.move(gpos.x() + 12, gpos.y() + 18)
        self._tip.show()
        self._timer.start(6000)

    def _hide(self):
        self._owner = None
        if self._tip is not None:
            self._tip.hide()


_tooltip_filter = None


def install_themed_tooltips(app) -> None:
    """Installe le filtre d'infobulles thématisées (une seule fois)."""
    global _tooltip_filter
    if _tooltip_filter is not None:
        return
    try:
        _tooltip_filter = _ThemedTooltipFilter()
        app.installEventFilter(_tooltip_filter._qobj)
    except Exception:
        pass


def _sync_native_color_scheme(is_dark: bool) -> None:
    """Règle le color scheme NATIF de l'application (Qt 6.8+).

    Aligne la palette de base de Qt (menus, tooltips, dialogues natifs) sur le
    thème de l'app. NB : sur Windows, ça ne suffit PAS toujours à colorer la
    barre de titre native — d'où l'appel DWM explicite ci-dessous."""
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt
        app = QGuiApplication.instance()
        if app is None:                       # avant la création de QApplication
            return
        hints = app.styleHints()
        scheme = Qt.ColorScheme.Dark if is_dark else Qt.ColorScheme.Light
        if hints is not None and hints.colorScheme() != scheme:
            hints.setColorScheme(scheme)
    except Exception:
        pass


def apply_title_bar_theme(widget, is_dark: bool | None = None) -> None:
    """Applique le thème clair/sombre à la barre de titre native Windows.

    Deux leviers complémentaires :
    1. color scheme Qt natif (palette des menus/tooltips/dialogues) ;
    2. DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE) pour la COULEUR réelle
       de la barre de titre — fiable sur toutes les builds, indépendamment du
       thème de l'OS.

    Point CLÉ : on ne fait PLUS de `SetWindowPos(SWP_FRAMECHANGED)`. C'était lui
    (et lui seul) qui corrompait la frame d'une fenêtre MAXIMISÉE au retour de
    réduction (barre de titre perdue + bande noire), car il déclenche un
    WM_NCCALCSIZE (recalcul de géométrie). L'attribut DWM posé sur le HWND
    persiste à travers minimiser/restaurer/maximiser ; pour rafraîchir un
    changement de thème en cours d'exécution, un `RedrawWindow(RDW_FRAME)` repeint
    la barre de titre SANS recalcul de géométrie (donc sans corruption)."""
    if is_dark is None:
        is_dark = MANAGER.is_dark()
    _sync_native_color_scheme(is_dark)
    if sys.platform != "win32" or widget is None:
        return
    try:
        hwnd = int(widget.winId())
        if not hwnd:
            return
        value = ctypes.c_int(1 if is_dark else 0)
        dwm = ctypes.windll.dwmapi
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 2004+/Win11), 19 = anciennes
        # builds. Poser les DEUX est inoffensif et couvre toutes les versions.
        for attr in (20, 19):
            try:
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass
        # Repaint de la zone non-cliente UNIQUEMENT (WM_NCPAINT), sans SetWindowPos
        # ni SWP_FRAMECHANGED → pas de WM_NCCALCSIZE → aucune corruption de frame.
        user32 = ctypes.windll.user32
        RDW_INVALIDATE, RDW_FRAME, RDW_UPDATENOW = 0x1, 0x400, 0x100
        user32.RedrawWindow(hwnd, None, None,
                            RDW_INVALIDATE | RDW_FRAME | RDW_UPDATENOW)
    except Exception:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────

def score_color(score: float) -> str:
    """Retourne une couleur dynamique selon le score 0→1."""
    pal = MANAGER.palette()
    if score >= 0.7:
        return pal["TELE_GREEN"]
    elif score >= 0.4:
        return pal["AMBER"]
    return pal["ERROR_RED"]


# ── Module-level constants (thème sombre par défaut, backward compat) ──────
# Pour le rendu dynamique, utiliser MANAGER.palette()["KEY"] dans les méthodes.

BG_VOID     = _DARK["BG_VOID"]
BG_PANEL    = _DARK["BG_PANEL"]
BG_SURFACE  = _DARK["BG_SURFACE"]
BG_ELEVATED = _DARK["BG_ELEVATED"]
BG_INPUT    = _DARK["BG_INPUT"]

ACCENT        = _DARK["ACCENT"]
ACCENT_BRIGHT = _DARK["ACCENT_BRIGHT"]

TELE_GREEN = _DARK["TELE_GREEN"]   # "#00B870" — vert Bambu
AMBER      = _DARK["AMBER"]
ERROR_RED  = _DARK["ERROR_RED"]

TEXT_PRIMARY   = _DARK["TEXT_PRIMARY"]
TEXT_SECONDARY = _DARK["TEXT_SECONDARY"]
TEXT_LABEL     = _DARK["TEXT_LABEL"]
INACTIVE       = _DARK["INACTIVE"]

import sys as _sys
FONT_MAIN = "Segoe UI" if _sys.platform == "win32" else "SF Pro Text" if _sys.platform == "darwin" else "Ubuntu"
# FONT_MONO n'est plus une police à chasse fixe (Courier) : remplacée par la même
# police propre que FONT_MAIN dans toute l'UI (préférence utilisateur). On garde la
# constante pour ne pas casser les ~55 appels existants ; seules les TAILLES comptent.
FONT_MONO = FONT_MAIN
RADIUS = 4

# Aliases backward compat
BG_PRIMARY       = BG_VOID
BG_CARD          = BG_SURFACE
BG_CARD_HOVER    = BG_ELEVATED
BORDER_DEFAULT   = INACTIVE
BORDER_FOCUS     = ACCENT_BRIGHT
ACCENT_PRIMARY   = ACCENT
ACCENT_SECONDARY = ACCENT_BRIGHT
ACCENT_SUCCESS   = TELE_GREEN
ACCENT_WARNING   = AMBER
ACCENT_DANGER    = ERROR_RED
TEXT_MUTED       = TEXT_LABEL

COLOR_SCORE_GOOD   = TELE_GREEN
COLOR_SCORE_MEDIUM = AMBER
COLOR_SCORE_BAD    = ERROR_RED
