"""Genere kb_manifest.json pour l'auto-mise-a-jour de la base d'Oen.

A lancer APRES avoir (re)construit l'index (tools/kb_index.py) et AVANT d'uploader
les fichiers dans la release GitHub `neoslice-assets` (tag assistant-latest).

Ce que ca fait :
  - calcule le SHA-256 et la taille de chaque fichier de l'index ;
  - ecrit un kb_manifest.json versionne (que Oen lit pour se mettre a jour tout seul).

Usage :
  python tools/kb_make_manifest.py [--index DIR] [--version 2026-08-01] [--notes "..."]
                                   [--min-app 0.1.7] [--out kb_manifest.json]

Puis : uploader dans la release les fichiers d'index MODIFIES + kb_manifest.json.
Les utilisateurs qui ont deja la base ne retelechargent que les fichiers dont le
SHA-256 a change (incremental).
"""
from __future__ import annotations
import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = _ROOT / "data" / "kb" / "index"
INDEX_FILES = ("meta.json", "chunks.jsonl", "vectors.npy")


def _sha256(path: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _embed_model(index_dir: Path) -> str:
    try:
        meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))
        return meta.get("model", "bge-m3")
    except Exception:
        return "bge-m3"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Genere kb_manifest.json pour Oen.")
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX,
                    help="dossier de l'index (defaut: data/kb/index)")
    ap.add_argument("--version", default=_dt.date.today().isoformat(),
                    help="identifiant de version (defaut: date du jour ISO)")
    ap.add_argument("--notes", default="", help="note affichee a l'utilisateur")
    ap.add_argument("--min-app", default="", help="version minimale de l'app (ex: 0.1.7)")
    ap.add_argument("--files", nargs="*", default=list(INDEX_FILES),
                    help="fichiers/shards a inclure (defaut: index complet)")
    ap.add_argument("--out", type=Path, default=None,
                    help="chemin de sortie (defaut: <index>/kb_manifest.json)")
    args = ap.parse_args(argv)

    index_dir = args.index
    if not index_dir.exists():
        print(f"[ERREUR] index introuvable : {index_dir}", file=sys.stderr)
        return 2

    # Detection auto d'un index SHARDE : si shards.json existe et que l'utilisateur
    # n'a pas force --files, on liste meta.json + shards.json + tous les shards.
    shards_json = index_dir / "shards.json"
    if args.files == list(INDEX_FILES) and shards_json.exists():
        spec = json.loads(shards_json.read_text(encoding="utf-8"))
        names = ["meta.json", "shards.json"]
        for s in spec.get("shards", []):
            names += [s["vectors"], s["chunks"]]
        args.files = names
        print(f"Index sharde detecte : {len(spec.get('shards', []))} shards.")

    files = []
    total = 0
    for name in args.files:
        p = index_dir / name
        if not p.exists():
            print(f"[ERREUR] fichier manquant : {p}", file=sys.stderr)
            return 2
        size = p.stat().st_size
        print(f"  hash {name} ({size/1e6:.1f} Mo)...", flush=True)
        files.append({"name": name, "sha256": _sha256(p), "size": size})
        total += size

    manifest = {
        "kb_version": args.version,
        "embed_model": _embed_model(index_dir),
        "files": files,
    }
    if args.min_app:
        manifest["min_app_version"] = args.min_app
    if args.notes:
        manifest["notes"] = args.notes

    out = args.out or (index_dir / "kb_manifest.json")
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nOK -> {out}")
    print(f"  version   : {manifest['kb_version']}")
    print(f"  embed     : {manifest['embed_model']}")
    print(f"  fichiers  : {len(files)}  |  total : {total/1e6:.0f} Mo")
    print("\nEtape suivante : uploader dans la release 'assistant-latest' les fichiers")
    print("d'index modifies + kb_manifest.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
