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


def test_texte_optionnel_sauf_lettre():
    """Le texte est OPTIONNEL (pièce nue valable) — sauf lettre_3d où il EST
    l'objet. Régression : avant, 5 objets bloquaient sur une question."""
    for o in ("porte_cle", "badge", "sousverre", "plaque", "magnet"):
        objet, _p, q = P.valider({"objet": o})
        assert objet == o and q is None, o
    objet, _p, q = P.valider({"objet": "lettre_3d"})
    assert objet is None and q


def test_hors_catalogue_route_vers_libre():
    """Un objet nommé HORS catalogue (cuillère, 'libre'...) doit router vers la
    création sur mesure — signal EXPLICITE __libre__, jamais une question
    (régression : Gemma reformulait la question -> l'utilisateur restait bloqué)."""
    for nom in ("libre", "sifflet", "casque", "fusee"):
        objet, _p, q = P.valider({"objet": nom})
        assert objet == "__libre__" and q is None, nom
    # cuillere/fourchette/vis sont désormais DES OBJETS DU CATALOGUE
    objet, _p, q = P.valider({"objet": "cuillere"})
    assert objet == "cuillere" and q is None
    objet, params, q = P.valider({"objet": "vis", "taille": "m8", "ecrou": True})
    assert objet == "vis" and params["taille"] == "M8" and params.get("ecrou") is True
    # une vraie question (texte manquant, demande floue) passe toujours
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


def test_photo_relief_lithophanie(tmp_path):
    """Photo -> plaque lithophanie ÉTANCHE : sombre = épais, clair = fin,
    cadre rigide, debout par défaut (qualité d'impression)."""
    import numpy as np
    from PIL import Image
    img = tmp_path / "grad.png"
    Image.fromarray(np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (48, 1)),
                    "L").save(img)
    from core.neogen import catalogue as C
    p = C.construire("photo_relief", {"image": str(img), "largeur": 80})
    assert p.is_watertight
    d = p.bounds[1] - p.bounds[0]
    assert abs(d[0] - 80) < 1
    assert 3.0 < d[1] < 6.5, "debout : l'épaisseur (cadre inclus) est en Y"
    # mode relief à plat : socle plein + amplitude
    p2 = C.construire("photo_relief", {"image": str(img), "largeur": 80,
                                       "mode": "relief", "debout": False,
                                       "cadre": False})
    assert p2.is_watertight
    assert p2.bounds[1][2] - p2.bounds[0][2] > 3.0


def test_profil_lithophanie_automatique(tmp_path, monkeypatch):
    """Une lithophanie doit s'imprimer PLEINE et lente : le profil auto force
    remplissage 100 %, 4 parois, couche fine, brim — et le fichier neoGen est
    nommé « lithophanie* » pour être reconnu au chargement."""
    from core.parameters.parameter_engine import appliquer_profil_lithophanie
    from core.parameters.print_config import PrintConfig
    cfg = PrintConfig(infill_density=15, wall_loops=2, layer_height=0.12,
                      outer_wall_speed=200, brim_type="no_brim")
    cfg = appliquer_profil_lithophanie(cfg)
    assert cfg.infill_density == 100 and cfg.wall_loops >= 4
    # « zig-zag » : nom BAMBU du rectiligne, seul motif accepté à 100 %
    # (« rectilinear » était inconnu de BS -> remplacé par cubic -> refusé)
    assert cfg.infill_pattern == "zig-zag"
    assert cfg.outer_wall_speed <= 50
    assert cfg.brim_type != "no_brim" and cfg.brim_width >= 5
    # la hauteur de couche N'EST PAS forcée : la Qualité (pré-sélectionnée
    # Fine, modifiable) garde la main
    assert cfg.layer_height == 0.12
    # nommage : mode lithophanie -> « lithophanie », mode relief -> nom normal
    import numpy as np
    from PIL import Image
    img = tmp_path / "g.png"
    Image.fromarray(np.tile(np.linspace(0, 255, 32, dtype=np.uint8), (24, 1)),
                    "L").save(img)
    monkeypatch.setattr(P, "DOSSIER_SORTIES", tmp_path)
    from core.neogen import catalogue as C
    assert C.generer_fichier("photo_relief", {"image": str(img)}).stem \
        .startswith("lithophanie")
    assert C.generer_fichier("photo_relief", {"image": str(img),
                                              "mode": "relief"}).stem \
        .startswith("photo_relief")


def test_maj_cookbook_valide_en_sandbox(tmp_path, monkeypatch):
    """La base d'objets distante : chaque recette est EXECUTEE en sandbox et
    verifiee avant installation — du code dangereux ou casse est ecarte."""
    from core.neogen import maj, libre as L
    monkeypatch.setattr(maj, "FICHIER_LOCAL", tmp_path / "extra.json")
    manifest = {"version": "t1", "recettes": [
        {"cles": "anneau test", "demande": "un anneau",
         "code": "piece = percer(cylindre(45, 35), cylindre(38, 60))"},
        {"cles": "hack", "demande": "hack", "code": "import os"},
    ]}
    n, ecartees = maj.appliquer(manifest)
    assert n == 1 and ecartees == 1
    assert maj.version_locale() == "t1"
    assert len(maj.charger_extra()) == 1
    L.COOKBOOK_EXTRA.clear()          # ne pas polluer les autres tests


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
