"""Construit l'index RAG de la base de connaissances a partir des .md aspires.

Lit data/kb/**/*.md (wikis nettoyes), decoupe en passages, calcule un embedding
local par passage (via Ollama, modele nomic-embed-text) et enregistre :
  data/kb/index/vectors.npy   float32 (N, 768), L2-normalises (cosinus = produit scalaire)
  data/kb/index/chunks.jsonl  un JSON/ligne : {text, title, url, source}
  data/kb/index/meta.json     {model, dim, count, built}

Reprise auto : les fichiers .md deja indexes (presents dans chunks.jsonl) sont
ignores. On peut relancer apres interruption. Checkpoint tous les N fichiers.

Usage :
  python tools/kb_index.py               # tout data/kb
  python tools/kb_index.py --limit 30    # test rapide
  python tools/kb_index.py --root data/kb/bambu_wiki/fr
"""
from __future__ import annotations
import sys
import re
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
KB_ROOT = ROOT / "data" / "kb"
OUT_DIR = KB_ROOT / "index"
VEC_PATH = OUT_DIR / "vectors.npy"
CHUNKS_PATH = OUT_DIR / "chunks.jsonl"
META_PATH = OUT_DIR / "meta.json"

TARGET = 750       # taille cible d'un passage (caracteres)
OVERLAP = 120      # chevauchement entre passages
CHECKPOINT = 800   # sauvegarde tous les N fichiers (l'ecriture du gros .npy coute cher)
MAX_BODY = 60000   # au-dela, la page est tronquee (menus/tables geants -> bruit)
MAX_CHUNKS = 80    # nb max de passages par page (anti-explosion memoire/index)
BATCH = 128        # passages par lot d'embedding (128 = fiable pour bge-m3 ; 256 -> HTTP 400 intermittents)


