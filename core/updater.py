"""Vérification des mises à jour en arrière-plan."""
from __future__ import annotations

import json
import urllib.request
from threading import Thread
from typing import Callable

from loguru import logger

CURRENT_VERSION = "0.1.0"

# URL vers un fichier JSON hébergé contenant {"version": "0.1.1", "url": "..."}
# Laisser vide pour désactiver la vérification.
UPDATE_CHECK_URL = ""


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip("v").split("."))
    except Exception:
        return (0, 0, 0)


def check_for_update(callback: Callable[[str | None], None]) -> None:
    """Lance la vérification dans un thread daemon.

    callback est appelé avec la nouvelle version (str) si disponible,
    ou None si déjà à jour ou en cas d'erreur réseau.
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
            if latest and _parse_version(latest) > _parse_version(CURRENT_VERSION):
                callback(latest)
            else:
                callback(None)
        except Exception as exc:
            logger.debug(f"Vérification mise à jour : {exc}")
            callback(None)

    Thread(target=_run, daemon=True).start()
