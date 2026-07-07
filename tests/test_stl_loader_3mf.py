"""Régression : 3MF SANS Metadata/model_settings.config (export Fusion/trimesh).

Bug post-0.1.6 : `_parse_threemf_multiobject` levait UnboundLocalError (`root`,
`modifier_part_ids`) quand le zip n'avait pas le config Bambu. Corrigé le
2026-07-08 : la fonction doit rendre la main proprement (None = mono-objet)."""
import trimesh

from core.geometry.stl_loader import _parse_threemf_multiobject


def test_3mf_sans_model_settings_config(tmp_path):
    p = tmp_path / "fusion_like.3mf"
    trimesh.creation.box((10, 10, 10)).export(p)   # 3MF standard, sans config Bambu
    loaded = trimesh.load(p)
    scene = loaded if isinstance(loaded, trimesh.Scene) else trimesh.Scene(loaded)
    # Ne doit lever AUCUNE exception ; mono-objet simple → None (repli normal).
    assert _parse_threemf_multiobject(p, scene) is None
