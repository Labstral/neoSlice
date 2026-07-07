"""Tests de core.assistant.kb_update (auto-MAJ de la base d'Oen).

Hermétiques : manifest et assets servis en file:// depuis un dossier temporaire,
index « installé » injecté — aucun réseau, aucun toucher au vrai index.
"""
import json
import hashlib
from pathlib import Path

import pytest

from core.assistant.kb_update import KBUpdater


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def _make_manifest(remote: Path, version: str, files, embed="bge-m3",
                   min_app=None, bad_sha_for=None) -> Path:
    entries = []
    for name in files:
        p = remote / name
        sha = _sha(p) if name != bad_sha_for else "deadbeef" * 8
        entries.append({"name": name, "sha256": sha, "size": p.stat().st_size})
    man = {"kb_version": version, "embed_model": embed, "files": entries}
    if min_app:
        man["min_app_version"] = min_app
    out = remote / "kb_manifest.json"
    out.write_text(json.dumps(man), encoding="utf-8")
    return out


def _updater(installed: Path, remote: Path) -> KBUpdater:
    return KBUpdater(index_dir=installed,
                     manifest_url=(remote / "kb_manifest.json").as_uri(),
                     base_url=remote.as_uri())


@pytest.fixture()
def env(tmp_path):
    """(remote, installed) : base distante v2026-08-01, locale v2026-07-01."""
    remote = tmp_path / "remote"
    installed = tmp_path / "installed"
    _write(remote / "meta.json", b'{"model":"bge-m3","kb_version":"2026-08-01"}')
    _write(remote / "chunks.jsonl", b'{"text":"NOUVEAU passage"}\n')
    _write(remote / "vectors.npy", b"\x01\x02\x03NEW")
    _make_manifest(remote, "2026-08-01", ["meta.json", "chunks.jsonl", "vectors.npy"])
    _write(installed / "meta.json", b'{"model":"bge-m3","kb_version":"2026-07-01"}')
    _write(installed / "chunks.jsonl", b'{"text":"vieux passage"}\n')
    _write(installed / "vectors.npy", b"\x00OLD")
    (installed / "kb_version.json").write_text(
        '{"kb_version":"2026-07-01","embed_model":"bge-m3"}')
    return remote, installed


def test_detecte_une_maj(env):
    remote, installed = env
    info = _updater(installed, remote).check()
    assert info is not None
    assert info["kb_version"] == "2026-08-01"
    assert info["download_size"] > 0


def test_update_applique_et_versionne(env):
    remote, installed = env
    up = _updater(installed, remote)
    assert up.update(up.check()) is True
    assert (installed / "chunks.jsonl").read_bytes() == b'{"text":"NOUVEAU passage"}\n'
    assert json.loads((installed / "kb_version.json").read_text())["kb_version"] == "2026-08-01"
    assert not (installed / ".staging").exists()
    assert not (installed / ".backup").exists()


def test_aucune_maj_quand_a_jour(env):
    remote, installed = env
    up = _updater(installed, remote)
    up.update(up.check())
    assert up.check() is None


def test_incremental_saute_fichier_inchange(tmp_path):
    remote, installed = tmp_path / "r", tmp_path / "i"
    same_meta = b'{"model":"bge-m3"}'
    _write(remote / "meta.json", same_meta)
    _write(installed / "meta.json", same_meta)
    _write(remote / "chunks.jsonl", b"CHUNKS v2")
    _write(installed / "chunks.jsonl", b"CHUNKS v1")
    _write(remote / "vectors.npy", b"VEC v2")
    _write(installed / "vectors.npy", b"VEC v1")
    (installed / "kb_version.json").write_text(
        '{"kb_version":"2026-07-01","embed_model":"bge-m3"}')
    _make_manifest(remote, "2026-09-01", ["meta.json", "chunks.jsonl", "vectors.npy"])
    up = _updater(installed, remote)
    info = up.check()
    # meta.json (identique) exclu du volume à télécharger
    assert info["download_size"] == info["total_size"] - (remote / "meta.json").stat().st_size
    up.update(info)
    assert (installed / "chunks.jsonl").read_bytes() == b"CHUNKS v2"
    assert (installed / "vectors.npy").read_bytes() == b"VEC v2"


def test_integrite_ko_rollback_index_conserve(tmp_path):
    remote, installed = tmp_path / "r", tmp_path / "i"
    _write(remote / "meta.json", b'{"model":"bge-m3"}')
    _write(remote / "chunks.jsonl", b"NOUVEAU chunks")
    _write(remote / "vectors.npy", b"NOUVEAU vectors CORROMPU")
    _make_manifest(remote, "2026-10-01", ["meta.json", "chunks.jsonl", "vectors.npy"],
                   bad_sha_for="vectors.npy")
    _write(installed / "meta.json", b'{"model":"bge-m3"}')
    _write(installed / "chunks.jsonl", b"ANCIEN chunks")
    _write(installed / "vectors.npy", b"ANCIEN vectors")
    (installed / "kb_version.json").write_text(
        '{"kb_version":"2026-07-01","embed_model":"bge-m3"}')
    up = _updater(installed, remote)
    with pytest.raises(Exception):
        up.update(up.check())
    # L'index existant est intact, version inchangée, pas de résidus
    assert (installed / "chunks.jsonl").read_bytes() == b"ANCIEN chunks"
    assert (installed / "vectors.npy").read_bytes() == b"ANCIEN vectors"
    assert json.loads((installed / "kb_version.json").read_text())["kb_version"] == "2026-07-01"
    assert not (installed / ".staging").exists()
    assert not (installed / ".backup").exists()


def test_refuse_autre_modele_embedding(tmp_path):
    remote, installed = tmp_path / "r", tmp_path / "i"
    _write(remote / "meta.json", b'{"model":"nomic"}')
    _write(remote / "chunks.jsonl", b"x")
    _write(remote / "vectors.npy", b"y")
    _make_manifest(remote, "2027-01-01", ["meta.json", "chunks.jsonl", "vectors.npy"],
                   embed="nomic-embed-text")
    _write(installed / "kb_version.json",
           b'{"kb_version":"2026-07-01","embed_model":"bge-m3"}')
    assert _updater(installed, remote).check() is None


def test_min_app_version_bloque(env, monkeypatch):
    remote, installed = env
    import core.assistant.kb_update as kbu
    monkeypatch.setattr(kbu, "_app_version", lambda: "0.1.6")
    _make_manifest(remote, "2026-08-01", ["meta.json", "chunks.jsonl", "vectors.npy"],
                   min_app="9.9.9")
    info = _updater(installed, remote).check()
    assert info is not None and info.get("incompatible_app") is True
    with pytest.raises(RuntimeError):
        _updater(installed, remote).update(info)


def test_hors_ligne_safe(tmp_path):
    up = KBUpdater(index_dir=tmp_path,
                   manifest_url="file:///zzz/inexistant.json",
                   base_url="file:///zzz")
    assert up.check() is None
