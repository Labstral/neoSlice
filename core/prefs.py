"""Gestionnaire de préférences utilisateur — partage prefs.json avec ThemeManager."""
from __future__ import annotations

import json
from pathlib import Path

_PREFS_FILE = Path.home() / ".neoslice" / "prefs.json"

_DEFAULTS: dict = {
    "theme":           "dark",
    "printer_default": "",
    "export_folder":   "",
    "auto_rotate":     False,
    "lang":            "fr",
}


class _PrefsManager:
    def get(self, key: str, default=None):
        data = self._load()
        if key in data:
            return data[key]
        return _DEFAULTS.get(key, default)

    def set(self, key: str, value) -> None:
        data = self._load()
        data[key] = value
        self._save(data)

    def _load(self) -> dict:
        try:
            if _PREFS_FILE.exists():
                return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self, data: dict) -> None:
        try:
            _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass


PREFS = _PrefsManager()
