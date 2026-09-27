# -*- coding: utf-8 -*-
"""Fichiers de projet .nfg : lecture, écriture, sauvegarde automatique et
projets récents.

Les projets sont rangés dans Documents/neoForge : ils appartiennent à
l'utilisateur et ne sont JAMAIS touchés par une désinstallation du module.
La sauvegarde automatique vit à côté (~/.neoslice), pour survivre elle aussi à
une réinstallation : si le noyau de CAO plante, la pièce en cours est reprise
au prochain lancement.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from neoforge.projet.modele import Projet

AUTO = Path.home() / ".neoslice" / "neoforge_travail.nfg"
RECENTS = Path.home() / ".neoslice" / "neoforge_recents.json"
MAX_RECENTS = 8
PREFS = Path.home() / ".neoslice" / "prefs.json"      # partagé avec neoSlice


def dossier_projets() -> Path:
    """Documents/neoForge (créé au besoin) ; repli sur le dossier personnel."""
    try:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation)
    except Exception:
        base = ""
    d = Path(base or Path.home()) / "neoForge"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        return Path.home()
    return d


def dossier_sortie(chemin_courant: Path | None = None) -> Path:
    """Où proposer d'enregistrer ou d'exporter.

    À côté de la pièce en cours si elle a déjà un fichier, sinon dans le dossier
    de sortie de neoSlice, c'est à dire Téléchargements (demande d'Emmanuel,
    2026-09-24). Documents/neoForge restait le dossier proposé partout, alors
    que les fichiers qu'on sort d'ici partent aussitôt vers une imprimante ou
    un message : ils vont dans Téléchargements comme tout le reste.
    """
    if chemin_courant is not None:
        try:
            if chemin_courant.parent.is_dir():
                return chemin_courant.parent
        except Exception:
            pass
    try:
        from core.prefs import dossier_sortie as _partage
        return _partage()
    except Exception:
        d = Path.home() / "Downloads"
        return d if d.is_dir() else Path.home()


def _ecrire_json(chemin: Path, donnees: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, chemin)


def unite() -> str:
    """L'unité d'affichage choisie (mm par défaut).

    Elle est rangée dans les préférences de neoSlice, comme le thème : elle
    survit ainsi à une réinstallation du module."""
    from neoforge.projet import unites as U
    try:
        donnees = json.loads(PREFS.read_text(encoding="utf-8"))
        return U.connue(donnees.get("neoforge_unite"))
    except Exception:
        return U.DEFAUT


def definir_unite(choix: str) -> str:
    """Écrit l'unité SANS toucher au reste du fichier : il est partagé avec
    neoSlice, qui y garde notamment le thème."""
    from neoforge.projet import unites as U
    retenue = U.connue(choix)
    donnees = {}
    try:
        lu = json.loads(PREFS.read_text(encoding="utf-8"))
        if isinstance(lu, dict):
            donnees = lu
    except Exception:
        donnees = {}
    donnees["neoforge_unite"] = retenue
    try:
        _ecrire_json(PREFS, donnees)
    except Exception:
        pass                       # un disque plein ne doit rien faire planter
    return retenue


def lire(chemin: str | Path) -> Projet:
    p = Projet.depuis_dico(json.loads(Path(chemin).read_text(encoding="utf-8")))
    p.nom = Path(chemin).stem
    return p


def ecrire(projet: Projet, chemin: str | Path) -> Path:
    chemin = Path(chemin)
    if chemin.suffix.lower() != ".nfg":
        chemin = chemin.with_suffix(".nfg")
    projet.nom = chemin.stem
    _ecrire_json(chemin, projet.dico())
    ajouter_recent(chemin)
    return chemin


# ── Reprise après un arrêt brutal ───────────────────────────────────────────
def auto_enregistrer(projet: Projet, chemin_projet: Path | None = None) -> None:
    try:
        d = projet.dico()
        d["_fichier"] = str(chemin_projet) if chemin_projet else ""
        _ecrire_json(AUTO, d)
    except Exception:
        pass                        # une sauvegarde auto ne doit jamais gêner


def auto_disponible() -> bool:
    return AUTO.is_file()


def auto_lire() -> tuple[Projet, Path | None] | None:
    try:
        d = json.loads(AUTO.read_text(encoding="utf-8"))
        fichier = d.get("_fichier") or ""
        return Projet.depuis_dico(d), (Path(fichier) if fichier else None)
    except Exception:
        return None


def auto_effacer() -> None:
    try:
        AUTO.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


# ── Projets récents ─────────────────────────────────────────────────────────
def recents() -> list[Path]:
    try:
        liste = json.loads(RECENTS.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [Path(x) for x in liste if isinstance(x, str) and Path(x).is_file()]


def ajouter_recent(chemin: str | Path) -> None:
    chemin = str(Path(chemin).resolve())
    liste = [str(p) for p in recents() if str(p.resolve()) != chemin]
    liste.insert(0, chemin)
    try:
        _ecrire_json(RECENTS, liste[:MAX_RECENTS])
    except Exception:
        pass
