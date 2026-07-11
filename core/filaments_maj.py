# -*- coding: utf-8 -*-
"""Auto-mise-à-jour de la BIBLIOTHÈQUE DE FILAMENTS PAR MARQUE, sans rebuild.

Même canal que la KB d'Oen et la base d'objets neoGen : un
`filament_brands.json` hébergé sur la release GitHub d'assets. Ajouter une
marque ou corriger une fiche = mettre à jour l'asset, tous les utilisateurs
en profitent au prochain lancement.

Garanties :
  - HORS-LIGNE-SAFE : toute erreur réseau => on garde la base actuelle,
    jamais d'exception qui remonte à l'UI.
  - LE CODE A LE DERNIER MOT : le chargeur (data/filaments.py) borne chaque
    valeur (_BORNES_PRODUIT) et écarte tout produit à base inconnue ou champ
    aberrant — une fiche corrompue ne peut pas produire de mauvais réglages.
  - ATOMIQUE : écriture en .tmp puis os.replace.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from loguru import logger

ASSET_BASE_URL = ("https://github.com/labstral/neoslice-assets/releases/"
                  "download/assistant-latest")
BRANDS_URL = f"{ASSET_BASE_URL}/filament_brands.json"
FICHIER_LOCAL = Path.home() / ".neoslice" / "filaments" / "brands.json"
TIMEOUT = 20


def verifier_et_appliquer() -> str | None:
    """Télécharge la base ; si sa version est plus récente que celle chargée,
    l'installe (atomique) et recharge la bibliothèque. Renvoie la nouvelle
    version, ou None (à jour / hors-ligne / fichier invalide)."""
    from data import filaments as F
    try:
        req = urllib.request.Request(BRANDS_URL, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        version = str(data.get("version", ""))
        if not version or not isinstance(data.get("marques"), dict):
            return None
        if version <= (F.MARQUES_VERSION or ""):
            return None                       # déjà à jour (dates ISO)
        FICHIER_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        tmp = FICHIER_LOCAL.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, FICHIER_LOCAL)
        F.recharger_marques()                 # bornes appliquées au chargement
        logger.info(f"Bibliothèque filaments {version} installée "
                    f"({sum(len(p) for p in data['marques'].values())} produits)")
        return version
    except Exception as exc:
        logger.debug(f"maj bibliothèque filaments : {exc}")
        return None
