#!/usr/bin/env python3
"""Prépare et consolide les datasets publics de défauts d'impression 3D.

Sources supportées :
  1. nimbus200 (Kaggle) — CSV labels + images dossier plat
  2. totolvroum (Kaggle) — dossiers par classe (bed_not_stick, etc.)
  3. Roboflow exports (format dossiers par classe)
  4. Photos de contribution neoSlice (~/.neoslice/defect_photos/)
  5. Dossier custom (structure dossiers par classe)

Résultat :
  data/defect_dataset/
  ├── train/  (80%)
  └── val/    (20%)

Usage :
  python scripts/prepare_dataset.py --nimbus c:/train_data/raw/nimbus
  python scripts/prepare_dataset.py --totolvroum c:/train_data/raw/totolvroum
  python scripts/prepare_dataset.py --all --output data/defect_dataset
"""
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

CLASSES = [
    "good", "stringing", "warping", "under_extrusion", "over_extrusion",
    "layer_shift", "spaghetti", "pillowing", "elephants_foot", "z_wobble",
]

# Mappings entre noms de classes des datasets publics et nos noms
KAGGLE_CLASS_MAP: dict[str, str] = {
    # nimbus200 — classes numériques (CSV)
    "0":                    "good",
    "1":                    "under_extrusion",
    "2":                    "stringing",
    "4":                    "spaghetti",
    # totolvroum — noms de dossiers
    "bed_not_stick":        "warping",
    "layer_shifting":       "layer_shift",
    "over_extrusion":       "over_extrusion",
    "under_extrusion":      "under_extrusion",
    "stringing":            "stringing",
    "spaghetti":            "spaghetti",
    "good":                 "good",
    "normal":               "good",
    "ok":                   "good",
    # noms génériques variantes
    "warping":              "warping",
    "underExtrusion":       "under_extrusion",
    "overExtrusion":        "over_extrusion",
    "layer_shift":          "layer_shift",
    "layerShift":           "layer_shift",
    "pillowing":            "pillowing",
    "elephants_foot":       "elephants_foot",
    "elephantsFoot":        "elephants_foot",
    "z_wobble":             "z_wobble",
    "zWobble":              "z_wobble",
    "NoDefects":            "good",
    # wengmhu (capitalisé)
    "Cracking":             "z_wobble",
    "Layer_shifting":       "layer_shift",
    "Off_platform":         "warping",
    "Stringing":            "stringing",
    "Warping":              "warping",
}

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def collect_from_nimbus(src: Path) -> dict[str, list[Path]]:
    """Collecte depuis le dataset nimbus200 (CSV labels + images dans un dossier plat)."""
    import csv
    collected: dict[str, list[Path]] = {cls: [] for cls in CLASSES}

    csv_candidates = list(src.rglob("all_images_no_filter.csv"))
    if not csv_candidates:
        print(f"  [!] all_images_no_filter.csv introuvable dans {src}")
        return collected

    csv_path = csv_candidates[0]
    img_dir = src / "Printing_Errors" / "images" / "all_images256"
    if not img_dir.exists():
        # chercher le dossier images
        candidates = list(src.rglob("all_images256"))
        img_dir = candidates[0] if candidates else src

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            img_name = row.get("image", "").strip()
            cls_num  = row.get("class", "").strip()
            mapped   = KAGGLE_CLASS_MAP.get(cls_num)
            if not mapped:
                continue
            img_path = img_dir / img_name
            if img_path.exists():
                collected[mapped].append(img_path)

    for cls, imgs in collected.items():
        if imgs:
            print(f"  {cls}: +{len(imgs)} images (nimbus200)")
    return collected


def collect_from_folder(src: Path, label_map: dict[str, str] | None = None) -> dict[str, list[Path]]:
    """Collecte les images depuis un dossier structuré en sous-dossiers par classe."""
    collected: dict[str, list[Path]] = {cls: [] for cls in CLASSES}
    for cls_dir in src.iterdir():
        if not cls_dir.is_dir():
            continue
        cls_name = cls_dir.name
        if label_map:
            cls_name = label_map.get(cls_name, cls_name)
        if cls_name not in CLASSES:
            print(f"  [skip] {cls_dir.name} (non mappee)")
            continue
        imgs = [p for p in cls_dir.rglob("*") if p.suffix.lower() in VALID_EXTENSIONS]
        collected[cls_name].extend(imgs)
        print(f"  {cls_name}: +{len(imgs)} images")
    return collected


def collect_from_contribution() -> dict[str, list[Path]]:
    """Collecte les photos confirmées depuis ~/.neoslice/defect_photos/."""
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from core.defect_detection.dataset_manager import DatasetManager

    dm = DatasetManager()
    samples = dm.get_confirmed_samples()
    collected: dict[str, list[Path]] = {cls: [] for cls in CLASSES}
    for s in samples:
        p = Path(s["image_path"])
        if p.exists() and s["true_class"] in CLASSES:
            collected[s["true_class"]].append(p)
    total = sum(len(v) for v in collected.values())
    print(f"  Contribution neoSlice : {total} images confirmées")
    return collected


def merge_collections(*collections: dict[str, list[Path]]) -> dict[str, list[Path]]:
    merged: dict[str, list[Path]] = {cls: [] for cls in CLASSES}
    for col in collections:
        for cls, imgs in col.items():
            merged[cls].extend(imgs)
    return merged


