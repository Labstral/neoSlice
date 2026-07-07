"""Tests du sharding de l'index RAG : équivalence mono-fichier/shardé, manifest
auto-shardé, mise à jour delta. L'embedder est court-circuité (aucun Ollama)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from core.assistant import rag
from core.assistant.engine import AssistantEngine
from core.assistant.kb_update import KBUpdater

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def mono_index(tmp_path, monkeypatch):
    """Index mono-fichier synthétique (50 passages, 8 dim) + requête déterministe."""
    D, N = 8, 50
    rng = np.random.default_rng(0)
    V = rng.standard_normal((N, D)).astype(np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    mono = tmp_path / "index"
    mono.mkdir()
    np.save(mono / "vectors.npy", V.astype(np.float16))
    (mono / "chunks.jsonl").write_text(
        "\n".join(json.dumps({"text": f"chunk_{i}", "title": "t", "url": ""})
                  for i in range(N)), encoding="utf-8")
    (mono / "meta.json").write_text('{"model":"bge-m3","dim":8}', encoding="utf-8")
    q = rng.standard_normal(D).astype(np.float32)
    q /= np.linalg.norm(q)
    monkeypatch.setattr(AssistantEngine.instance(), "embed_one",
                        lambda text: q.tolist())
    return mono


def _search_in(dirpath: Path):
    rag._index_dir = lambda: Path(dirpath)   # injection du dossier d'index
    rag._loaded = False
    rag._shards = None
    rag._chunks = None
    rag._meta_cache = None
    return rag.search("peu importe", k=5, min_score=-1.0)


def _shard(mono: Path, out: Path, rows: int = 10):
    r = subprocess.run(
        [sys.executable, str(_ROOT / "tools" / "kb_shard.py"),
         "--index", str(mono), "--rows", str(rows), "--out", str(out)],
        cwd=_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_sharde_equivaut_au_mono(mono_index, tmp_path):
    mono_res = _search_in(mono_index)
    assert len(mono_res) == 5
    sharded = tmp_path / "sharded"
    _shard(mono_index, sharded)
    spec = json.loads((sharded / "shards.json").read_text())
    assert len(spec["shards"]) == 5
    assert (sharded / "meta.json").exists()
    sh_res = _search_in(sharded)
    assert [h["text"] for h in sh_res] == [h["text"] for h in mono_res]
    assert all(abs(a["score"] - b["score"]) < 1e-3
               for a, b in zip(mono_res, sh_res))


def test_manifest_auto_sharde(mono_index, tmp_path):
    sharded = tmp_path / "sharded"
    _shard(mono_index, sharded)
    r = subprocess.run(
        [sys.executable, str(_ROOT / "tools" / "kb_make_manifest.py"),
         "--index", str(sharded), "--version", "2026-09-01"],
        cwd=_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    man = json.loads((sharded / "kb_manifest.json").read_text())
    names = [f["name"] for f in man["files"]]
    assert "shards.json" in names and "meta.json" in names
    assert sum(n.startswith("vectors_") for n in names) == 5
    assert sum(n.startswith("chunks_") for n in names) == 5
    assert "vectors.npy" not in names   # forme mono non listée


def test_maj_delta_ne_telecharge_que_le_shard_modifie(mono_index, tmp_path):
    sharded = tmp_path / "sharded"
    _shard(mono_index, sharded)
    subprocess.run(
        [sys.executable, str(_ROOT / "tools" / "kb_make_manifest.py"),
         "--index", str(sharded), "--version", "2026-09-01"],
        cwd=_ROOT, capture_output=True, text=True)
    man = json.loads((sharded / "kb_manifest.json").read_text())
    installed = tmp_path / "installed"
    installed.mkdir()
    for f in man["files"]:
        if f["name"] != "vectors_002.npy":     # simule 1 shard modifié/absent
            shutil.copy(sharded / f["name"], installed / f["name"])
    (installed / "kb_version.json").write_text(
        '{"kb_version":"2026-08-01","embed_model":"bge-m3"}')
    up = KBUpdater(index_dir=installed,
                   manifest_url=(sharded / "kb_manifest.json").as_uri(),
                   base_url=sharded.as_uri())
    info = up.check()
    missing = next(f for f in man["files"] if f["name"] == "vectors_002.npy")
    assert info["download_size"] == missing["size"]
    up.update(info)
    assert (installed / "vectors_002.npy").exists()
    assert json.loads((installed / "kb_version.json").read_text())["kb_version"] == "2026-09-01"
