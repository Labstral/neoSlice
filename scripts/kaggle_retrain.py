#!/usr/bin/env python3
"""Ré-entraînement automatique hebdomadaire du modèle de défauts — Kaggle.

À exécuter dans un notebook Kaggle planifié (GPU T4/P100, gratuit).
Pipeline 100% automatique, zéro intervention :

  1. Télécharge les nouvelles photos contribuées depuis Supabase Storage
  2. Les fusionne avec le dataset de base (Kaggle Dataset attaché)
  3. Ré-entraîne EfficientNet-V2-S
  4. GARDE-FOU : ne publie QUE si val_acc >= modèle actuel (sinon rejet)
  5. Publie l'ONNX + met à jour model_manifest.json sur GitHub Releases
     → l'app récupère le nouveau modèle automatiquement

Secrets Kaggle requis (Add-ons → Secrets) :
  - SUPABASE_URL        : https://obmypmocuwnhuxbsaxhx.supabase.co
  - SUPABASE_SERVICE_KEY: clé service_role (lecture du bucket — JAMAIS dans l'app)
  - GITHUB_TOKEN        : token avec scope 'repo' (publication des releases)

Dataset Kaggle attaché (base) :
  - Nommé "neoslice-defect-base", monté dans /kaggle/input/neoslice-defect-base/
    avec la structure train/<classe>/ et val/<classe>/

Usage Kaggle (une cellule) :
    !pip -q install timm onnx onnxruntime albumentations
    exec(open('/kaggle/input/neoslice-scripts/kaggle_retrain.py').read())
  ou coller directement le contenu de ce fichier dans une cellule.
"""
from __future__ import annotations

import io
import json
import hashlib
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

# DOIT rester identique à core/defect_detection/detector.py CLASS_ORDER (10 sorties)
CLASS_NAMES = [
    "good", "stringing", "warping", "under_extrusion", "over_extrusion",
    "layer_shift", "spaghetti", "pillowing", "elephants_foot", "z_wobble",
]

GITHUB_OWNER  = "Labstral"
GITHUB_REPO   = "neoSlice"
RELEASE_TAG   = "models"
SUPABASE_BUCKET = "defect-contributions"

BASE_DATASET = Path("/kaggle/input/neoslice-defect-base")  # train/ et val/
WORK         = Path("/kaggle/working")
DATA_DIR     = WORK / "dataset"
OUT_DIR      = WORK / "out"

MODEL_NAME   = "tf_efficientnetv2_s.in21k_ft_in1k"
INPUT_SIZE   = 224
BATCH_SIZE   = 32
EPOCHS       = int(os.environ.get("NEOSLICE_EPOCHS", "15"))
LR           = 3e-4
MIN_NEW_PHOTOS = int(os.environ.get("NEOSLICE_MIN_NEW", "1"))  # seuil de déclenchement
VAL_MARGIN   = 0.0   # nouveau modèle accepté si val_acc >= ancien - VAL_MARGIN


# ──────────────────────────────────────────────────────────────────────────────
# Secrets
# ──────────────────────────────────────────────────────────────────────────────

def get_secrets() -> dict:
    """Récupère les secrets Kaggle (ou variables d'env en local)."""
    vals = {}
    try:
        from kaggle_secrets import UserSecretsClient
        c = UserSecretsClient()
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN"):
            vals[k] = c.get_secret(k)
    except Exception:
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN"):
            vals[k] = os.environ.get(k, "")
    missing = [k for k, v in vals.items() if not v]
    if missing:
        raise RuntimeError(f"Secrets manquants : {missing}")
    vals["SUPABASE_URL"] = vals["SUPABASE_URL"].rstrip("/")
    return vals


# ──────────────────────────────────────────────────────────────────────────────
# 1. Téléchargement des contributions Supabase
# ──────────────────────────────────────────────────────────────────────────────

