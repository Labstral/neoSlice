"""Gestionnaire de préférences utilisateur — partage prefs.json avec ThemeManager."""
from __future__ import annotations

import json
from pathlib import Path

_PREFS_FILE = Path.home() / ".neoslice" / "prefs.json"

_DEFAULTS: dict = {
    "theme":           "dark",
    "printer_default": "",
    "export_folder":   "",
    "auto_rotate":     True,
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


def dossier_sortie() -> Path:
    """Le dossier où proposer TOUT enregistrement : le dossier d'export choisi
    dans les réglages, sinon Téléchargements, sinon le dossier personnel.

    Un seul endroit pour tout le monde (export 3MF, CSV, PDF, neoForge) :
    chaque fenêtre d'enregistrement qui décidait dans son coin ouvrait le
    dossier courant du programme, donc un endroit imprévisible (retour
    d'Emmanuel, 2026-09-24).
    """
    choisi = str(PREFS.get("export_folder", "") or "").strip()
    if choisi and Path(choisi).is_dir():
        return Path(choisi)
    try:
        from PySide6.QtCore import QStandardPaths
        d = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation)
    except Exception:
        d = ""
    for candidat in (Path(d) if d else None, Path.home() / "Downloads",
                     Path.home() / "Téléchargements"):
        if candidat is not None and candidat.is_dir():
            return candidat
    return Path.home()
