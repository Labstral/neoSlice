# -*- coding: utf-8 -*-
"""neoForge : imprimabilité et exports (STL, 3MF, STEP)."""
import pytest

try:
    from neoforge.noyau import occ as O
except ImportError:
    pytest.skip("noyau neoForge non installé", allow_module_level=True)

import numpy as np
import trimesh

from neoforge.noyau import export as X
from neoforge.noyau.construction import Constructeur
from neoforge.noyau.maillage import trianguler
from neoforge.projet.modele import Arrondi, Forme, Projet


def _piece(projet):
    f = Constructeur().construire(projet)[-1].forme
    V, F = trianguler(f)
    return f, V, F


def test_piece_saine_aucun_constat():
    _f, V, F = _piece(Projet([Forme("cube", "matiere", [0, 0, 10], [20, 20, 20]),
                              Arrondi("conge", 2, "toutes")]))
    assert X.verifier(V, F, (256, 256, 256)) == []


def test_trop_grande_pour_le_plateau_est_bloquant():
    _f, V, F = _piece(Projet([Forme("cube", "matiere", [0, 0, 5], [300, 20, 10])]))
    c = X.verifier(V, F, (256, 256, 256))
    assert [(k.code, k.gravite) for k in c] == [("trop_grande", X.BLOQUANT)]
    assert c[0].detail["taille"][0] == pytest.approx(300)


def test_morceaux_separes_et_maillage_ouvert():
    _f, V, F = _piece(Projet([Forme("cube", "matiere", [0, 0, 5], [10, 10, 10]),
                              Forme("cube", "matiere", [50, 0, 5], [10, 10, 10])]))
    assert [k.code for k in X.verifier(V, F)] == ["morceaux"]
    codes = [k.code for k in X.verifier(V, F[:-3])]              # 3 triangles en moins
    assert "ouverte" in codes


def test_exports_relus(tmp_path):
    platine = Projet([Forme("cube", "matiere", [0, 0, 5], [80, 50, 10]),
                      Forme("cylindre", "creux", [-30, -16, 5], [8, 8, 30]),
                      Forme("cylindre", "creux", [30, -16, 5], [8, 8, 30]),
                      Forme("cube", "matiere", [0, 12, 16], [30, 20, 12])])
    f, V, F = _piece(platine)
    V = X.poser_au_sol(V)
    stl = trimesh.load(X.exporter_stl(V, F, tmp_path / "p.stl"))
    assert len(stl.faces) == len(F) and stl.is_watertight
    tmf = trimesh.load(X.exporter_3mf(V, F, tmp_path / "p.3mf"), force="mesh")
    assert tmf.volume == pytest.approx(O.volume(f), rel=2e-3)
    step = X.exporter_step(f, tmp_path / "p.step")
    assert step.read_text(errors="ignore").startswith("ISO-10303-21")
    assert np.isclose(V[:, 2].min(), 0)