def split_and_copy(
    collected: dict[str, list[Path]],
    output: Path,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> None:
    rng = random.Random(seed)
    output.mkdir(parents=True, exist_ok=True)
    (output / "train").mkdir(exist_ok=True)
    (output / "val").mkdir(exist_ok=True)

    total_train = 0
    total_val = 0

    print(f"\nCopie vers {output}...")
    for cls in CLASSES:
        imgs = collected[cls]
        if not imgs:
            print(f"  [!] {cls}: 0 images — classe ignorée")
            continue

        rng.shuffle(imgs)
        n_val = max(1, int(len(imgs) * val_ratio))
        val_imgs = imgs[:n_val]
        train_imgs = imgs[n_val:]

        for split_name, split_imgs in (("train", train_imgs), ("val", val_imgs)):
            dest_dir = output / split_name / cls
            dest_dir.mkdir(parents=True, exist_ok=True)
            for i, src in enumerate(split_imgs):
                ext = src.suffix.lower()
                dest = dest_dir / f"{cls}_{i:05d}{ext}"
                if not dest.exists():
                    shutil.copy2(src, dest)

        print(f"  {cls}: {len(train_imgs)} train, {n_val} val")
        total_train += len(train_imgs)
        total_val += n_val

    print(f"\nTotal : {total_train} train + {total_val} val = {total_train + total_val} images")

    # Stats rapides
    counts = {cls: len(imgs) for cls, imgs in collected.items() if imgs}
    if counts:
        min_cls = min(counts, key=counts.get)
        max_cls = max(counts, key=counts.get)
        ratio = counts[max_cls] / max(1, counts[min_cls])
        if ratio > 10:
            print(f"\n[!] Déséquilibre fort : {max_cls}({counts[max_cls]}) vs {min_cls}({counts[min_cls]})")
            print("  -> Le script d'entraînement utilise class_weight='balanced' pour compenser.")


def main():
    parser = argparse.ArgumentParser(description="Prépare le dataset de défauts 3D")
    parser.add_argument("--nimbus",    help="Dossier nimbus200 (CSV + images/all_images256/)")
    parser.add_argument("--totolvroum", help="Dossier totolvroum (sous-dossiers par classe)")
    parser.add_argument("--kaggle",    help="Dossier dataset Kaggle générique")
    parser.add_argument("--roboflow",  help="Dossier export Roboflow")
    parser.add_argument("--custom",    help="Dossier custom (structure par classe)")
    parser.add_argument("--contrib",   action="store_true",
                        help="Inclure les photos de contribution neoSlice")
    parser.add_argument("--all",       action="store_true",
                        help="Inclure toutes les sources détectées automatiquement")
    parser.add_argument("--output",    default="data/defect_dataset",
                        help="Dossier de sortie")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    args = parser.parse_args()

    collections = []

    if args.kaggle or args.all:
        src = Path(args.kaggle or "data/raw/kaggle_3dprint")
        if src.exists():
            print(f"Kaggle dataset : {src}")
            collections.append(collect_from_folder(src, KAGGLE_CLASS_MAP))
        else:
            print(f"[!] Kaggle dataset introuvable : {src}")

    # nimbus200 — auto-détect si --all
    nimbus_path = Path(args.nimbus) if args.nimbus else Path("c:/train_data/raw/nimbus")
    if args.nimbus or (args.all and nimbus_path.exists()):
        print(f"nimbus200 dataset : {nimbus_path}")
        collections.append(collect_from_nimbus(nimbus_path))

    # totolvroum — auto-détect si --all
    totol_path = Path(args.totolvroum) if args.totolvroum else Path("c:/train_data/raw/totolvroum")
    if args.totolvroum or (args.all and totol_path.exists()):
        print(f"totolvroum dataset : {totol_path}")
        # chercher le sous-dossier "3d printing defects" ou directement les classes
        inner = totol_path / "3d printing defects"
        src_dir = inner if inner.exists() else totol_path
        collections.append(collect_from_folder(src_dir, KAGGLE_CLASS_MAP))

    if args.kaggle:
        src = Path(args.kaggle)
        if src.exists():
            print(f"Kaggle dataset : {src}")
            collections.append(collect_from_folder(src, KAGGLE_CLASS_MAP))

    if args.roboflow:
        src = Path(args.roboflow)
        if src.exists():
            print(f"Roboflow dataset : {src}")
            collections.append(collect_from_folder(src, KAGGLE_CLASS_MAP))

    if args.custom:
        src = Path(args.custom)
        if src.exists():
            print(f"Dataset custom : {src}")
            collections.append(collect_from_folder(src, KAGGLE_CLASS_MAP))

    if args.contrib or args.all:
        print("Photos contribution neoSlice :")
        collections.append(collect_from_contribution())

    if not collections:
        print("Aucune source spécifiée. Utilisez --help pour les options.")
        return

    merged = merge_collections(*collections)
    total = sum(len(v) for v in merged.values())
    print(f"\nTotal après fusion : {total} images")

    split_and_copy(merged, Path(args.output), args.val_ratio)
    print(f"\n[OK] Dataset prêt dans {args.output}")
    print(f"Lancez maintenant : python scripts/train_defect_model.py --data {args.output}")


if __name__ == "__main__":
    main()
