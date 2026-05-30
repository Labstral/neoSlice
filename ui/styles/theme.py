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
    "FONT_MONO": "Courier New",
    "RADIUS": 4,

    # Viewer 3D PyVista — fond gris Bambu Studio (identique thème clair/foncé)
    "VIEWER_BG":     "#606468",
    "VIEWER_BG_TOP": "#606468",

    # paintEvent — grille fond et scan-line (RGBA composantes)
    "GRID_R": 30, "GRID_G": 144, "GRID_B": 255, "GRID_A": 8,
    "SCAN_R": 30, "SCAN_G": 144, "SCAN_B": 255, "SCAN_A": 25,

    # Export button
    "EXPORT_FG": "#020408",
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
    "FONT_MONO": "Courier New",
    "RADIUS": 4,

    # Viewer 3D PyVista — fond gris plus clair en thème clair (moins de contraste)
    "VIEWER_BG":     "#9E9EA2",
    "VIEWER_BG_TOP": "#9E9EA2",

    "GRID_R": 0, "GRID_G": 0, "GRID_B": 0, "GRID_A": 12,
    "SCAN_R": 45, "SCAN_G": 138, "SCAN_B": 78, "SCAN_A": 12,

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


def apply_title_bar_theme(widget, is_dark: bool | None = None) -> None:
    """Applique le thème sombre/clair à la barre de titre Windows (DWM API)."""
    if sys.platform != "win32":
        return
    try:
        if is_dark is None:
            is_dark = MANAGER.is_dark()
        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if is_dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
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

FONT_MAIN = "Segoe UI"
FONT_MONO = "Courier New"
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
