# -*- coding: utf-8 -*-
"""Choix de l'interpréteur pour neoForge.

Le noyau de CAO est compilé pour Python 3.12. L'application distribuée embarque
cette version, mais depuis les sources neoSlice peut tourner avec une autre
(ici Python 3.14) : neoForge doit alors être lancé avec le Python 3.12 du
projet, sans rien demander à l'utilisateur. Retour d'Emmanuel 2026-09-12 :
« neoForge n'a pas pu démarrer », parce que son python par défaut est 3.14."""
import sys
from pathlib import Path

from core.neoforge import pont as P

RACINE = Path(__file__).resolve().parent.parent


def test_meme_python_si_version_du_noyau():
    assert P.interpreteur_neoforge(version=P.PYTHON_NOYAU) == sys.executable


def test_python_du_projet_si_version_differente():
    choisi = Path(P.interpreteur_neoforge(version=(3, 14)))
    venv = RACINE / ".venv312"
    if not venv.exists():                       # machine sans le venv de build
        assert str(choisi) == sys.executable
        return
    assert venv in choisi.parents, choisi
    assert choisi.exists()


def test_commande_de_lancement_passe_par_main_py():
    prog, args = P._commande([P.ARG_NEOFORGE], python="C:/py/python.exe")
    assert prog == "C:/py/python.exe"
    assert Path(args[0]).name == "main.py" and args[1] == "--neoforge"
