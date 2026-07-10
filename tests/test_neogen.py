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


# ================= Bibliotheque (catalogue) & atelier libre =================
def test_catalogue_complet_construit():
    """Chaque entree du catalogue se construit avec ses defauts (etanche)."""
    import trimesh
    from core.neogen import catalogue as C
    assert len(C.CATALOGUE) >= 50
    for e in C.CATALOGUE:
        if e["image"]:
            continue   # logo : demande un fichier (teste a part)
        params = {"texte": "Test"} if e["texte"] == "requis" else {}
        piece = C.construire(e["id"], params)
        if isinstance(piece, trimesh.Scene):
            assert all(g.is_watertight for g in piece.geometry.values()), e["id"]
        else:
            assert piece.is_watertight, e["id"]
            assert piece.bounds[0][2] < 0.01, e["id"] + " pas au sol"


def test_catalogue_bornes():
    from core.neogen import catalogue as C
    p = C.construire("de", {"taille": 9999})   # borne a 40
    d = p.bounds[1] - p.bounds[0]
    assert d[0] <= 41


def test_sandbox_interdictions():
    from core.neogen import libre as L
    import pytest as _pt
    for code in ("import os", "exec('x')", "open('f')", "__import__('os')"):
        with _pt.raises(ValueError):
            L.executer_sandbox(code)


def test_sandbox_kit_polymorphe():
    """percer/deplacer acceptent 2D et 3D (le modele les melange)."""
    from core.neogen import libre as L
    piece = L.executer_sandbox(
        "d = disque(30)\n"
        "d = percer(d, disque(10))\n"          # 2D - 2D
        "rondelle = extrusion(d, 4)\n"
        "piece = percer(rondelle, deplacer(disque(4), 8, 0, 0))\n"  # 3D - 2D auto-extrude
    )
    assert piece.is_watertight


def test_sandbox_piece_2d_refusee():
    from core.neogen import libre as L
    import pytest as _pt
    with _pt.raises(ValueError):
        L.executer_sandbox("piece = disque(30)")


def test_cookbook_retrieval():
    from core.neogen.libre import _exemples_pertinents
    ex = _exemples_pertinents("un bol de soupe")
    assert ex and "bol" in ex[0][0]
    ex2 = _exemples_pertinents("une pyramide egyptienne")
    assert ex2 and "pyramide" in ex2[0][0]


def test_verifier_rejette_geant_et_flottant():
    from core.neogen import libre as L
    p = L.boite_3d(500, 10, 10)
    assert L.verifier(p) is not None            # trop grand
    p2 = L.deplacer(L.boite_3d(10, 10, 10), 0, 0, 30)
    assert L.verifier(p2) is not None           # flottant


def test_installation_marker(tmp_path, monkeypatch):
    from core.neogen import installation as I
    monkeypatch.setattr(I, "NEOGEN_DIR", tmp_path)
    monkeypatch.setattr(I, "MARKER", tmp_path / "installed.json")
    # CRUCIAL : nom factice, sinon desinstaller() supprimerait le VRAI modele
    # 14b du serveur Ollama local (vecu : pytest a efface 9 Go...).
    monkeypatch.setattr(I, "MODELE", "test-modele-inexistant")
    assert not I.est_installe()
    (tmp_path / "installed.json").write_text("{}")
    assert I.est_installe()
    I.desinstaller()
    assert not I.est_installe()


def test_entonnoir_canal_traversant():
    """REGRESSION : l'entonnoir doit etre OUVERT de bout en bout (le profil
    referme sur l'axe le BOUCHAIT — 5/12 points de l'axe dans la matiere)."""
    import numpy as np
    from core.neogen.formes import entonnoir
    p = entonnoir(80, 12, 70)
    zs = np.linspace(1, p.bounds[1][2] - 1, 12)
    assert int(p.contains([[0, 0, z] for z in zs]).sum()) == 0
    assert p.is_watertight


def test_cookbook_recettes_toutes_valides():
    """Les 50 recettes du cookbook DOIVENT s'executer et passer le verificateur
    (ce sont les exemples montres au modele : zero tolerance)."""
    from core.neogen import libre as L
    for _cles, demande, code in L.COOKBOOK:
        p = L.poser_au_sol(L.executer_sandbox(code))
        assert L.verifier(p) is None, demande
