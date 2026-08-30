"""Mes machines — imprimantes épinglées par l'utilisateur (retour Dominique).

Un possesseur de plusieurs machines de MARQUES différentes (ex. Bambu X1C +
Snapmaker U1) devait passer par Réglages → changer de slicer de sortie → re-choisir
l'imprimante. Ici : il épingle ses machines (★ à côté du sélecteur), elles
apparaissent en tête du menu imprimante dans un groupe « Mes machines », et en
choisir une bascule automatiquement slicer + imprimante d'un seul geste.

Stockage : PREFS["mes_machines"] = [{"slicer": code, "printer": clé, "label": nom}].
"""
from __future__ import annotations

from core.prefs import PREFS

_KEY = "mes_machines"

# Libellés courts des slicers de sortie (pour « X1 Carbon · Bambu Studio »)
SLICER_LABELS = {
    "bambu": "Bambu Studio", "orca": "OrcaSlicer", "prusa": "PrusaSlicer",
    "creality": "CrealityPrint", "elegoo": "ElegooSlicer",
    "anycubic": "AnycubicSlicer", "snapmaker": "Snapmaker Orca",
    "cura": "UltiMaker Cura", "flashprint": "FlashPrint",
}


def slicer_label(code: str) -> str:
    return SLICER_LABELS.get(code, code or "?")


def list_machines() -> list[dict]:
    """Machines épinglées, entrées valides uniquement."""
    out = []
    for m in PREFS.get(_KEY, []) or []:
        if isinstance(m, dict) and m.get("slicer") and m.get("printer"):
            out.append({"slicer": str(m["slicer"]), "printer": str(m["printer"]),
                        "label": str(m.get("label") or m["printer"])})
    return out


def is_pinned(slicer: str, printer: str) -> bool:
    return any(m["slicer"] == slicer and m["printer"] == printer
               for m in list_machines())


def pin(slicer: str, printer: str, label: str = "") -> bool:
    """Épingle une machine (dédupliquée). True si ajoutée."""
    if not slicer or not printer or is_pinned(slicer, printer):
        return False
    items = list_machines()
    items.append({"slicer": slicer, "printer": printer,
                  "label": label or printer})
    PREFS.set(_KEY, items)
    return True


def unpin(slicer: str, printer: str) -> bool:
    items = list_machines()
    new = [m for m in items if not (m["slicer"] == slicer and m["printer"] == printer)]
    if len(new) != len(items):
        PREFS.set(_KEY, new)
        return True
    return False


def toggle(slicer: str, printer: str, label: str = "") -> bool:
    """Épingle/désépingle. Renvoie l'état FINAL (True = épinglée)."""
    if is_pinned(slicer, printer):
        unpin(slicer, printer)
        return False
    pin(slicer, printer, label)
    return True


# Clés spéciales du menu « Mes machines » dans le sélecteur d'imprimante
MM_PREFIX = "@mm:"


def machine_key(m: dict) -> str:
    return f"{MM_PREFIX}{m['slicer']}:{m['printer']}"


def parse_machine_key(key: str) -> tuple[str, str] | None:
    """"@mm:<slicer>:<printer>" -> (slicer, printer) — None si autre clé."""
    if not key or not key.startswith(MM_PREFIX):
        return None
    body = key[len(MM_PREFIX):]
    slicer, sep, printer = body.partition(":")
    if not sep or not slicer or not printer:
        return None
    return slicer, printer
