"""Recuperation RAG : retrouve les passages de wiki les plus pertinents pour une
question, a partir de l'index construit par tools/kb_index.py.

100 pour cent local : embedding de la question via Ollama, similarite cosinus avec
les vecteurs pre-calcules (charges une fois, en memoire). Tolerant aux erreurs :
si l'index est absent, search() renvoie une liste vide et l'assistant repond avec
ses seules connaissances de base.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import numpy as np

# Liste de matrices (N_i, D) float16 en mmap : 1 element pour un index mono-fichier,
# plusieurs pour un index decoupe en shards (voir shards.json). Garder des mmap
# separes evite de tout charger en RAM (~1,5 Go) et permet les MAJ delta par shard.
_shards: Optional[list] = None
_chunks: Optional[list[dict]] = None
_loaded = False


_meta_cache: dict | None = None


def _index_dir() -> Path:
    """Dossier d'index actif (installe si present, sinon celui livre en dev)."""
    from core.assistant.engine import kb_index_dir
    return kb_index_dir()


def _meta() -> dict:
    """Lit meta.json de l'index (mis en cache). Contient notamment
    `nomic_prefixed` : True si les passages ont ete embarques avec le prefixe
    nomic `search_document:` (alors la requete doit etre prefixee `search_query:`)."""
    global _meta_cache
    if _meta_cache is None:
        _meta_cache = {}
        try:
            p = _index_dir() / "meta.json"
            if p.exists():
                _meta_cache = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _meta_cache = {}
    return _meta_cache


def available() -> bool:
    d = _index_dir()
    if (d / "shards.json").exists():
        return True
    return (d / "vectors.npy").exists() and (d / "chunks.jsonl").exists()


def _read_chunks(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load() -> bool:
    """Charge l'index : soit mono-fichier (vectors.npy + chunks.jsonl), soit decoupe
    en shards (shards.json liste des paires vectors/chunks). Les deux formes donnent
    la meme liste _shards (mmap) + _chunks (concatenation, ordre des shards)."""
    global _shards, _chunks, _loaded
    if _loaded:
        return _shards is not None
    _loaded = True
    if not available():
        return False
    try:
        d = _index_dir()
        shard_manifest = d / "shards.json"
        if shard_manifest.exists():
            spec = json.loads(shard_manifest.read_text(encoding="utf-8"))
            shards, chunks = [], []
            for s in spec.get("shards", []):
                shards.append(np.load(d / s["vectors"], mmap_mode="r"))
                chunks.extend(_read_chunks(d / s["chunks"]))
            _shards, _chunks = shards, chunks
        else:
            _shards = [np.load(d / "vectors.npy", mmap_mode="r")]
            _chunks = _read_chunks(d / "chunks.jsonl")
        if not _shards or sum(int(s.shape[0]) for s in _shards) != len(_chunks):
            _shards, _chunks = None, None
            return False
    except Exception:
        _shards, _chunks = None, None
        return False
    return True


def search(query: str, k: int = 8, min_score: float = 0.30) -> list[dict]:
    """Renvoie jusqu'a k passages {text, title, url, score} tries par pertinence."""
    if not query or not _load():
        return []
    try:
        from core.assistant.engine import AssistantEngine
        # nomic-embed-text exige le prefixe `search_query:` pour la requete, MAIS
        # seulement si les passages ont ete embarques avec `search_document:`
        # (sinon on melange deux espaces et on degrade). Conditionne au meta.
        q_text = query
        if _meta().get("nomic_prefixed"):
            q_text = "search_query: " + query
        qv = AssistantEngine.instance().embed_one(q_text)
        if not qv:
            return []
        q = np.asarray(qv, np.float32)
        q /= (np.linalg.norm(q) or 1.0)
        # Produit scalaire (cosinus, vecteurs deja normalises) PAR BLOCS, sur chaque
        # shard : les vecteurs sont stockes en float16 (index plus leger) ; on recaste
        # en float32 par tranches pour eviter une copie geante de toute la matrice.
        # Les scores sont concatenes dans l'ordre des shards = ordre de _chunks.
        _B = 100_000
        _parts = []
        for _V in _shards:
            _N = int(_V.shape[0])
            sc = np.empty(_N, dtype=np.float32)
            for _i in range(0, _N, _B):
                sc[_i:_i + _B] = np.asarray(_V[_i:_i + _B], dtype=np.float32) @ q
            _parts.append(sc)
        scores = _parts[0] if len(_parts) == 1 else np.concatenate(_parts)
        n = min(k, scores.shape[0])
        idx = np.argpartition(-scores, n - 1)[:n]
        idx = idx[np.argsort(-scores[idx])]
    except Exception:
        return []
    out = []
    for i in idx:
        s = float(scores[i])
        if s < min_score:
            continue
        c = _chunks[int(i)]
        out.append({"text": c.get("text", ""), "title": c.get("title", ""),
                    "url": c.get("url", ""), "score": round(s, 3)})
    return out


def context_block(query: str, k: int = 8, max_chars: int = 3000) -> str:
    """Bloc de connaissances (extraits de wikis) a injecter dans le prompt. Vide si
    rien de pertinent."""
    hits = search(query, k=k)
    if not hits:
        return ""
    parts, total = [], 0
    for h in hits:
        txt = h["text"].strip()
        src = h.get("title") or h.get("url") or "wiki"
        block = f"[{src}]\n{txt}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    if not parts:
        return ""
    return ("CONNAISSANCES (documentation constructeur ci-dessous). Elle FAIT AUTORITE : "
            "base ta reponse dessus EN PRIORITE et ne la contredis pas avec ta memoire. "
            "Chaque extrait indique sa source entre [crochets] : tiens compte de la MARQUE "
            "de la source et ne l'attribue pas a une autre marque. Reponds pour l'imprimante "
            "de l'utilisateur ; si un extrait concerne une autre marque, ne t'en sers pas "
            "pour affirmer une specificite de sa machine :\n\n"
            + "\n\n---\n\n".join(parts))
