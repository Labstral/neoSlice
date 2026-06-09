#!/usr/bin/env python3
"""Télécharge des images candidates depuis la recherche web pour les classes
sans dataset public (pillowing, elephants_foot) -> dossiers À VALIDER par un humain.

[!] Les résultats contiennent du bruit (schémas, hors-sujet, watermarks) : un tri
manuel est OBLIGATOIRE avant d'entraîner. Usage : amorçage (seed) uniquement.

    python scripts/fetch_web_images.py --out c:/train_data/web_review
"""
from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

QUERIES = {
    "elephants_foot": [
        "3d print elephant foot defect",
        "elephant's foot 3d printing first layer",
        "3d print elephant foot bottom bulge",
        "pied d'elephant impression 3d defaut",
        "fdm print elephant foot base flare",
        "elephant foot 3d print problem photo",
    ],
    "pillowing": [
        "3d print pillowing top surface",
        "pillowing 3d printing defect top layer",
        "3d print rough bumpy top surface pillowing",
        "pillowing fdm print top layer holes",
        "3d printing top layer pillowing problem photo",
    ],
}

_MAX_PER_CLASS = 130
_MIN_BYTES = 6000
_HEADERS = {"User-Agent": "Mozilla/5.0 (neoSlice dataset seed)"}


def _ddgs():
    try:
        from ddgs import DDGS
    except Exception:
        from duckduckgo_search import DDGS
    return DDGS


def fetch_urls(queries: list[str], limit: int) -> list[str]:
    DDGS = _ddgs()
    seen, urls = set(), []
    with DDGS() as d:
        for q in queries:
            try:
                for r in d.images(q, max_results=40):
                    u = r.get("image")
                    if u and u not in seen and u.lower().split("?")[0].endswith(
                        (".jpg", ".jpeg", ".png", ".webp", ".bmp")
                    ):
                        seen.add(u); urls.append(u)
            except Exception as exc:
                print(f"    requête '{q}': {exc}")
            if len(urls) >= limit * 2:
                break
    return urls


def download(urls: list[str], dest: Path, limit: int) -> int:
    from PIL import Image
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for u in urls:
        if n >= limit:
            break
        try:
            req = urllib.request.Request(u, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) < _MIN_BYTES:
                continue
            img = Image.open(io.BytesIO(data)).convert("RGB")
            if min(img.size) < 120:          # trop petit
                continue
            img.save(dest / f"web_{n:04d}.jpg", quality=90)
            n += 1
        except Exception:
            pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="c:/train_data/web_review")
    ap.add_argument("--max", type=int, default=_MAX_PER_CLASS)
    args = ap.parse_args()
    out = Path(args.out)

    for cls, queries in QUERIES.items():
        print(f"\n=== {cls} ===")
        urls = fetch_urls(queries, args.max)
        print(f"  {len(urls)} URLs candidates")
        kept = download(urls, out / cls, args.max)
        print(f"  {kept} images téléchargées -> {out / cls}")

    print("\n[!] TRI MANUEL REQUIS : ouvre chaque dossier, supprime les images")
    print("   hors-sujet / schémas / mauvaise classe. Garde uniquement les vraies photos.")


if __name__ == "__main__":
    main()
