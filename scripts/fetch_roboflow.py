#!/usr/bin/env python3
"""Télécharge des datasets Roboflow (détection) et les convertit en crops de
classification mappés sur la taxonomie neoSlice → enrichit la base d'entraînement.

Sortie : <out>/<classe>/*.jpg  (crops centrés sur le défaut, prêts à fusionner).

Usage :
    python scripts/fetch_roboflow.py --key <ROBOFLOW_KEY> --out c:/train_data/roboflow_crops
"""
from __future__ import annotations

import argparse
import io
import json
import urllib.request
from pathlib import Path

# Mapping Roboflow → classes neoSlice (on ignore ce qui n'est pas mappé)
CLASS_MAP = {
    "Over Extrusion":  "over_extrusion",
    "over extrusion":  "over_extrusion",
    # "error extrusion" volontairement NON mappé : ambigu (sur OU sous-extrusion)
    "Under Extrusion": "under_extrusion",
    "under extrusion": "under_extrusion",
    "Warping":         "warping",
    "warping":         "warping",
    "Layer Shifting":  "layer_shift",
    "layer shifting":  "layer_shift",
    "Z-Banding":       "z_wobble",
    "z-banding":       "z_wobble",
    "Spaghetti":       "spaghetti",
    "spaghetti":       "spaghetti",
    "Stringing":       "stringing",
    "stringing":       "stringing",
}

# Datasets Roboflow à récupérer (workspace, project)
DATASETS = [
    ("project-jkfnh", "defect-detection-in-3d-printing-9vutd"),
    ("atco",          "3d-printing-error"),
]

_MIN_CROP = 48   # ignore les crops plus petits que 48px (trop flous/petits)


def latest_version(ws: str, proj: str, key: str) -> int | None:
    url = f"https://api.roboflow.com/{ws}/{proj}?api_key={key}"
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.loads(r.read())
    versions = d.get("versions", [])
    if versions:
        # versions triées : prendre la plus récente (id le plus grand)
        ids = []
        for v in versions:
            vid = v.get("id", "").split("/")[-1]
            try: ids.append(int(vid))
            except Exception: pass
        if ids:
            return max(ids)
    return 1


def crop_and_map(coco_dir: Path, out: Path, prefix: str) -> dict:
    """Parse un export COCO, découpe chaque boîte, mappe la classe, sauve le crop.
    `prefix` (nom du dataset) évite les collisions de noms entre datasets."""
    from PIL import Image
    counts: dict[str, int] = {}
    for split in ("train", "valid", "test"):
        ann = coco_dir / split / "_annotations.coco.json"
        if not ann.exists():
            continue
        data = json.loads(ann.read_text())
        cats = {c["id"]: c["name"] for c in data.get("categories", [])}
        imgs = {im["id"]: im for im in data.get("images", [])}
        for a in data.get("annotations", []):
            cat = cats.get(a["category_id"], "")
            cls = CLASS_MAP.get(cat) or CLASS_MAP.get(cat.strip())
            if not cls:
                continue
            im = imgs.get(a["image_id"])
            if not im:
                continue
            x, y, w, h = a["bbox"]
            if w < _MIN_CROP or h < _MIN_CROP:
                continue
            img_path = coco_dir / split / im["file_name"]
            if not img_path.exists():
                continue
            try:
                img = Image.open(img_path).convert("RGB")
                # marge de 15% autour de la boîte pour le contexte
                mx, my = int(w * 0.15), int(h * 0.15)
                box = (max(0, int(x - mx)), max(0, int(y - my)),
                       min(img.width,  int(x + w + mx)),
                       min(img.height, int(y + h + my)))
                crop = img.crop(box)
                cls_dir = out / cls
                cls_dir.mkdir(parents=True, exist_ok=True)
                n = counts.get(cls, 0)
                crop.save(cls_dir / f"rf_{prefix}_{cls}_{n:05d}.jpg", quality=90)
                counts[cls] = n + 1
            except Exception:
                pass
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", default="c:/train_data/roboflow_crops")
    args = ap.parse_args()

    from roboflow import Roboflow
    rf = Roboflow(api_key=args.key)
    out = Path(args.out)
    total: dict[str, int] = {}

    for ws, proj in DATASETS:
        print(f"\n=== {ws}/{proj} ===")
        try:
            ver = latest_version(ws, proj, args.key)
            print(f"  version {ver} — téléchargement (COCO)...")
            project = rf.workspace(ws).project(proj)
            dl = project.version(ver).download(
                "coco", location=str(Path("c:/train_data/_rf_tmp") / proj), overwrite=True
            )
            counts = crop_and_map(Path(dl.location), out, prefix=proj[:12])
            print(f"  crops: {counts}")
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        except Exception as exc:
            print(f"  ERREUR : {exc}")

    print("\n=== TOTAL crops par classe ===")
    for k in sorted(total):
        print(f"  {k}: {total[k]}")
    print(f"\nSortie : {out}")


if __name__ == "__main__":
    main()
