# -*- coding: utf-8 -*-
"""neoForge : noyau de CAO (OpenCascade). Volumes comparés aux formules
exactes, parité avec la console, congés et chanfreins, arêtes retrouvées
après modification. Ignoré si le noyau n'est pas installé sur la machine."""
import math

import numpy as np
import pytest

try:
    from neoforge.noyau import occ as O
except ImportError:
    pytest.skip("noyau neoForge non installé", allow_module_level=True)

import trimesh

from neoforge.noyau import aretes as A
from neoforge.noyau.construction import (Constructeur, ERR_TROP_GRAND, ERR_VIDE,
                                         ERR_AUCUNE)
from neoforge.noyau.maillage import polyligne, trianguler
from neoforge.noyau.primitives import solide
from neoforge.projet.modele import Arrondi, Forme, Projet


def _construire(projet):
    res = Constructeur().construire(projet)
    return res, res[-1].forme


def _mesh(forme):
    V, F = trianguler(forme)
    return trimesh.Trimesh(V, F, process=False)


def _cube(a=30.0):
    return Forme("cube", "matiere", [0, 0, a / 2], [a, a, a])


def _platine():
    """La pièce d'exemple de la console : plaque percée deux fois + bloc."""
    return Projet([Forme("cube", "matiere", [0, 0, 5], [80, 50, 10]),
                   Forme("cylindre", "creux", [-30, -16, 5], [8, 8, 30]),
                   Forme("cylindre", "creux", [30, -16, 5], [8, 8, 30]),
                   Forme("cube", "matiere", [0, 12, 16], [30, 20, 12])])


# ── Parité avec la console (même projet, mêmes résultats) ───────────────────
def test_platine_de_la_console_volume_exact_et_deux_trous():
    res, f = _construire(_platine())
    assert all(r.erreur is None for r in res)
    # 80×50×10 − 2 trous Ø8 sur 10 + bloc 30×20×12 (la console, facettée : 46 197,6)
    assert O.volume(f) == pytest.approx(40000 - 2 * math.pi * 16 * 10 + 7200, abs=0.5)
    m = _mesh(f)
    assert m.is_watertight and m.is_winding_consistent
    assert m.euler_number == -2              # genre 2 : deux trous traversants


def test_intersection_cube_sphere():
    p = Projet([Forme("cube", "matiere", [0, 0, 10], [20, 20, 20]),
                Forme("sphere", "intersection", [0, 0, 10], [26, 26, 26])])
    res, f = _construire(p)
    assert res[-1].erreur is None
    # sphère r13 moins 6 calottes de hauteur 3 (console facettée : 7 135)
    attendu = 4 / 3 * math.pi * 13 ** 3 - 6 * math.pi * 9 * (39 - 3) / 3
    assert O.volume(f) == pytest.approx(attendu, rel=1e-4)


def test_cones_pivote_et_pointu():
    tronc = Projet([Forme("cone", "matiere", [0, 0, 10], [30, 10, 20], [0, 0, 30])])
    pointu = Projet([Forme("cone", "matiere", [0, 0, 12], [20, 0, 24])])
    assert O.volume(_construire(tronc)[1]) == pytest.approx(
        math.pi * 20 / 3 * (15 ** 2 + 15 * 5 + 5 ** 2), rel=1e-4)
    f = _construire(pointu)[1]
    assert O.volume(f) == pytest.approx(math.pi * 24 / 3 * 100, rel=1e-4)
    assert _mesh(f).is_watertight


def test_meme_placement_que_la_console():
    """Boîte englobante et volume identiques à la console (manifold3d) pour des
    formes pivotées : même centrage, même ordre de rotation X puis Y puis Z."""
    import manifold3d as mf
    cas = [Forme("cube", "matiere", [5, -3, 12], [30, 12, 8], [20, 35, 50]),
           Forme("cylindre", "matiere", [0, 0, 10], [16, 16, 30], [90, 0, 45]),
           Forme("cone", "matiere", [10, 10, 10], [20, 6, 18], [0, 60, 0])]
    for f in cas:
        d = f.dim
        if f.forme == "cube":
            m = mf.Manifold.cube(d, True)
        else:
            haut = d[0] if f.forme == "cylindre" else d[1]
            m = mf.Manifold.cylinder(d[2], d[0] / 2, haut / 2, 256, True)
        m = m.rotate(f.rot).translate(f.pos)
        pts = np.asarray(m.to_mesh().vert_properties)[:, :3]
        V, _F = trianguler(solide(f))
        assert np.allclose(V.min(0), pts.min(0), atol=0.05), f.forme
        assert np.allclose(V.max(0), pts.max(0), atol=0.05), f.forme
        assert O.volume(solide(f)) == pytest.approx(m.volume(), rel=2e-3), f.forme


