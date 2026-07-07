"""Ecrit les couleurs choisies par slot dans un 3MF Bambu deja exporte.

Best-effort et NON bloquant : transmet l'intention "slot N = telle couleur" a
Bambu Studio via `filament_colour` dans Metadata/project_settings.config, pour que
le projet s'ouvre deja colore par slot. L'utilisateur doit toujours charger le bon
filament physique dans le bon emplacement AMS ; ceci ne fait que porter l'intention.

Prudence (cf. regles critiques 3MF) : Bambu exige que TOUS les tableaux
`filament_*` aient la meme longueur = nombre de filaments. On aligne donc la
longueur de tous les tableaux `filament_*` sur le nombre de couleurs, en repetant
la derniere valeur. Toute erreur est avalee : l'export reste valide tel quel.
"""
from __future__ import annotations
import json
import os
import shutil
import zipfile
from pathlib import Path

from loguru import logger

_SETTINGS_SUFFIX = "project_settings.config"


def _normalize_hex(c: str) -> str:
    c = (c or "").strip()
    if not c:
        return "#FFFFFF"
    if not c.startswith("#"):
        c = "#" + c
    return c.upper()


def patch_filament_colours(path: str | Path, colors: list[str]) -> bool:
    """Met `filament_colour` = `colors` (par slot 1..N) dans le 3MF `path`.
    Renvoie True si le fichier a ete modifie, False sinon. Ne leve jamais."""
    try:
        path = Path(path)
        colors = [_normalize_hex(c) for c in colors if c]
        if not path.exists() or len(colors) < 2:
            return False
        if not zipfile.is_zipfile(path):
            return False

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            cfg_name = next((n for n in names if n.endswith(_SETTINGS_SUFFIX)), None)
            if cfg_name is None:
                return False
            raw = zf.read(cfg_name)
            others = {n: zf.read(n) for n in names if n != cfg_name}

        try:
            cfg = json.loads(raw.decode("utf-8"))
        except Exception:
            return False
        if not isinstance(cfg, dict):
            return False

        n = len(colors)
        cfg["filament_colour"] = colors
        # Aligner la longueur de tous les tableaux filament_* sur n (Bambu l'exige).
        for k, v in list(cfg.items()):
            if not k.startswith("filament_") or k == "filament_colour":
                continue
            if isinstance(v, list) and v:
                if len(v) < n:
                    cfg[k] = list(v) + [v[-1]] * (n - len(v))
                elif len(v) > n:
                    cfg[k] = v[:n]

        new_raw = json.dumps(cfg, ensure_ascii=False).encode("utf-8")

        tmp = path.with_suffix(path.suffix + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for n_, data in others.items():
                zout.writestr(n_, data)
            zout.writestr(cfg_name, new_raw)
        os.replace(tmp, path)
        logger.info(f"[3MF] filament_colour patché ({n} couleurs) dans {path.name}")
        return True
    except Exception as exc:
        logger.warning(f"[3MF] patch couleurs ignoré : {exc}")
        try:
            _t = Path(path).with_suffix(Path(path).suffix + ".tmp")
            if _t.exists():
                _t.unlink()
        except Exception:
            pass
        return False
