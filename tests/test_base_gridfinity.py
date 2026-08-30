# -*- coding: utf-8 -*-
"""Base neoGen — recette Gridfinity + garde-fou photo_relief.

Ces recettes vivent dans tools/gen_neogen_objets.py (données de la base
téléchargeable, pas du code applicatif) mais DOIVENT passer la validation
« download » de l'app (sandbox sans image, vérificateur). Régression vécue :
photo_relief écarté à l'installation (NameError sur `image`) car le garde-fou
« pièce-témoin sans image » manquait dans le générateur."""
import importlib.util
from pathlib import Path

import pytest

_GEN = Path(__file__).resolve().parents[1] / "tools" / "gen_neogen_objets.py"


@pytest.fixture(scope="module")
def objets():
    spec = importlib.util.spec_from_file_location("gen_objets", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {o["id"]: o for o in mod.OBJETS}


def _construire(obj, extra=None):
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts
    ns = _defauts(obj)
    ns.update(extra or {})
    if obj.get("texte", "aucun") != "aucun":
        ns["texte"] = "Test"
    return L.poser_au_sol(L.executer_sandbox(str(obj["code"]), ns))


def test_photo_relief_valide_sans_image(objets):
    """La validation download tourne SANS image → le garde-fou doit rendre une
    pièce-témoin saine au lieu de crasher (sinon l'objet est écarté de la base)."""
    from core.neogen import libre as L
    piece = _construire(objets["photo_relief"])
    assert L.verifier(piece) is None


def test_gridfinity_defauts(objets):
    """Dimensions LIBRES et EXACTES (retour Emmanuel) : le bac fait pile la
    taille demandée, pas un multiple d'« unités »."""
    from core.neogen import libre as L
    piece = _construire(objets["gridfinity"])
    assert L.verifier(piece) is None
    d = piece.bounds[1] - piece.bounds[0]
    assert d[0] == pytest.approx(84.0, abs=0.05)
    assert d[1] == pytest.approx(42.0, abs=0.05)
    assert d[2] == pytest.approx(42.0, abs=0.05)


def test_gridfinity_dimensions_exactes(objets):
    from core.neogen import libre as L
    piece = _construire(objets["gridfinity"],
                        {"longueur": 117, "largeur": 73, "hauteur": 55})
    assert L.verifier(piece) is None
    d = piece.bounds[1] - piece.bounds[0]
    assert d[0] == pytest.approx(117.0, abs=0.05)
    assert d[1] == pytest.approx(73.0, abs=0.05)
    assert d[2] == pytest.approx(55.0, abs=0.05)


def test_gridfinity_pied_profil_officiel_lisse(objets):
    """Le pied suit EXACTEMENT le profil officiel (chanfreins 45° lisses — plus
    d'escalier, retour Emmanuel) : 35,6 → 37,2 sur 0,8 mm ; droit jusqu'à
    2,6 mm ; puis → 41,5 à 4,75 mm."""
    piece = _construire(objets["gridfinity"], {"longueur": 42, "largeur": 42})

    def ideal(z):
        if z <= 0.8:
            return 35.6 + 2 * z
        if z <= 2.6:
            return 37.2
        return 37.2 + 2 * (z - 2.6)

    for z in (0.2, 0.6, 1.5, 3.0, 4.0, 4.5):
        sec = piece.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        lo, hi = sec.bounds[0][:2], sec.bounds[1][:2]
        w = max(hi[0] - lo[0], hi[1] - lo[1])
        assert w == pytest.approx(ideal(z), abs=0.05), f"z={z}"


def test_gridfinity_interieur_lisse(objets):
    """Aucun rebord le long de l'intérieur (vécu : lèvre non affleurée) — le
    flanc intérieur est au même endroit à mi-hauteur et près du bord."""
    import numpy as np
    piece = _construire(objets["gridfinity"],
                        {"longueur": 84, "largeur": 42, "hauteur": 42, "paroi": 2.0})
    def flanc(z):
        v = piece.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).vertices
        # sommets du contour INTÉRIEUR (hors coque extérieure et ses congés)
        inner = v[(np.abs(v[:, 0]) < 41.0) & (np.abs(v[:, 1]) < 20.0)]
        return np.abs(inner[:, 0]).max()
    assert flanc(20.0) == pytest.approx(flanc(41.5), abs=0.02)


def test_gridfinity_etroit_fond_plat(objets):
    """Sous 41,5 mm dans un sens, aucun pied standard ne tient → fond PLAT aux
    dimensions exactes (la largeur reste libre, retour Emmanuel)."""
    from core.neogen import libre as L
    piece = _construire(objets["gridfinity"], {"longueur": 84, "largeur": 30})
    assert L.verifier(piece) is None
    d = piece.bounds[1] - piece.bounds[0]
    assert d[1] == pytest.approx(30.0, abs=0.05)
    # pas de pied : à 1 mm du sol, la section fait déjà toute la semelle
    sec = piece.section(plane_origin=[0, 0, 1.0], plane_normal=[0, 0, 1])
    assert sec.bounds[1][1] - sec.bounds[0][1] == pytest.approx(30.0, abs=0.05)


def test_gridfinity_variantes(objets):
    from core.neogen import libre as L
    for extra in ({"cases_x": 3, "cases_y": 2, "longueur": 126, "largeur": 84},
                  {"paroi": 2.4}, {"longueur": 250, "largeur": 250, "hauteur": 15}):
        piece = _construire(objets["gridfinity"], extra)
        assert L.verifier(piece) is None, extra