# ── Congés et chanfreins ─────────────────────────────────────────────────────
def test_conge_sur_toutes_les_aretes_volume_exact():
    a, r = 30.0, 3.0
    res, f = _construire(Projet([_cube(a), Arrondi("conge", r, "toutes")]))
    assert res[-1].erreur is None and len(res[-1].aretes) == 12
    c = a - 2 * r
    attendu = c ** 3 + 6 * r * c ** 2 + 3 * math.pi * r ** 2 * c + 4 / 3 * math.pi * r ** 3
    assert O.volume(f) == pytest.approx(attendu, rel=1e-4)
    m = _mesh(f)
    assert m.is_watertight and m.is_winding_consistent


def test_chanfrein_sur_les_aretes_du_haut():
    a, d = 30.0, 2.0
    res, f = _construire(Projet([_cube(a), Arrondi("chanfrein", d, "haut")]))
    assert res[-1].erreur is None and len(res[-1].aretes) == 4
    assert O.volume(f) == pytest.approx(a ** 3 - (4 * a * d * d / 2 - 4 * d ** 3 / 3), abs=0.05)
    assert _mesh(f).is_watertight


def test_regles_bas_et_verticales():
    res, _f = _construire(Projet([_cube(), Arrondi("conge", 1, "bas")]))
    assert res[-1].erreur is None and len(res[-1].aretes) == 4
    res, _f = _construire(Projet([_cube(), Arrondi("conge", 1, "verticales")]))
    assert res[-1].erreur is None and len(res[-1].aretes) == 4


def test_deux_conges_successifs_n_arrondissent_pas_les_bords_lisses():
    """Après un congé, ses bords sont tangents : un 2e « toutes » ne doit viser
    que les vraies arêtes vives restantes (sinon le noyau échoue)."""
    p = Projet([_cube(), Arrondi("conge", 2, "verticales"), Arrondi("conge", 1, "toutes")])
    res, f = _construire(p)
    assert [r.erreur for r in res] == [None, None, None]
    assert _mesh(f).is_watertight


def test_conge_trop_grand_garde_la_piece_et_propose_un_maximum():
    res, f = _construire(Projet([_cube(20), Arrondi("conge", 15, "toutes")]))
    assert res[-1].erreur == ERR_TROP_GRAND
    assert O.volume(f) == pytest.approx(8000, abs=0.5)        # pièce intacte
    assert 0 < res[-1].detail["max"] < 10


def test_arrondi_sans_arete_designee():
    p = Projet([Forme("sphere", "matiere", [0, 0, 10], [20, 20, 20]),
                Arrondi("conge", 1, "verticales")])
    assert _construire(p)[0][-1].erreur == ERR_AUCUNE


# ── Arêtes cliquées retrouvées après modification ────────────────────────────
def _sigs(forme, regle, n=None, genre=None):
    b = O.boite(forme)
    es = A.selon_regle(regle, A.aretes_arrondissables(forme), b)
    if genre:
        es = [e for e in es if A.signature(e, b)["genre"] == genre]
    return [A.signature(e, b) for e in es[:n]]


