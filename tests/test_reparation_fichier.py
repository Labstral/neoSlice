# -*- coding: utf-8 -*-
"""Réparation automatique des fichiers au chargement — désormais VISIBLE.

La réparation (fill_holes, faces dégénérées, conversion d'unités) existait dans
load_stl mais était muette (logs seulement). Elle remonte maintenant un rapport
dans mesh.metadata["neoslice_reparations"], affiché dans le panneau d'analyse.
"""
import numpy as np
import pytest
import trimesh

from core.geometry.stl_loader import load_stl


def _cube_troue(tmp_path, nom="troue.stl"):
    """Cube 20 mm auquel on retire une face → non étanche."""
    m = trimesh.creation.box(extents=(20, 20, 20))
    m = trimesh.Trimesh(vertices=m.vertices, faces=m.faces[:-1], process=False)
    assert not m.is_watertight
    p = tmp_path / nom
    m.export(p)
    return p


def test_trous_rebouches_et_rapport(tmp_path):
    mesh = load_stl(_cube_troue(tmp_path))
    rep = mesh.metadata.get("neoslice_reparations") or {}
    assert rep.get("trous") == "rebouches"
    assert mesh.is_watertight                      # la réparation a réellement eu lieu


def test_conversion_unites_signalee(tmp_path):
    """Cube exporté en mètres (0,02) → converti en mm ET signalé (code neutre)."""
    m = trimesh.creation.box(extents=(0.02, 0.02, 0.02))
    p = tmp_path / "metres.stl"
    m.export(p)
    mesh = load_stl(p)
    rep = mesh.metadata.get("neoslice_reparations") or {}
    assert rep.get("unites") == "m"
    assert float(mesh.bounding_box.extents.max()) == pytest.approx(20.0, rel=1e-3)


def test_fichier_sain_aucune_mention(tmp_path):
    """Une pièce propre ne doit afficher AUCUN message de réparation."""
    m = trimesh.creation.box(extents=(20, 20, 20))
    p = tmp_path / "sain.stl"
    m.export(p)
    mesh = load_stl(p)
    assert "neoslice_reparations" not in (mesh.metadata or {})


def test_cles_i18n_reparation():
    from core import i18n
    for k in ("repair.holes", "repair.holes_partial", "repair.degenerate",
              "repair.units", "repair.unit_m", "repair.unit_dm",
              "repair.unit_cm", "repair.unit_in"):
        assert k in i18n._FR and k in i18n._EN, k
