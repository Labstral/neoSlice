"""Decoupe un index RAG mono-fichier en SHARDS, pour des mises a jour DELTA.

Pourquoi : l'index complet fait ~2,2 Go. En le decoupant en N shards
(vectors_XXX.npy + chunks_XXX.jsonl) chacun avec son empreinte, un enrichissement
ne remplace que les shards modifies -> les utilisateurs ne retelechargent que
quelques dizaines de Mo (voir core/assistant/kb_update.py, incremental par fichier).

Ce script NE re-embarque RIEN : il tranche l'index existant (vectors.npy /
chunks.jsonl) en morceaux. Le RAG (rag.py) sait charger la forme shardee si
`shards.json` est present, sinon la forme mono-fichier (retro-compatible).

Usage :
  python tools/kb_shard.py [--index data/kb/index] [--rows 20000] [--out DIR]
  # puis: python tools/kb_make_manifest.py --index <OUT> --version ... (auto-shards)

Recommandation : garder des shards ~ constants (par ex. 20 000 passages) et surtout
STABLES dans le temps : ajouter du contenu = de NOUVEAUX shards a la fin, sans
retoucher les anciens -> delta minimal. (Ce decoupage initial est par blocs de
lignes ; l'ordre des passages est preserve, donc rag reste identique.)
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = _ROOT / "data" / "kb" / "index"


def _read_chunks(path: Path) -> list[str]:
    return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Decoupe l'index RAG en shards.")
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX,
                    help="index mono-fichier source (defaut: data/kb/index)")
    ap.add_argument("--rows", type=int, default=20000,
                    help="passages par shard (defaut: 20000)")
    ap.add_argument("--out", type=Path, default=None,
                    help="dossier de sortie (defaut: <index>_sharded)")
    args = ap.parse_args(argv)

    src = args.index
    vec_p = src / "vectors.npy"
    chunk_p = src / "chunks.jsonl"
    meta_p = src / "meta.json"
    if not (vec_p.exists() and chunk_p.exists()):
        print(f"[ERREUR] index mono-fichier introuvable dans {src}", file=sys.stderr)
        return 2

    out = args.out or src.parent / (src.name + "_sharded")
    out.mkdir(parents=True, exist_ok=True)

    vectors = np.load(vec_p, mmap_mode="r")
    chunk_lines = _read_chunks(chunk_p)
    n = vectors.shape[0]
    if n != len(chunk_lines):
        print(f"[ERREUR] desynchronisation vectors ({n}) / chunks ({len(chunk_lines)})",
              file=sys.stderr)
        return 2

    rows = max(1, args.rows)
    shards = []
    idx = 0
    for start in range(0, n, rows):
        end = min(start + rows, n)
        vname = f"vectors_{idx:03d}.npy"
        cname = f"chunks_{idx:03d}.jsonl"
        np.save(out / vname, np.asarray(vectors[start:end]))
        (out / cname).write_text("\n".join(chunk_lines[start:end]) + "\n", encoding="utf-8")
        shards.append({"vectors": vname, "chunks": cname, "rows": end - start})
        print(f"  shard {idx:03d} : {end - start} passages -> {vname}", flush=True)
        idx += 1

    (out / "shards.json").write_text(
        json.dumps({"shards": shards}, indent=2), encoding="utf-8")
    # meta.json est copie tel quel (modele d'embedding, dim...) : indispensable au RAG.
    if meta_p.exists():
        (out / "meta.json").write_text(meta_p.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"\nOK -> {out}  ({idx} shards de {rows} passages)")
    print("Etape suivante :")
    print(f"  python tools/kb_make_manifest.py --index \"{out}\" --version <ID> [--notes ...]")
    print("  puis uploader dans la release les shards MODIFIES + shards.json + meta.json + kb_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