def test_aretes_cliquees_suivent_le_redimensionnement():
    p = Projet([_cube(30)])
    c = Constructeur()
    sigs = _sigs(c.construire(p)[-1].forme, "haut", 2)
    p.etapes.append(Arrondi("conge", 2, "liste", sigs))
    assert c.construire(p)[-1].erreur is None
    p.etapes[0].dim, p.etapes[0].pos = [40, 40, 40], [0, 0, 20]
    r = c.construire(p)[-1]
    assert r.erreur is None and len(r.aretes) == 2
    b = O.boite(r.forme)
    nouvelles = sorted(A.signature(e, b)["relatif"] for e in r.aretes)
    for e in r.aretes:
        assert np.allclose(polyligne(e)[:, 2], 40, atol=1e-6)    # toujours en haut
    assert np.allclose(nouvelles, sorted(s["relatif"] for s in sigs), atol=0.02)


def test_chanfrein_du_trou_suit_le_trou_deplace_et_agrandi():
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [60, 40, 10]),
                Forme("cylindre", "creux", [-10, 0, 5], [10, 10, 30])])
    c = Constructeur()
    sigs = _sigs(c.construire(p)[-1].forme, "haut", genre="cercle")
    assert len(sigs) == 1
    p.etapes.append(Arrondi("chanfrein", 1, "liste", sigs))
    assert c.construire(p)[-1].erreur is None
    p.etapes[1].pos = [12, 5, 5]                      # trou déplacé…
    p.etapes[1].dim = [14, 14, 30]                    # …et agrandi
    r = c.construire(p)[-1]
    assert r.erreur is None and len(r.aretes) == 1
    s = A.signature(r.aretes[0], O.boite(r.forme))
    assert s["genre"] == "cercle" and s["rayon"] == pytest.approx(7)
    assert s["milieu"] == pytest.approx([12, 5, 10], abs=1e-3)   # le bord du HAUT


# ── Choisir une pièce en cliquant dessus ─────────────────────────────────────
def test_clic_sur_la_piece_designe_la_bonne_etape():
    """Demande d'Emmanuel : sélectionner une pièce en cliquant dessus. Le clic
    tombe sur la SURFACE : on retrouve la forme qui la porte."""
    from neoforge.noyau.selection import etape_au_point
    p = _platine()
    assert etape_au_point(p, (0, -20, 10)) == 0        # dessus de la plaque
    assert etape_au_point(p, (0, 12, 22)) == 3         # dessus du bloc
    assert etape_au_point(p, (-30, -12, 5)) == 1       # paroi du premier trou
    assert etape_au_point(p, (30, -12, 5)) == 2        # paroi du second trou
    assert etape_au_point(p, (0, 0, 200)) is None      # dans le vide


def test_clic_ignore_une_etape_masquee():
    from neoforge.noyau.selection import etape_au_point
    p = _platine()
    p.etapes[3].actif = False
    assert etape_au_point(p, (0, 12, 22)) is None


# ── Robustesse et cache ──────────────────────────────────────────────────────
def test_intersection_vide_signalee_sans_perdre_la_piece():
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [10, 10, 10]),
                Forme("sphere", "intersection", [100, 0, 5], [10, 10, 10])])
    res, f = _construire(p)
    assert res[-1].erreur == ERR_VIDE
    assert O.volume(f) == pytest.approx(1000, abs=0.01)


def test_etape_masquee_et_premiere_forme_toujours_matiere():
    p = Projet([Forme("cube", "creux", [0, 0, 5], [10, 10, 10]),
                Forme("cylindre", "creux", [0, 0, 5], [4, 4, 30])])
    assert O.volume(_construire(p)[1]) < 1000
    p.etapes[1].actif = False
    assert O.volume(_construire(p)[1]) == pytest.approx(1000, abs=0.01)


def test_cache_ne_recalcule_que_depuis_l_etape_modifiee():
    p = _platine()
    c = Constructeur()
    r1 = c.construire(p)
    p.etapes[3].dim = [30, 20, 14]
    r2 = c.construire(p)
    assert r2[2].forme is r1[2].forme
    assert r2[3].forme is not r1[3].forme


def test_fusion_de_deux_cubes_alignes_sans_arete_de_couture():
    """Deux cubes empilés de même section = un seul pavé : 12 arêtes, pas 20."""
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [20, 20, 10]),
                Forme("cube", "matiere", [0, 0, 15], [20, 20, 10])])
    f = _construire(p)[1]
    assert len(A.aretes_arrondissables(f)) == 12
