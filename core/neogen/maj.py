# -*- coding: utf-8 -*-
"""Auto-mise-à-jour de la BASE D'OBJETS de neoGen, SANS rebuild de l'app.

Même canal que la KB d'Oen : un `neogen_cookbook.json` hébergé sur la release
GitHub d'assets. Il contient des RECETTES supplémentaires pour l'atelier libre
(exemples montrés au modèle : plus il y en a, plus la création sur mesure est
fiable et variée).

Garanties :
  - HORS-LIGNE-SAFE : toute erreur réseau => on garde la base actuelle.
  - VALIDATION SANDBOX : chaque recette téléchargée est EXÉCUTÉE dans le bac à
    sable (interdictions d'import) puis passée au vérificateur (étanche, un
    seul tenant, imprimable). Une recette qui échoue est simplement écartée —
    du code distant n'atteint JAMAIS l'utilisateur sans être prouvé sain.
  - ATOMIQUE : écriture en .tmp puis os.replace.

Format attendu de neogen_cookbook.json :
{
  "version": "2026-07-11",
  "notes": "20 nouvelles recettes",
  "recettes": [
    {"cles": "bol soupe cuisine", "demande": "un bol de soupe",
     "code": "piece = demi_sphere(110, creuse=3)"}
  ]
}
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from loguru import logger

ASSET_BASE_URL = ("https://github.com/labstral/neoslice-assets/releases/"
                  "download/assistant-latest")
COOKBOOK_URL = f"{ASSET_BASE_URL}/neogen_cookbook.json"
FICHIER_LOCAL = Path.home() / ".neoslice" / "neogen" / "cookbook_extra.json"
TIMEOUT = 20


def version_locale() -> str | None:
    try:
        return json.loads(FICHIER_LOCAL.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def verifier_maj() -> dict | None:
    """Télécharge le manifest ; renvoie le dict s'il est PLUS RÉCENT que la
    version locale, sinon None. Jamais d'exception (hors-ligne-safe)."""
    try:
        req = urllib.request.Request(COOKBOOK_URL,
                                     headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data.get("recettes"), list) or not data.get("version"):
            return None
        if data["version"] == version_locale():
            return None
        return data
    except Exception as exc:
        logger.debug(f"neoGen maj cookbook : {exc}")
        return None


def appliquer(manifest: dict, progress_cb=None) -> tuple[int, int]:
    """Valide CHAQUE recette en sandbox + vérificateur, écrit atomiquement les
    seules recettes prouvées saines. Renvoie (acceptées, écartées)."""
    from core.neogen import libre as L
    valides, ecartees = [], 0
    recettes = manifest.get("recettes", [])
    for i, r in enumerate(recettes):
        if progress_cb:
            progress_cb(f"{i + 1}/{len(recettes)}", (i + 1) / max(1, len(recettes)))
        try:
            cles, demande, code = str(r["cles"]), str(r["demande"]), str(r["code"])
            piece = L.poser_au_sol(L.executer_sandbox(code))
            if L.verifier(piece) is None:
                valides.append({"cles": cles, "demande": demande, "code": code})
            else:
                ecartees += 1
        except Exception:
            ecartees += 1
    FICHIER_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER_LOCAL.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": manifest["version"],
                               "notes": manifest.get("notes", ""),
                               "recettes": valides},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FICHIER_LOCAL)
    L.recharger_extra()
    logger.info(f"neoGen cookbook {manifest['version']} : "
                f"{len(valides)} recettes, {ecartees} écartées")
    return len(valides), ecartees


def charger_extra() -> list[tuple[str, str, str]]:
    """Recettes supplémentaires installées (déjà validées à l'installation)."""
    try:
        data = json.loads(FICHIER_LOCAL.read_text(encoding="utf-8"))
        return [(r["cles"], r["demande"], r["code"])
                for r in data.get("recettes", [])]
    except Exception:
        return []


# ═══════════════════ OBJETS COMPLETS de la bibliothèque (sans rebuild) ══════
# En plus du cookbook (aide à la création libre), on met à jour la BIBLIOTHÈQUE
# elle-même : des objets neoGen complets (avec formulaire de réglages) qui
# apparaissent dans le menu et la recherche. Même canal, mêmes garanties.
OBJETS_URL = f"{ASSET_BASE_URL}/neogen_objets.json"


def _fichier_objets() -> Path:
    from core.neogen.objets_module import FICHIER_LOCAL as _F
    return _F


def _version_objets_locale() -> str | None:
    try:
        return json.loads(_fichier_objets().read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def verifier_maj_objets() -> dict | None:
    """Télécharge la liste d'objets ; renvoie le manifest s'il est PLUS RÉCENT
    que la version locale, sinon None. Jamais d'exception (hors-ligne-safe)."""
    try:
        req = urllib.request.Request(OBJETS_URL, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data.get("objets"), list) or not data.get("version"):
            return None
        if data["version"] == _version_objets_locale():
            return None
        return data
    except Exception as exc:
        logger.debug(f"neoGen maj objets : {exc}")
        return None


def appliquer_objets(manifest: dict, progress_cb=None) -> tuple[int, int]:
    """VALIDE chaque objet (sandbox + vérificateur, params par défaut) puis écrit
    atomiquement les seuls objets prouvés sains. Renvoie (acceptés, écartés).
    Du code distant n'atteint JAMAIS l'utilisateur sans être prouvé imprimable."""
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts, FICHIER_LOCAL
    valides, ecartes = [], 0
    objets = manifest.get("objets", [])
    for i, obj in enumerate(objets):
        if progress_cb:
            progress_cb(f"{i + 1}/{len(objets)}", (i + 1) / max(1, len(objets)))
        try:
            if not obj.get("id") or not obj.get("code"):
                ecartes += 1
                continue
            ns = _defauts(obj)
            if obj.get("texte", "aucun") != "aucun":
                ns["texte"] = "Test"
            piece = L.poser_au_sol(L.executer_sandbox(str(obj["code"]), ns))
            if L.verifier(piece) is None:
                valides.append(obj)
            else:
                ecartes += 1
        except Exception:
            ecartes += 1
    FICHIER_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER_LOCAL.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": manifest["version"],
                               "notes": manifest.get("notes", ""),
                               "objets": valides},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FICHIER_LOCAL)
    logger.info(f"neoGen objets {manifest['version']} : "
                f"{len(valides)} objets, {ecartes} écartés")
    return len(valides), ecartes
