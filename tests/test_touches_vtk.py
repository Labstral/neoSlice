# -*- coding: utf-8 -*-
"""Les raccourcis clavier cachés de VTK doivent rester muselés.

« Quand j'appuie sur S la grille a disparu » (Emmanuel, 2026-09-26). Ce n'était
pas un défaut d'affichage : le style d'interaction de VTK écoute le clavier et
répond de lui même à une dizaine de lettres, sans que rien ne l'annonce.

Mesuré au pilote sur la vue 3D de neoForge, avant correction :
    au départ           grille = fil de fer
    après la touche S   grille = SURFACE      → la grille disparaît
    après la touche W   grille = fil de fer   → elle revient

Et les autres sont pires : `e` et `q` demandent la sortie de l'application,
`r` recadre la caméra, `f` y projette la vue, `p` déclenche une désignation,
`3` bascule en stéréo. Après correction, les huit touches ne font plus rien, la
caméra ne bouge pas, la fenêtre reste ouverte, et la touche Suppr continue
d'arriver par Qt.

Ce test ne construit aucune fenêtre (aucun test du projet ne le fait) : il
vérifie que le muselage est bien POSÉ dans les deux viewers, puisque c'est son
absence qui a causé le défaut.
"""
import ast
from pathlib import Path

import pytest

_RACINE = Path(__file__).resolve().parents[1]
_VIEWERS = [_RACINE / "neoforge" / "ui" / "viewer.py",
            _RACINE / "ui" / "components" / "viewer_3d.py"]


def _methodes(fichier):
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)}


@pytest.mark.parametrize("fichier", _VIEWERS, ids=lambda f: f.name)
def test_le_muselage_existe(fichier):
    assert "_museler_les_touches_vtk" in _methodes(fichier), fichier.name


@pytest.mark.parametrize("fichier", _VIEWERS, ids=lambda f: f.name)
def test_le_muselage_retire_bien_les_deux_ecoutes(fichier):
    """Retirer CharEvent seul ne suffit pas, et KeyPressEvent seul non plus."""
    corps = ast.get_source_segment(
        fichier.read_text(encoding="utf-8"),
        _methodes(fichier)["_museler_les_touches_vtk"])
    assert 'RemoveObservers("CharEvent")' in corps, fichier.name
    assert 'RemoveObservers("KeyPressEvent")' in corps, fichier.name


@pytest.mark.parametrize("fichier", _VIEWERS, ids=lambda f: f.name)
def test_le_muselage_est_appele_a_la_construction(fichier):
    """Une méthode jamais appelée ne protège de rien."""
    texte = fichier.read_text(encoding="utf-8")
    appels = [n for n in ast.walk(ast.parse(texte))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "_museler_les_touches_vtk"]
    assert appels, f"{fichier.name} : le muselage n'est jamais appelé"
