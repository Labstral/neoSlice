"""Régression : 3MF SANS Metadata/model_settings.config (export Fusion/trimesh).

Bug post-0.1.6 : `_parse_threemf_multiobject` levait UnboundLocalError (`root`,
`modifier_part_ids`) quand le zip n'avait pas le config Bambu. Corrigé le
2026-07-08 : la fonction doit rendre la main proprement (None = mono-objet)."""
import zipfile

import pytest
import trimesh

from core.geometry.stl_loader import (
    STLLoadError, _is_sliced_3mf, _parse_threemf_multiobject, load_stl,
)


def test_3mf_sans_model_settings_config(tmp_path):
    p = tmp_path / "fusion_like.3mf"
    trimesh.creation.box((10, 10, 10)).export(p)   # 3MF standard, sans config Bambu
    loaded = trimesh.load(p)
    scene = loaded if isinstance(loaded, trimesh.Scene) else trimesh.Scene(loaded)
    # Ne doit lever AUCUNE exception ; mono-objet simple → None (repli normal).
    assert _parse_threemf_multiobject(p, scene) is None


def _make_sliced(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Metadata/plate_1.gcode", "; G-code\nG28\n")
        z.writestr("3D/3dmodel.model", "<model/>")


def test_sliced_3mf_detecte_par_nom(tmp_path):
    p = tmp_path / "piece.gcode.3mf"
    _make_sliced(p)
    assert _is_sliced_3mf(p) is True


def test_sliced_3mf_detecte_par_contenu_meme_renomme(tmp_path):
    # Fichier tranché renommé en .3mf → détecté via Metadata/plate_N.gcode.
    p = tmp_path / "piece_renomme.3mf"
    _make_sliced(p)
    assert _is_sliced_3mf(p) is True


def test_3mf_modele_normal_pas_flagge(tmp_path):
    # Un vrai modèle (avec une vignette de plateau .png mais AUCUN .gcode) doit passer.
    p = tmp_path / "modele.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
        z.writestr("Metadata/plate_1.png", "fake")
    assert _is_sliced_3mf(p) is False


def test_load_stl_refuse_fichier_tranche(tmp_path):
    p = tmp_path / "piece.gcode.3mf"
    _make_sliced(p)
    with pytest.raises(STLLoadError, match="tranch"):
        load_stl(p)
