# -*- coding: utf-8 -*-
"""neoForge : fichiers .nfg, sauvegarde automatique, projets récents."""
import json

from neoforge.projet import nfg
from neoforge.projet.modele import Arrondi, Forme, Projet


def _isoler(tmp_path, monkeypatch):
    monkeypatch.setattr(nfg, "AUTO", tmp_path / "travail.nfg")
    monkeypatch.setattr(nfg, "RECENTS", tmp_path / "recents.json")


def test_aller_retour_fichier(tmp_path, monkeypatch):
    _isoler(tmp_path, monkeypatch)
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [80, 50, 10]),
                Forme("cylindre", "creux", [-30, -16, 5], [8, 8, 30])])
    p.etapes.append(Arrondi("conge", 2, "haut"))
    chemin = nfg.ecrire(p, tmp_path / "support")
    assert chemin.name == "support.nfg"
    q = nfg.lire(chemin)
    assert q.nom == "support" and q.dico()["etapes"] == p.dico()["etapes"]
    assert nfg.recents() == [chemin]


def test_projet_de_la_console_relu(tmp_path, monkeypatch):
    _isoler(tmp_path, monkeypatch)
    console = {"neoforge": "1.1", "nom": "piece_001.nfg", "primitives": [
        {"forme": 0, "op": 0, "pos": [0, 0, 5], "dim": [40, 40, 10], "rot": [0, 0, 0]}]}
    f = tmp_path / "piece_001.nfg"
    f.write_text(json.dumps(console), encoding="utf-8")
    p = nfg.lire(f)
    assert isinstance(p.etapes[0], Forme) and p.etapes[0].dim == [40, 40, 10]


def test_reprise_apres_arret_brutal(tmp_path, monkeypatch):
    _isoler(tmp_path, monkeypatch)
    assert not nfg.auto_disponible()
    p = Projet([Forme("cube", "matiere", [0, 0, 15], [12, 34, 56])])
    nfg.auto_enregistrer(p, tmp_path / "en_cours.nfg")
    assert nfg.auto_disponible()
    repris, fichier = nfg.auto_lire()
    assert repris.etapes[0].dim == [12, 34, 56]
    assert fichier == tmp_path / "en_cours.nfg"
    nfg.auto_effacer()
    assert not nfg.auto_disponible() and nfg.auto_lire() is None


def test_recents_sans_doublon_et_bornes(tmp_path, monkeypatch):
    _isoler(tmp_path, monkeypatch)
    for i in range(nfg.MAX_RECENTS + 3):
        nfg.ecrire(Projet.nouveau(), tmp_path / f"p{i}")
    liste = nfg.recents()
    assert len(liste) == nfg.MAX_RECENTS
    assert liste[0].stem == f"p{nfg.MAX_RECENTS + 2}"          # le dernier en tête
    nfg.ajouter_recent(liste[3])
    assert nfg.recents()[0] == liste[3]
    assert len(nfg.recents()) == nfg.MAX_RECENTS
    disparu = liste[1]
    disparu.unlink()
    assert disparu not in nfg.recents()                        # fichier supprimé : oublié
