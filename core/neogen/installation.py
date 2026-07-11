# -*- coding: utf-8 -*-
"""neoGen — installation/désinstallation (indépendante de l'assistant Oen).

neoGen utilise SON propre modèle (qwen3:14b, ~9 Go) téléchargé depuis le
registre Ollama, distinct du 8B d'Oen. L'utilisateur installe/désinstalle
chacun librement depuis les réglages.

Prérequis : le runtime Ollama (installé avec Oen ou via son installateur).
Si absent, l'UI invite à installer d'abord l'assistant.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from core.assistant.engine import HOST, OLLAMA_EXE

NEOGEN_DIR = Path.home() / ".neoslice" / "neogen"
MARKER = NEOGEN_DIR / "installed.json"
MODELE = "gemma4:12b"
TAILLE_GO = 7.6


def runtime_present() -> bool:
    """Le runtime Ollama est-il disponible (installé par Oen) ?"""
    return OLLAMA_EXE.exists()


def modele_present() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}/api/tags", timeout=5) as r:
            tags = json.loads(r.read())
        return any(m.get("name", "").startswith(MODELE)
                   for m in tags.get("models", []))
    except Exception:
        return False


def est_installe() -> bool:
    return MARKER.exists()


def installer(progress_cb=None) -> None:
    """Télécharge le modèle neoGen (bloquant — appeler depuis un QThread).
    progress_cb(pct: int, statut: str) est appelé pendant le téléchargement."""
    if not runtime_present():
        raise RuntimeError("Le runtime IA n'est pas installé — installez "
                           "d'abord l'assistant Oen dans les réglages.")
    from core.neogen.pilote import _preparer_moteur
    _preparer_moteur()
    corps = json.dumps({"name": MODELE, "stream": True}).encode("utf-8")
    req = urllib.request.Request(f"http://{HOST}/api/pull", data=corps,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=24 * 3600) as r:
        for ligne in r:
            try:
                d = json.loads(ligne)
            except Exception:
                continue
            if progress_cb and d.get("total"):
                pct = int(100 * d.get("completed", 0) / max(d["total"], 1))
                progress_cb(pct, d.get("status", ""))
            if d.get("error"):
                raise RuntimeError(d["error"])
    if not modele_present():
        raise RuntimeError("Le modèle n'a pas pu être téléchargé.")
    NEOGEN_DIR.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({"modele": MODELE}), encoding="utf-8")


def desinstaller() -> None:
    """Supprime le modèle neoGen (libère ~9 Go) et le marqueur."""
    try:
        corps = json.dumps({"name": MODELE}).encode("utf-8")
        req = urllib.request.Request(f"http://{HOST}/api/delete", data=corps,
                                     method="DELETE",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60)
    except Exception:
        pass   # serveur éteint : le marqueur reste la référence
    if MARKER.exists():
        MARKER.unlink()
