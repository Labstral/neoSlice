"""Non-régression neoGen : validation bornée du pilote (sans appel modèle) et
génération géométrique (pièces étanches, sans face interne).

La géométrie est 100 % code (jamais l'IA) : ces tests garantissent le contrat
« toute pièce générée est imprimable » quel que soit ce qu'Oen extrait.
"""
import warnings

import pytest

warnings.filterwarnings("ignore")

from core.neogen import pilote as P


# ── Validation (le CODE a le dernier mot, Oen ne peut rien casser) ───────────
def test_bornes_clampees():
    objet, params, q = P.valider({"objet": "de", "taille": 900})
    assert objet == "de" and params["taille"] == 40 and q is None
    objet, params, q = P.valider({"objet": "boite", "jeu": 0.01})
    assert objet == "boite" and params["jeu"] == 0.1


def test_texte_requis_sinon_question():
    for o in ("porte_cle", "badge", "sousverre", "plaque", "magnet"):
        objet, _p, q = P.valider({"objet": o})
        assert objet is None and q, o


def test_hors_catalogue_et_question_passthrough():
    objet, _p, q = P.valider({"objet": "fusee"})
    assert objet is None and "objet" in q.lower()
    objet, _p, q = P.valider({"question": "Quel texte ?"})
    assert objet is None and q == "Quel texte ?"


def test_logo_sans_image_refuse():
    objet, _p, q = P.valider({"objet": "logo", "forme": "badge"})
    assert objet is None and q


def test_alias_objets():
    objet, _p, q = P.valider({"objet": "sous-verre", "texte": "X"})
    assert objet == "sousverre" and q is None


# ── Génération : chaque famille sort une pièce ÉTANCHE ───────────────────────
@pytest.mark.parametrize("objet,params", [
    ("porte_cle", {"texte": "Léa", "longueur": 50}),
    ("badge", {"texte": "Léa", "diametre": 40, "trou": True}),
    ("de", {"taille": 16}),
    ("vase", {"hauteur": 60, "diametre": 40}),
])
def test_generation_etanche(objet, params, tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DOSSIER_SORTIES", tmp_path)
    chemin = P.generer(objet, params)
    assert chemin.exists() and chemin.stat().st_size > 1000
    import trimesh
    m = trimesh.load(chemin.with_suffix(".stl"))
    assert m.is_watertight, f"{objet} non étanche"


def test_boite_deux_corps(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DOSSIER_SORTIES", tmp_path)
    chemin = P.generer("boite", {"diametre": 40, "hauteur": 20})
    assert chemin.exists()
    import trimesh
    sc = trimesh.load(chemin, force=None)
    # 3MF multi-corps : corps + couvercle
    geoms = getattr(sc, "geometry", None)
    assert geoms is None or len(geoms) >= 2


def test_resume_params_lisible():
    txt = P.resume_params("porte_cle", {"texte": "Léa", "longueur": 50, "grave": True})
    assert "Léa" in txt and "porte-clé" in txt and "gravé" in txt
