"""Vérification des mises à jour en arrière-plan."""
from __future__ import annotations

import json
import sys
import urllib.request
from threading import Thread
from typing import Callable

from loguru import logger

from version import __version__ as CURRENT_VERSION

# Fichier latest.json hébergé sur GitHub Gist — mis à jour à chaque release.
# Format :
# {
#   "version": "0.2.0",
#   "download_url_win": "https://...neoSlice_Setup_v0.2.0.exe",
#   "download_url_mac": "https://...neoSlice-macOS.zip",
#   "download_url": "https://github.com/Labstral/neoSlice/releases/latest",  ← fallback
#   "notes": "Nouveautés..."
# }
UPDATE_CHECK_URL = (
    "https://gist.githubusercontent.com/Labstral/73d8c1bc62235780b4822ef2301edd45/raw/latest.json"
)


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip("v").split("."))
    except Exception:
        return (0, 0, 0)


def _platform_download_url(data: dict) -> str:
    """Retourne l'URL de téléchargement adaptée à la plateforme courante."""
    fallback = data.get("download_url", "https://github.com/Labstral/neoSlice/releases/latest")
    if sys.platform == "darwin":
        return data.get("download_url_mac") or fallback
    return data.get("download_url_win") or fallback


def check_for_update(callback: Callable[[str | None, str, str], None]) -> None:
    """Lance la vérification dans un thread daemon.

    callback(version, download_url, notes) si une mise à jour est disponible,
    callback(None, "", "") si déjà à jour ou en cas d'erreur réseau.
    L'URL retournée est celle adaptée à la plateforme courante (win/mac).
    """
    if not UPDATE_CHECK_URL:
        return

    def _run():
        try:
            import time as _time
            _url = f"{UPDATE_CHECK_URL}?t={int(_time.time())}"
            req = urllib.request.Request(
                _url,
                headers={"User-Agent": f"neoSlice/{CURRENT_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            latest = data.get("version", "").strip("v")
            url    = _platform_download_url(data)
            notes  = data.get("notes", "")
            if latest and _parse_version(latest) > _parse_version(CURRENT_VERSION):
                callback(latest, url, notes)
            else:
                callback(None, "", "")
        except Exception as exc:
            logger.debug(f"Vérification mise à jour : {exc}")
            callback(None, "", "")

    Thread(target=_run, daemon=True).start()
