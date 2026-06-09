#!/usr/bin/env python3
"""Script d'entraînement du modèle de détection de défauts 3D.

Architecture : EfficientNet-V2-S (timm) + fine-tuning + export ONNX INT8 quantisé

Environnement requis (séparé de l'env neoSlice) :
    pip install torch torchvision timm onnx onnxruntime scikit-learn
    pip install albumentations pillow tqdm

Datasets recommandés :
    1. Bambu/Obico Spaghetti Detective open dataset
       https://github.com/TheSpaghettiDetective/obico-server (Apache 2.0)

    2. Kaggle — 3D Printing Failure Dataset
       https://www.kaggle.com/datasets/nipunsoumya/3d-printing-failure-dataset

    3. Roboflow Universe — 3D Printing Defects
       https://roboflow.com/search?q=3d+printing+defects

    4. Dataset synthétique neoSlice (photos collectées via contribution)
       ~/.neoslice/defect_photos/

Structure dossier attendue :
    data/defect_dataset/
    ├── train/
    │   ├── good/           (photos de bonnes impressions)
    │   ├── stringing/
    │   ├── warping/
    │   ├── under_extrusion/
    │   ├── over_extrusion/
    │   ├── layer_shift/
    │   ├── spaghetti/
    │   ├── pillowing/
    │   ├── elephants_foot/
    │   └── z_wobble/
    └── val/
        └── (même structure)

Usage :
    python scripts/train_defect_model.py --data data/defect_dataset --epochs 30
    python scripts/train_defect_model.py --data data/defect_dataset --resume checkpoint.pth
"""
from __future__ import annotations

import argparse
import json
import hashlib
import time
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

CLASS_NAMES = [
    "good", "stringing", "warping", "under_extrusion", "over_extrusion",
    "layer_shift", "spaghetti", "pillowing", "elephants_foot", "z_wobble",
]

MODEL_NAME      = "tf_efficientnetv2_s.in21k_ft_in1k"
INPUT_SIZE      = 224
BATCH_SIZE      = 32
LR              = 3e-4
LR_MIN          = 1e-6
WEIGHT_DECAY    = 1e-4
WARMUP_EPOCHS   = 3
DROPOUT         = 0.3
EMBED_DIM       = 1280    # dimension du penultième layer EfficientNet-V2-S

OUTPUT_DIR      = Path("models/defect_detector")
CHECKPOINT_FILE = OUTPUT_DIR / "best_checkpoint.pth"
ONNX_FILE       = OUTPUT_DIR / "defect_detector_v1.onnx"


# ──────────────────────────────────────────────────────────────────────────────
# Modèle
# ──────────────────────────────────────────────────────────────────────────────

def build_model(num_classes: int):
    import timm
    import torch.nn as nn

    backbone = timm.create_model(
        MODEL_NAME,
        pretrained=True,
        num_classes=0,      # on retire la tête de classification
        drop_rate=DROPOUT,
    )
    embed_dim = backbone.num_features

    class DefectClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = backbone
            self.dropout = nn.Dropout(DROPOUT)
            self.head = nn.Linear(embed_dim, num_classes)

        def forward(self, x):
            emb = self.backbone(x)
            emb = self.dropout(emb)
            logits = self.head(emb)
            return logits, emb  # retourne logits ET embedding

    return DefectClassifier(), embed_dim


# ──────────────────────────────────────────────────────────────────────────────
# Augmentation
# ──────────────────────────────────────────────────────────────────────────────

def build_transforms(is_train: bool):
    import albumentations as A
    from albumentations.pytorch import ToTensorV2

    if is_train:
        return A.Compose([
            A.RandomResizedCrop(size=(INPUT_SIZE, INPUT_SIZE), scale=(0.7, 1.0)),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.2),
            A.Rotate(limit=15, p=0.5),
            A.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.1, p=0.7),
            A.GaussianBlur(blur_limit=(3, 7), p=0.3),
            A.GaussNoise(p=0.3),
            A.RandomBrightnessContrast(p=0.5),
            A.CLAHE(p=0.3),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ])
    else:
        return A.Compose([
            A.Resize(height=INPUT_SIZE, width=INPUT_SIZE),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ])


# ──────────────────────────────────────────────────────────────────────────────
# Dataset
# ──────────────────────────────────────────────────────────────────────────────

def build_dataloaders(data_root: Path, batch_size: int):
    import torch
    from torch.utils.data import DataLoader, Dataset
    from PIL import Image
    import numpy as np

    class DefectDataset(Dataset):
        def __init__(self, root: Path, is_train: bool):
            self.samples = []
            self.transform = build_transforms(is_train)
            for cls_idx, cls_name in enumerate(CLASS_NAMES):
                cls_dir = root / cls_name
                if not cls_dir.exists():
                    continue
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    for p in cls_dir.glob(ext):
                        self.samples.append((p, cls_idx))

        def __len__(self):
            return len(self.samples)

        def __getitem__(self, idx):
            path, label = self.samples[idx]
            img = np.array(Image.open(path).convert("RGB"))
            augmented = self.transform(image=img)
            return augmented["image"], label

    train_ds = DefectDataset(data_root / "train", is_train=True)
    val_ds   = DefectDataset(data_root / "val",   is_train=False)

    print(f"Train : {len(train_ds)} images | Val : {len(val_ds)} images")

    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                          num_workers=0, pin_memory=True)
    val_dl   = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                          num_workers=0, pin_memory=True)
    return train_dl, val_dl


# ──────────────────────────────────────────────────────────────────────────────
# Entraînement
# ──────────────────────────────────────────────────────────────────────────────