def _sb_request(method: str, url: str, key: str, data: bytes | None = None,
                content_type: str = "application/json") -> bytes:
    req = urllib.request.Request(url, data=data, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": content_type,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _sb_list(base: str, key: str, prefix: str) -> list[dict]:
    """Liste les objets sous un préfixe (un niveau)."""
    url = f"{base}/storage/v1/object/list/{SUPABASE_BUCKET}"
    out, offset = [], 0
    while True:
        body = json.dumps({"prefix": prefix, "limit": 1000, "offset": offset}).encode()
        items = json.loads(_sb_request("POST", url, key, body))
        if not items:
            break
        out.extend(items)
        if len(items) < 1000:
            break
        offset += 1000
    return out


def download_contributions(secrets: dict, dest: Path) -> int:
    """Télécharge images/<classe>/<hash>.jpg → dest/<classe>/<hash>.jpg."""
    base, key = secrets["SUPABASE_URL"], secrets["SUPABASE_SERVICE_KEY"]
    total = 0
    for cls in CLASS_NAMES:
        prefix = f"images/{cls}/"
        try:
            objs = _sb_list(base, key, prefix)
        except Exception as exc:
            print(f"  list {cls}: {exc}")
            continue
        cls_dir = dest / cls
        cls_dir.mkdir(parents=True, exist_ok=True)
        for o in objs:
            name = o.get("name")
            if not name or o.get("id") is None:
                continue  # entrée dossier
            out = cls_dir / name
            if out.exists():
                continue
            try:
                url = f"{base}/storage/v1/object/{SUPABASE_BUCKET}/{prefix}{name}"
                out.write_bytes(_sb_request("GET", url, key))
                total += 1
            except Exception:
                pass
        if objs:
            print(f"  {cls}: {len(list(cls_dir.glob('*.jpg')))} photos contribuées")
    return total


# ──────────────────────────────────────────────────────────────────────────────
# 2. Fusion dataset de base + contributions
# ──────────────────────────────────────────────────────────────────────────────

def build_dataset(contrib: Path) -> None:
    import shutil, random
    rng = random.Random(42)
    for split in ("train", "val"):
        for cls in CLASS_NAMES:
            (DATA_DIR / split / cls).mkdir(parents=True, exist_ok=True)
    # Base
    if BASE_DATASET.exists():
        for split in ("train", "val"):
            for cls in CLASS_NAMES:
                src = BASE_DATASET / split / cls
                if src.exists():
                    for p in src.glob("*"):
                        dst = DATA_DIR / split / cls / p.name
                        if not dst.exists():
                            try: shutil.copy2(p, dst)
                            except Exception: pass
    # Contributions → 85% train / 15% val
    for cls in CLASS_NAMES:
        src = contrib / cls
        if not src.exists():
            continue
        imgs = list(src.glob("*.jpg"))
        rng.shuffle(imgs)
        n_val = max(1, int(len(imgs) * 0.15)) if imgs else 0
        for i, p in enumerate(imgs):
            split = "val" if i < n_val else "train"
            dst = DATA_DIR / split / cls / f"contrib_{p.name}"
            if not dst.exists():
                try: shutil.copy2(p, dst)
                except Exception: pass


# ──────────────────────────────────────────────────────────────────────────────
# 3-4. Entraînement + validation
# ──────────────────────────────────────────────────────────────────────────────

def build_model(num_classes: int):
    import timm, torch.nn as nn
    backbone = timm.create_model(MODEL_NAME, pretrained=True, num_classes=0, drop_rate=0.3)
    dim = backbone.num_features

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = backbone
            self.dropout = nn.Dropout(0.3)
            self.head = nn.Linear(dim, num_classes)
        def forward(self, x):
            e = self.dropout(self.backbone(x))
            return self.head(e), e
    return Net()


def transforms(train: bool):
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    if train:
        return A.Compose([
            A.RandomResizedCrop(size=(INPUT_SIZE, INPUT_SIZE), scale=(0.7, 1.0)),
            A.HorizontalFlip(p=0.5), A.Rotate(limit=15, p=0.5),
            A.ColorJitter(0.3, 0.3, 0.2, 0.1, p=0.7),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ])
    return A.Compose([
        A.Resize(INPUT_SIZE, INPUT_SIZE),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])


def loaders():
    import numpy as np, torch
    from torch.utils.data import Dataset, DataLoader
    from PIL import Image

    class DS(Dataset):
        def __init__(self, root, train):
            self.s, self.t = [], transforms(train)
            for i, c in enumerate(CLASS_NAMES):
                d = root / c
                if d.exists():
                    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                        self.s += [(p, i) for p in d.glob(ext)]
        def __len__(self): return len(self.s)
        def __getitem__(self, i):
            p, y = self.s[i]
            a = self.t(image=np.array(Image.open(p).convert("RGB")))
            return a["image"], y

    tr = DS(DATA_DIR / "train", True)
    va = DS(DATA_DIR / "val", False)
    print(f"Train {len(tr)} | Val {len(va)}")
    return (DataLoader(tr, BATCH_SIZE, shuffle=True, num_workers=2, pin_memory=True),
            DataLoader(va, BATCH_SIZE, shuffle=False, num_workers=2, pin_memory=True))


def train_and_eval() -> tuple[object, float]:
    import torch, torch.nn as nn
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import OneCycleLR

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", dev)
    tr, va = loaders()
    model = build_model(len(CLASS_NAMES)).to(dev)
    crit = nn.CrossEntropyLoss(label_smoothing=0.1)
    opt = AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = OneCycleLR(opt, max_lr=LR, epochs=EPOCHS, steps_per_epoch=max(1, len(tr)), pct_start=0.2)

    best = 0.0
    best_state = None
    for ep in range(1, EPOCHS + 1):
        model.train()
        for x, y in tr:
            x, y = x.to(dev), y.to(dev)
            opt.zero_grad()
            out, _ = model(x)
            loss = crit(out, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
        # val
        model.eval(); ok = tot = 0
        with torch.no_grad():
            for x, y in va:
                x, y = x.to(dev), y.to(dev)
                out, _ = model(x)
                ok += (out.argmax(1) == y).sum().item(); tot += len(y)
        acc = ok / max(1, tot)
        print(f"  epoch {ep}/{EPOCHS} val_acc={acc:.4f}")
        if acc >= best:
            best, best_state = acc, {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model, best


def export_onnx(model) -> Path:
    import torch
    from onnxruntime.quantization import quantize_dynamic, QuantType
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.eval().cpu()
    fp32 = OUT_DIR / "model_fp32.onnx"
    torch.onnx.export(
        model, torch.randn(1, 3, INPUT_SIZE, INPUT_SIZE), str(fp32),
        input_names=["image"], output_names=["logits", "embedding"],
        dynamic_axes={"image": {0: "batch"}}, opset_version=17, do_constant_folding=True,
    )
    out = OUT_DIR / "defect_detector.onnx"
    quantize_dynamic(str(fp32), str(out), weight_type=QuantType.QInt8)
    fp32.unlink(missing_ok=True)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 5. Publication GitHub Release + manifest
# ──────────────────────────────────────────────────────────────────────────────

def _gh(method: str, url: str, token: str, data: bytes | None = None,
        content_type: str = "application/json") -> bytes:
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": content_type,
        "User-Agent": "neoslice-retrain",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def get_current_manifest(token: str) -> dict:
    url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/{RELEASE_TAG}/model_manifest.json?t={int(time.time())}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "neoslice-retrain"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {"version": 0, "val_acc": 0.0}


def publish(onnx_path: Path, val_acc: float, num_images: int, token: str) -> None:
    api = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tags/{RELEASE_TAG}"
    rel = json.loads(_gh("GET", api, token))
    rel_id = rel["id"]
    upload_base = rel["upload_url"].split("{")[0]

    cur = get_current_manifest(token)
    new_version = int(cur.get("version", 0)) + 1
    onnx_name = f"defect_detector_v{new_version}.onnx"
    sha = hashlib.sha256(onnx_path.read_bytes()).hexdigest()

    # Supprime d'anciens assets de même nom (onnx + manifest)
    for a in rel.get("assets", []):
        if a["name"] in (onnx_name, "model_manifest.json"):
            try: _gh("DELETE", f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/assets/{a['id']}", token)
            except Exception: pass

    # Upload ONNX
    _gh("POST", f"{upload_base}?name={onnx_name}", token,
        data=onnx_path.read_bytes(), content_type="application/octet-stream")

    manifest = {
        "version": new_version,
        "filename": onnx_name,
        "url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/{RELEASE_TAG}/{onnx_name}",
        "sha256": sha,
        "val_acc": round(float(val_acc), 4),
        "num_images": num_images,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _gh("POST", f"{upload_base}?name=model_manifest.json", token,
        data=json.dumps(manifest, indent=2).encode(), content_type="application/json")
    print(f"[PUBLIE] v{new_version} val_acc={val_acc:.4f} sha={sha[:12]}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    secrets = get_secrets()
    print("=== Téléchargement contributions Supabase ===")
    contrib = WORK / "contrib"
    n_new = download_contributions(secrets, contrib)
    print(f"Total nouvelles photos : {n_new}")

    if n_new < MIN_NEW_PHOTOS:
        print(f"Moins de {MIN_NEW_PHOTOS} nouvelle(s) photo(s) — ré-entraînement ignoré.")
        return

    print("=== Construction dataset ===")
    build_dataset(contrib)

    print("=== Entraînement ===")
    model, val_acc = train_and_eval()
    print(f"Meilleure val_acc : {val_acc:.4f}")

    # GARDE-FOU
    cur = get_current_manifest(secrets["GITHUB_TOKEN"])
    cur_acc = float(cur.get("val_acc", 0.0))
    print(f"val_acc actuel publié : {cur_acc:.4f}")
    if val_acc + 1e-9 < cur_acc - VAL_MARGIN:
        print(f"[REJET] Nouveau modèle ({val_acc:.4f}) < actuel ({cur_acc:.4f}) — pas de publication.")
        return

    print("=== Export ONNX + publication ===")
    onnx = export_onnx(model)
    n_total = sum(len(list((DATA_DIR / 'train' / c).glob('*')) + list((DATA_DIR / 'val' / c).glob('*'))) for c in CLASS_NAMES)
    publish(onnx, val_acc, n_total, secrets["GITHUB_TOKEN"])
    print("=== Terminé ===")


if __name__ == "__main__":
    main()