def _parse_md(path: Path) -> tuple[str, str, str]:
    """Renvoie (title, url, body) en retirant le front-matter YAML."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    title = url = ""
    body = raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if m:
        fm = m.group(1)
        for line in fm.splitlines():
            if line.startswith("title:"):
                title = line[6:].strip()
            elif line.startswith("url:"):
                url = line[4:].strip()
        body = raw[m.end():]
    # Retire un eventuel titre H1 repete en tete
    body = re.sub(r"^\s*#\s+.*\n", "", body, count=1)
    return title, url, body.strip()


def _chunk(title: str, body: str) -> list[str]:
    """Decoupe le corps en passages ~TARGET caracteres, sur les limites de blocs,
    en prefixant le titre du document pour garder le contexte. Borne (MAX_BODY /
    MAX_CHUNKS) pour ne pas exploser sur des pages geantes (menus, tables, dumps)."""
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY]
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    chunks, cur = [], ""
    for b in blocks:
        if len(b) > TARGET * 1.6:
            # Bloc tres long : on le coupe en tranches avec chevauchement
            if cur:
                chunks.append(cur); cur = ""
            i = 0
            while i < len(b):
                chunks.append(b[i:i + TARGET])
                i += TARGET - OVERLAP
            continue
        if len(cur) + len(b) + 1 <= TARGET:
            cur = (cur + "\n" + b) if cur else b
        else:
            if cur:
                chunks.append(cur)
            cur = b
    if cur:
        chunks.append(cur)
    prefix = f"{title}\n" if title else ""
    out = [(prefix + c).strip() for c in chunks if c.strip()]
    return out[:MAX_CHUNKS]


def _load_existing(model: str = "") -> tuple[list, list, set]:
    """Charge un index partiel (reprise). Renvoie (vectors_list, chunk_dicts, sources_done).
    SECURITE : si l'index existant a ete construit avec un AUTRE modele d'embedding
    (donc une autre dimension), on NE reprend PAS (sinon on melangerait des vecteurs
    de dimensions differentes -> index corrompu). On repart de zero."""
    if model and META_PATH.exists():
        try:
            _old = json.loads(META_PATH.read_text(encoding="utf-8")).get("model")
            if _old and _old != model:
                print(f"  Modele d'embedding change ({_old} -> {model}) : re-index COMPLET.",
                      flush=True)
                return [], [], set()
        except Exception:
            pass
    vecs, chunks, done = [], [], set()
    if CHUNKS_PATH.exists() and VEC_PATH.exists():
        try:
            arr = np.load(VEC_PATH)
            vecs = [row for row in arr]
            for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    chunks.append(d)
                    done.add(d.get("source", ""))
            # Coherence : autant de vecteurs que de chunks
            if len(vecs) != len(chunks):
                return [], [], set()
        except Exception:
            return [], [], set()
    return vecs, chunks, done


def _save(vecs: list, chunks: list, model: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Vecteurs stockes en float16 : deux fois plus petits (un index bge-m3 1024 dim
    # sur 584k passages = ~2,4 Go en float32 > limite 2 Go d'un asset GitHub ; en
    # float16 -> ~1,2 Go, sous la limite, sans perte notable pour le cosinus sur des
    # vecteurs normalises). rag.py recaste en float32 pour le produit scalaire.
    arr = np.asarray(vecs, dtype=np.float16) if vecs else np.zeros((0, 1024), np.float16)
    # Ecriture atomique : fichier temporaire puis remplacement (evite un index a
    # moitie ecrit si l'ecriture est interrompue ou si un lecteur tient le fichier).
    import os
    tmp_vec = VEC_PATH.with_suffix(".npy.tmp")
    # IMPORTANT : passer un OBJET fichier, sinon np.save rajoute ".npy" au nom du
    # temporaire (-> "vectors.npy.tmp.npy") et os.replace echoue (FileNotFound).
    with open(tmp_vec, "wb") as f:
        np.save(f, arr)
    os.replace(tmp_vec, VEC_PATH)
    tmp_chunks = CHUNKS_PATH.with_suffix(".jsonl.tmp")
    with tmp_chunks.open("w", encoding="utf-8") as f:
        for d in chunks:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp_chunks, CHUNKS_PATH)
    META_PATH.write_text(json.dumps(
        {"model": model, "dim": int(arr.shape[1]) if arr.size else 1024,
         "count": len(chunks), "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "dtype": "float16",
         # True seulement pour nomic (prefixes de tache) : rag.py prefixe alors la
         # requete `search_query:`. bge-m3/multilingues -> False (aucun prefixe).
         "nomic_prefixed": ("nomic" in model.lower())},
        ensure_ascii=False, indent=2), encoding="utf-8")


def build(root: Path, limit: int | None = None) -> None:
    from core.assistant.engine import AssistantEngine, EMBED_MODEL
    eng = AssistantEngine.instance()
    _NOMIC = "nomic" in EMBED_MODEL.lower()   # seul nomic exige les prefixes de tache

    files = sorted(p for p in root.rglob("*.md"))
    if limit:
        files = files[:limit]
    vecs, chunks, done = _load_existing(EMBED_MODEL)
    todo = [f for f in files if str(f.relative_to(KB_ROOT)) not in done]
    print(f"{len(files)} fichiers, {len(done)} deja indexes, {len(todo)} a traiter. "
          f"{len(chunks)} passages existants.", flush=True)

    # PIPELINE (satura le GPU) : un thread PRODUCTEUR lit + decoupe les fichiers .md
    # (CPU) et remplit une file d'attente, pendant que le thread principal EMBARQUE en
    # continu (GPU). Sans pipeline, GPU et CPU s'attendaient (GPU ~60%) ; avec, le GPU
    # reste alimente en permanence -> nettement plus rapide.
    import threading
    import queue as _queue
    _q: "_queue.Queue" = _queue.Queue(maxsize=400)   # items : (src, [metas]) par fichier
    _SENTINEL = object()

    def _producer():
        for path in todo:
            src = str(path.relative_to(KB_ROOT))
            try:
                title, url, body = _parse_md(path)
                passages = _chunk(title, body)
                metas = [{"text": t, "title": title, "url": url, "source": src} for t in passages]
            except Exception:
                metas = []
            _q.put((src, metas))
        _q.put(_SENTINEL)

    threading.Thread(target=_producer, daemon=True).start()

    buf_texts: list[str] = []
    buf_meta: list[dict] = []
    buf_sources: list[str] = []

    def flush():
        # Marque les fichiers vides comme faits meme sans passage a embarquer.
        if not buf_texts:
            for s in buf_sources:
                done.add(s)
            buf_sources.clear()
            return
        try:
            # nomic-embed-text EXIGE le prefixe `search_document:` cote passages (et
            # `search_query:` cote requete, gere par rag.py). bge-m3/multilingues n'en
            # ont PAS besoin. Le prefixe n'est jamais stocke dans chunks.jsonl.
            if _NOMIC:
                embs = eng.embed(["search_document: " + t for t in buf_texts])
            else:
                embs = eng.embed(buf_texts)
        except Exception as e:
            print(f"  FAIL batch ({len(buf_texts)} passages): {str(e)[:80]}", flush=True)
            embs = []
        if embs and len(embs) == len(buf_texts):
            for meta, v in zip(buf_meta, embs):
                if not v:
                    continue
                n = float(np.linalg.norm(v)) or 1.0
                vecs.append(np.asarray(v, np.float32) / n)
                chunks.append(meta)
            for s in buf_sources:
                done.add(s)
        buf_texts.clear(); buf_meta.clear(); buf_sources.clear()

    processed = 0
    since_ckpt = 0
    _t0 = time.time()
    _n0 = len(chunks)   # passages deja presents (reprise)
    while True:
        item = _q.get()
        if item is _SENTINEL:
            break
        src, metas = item
        for m in metas:
            buf_texts.append(m["text"])
            buf_meta.append(m)
        buf_sources.append(src)
        processed += 1
        since_ckpt += 1
        if len(buf_texts) >= BATCH:
            flush()
        if processed % 20 == 0:
            _np = len(chunks) + len(buf_texts)
            _el = max(1e-6, time.time() - _t0)
            _rate = (_np - _n0) / _el                       # passages/s (session)
            _pct = 100.0 * processed / max(1, len(todo))
            _eta = (len(todo) - processed) / max(0.1, processed / _el) / 60.0  # min restantes
            print(f"[{processed}/{len(todo)} {_pct:4.1f}%] {_np} passages | "
                  f"{_rate:.0f} passages/s | ETA ~{_eta:.0f} min", flush=True)
        if since_ckpt >= CHECKPOINT:
            flush()   # vider le tampon avant sauvegarde (coherence chunks/vecteurs)
            _save(vecs, chunks, EMBED_MODEL)
            since_ckpt = 0
            print(f"  checkpoint : {len(chunks)} passages sauvegardes", flush=True)

    flush()
    _save(vecs, chunks, EMBED_MODEL)
    print(f"TERMINE : {len(chunks)} passages indexes -> {OUT_DIR}", flush=True)


def main():
    args = sys.argv[1:]
    root = KB_ROOT
    limit = None
    if "--root" in args:
        root = (ROOT / args[args.index("--root") + 1]).resolve()
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    build(root, limit)


if __name__ == "__main__":
    main()