def train(args):
    import torch
    import torch.nn as nn
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import OneCycleLR
    from tqdm import tqdm

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device : {device}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data_root = Path(args.data)
    train_dl, val_dl = build_dataloaders(data_root, args.batch_size)

    model, _ = build_model(len(CLASS_NAMES))
    model = model.to(device)

    if args.resume and Path(args.resume).exists():
        ckpt = torch.load(args.resume, map_location=device)
        model.load_state_dict(ckpt["model"])
        print(f"Repris depuis {args.resume}")

    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=WEIGHT_DECAY)
    scheduler = OneCycleLR(
        optimizer,
        max_lr=args.lr,
        epochs=args.epochs,
        steps_per_epoch=len(train_dl),
        pct_start=WARMUP_EPOCHS / args.epochs,
    )

    best_val_acc = 0.0
    history = []

    for epoch in range(1, args.epochs + 1):
        # ── Train ────────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        correct = 0
        total = 0
        for imgs, labels in tqdm(train_dl, desc=f"Epoch {epoch}/{args.epochs}"):
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            logits, _ = model(imgs)
            loss = criterion(logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            train_loss += loss.item()
            correct += (logits.argmax(1) == labels).sum().item()
            total += len(labels)

        train_acc = correct / total
        avg_loss = train_loss / len(train_dl)

        # ── Validation ───────────────────────────────────────────────────
        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for imgs, labels in val_dl:
                imgs, labels = imgs.to(device), labels.to(device)
                logits, _ = model(imgs)
                val_correct += (logits.argmax(1) == labels).sum().item()
                val_total += len(labels)
        val_acc = val_correct / val_total

        print(f"  loss={avg_loss:.4f}  train_acc={train_acc:.3f}  val_acc={val_acc:.3f}")
        history.append({"epoch": epoch, "loss": avg_loss, "train_acc": train_acc, "val_acc": val_acc})

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save({"model": model.state_dict(), "val_acc": val_acc, "epoch": epoch},
                       CHECKPOINT_FILE)
            print(f"  [OK] Nouveau meilleur modèle sauvegardé ({val_acc:.3%})")

    # Sauvegarde historique
    (OUTPUT_DIR / "training_history.json").write_text(
        json.dumps(history, indent=2), encoding="utf-8"
    )
    print(f"\nMeilleure précision val : {best_val_acc:.3%}")
    return CHECKPOINT_FILE


# ──────────────────────────────────────────────────────────────────────────────
# Export ONNX
# ──────────────────────────────────────────────────────────────────────────────

def export_onnx(checkpoint_path: Path) -> Path:
    import torch
    import onnx
    from onnxruntime.quantization import quantize_dynamic, QuantType

    device = torch.device("cpu")
    model, _ = build_model(len(CLASS_NAMES))
    ckpt = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(ckpt["model"])
    model.eval()

    dummy = torch.randn(1, 3, INPUT_SIZE, INPUT_SIZE)
    onnx_fp32 = OUTPUT_DIR / "defect_detector_fp32.onnx"

    torch.onnx.export(
        model,
        dummy,
        str(onnx_fp32),
        input_names=["image"],
        output_names=["logits", "embedding"],
        dynamic_axes={"image": {0: "batch"}},
        opset_version=17,
        do_constant_folding=True,
    )
    print(f"ONNX FP32 exporté : {onnx_fp32} ({onnx_fp32.stat().st_size // 1024} Ko)")

    # Quantisation INT8 -> ~4× plus léger
    quantize_dynamic(
        str(onnx_fp32),
        str(ONNX_FILE),
        weight_type=QuantType.QInt8,
    )
    size_mb = ONNX_FILE.stat().st_size / 1024 / 1024
    print(f"ONNX INT8 exporté : {ONNX_FILE} ({size_mb:.1f} Mo)")

    # Calcule le SHA256 pour KNOWN_CHECKSUMS
    sha = hashlib.sha256(ONNX_FILE.read_bytes()).hexdigest()
    print(f"\n[SHA256] SHA256 pour model_manager.py :\n  \"{ONNX_FILE.name}\": \"{sha}\"")

    # Sauvegarde un fichier metadata
    meta = {
        "filename": ONNX_FILE.name,
        "sha256": sha,
        "size_mb": round(size_mb, 2),
        "class_order": CLASS_NAMES,
        "input_size": INPUT_SIZE,
        "architecture": MODEL_NAME,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUTPUT_DIR / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\n[INFO] Metadata : {OUTPUT_DIR / 'model_meta.json'}")

    onnx_fp32.unlink()  # supprime la version FP32
    return ONNX_FILE


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Entraîne le modèle de détection de défauts 3D")
    parser.add_argument("--data",       required=True,  help="Dossier du dataset (contient train/ et val/)")
    parser.add_argument("--epochs",     type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--lr",         type=float, default=LR)
    parser.add_argument("--resume",     default="",   help="Chemin vers un checkpoint .pth")
    parser.add_argument("--export-only", action="store_true",
                        help="Export ONNX uniquement depuis le meilleur checkpoint existant")
    args = parser.parse_args()

    if args.export_only:
        if not CHECKPOINT_FILE.exists():
            print(f"Checkpoint introuvable : {CHECKPOINT_FILE}")
            return
        export_onnx(CHECKPOINT_FILE)
    else:
        ckpt = train(args)
        print("\nExport ONNX...")
        export_onnx(ckpt)

    print("\n[OK] Terminé.")
    print(f"Copiez {ONNX_FILE} vers :")
    print(f"  ~/.neoslice/models/defect_detector_v1.onnx")
    print(f"Et publiez sur GitHub Releases -> {ONNX_FILE.name}")


if __name__ == "__main__":
    main()

