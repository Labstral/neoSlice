# -*- coding: utf-8 -*-
"""neoForge : modèle de projet et compatibilité avec la console (sans noyau)."""
import json

from neoforge.projet.modele import Arrondi, Forme, Projet

CONSOLE = {"neoforge": "1.1", "nom": "platine.nfg", "primitives": [
    {"forme": 0, "op": 0, "pos": [0, 0, 5], "dim": [80, 50, 10], "rot": [0, 0, 0]},
    {"forme": 2, "op": 1, "pos": [-30, -16, 5], "dim": [8, 8, 30], "rot": [0, 0, 0]},
    {"forme": 3, "op": 2, "pos": [0, 0, 10], "dim": [30, 0, 20], "rot": [0, 15, 30]},
]}


def test_projet_console_relu_avec_les_bons_noms():
    p = Projet.depuis_dico(CONSOLE)
    assert [e.forme for e in p.etapes] == ["cube", "cylindre", "cone"]
    assert [e.op for e in p.etapes] == ["matiere", "creux", "intersection"]
    assert p.etapes[2].rot == [0.0, 15.0, 30.0]
    assert p.nom == "platine.nfg"


def test_fichier_ecrit_reste_lisible_par_la_console():
    p = Projet.depuis_dico(CONSOLE)
    p.etapes.append(Arrondi("conge", 1.5, "haut"))
    d = p.dico()
    assert d["primitives"] == CONSOLE["primitives"]       # la console relit ses formes
    assert d["etapes"][-1]["type"] == "arrondi"
    q = Projet.depuis_dico(json.loads(json.dumps(d)))
    assert q.dico() == d


def test_valeurs_abimees_ne_cassent_rien():
    p = Projet.depuis_dico({"etapes": [
        {"type": "forme", "forme": "pyramide", "op": "?", "pos": "x", "dim": [1]},
        {"type": "arrondi", "genre": "??", "taille": "grand", "regle": "zz", "aretes": [3]},
    ]})
    f, a = p.etapes
    assert (f.forme, f.op, f.pos, f.dim) == ("cube", "matiere", [0.0, 0.0, 10.0], [20.0, 20.0, 20.0])
    assert (a.genre_arrondi, a.taille, a.regle, a.aretes) == ("conge", 1.0, "toutes", [])


def test_projet_sans_forme_NE_recoit_PLUS_de_cube():
    """La règle a changé sur demande d'Emmanuel : « quand on lance le logiciel ou
    qu'on fait nouveau, je ne veux voir aucune pièce dans la scène ». Une scène
    sans forme est désormais un état normal, on n'y glisse plus un cube d'office.
    """
    p = Projet.depuis_dico({"etapes": [{"type": "arrondi"}]})
    assert len(p.etapes) == 1 and isinstance(p.etapes[0], Arrondi)
