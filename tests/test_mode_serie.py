# -*- coding: utf-8 -*-
"""Mode série — ×N exemplaires disposés en grille, débordement multi-plateaux."""
import pytest

from core.geometry.serie import plan_grille, copies_serie


def test_grille_de_base():
    # pièce 20×20 sur plateau 256×256 : zone utile 240 → 8 colonnes de 28 mm
    p = plan_grille(20, 20, 5, 256, 256)
    assert p["cols"] == 8 and p["rows"] == 8
    assert p["par_plateau"] == 64
    assert p["plateaux"] == 1
    assert len(p["offsets"][0]) == 5
    # pas de grille = empreinte + espacement
    assert p["offsets"][0][1] == (28.0, 0.0)
    assert p["offsets"][0][0] == (0.0, 0.0)


def test_debordement_plateaux():
    p = plan_grille(20, 20, 70, 256, 256)
    assert p["plateaux"] == 2
    assert len(p["offsets"][0]) == 64
    assert len(p["offsets"][1]) == 6
    # le 2e plateau repart d'une grille locale (pas de dérive cumulée)
    assert p["offsets"][1][0] == (0.0, 0.0)


def test_piece_plus_grande_que_le_plateau():
    with pytest.raises(ValueError):
        plan_grille(250, 20, 2, 256, 256)          # 250 > 240 utile
    with pytest.raises(ValueError):
        plan_grille(20, 20, 0, 256, 256)           # n invalide


def test_piece_pleine_largeur_une_par_plateau():
    """Une pièce qui occupe presque tout le plateau → 1 exemplaire/plateau."""
    p = plan_grille(230, 230, 3, 256, 256)
    assert p["par_plateau"] == 1
    assert p["plateaux"] == 3


def test_copies_serie_translations():
    trimesh = pytest.importorskip("trimesh")
    m = trimesh.creation.box(extents=(20, 20, 10))
    plateaux = copies_serie(m, 5, (256, 256))
    assert len(plateaux) == 1 and len(plateaux[0]) == 5
    c0, c1 = plateaux[0][0], plateaux[0][1]
    assert c1.bounds[0][0] - c0.bounds[0][0] == pytest.approx(28.0)
    assert c0.bounds[0][2] == pytest.approx(m.bounds[0][2])   # Z inchangé
    # volume total = N × volume unitaire (vraies copies)
    total = sum(c.volume for c in plateaux[0])
    assert total == pytest.approx(5 * m.volume)


def test_i18n_cles_serie():
    from core.i18n import _FR, _EN
    for cle in ("serie.tip", "serie.not_applicable", "serie.too_big",
                "serie.exported"):
        assert cle in _FR and cle in _EN, cle
