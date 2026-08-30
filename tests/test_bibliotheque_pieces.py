# -*- coding: utf-8 -*-
"""Bibliothèque de pièces — chaque export mémorise la pièce + ses réglages
EXACTS pour « Réimprimer à l'identique » (Espace Pro)."""
import pytest

from core.business import store


@pytest.fixture(autouse=True)
def _isole_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_BIBLIOTHEQUE", tmp_path / "bibliotheque.json")
    monkeypatch.setattr(store, "_VIGNETTES", tmp_path / "vignettes")
    yield


def test_add_list_delete(tmp_path):
    e = store.add_library_entry({"nom": "Support mural", "fichier": "C:/x.stl",
                                 "sha1": "abc", "imprimante": "X1C",
                                 "filament": "PLA", "buse_mm": 0.4,
                                 "config": {"layer_height": 0.2}})
    assert e["id"] and e["date"] and e["exports"] == 1
    assert [x["nom"] for x in store.list_library()] == ["Support mural"]
    assert store.delete_library_entry(e["id"]) is True
    assert store.list_library() == []
    assert store.delete_library_entry("inexistant") is False


def test_reexport_identique_rafraichit_sans_dupliquer():
    base = {"nom": "Boîtier", "fichier": "C:/b.stl", "sha1": "s1",
            "imprimante": "X1C", "filament": "PLA", "plateau": "Textured PEI Plate",
            "buse_mm": 0.4, "config": {"layer_height": 0.2, "wall_loops": 3}}
    e1 = store.add_library_entry(dict(base))
    e2 = store.add_library_entry(dict(base))
    assert e2["id"] == e1["id"]
    assert e2["exports"] == 2
    assert len(store.list_library()) == 1
    # réglages différents (même fichier) → NOUVELLE entrée : deux façons
    # d'imprimer la même pièce coexistent dans la bibliothèque
    e3 = store.add_library_entry({**base, "config": {"layer_height": 0.28}})
    assert e3["id"] != e1["id"]
    assert len(store.list_library()) == 2
    # autre buse → nouvelle entrée aussi
    e4 = store.add_library_entry({**base, "buse_mm": 0.2})
    assert e4["id"] not in (e1["id"], e3["id"])


def test_file_sha1(tmp_path):
    f = tmp_path / "piece.stl"
    f.write_bytes(b"solid neoslice")
    h1 = store.file_sha1(f)
    assert len(h1) == 40
    f.write_bytes(b"solid modifie")
    assert store.file_sha1(f) != h1                        # contenu → empreinte
    assert store.file_sha1(tmp_path / "absent.stl") == ""  # illisible → ""


def test_vignette_supprimee_avec_entree(tmp_path):
    e = store.add_library_entry({"nom": "P", "sha1": "v1"})
    vp = store.vignette_path(e["id"])
    vp.write_bytes(b"\x89PNG")
    store.delete_library_entry(e["id"])
    assert not vp.exists()


def test_config_round_trip():
    """La config mémorisée (model_dump) redonne une PrintConfig IDENTIQUE."""
    from core.parameters.print_config import PrintConfig
    cfg = PrintConfig(layer_height=0.28, wall_loops=5, infill_density=42,
                      brim_type="outer_only", brim_width=6.0)
    e = store.add_library_entry({"nom": "RT", "config": cfg.model_dump()})
    relu = PrintConfig(**store.list_library()[0]["config"])
    assert relu == cfg
    assert e["config"]["infill_density"] == 42


def test_i18n_cles_bibliotheque():
    from core.i18n import _FR, _EN
    for cle in ("pro.tab_library", "library.intro", "library.none",
                "library.reprint", "library.delete", "library.delete_confirm",
                "library.file_missing", "library.exports", "library.missing_title",
                "library.missing_file", "library.changed_file",
                "library.reprint_ready", "library.reprint_failed"):
        assert cle in _FR, f"FR manquante : {cle}"
        assert cle in _EN, f"EN manquante : {cle}"
