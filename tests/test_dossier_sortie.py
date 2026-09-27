# -*- coding: utf-8 -*-
"""Dossier proposé par TOUTES les fenêtres d'enregistrement.

« Il faut que quand on enregistre ça aille de base dans téléchargement »
(Emmanuel, 2026-09-24). Plusieurs fenêtres ne donnaient aucun dossier, elles
s'ouvraient donc sur le dossier courant du programme ; d'autres codaient
« Downloads » en dur, ce qui rate le dossier d'un Windows en français et ignore
le réglage d'export. Il n'y a désormais qu'une seule fonction.
"""
from pathlib import Path

import pytest


def test_dossier_sortie_existe():
    from core.prefs import dossier_sortie
    d = dossier_sortie()
    assert isinstance(d, Path) and d.is_dir()


def test_reglage_utilisateur_prioritaire(tmp_path, monkeypatch):
    """Le dossier choisi dans les réglages passe avant Téléchargements."""
    from core import prefs
    monkeypatch.setattr(prefs.PREFS, "get",
                        lambda cle, defaut=None: (str(tmp_path)
                                                  if cle == "export_folder" else defaut))
    assert prefs.dossier_sortie() == tmp_path


def test_reglage_vers_dossier_disparu_ne_casse_rien(monkeypatch):
    """Un dossier réglé puis supprimé ne doit pas rendre un chemin mort."""
    from core import prefs
    monkeypatch.setattr(prefs.PREFS, "get",
                        lambda cle, defaut=None: (r"Z:\\nexiste\\pas"
                                                  if cle == "export_folder" else defaut))
    assert prefs.dossier_sortie().is_dir()


def test_neoforge_suit_le_meme_dossier():
    from core.prefs import dossier_sortie
    from neoforge.projet import nfg
    assert nfg.dossier_sortie() == dossier_sortie()


def test_neoforge_reste_a_cote_de_la_piece_ouverte(tmp_path):
    """Une pièce déjà enregistrée se ré-enregistre et s'exporte là où elle est,
    pas ailleurs."""
    from neoforge.projet import nfg
    piece = tmp_path / "support.nfg"
    piece.write_text("{}", encoding="utf-8")
    assert nfg.dossier_sortie(piece) == tmp_path


def test_aucune_fenetre_denregistrement_sans_dossier():
    """Garde-fou : une fenêtre d'enregistrement à qui on ne passe qu'un NOM de
    fichier s'ouvre là où le programme a été lancé. On vérifie donc que chaque
    appel part d'un chemin, jamais d'un simple nom."""
    import re
    racine = Path(__file__).resolve().parents[1]
    # Le chemin proposé est parfois préparé quelques lignes plus haut : on
    # regarde donc le voisinage de l'appel, pas seulement ses parenthèses.
    sources = ("dossier_sortie", "_dossier_export_defaut", "dossier_export",
               "start_dir", "start /", "downloads", "out /", "setDirectory")
    fautes = []
    for f in list((racine / "ui").rglob("*.py")) + list((racine / "neoforge").rglob("*.py")):
        lignes = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, ligne in enumerate(lignes):
            if "getSaveFileName(" not in ligne:
                continue
            voisinage = "\n".join(lignes[max(0, i - 25):i + 6])
            if not any(s in voisinage for s in sources):
                fautes.append(f"{f.relative_to(racine)}:{i + 1}  {ligne.strip()[:80]}")
    assert not fautes, ("fenêtres d'enregistrement sans dossier proposé :\n"
                        + "\n".join(fautes))
