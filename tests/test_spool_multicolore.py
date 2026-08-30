# -*- coding: utf-8 -*-
"""Bobines multi-couleurs (dual/tri/quadri) — demande utilisateur Matthieu D. :
répertorier correctement les bobines à plusieurs couleurs (jusqu'à 4)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.business import store                        # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isole_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_SPOOLS", tmp_path / "spools.json")
    yield


def test_spool_couleurs():
    assert store.spool_couleurs({"couleur_hex": "#FF0000"}) == ["#FF0000"]
    s = {"couleur_hex": "#FF0000", "couleurs_hex": ["#00FF00", "#0000FF"]}
    assert store.spool_couleurs(s) == ["#FF0000", "#00FF00", "#0000FF"]
    # doublons et vides filtrés, plafond à 4
    s = {"couleur_hex": "#111111",
         "couleurs_hex": ["#111111", "", "#222222", "#333333", "#444444", "#555555"]}
    assert store.spool_couleurs(s) == ["#111111", "#222222", "#333333", "#444444"]
    assert store.spool_couleurs({}) == ["#888888"]      # jamais vide


def test_store_conserve_les_couleurs():
    s = store.add_spool({"materiau": "PLA", "couleur_hex": "#FF0000",
                         "couleurs_hex": ["#00FF00", "#0000FF"]})
    relu = store.get_spool(s["id"])
    assert relu["couleurs_hex"] == ["#00FF00", "#0000FF"]
    # une bobine classique a une liste vide par défaut
    mono = store.add_spool({"materiau": "PETG"})
    assert store.get_spool(mono["id"])["couleurs_hex"] == []


def test_pixmap_secteurs(app):
    """La pastille multi-couleur contient bien CHAQUE couleur (échantillonnage
    de pixels dans les secteurs), et l'appel historique à un seul hex marche."""
    from ui.components.spool_visuals import spool_pixmap, spool_icon
    pm = spool_pixmap(["#FF0000", "#0000FF"], 32)
    img = pm.toImage()
    haut = img.pixelColor(22, 8)          # secteur droit (1re couleur, départ 12 h)
    bas = img.pixelColor(9, 24)           # secteur gauche (2e couleur)
    assert haut.red() > 200 and haut.blue() < 60
    assert bas.blue() > 200 and bas.red() < 60
    assert not spool_icon("#00FF00").isNull()           # compat un seul hex
    assert not spool_icon(["#111111"] ).isNull()
    q = spool_pixmap(["#FF0000", "#00FF00", "#0000FF", "#FFFF00"], 32)
    assert not q.isNull()


def test_formulaire_round_trip(app):
    """SpoolForm : une bobine tricolore éditée rend bien ses 3 couleurs."""
    from ui.components.pro_hub import SpoolForm
    f = SpoolForm(spool={"materiau": "PLA", "couleur_hex": "#FF0000",
                         "couleurs_hex": ["#00FF00", "#0000FF"]})
    assert f._colors == ["#FF0000", "#00FF00", "#0000FF"]
    d = f.data()
    assert d["couleur_hex"] == "#FF0000"
    assert d["couleurs_hex"] == ["#00FF00", "#0000FF"]
    # retrait de la 2e couleur → il en reste 2 ; la principale est intouchable
    f._remove_color(1)
    assert f._colors == ["#FF0000", "#0000FF"]
    f._remove_color(0)
    assert f._colors[0] == "#FF0000"
    f.deleteLater()


def test_i18n_cles_multicolore():
    from core.i18n import _FR, _EN
    for cle in ("spool.add_color", "spool.remove_color"):
        assert cle in _FR and cle in _EN, cle
