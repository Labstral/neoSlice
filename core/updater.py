"""Vérification des mises à jour en arrière-plan."""
from __future__ import annotations

import json
import urllib.request
from threading import Thread
from typing import Callable

from loguru import logger

from version import __version__ as CURRENT_VERSION

# Fichier latest.json hébergé sur GitHub — mis à jour à chaque release.
# Format : {"version": "0.2.0", "download_url": "...", "notes": ""}
UPDATE_CHECK_URL = (
    "https://raw.githubusercontent.com/Labstral/neoSlice/main/latest.json"
)


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip("v").split("."))
    except Exception:
        return (0, 0, 0)


def check_for_update(callback: Callable[[str | None, str, str], None]) -> None:
    """Lance la vérification dans un thread daemon.

    callback(version, download_url, notes) si une mise à jour est disponible,
    callback(None, "", "") si déjà à jour ou en cas d'erreur réseau.
    """
    if not UPDATE_CHECK_URL:
        return

    def _run():
        try:
            req = urllib.request.Request(
                UPDATE_CHECK_URL,
                headers={"User-Agent": f"neoSlice/{CURRENT_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            latest = data.get("version", "").strip("v")
            url    = data.get("download_url", "https://github.com/Labstral/neoSlice/releases/latest")
            notes  = data.get("notes", "")
            if latest and _parse_version(latest) > _parse_version(CURRENT_VERSION):
                callback(latest, url, notes)
            else:
                callback(None, "", "")
        except Exception as exc:
            logger.debug(f"Vérification mise à jour : {exc}")
            callback(None, "", "")

    Thread(target=_run, daemon=True).start()
