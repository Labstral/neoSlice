"""Non-régressions issues de l'audit complet (2026-08-02).

Couvre les corrections vérifiables sans UI (règle : ne JAMAIS importer ui.*
dans un test — casse toute la suite) :
- tags plateau()/profil() préservés à travers les opérations booléennes DSL ;
- bornes de paramètres neoGen qui crashaient (rondelle, entretoise, magnet) ;
- percer() qui retire tout le volume → erreur claire (plus de NoneType) ;
- vase à 0 ondulation (plus de division par zéro) ;
- multiplate : pièces d'un même plateau NON superposées (positions relatives) ;
- multiplate : noms d'objets échappés XML ;
- patch per-object : repli id racine pour les assemblages (« 2_5 » → « 2 »).
"""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import trimesh

from core.neogen import libre as L
# Imports AU NIVEAU MODULE (pas dans les tests) : ces modules initialisent
# matplotlib ; l'importer pendant la capture par-test lie son logger au flux
# temporaire de pytest → « I/O operation on closed file » en cascade sur toute
# la suite (vécu). À la collection, la liaison est sûre.
from core.neogen.formes import entretoise, rondelle
from core.neogen.goodies import magnet
from core.neogen.objets import vase
from core.parameters.parameter_engine import PrintConfig


# ── Tags à travers les opérations booléennes ─────────────────────────────────
def _tags(o):
    md = getattr(o, "metadata", {}) or {}
    return (md.get("neoslice_plate"), md.get("neoslice_profil"))


def _tagged_box():
    return L.plateau(L.profil(L.boite_3d(20, 20, 10), "standard"), 1)


@pytest.mark.parametrize("op", [
    lambda b: L.fusionner(b, L.cylindre(8, 12)),
    lambda b: L.percer(b, L.cylindre(8, 30)),
    lambda b: L.creuser(b, 2),
    lambda b: L.intersection(b, L.boite_3d(30, 30, 30)),
    lambda b: L.repeter_cercle(b, 3, 30),
    lambda b: L.repeter_ligne(b, 2, 25),
])
def test_tags_survivent_operations_booleennes(op):
    assert _tags(op(_tagged_box())) == (1, "standard")


def test_outil_taggue_ne_contamine_pas():
    """percer(corps_non_taggé, outil_taggé) → le résultat reste NON taggé."""
    outil = L.plateau(L.profil(L.cylindre(6, 30), "standard"), 1)
    assert _tags(L.percer(L.boite_3d(20, 20, 10), outil)) == (None, None)


# ── Bornes de paramètres neoGen (crashaient aux extrêmes des curseurs) ───────
def test_rondelle_d_int_superieur_d_ext():

    m = rondelle(d_ext=8, d_int=12, ep=3)      # d_int > d_ext → clampé, pas de crash
    assert len(m.faces) > 0


def test_entretoise_ronde_d_int_max():

    m = entretoise(d_ext=12, d_int=20, hauteur=15, forme="rond")
    assert len(m.faces) > 0


def test_magnet_logement_trop_profond_clampe():

    piece = magnet(texte="", diametre=35, ep=4, prof_aimant=5.0)   # levait ValueError
    assert piece is not None


def test_vase_zero_ondulation_sans_division_par_zero():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)   # tout /0 numpy = échec
        m = vase(hauteur=80, diametre=50, ondulations=0)
    assert len(m.faces) > 0


def test_percer_tout_le_volume_erreur_claire():
    with pytest.raises(ValueError, match="retire tout le volume"):
        L.percer(L.cylindre(20, 10), L.cylindre(40, 30))


# ── Sandbox : les clés « _ » des params ne polluent pas le namespace ─────────
def test_sandbox_ignore_cles_privees():
    piece = L.executer_sandbox("piece = boite_3d(t, t, 5)",
                               {"t": 20, "__builtins__": {"open": open}})
    assert len(piece.faces) > 0


# ── Multiplate : positions relatives sur un même plateau + échappement XML ───
def _build_two_on_same_plate(tmp_path):
    from core.export.multiplate_3mf import build_multiplate_bambu
    a = trimesh.creation.box(extents=(20, 20, 10))
    b = trimesh.creation.box(extents=(20, 20, 10))
    b.apply_translation([40, 0, 0])            # côte à côte, même plateau
    cfg = PrintConfig()
    out = tmp_path / "deux_meme_plateau.3mf"
    build_multiplate_bambu(
        [{"mesh": a, "config": cfg, "plate": 0, "name": "A & <b>"},
         {"mesh": b, "config": cfg, "plate": 0, "name": "B"}],
        cfg, out, "X1 Carbon", "PLA", 0.4)
    return out


def test_multiplate_meme_plateau_pas_de_superposition(tmp_path):
    out = _build_two_on_same_plate(tmp_path)
    ns = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    with zipfile.ZipFile(out) as z:
        mm = ET.fromstring(z.read("3D/3dmodel.model").decode())
    items = mm.find(f"{ns}build").findall(f"{ns}item")
    # même plateau → même translation de groupe pour les 2 items (les positions
    # RELATIVES des meshes sont conservées, pas de recentrage individuel)
    t1 = items[0].get("transform").split()
    t2 = items[1].get("transform").split()
    assert t1[9:11] == t2[9:11], "recentrage individuel → superposition"


def test_multiplate_nom_objet_echappe_xml(tmp_path):
    out = _build_two_on_same_plate(tmp_path)   # nom « A & <b> » → XML doit parser
    with zipfile.ZipFile(out) as z:
        mm = ET.fromstring(z.read("3D/3dmodel.model").decode())      # ne lève pas
        ms = ET.fromstring(z.read("Metadata/model_settings.config").decode())
    assert mm is not None and ms is not None


# ── Patch per-object : repli id racine (assemblages « parent_sub ») ──────────
def test_patch_perobject_fallback_id_racine():
    from core.export.tmf_builder import _patch_model_settings_per_object
    xml = ('<?xml version="1.0"?><config>'
           '<object id="2"><metadata key="name" value="A"/>'
           '<part id="1" subtype="normal_part"/></object></config>')
    patched, n = _patch_model_settings_per_object(xml, {"2_5": {"wall_loops": "6"}})
    assert n == 1
    obj = ET.fromstring(patched).find("object")
    assert {"wall_loops"} <= {m.get("key") for m in obj.findall("metadata")}


# ── Décisions Emmanuel post-audit (Q1/Q2) ────────────────────────────────────
def test_volume_impression_parse_et_repli():
    from data.printers import volume_impression
    assert volume_impression("A1 Mini") == (180.0, 180.0, 180.0)
    assert volume_impression("Imprimante inconnue") == (256.0, 256.0, 256.0)


def test_piece_hors_plateau_mono():
    from core.neogen.catalogue import piece_hors_plateau
    ok = trimesh.creation.box(extents=(100, 100, 50))
    trop = trimesh.creation.box(extents=(300, 100, 50))
    assert piece_hors_plateau(ok, (256, 256, 256)) is None
    assert "plateau" in (piece_hors_plateau(trop, (256, 256, 256)) or "")
    # rotation 90° possible : 100×300 tient sur 310×110
    assert piece_hors_plateau(trop, (310, 110, 256)) is None


def test_piece_hors_plateau_multiplateaux_par_plateau():
    """Boîte lumineuse : la scène GLOBALE déborde mais chaque plateau tient."""
    from core.neogen.catalogue import piece_hors_plateau
    a = L.plateau(L.boite_3d(100, 100, 10), 0)
    b = L.deplacer(L.plateau(L.boite_3d(100, 100, 40), 1), 0, 200, 0)  # loin en Y
    sc = L.scene(a, b)
    assert piece_hors_plateau(sc, (256, 256, 256)) is None     # par plateau : OK
    # sans tags (tout plateau 0) la même scène déborderait
    sc2 = L.scene(L.boite_3d(100, 100, 10),
                  L.deplacer(L.boite_3d(100, 100, 40), 0, 200, 0))
    assert piece_hors_plateau(sc2, (256, 256, 256)) is not None


def test_renfort_exclut_profil_standard():
    """La boîte (profil 'standard' explicite) n'est JAMAIS renforcée auto."""
    from types import SimpleNamespace as NS
    from core.prefs import PREFS
    from ui.main_window import MainWindow
    PREFS.set("auto_reinforce_fragile", True)
    td = NS(object_count=2, objects=[NS(object_id="c"), NS(object_id="b")])
    fake = NS(
        _threemf_data=td,
        _overview_cache={"td": td, "obj_severities": {"c": 0.9, "b": 0.9}},
        _neogen_multiplate_profils={"c": "lithophanie", "b": "standard"},
        _current_config=PrintConfig(), _current_selection=None,
        _per_object_state={},
        _intent_selector=NS(capturer_selection=lambda: None,
                            _strength_group_idx=-1),
        _statusbar=NS(set_message=lambda *a, **k: None,
                      set_export_enabled=lambda *a, **k: None),
    )
    MainWindow._auto_renforcer_pieces_fragiles(fake)
    assert fake._per_object_state == {}    # ni couvercle ni boîte renforcés


def test_precompilation_recette_base_invalide_ecartee():
    from core.neogen.objets_module import _make_builder
    assert _make_builder({"id": "cassé", "code": "piece = boite_3d(10 10, 5)"}) is None
    ok = _make_builder({"id": "ok", "code": "piece = boite_3d(10, 10, 5)"})
    assert callable(ok)
