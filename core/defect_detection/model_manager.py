"""Gestion du modèle ONNX — téléchargement, vérification intégrité, auto-update.

Auto-update via manifest :
  - Un fichier model_manifest.json est publié sur les GitHub Releases (tag "models").
  - Il décrit le dernier modèle : version, url, sha256, précision de validation.
  - L'app lit le manifest au démarrage ; si une version plus récente existe,
    elle télécharge le nouveau modèle automatiquement (vérif SHA256).
  - Le manifest est mis à jour par le pipeline de ré-entraînement Kaggle.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.request import urlopen, Request

from loguru import logger

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

MODELS_DIR      = Path.home() / ".neoslice" / "models"
LOCAL_MODEL     = MODELS_DIR / "defect_detector.onnx"     # nom local fixe (toutes versions)
LEGACY_MODEL_V1 = MODELS_DIR / "defect_detector_v1.onnx"  # ancien nom (migration)
MODEL_META_FILE = MODELS_DIR / "model_meta.json"

_RELEASE_BASE = os.environ.get(
    "NEOSLICE_MODEL_URL",
    "https://github.com/Labstral/neoSlice/releases/download/models",
)
MANIFEST_URL = f"{_RELEASE_BASE}/model_manifest.json"

# Modèle v1 de secours (si le manifest est injoignable au tout premier lancement)
_FALLBACK = {
    "version":  1,
    "filename": "defect_detector_v1.onnx",
    "url":      f"{_RELEASE_BASE}/defect_detector_v1.onnx",
    "sha256":   "40824ad3063fc2a7cb15d88e3477c2769bf04f89e745d70d435e62fe7828f500",
}


class ModelManager:
    """Cycle de vie du modèle ONNX : présence, intégrité, auto-update.

    Usage :
        mgr = ModelManager()
        mgr.ensure_latest_async(on_done=cb)   # télécharge/maj en arrière-plan
        path = mgr.get_model_path()           # chemin local si dispo
    """

    def __init__(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy()

    # ── Migration ancien nom ────────────────────────────────────────────────

    def _migrate_legacy(self) -> None:
        if not LOCAL_MODEL.exists() and LEGACY_MODEL_V1.exists():
            try:
                LEGACY_MODEL_V1.replace(LOCAL_MODEL)
                meta = self._load_meta()
                meta.setdefault("installed", {"version": 1, "sha256": _FALLBACK["sha256"]})
                self._save_meta_raw(meta)
                logger.info("Modèle v1 migré vers le nom local fixe.")
            except Exception as exc:
                logger.debug(f"Migration v1 ignorée : {exc}")

    # ── État ────────────────────────────────────────────────────────────────

    @property
    def model_path(self) -> Path:
        return LOCAL_MODEL

    @property
    def is_available(self) -> bool:
        return LOCAL_MODEL.exists() and LOCAL_MODEL.stat().st_size > 0

    def get_model_path(self) -> Path | None:
        return LOCAL_MODEL if self.is_available else None

    def installed_version(self) -> int:
        return int(self._load_meta().get("installed", {}).get("version", 0))

    # ── Auto-update via manifest ────────────────────────────────────────────

    def ensure_latest_async(
        self,
        on_progress: Callable[[int, int], None] | None = None,
        on_done: Callable[[Path | None, str | None], None] | None = None,
    ) -> threading.Thread:
        """Vérifie le manifest et télécharge le modèle si nécessaire (arrière-plan)."""
        t = threading.Thread(
            target=self._update_worker, args=(on_progress, on_done), daemon=True
        )
        t.start()
        return t

    def ensure_latest_sync(self, on_progress: Callable | None = None) -> Path | None:
        """Version bloquante (à appeler depuis un thread de travail).
        Télécharge/maj le modèle si besoin et retourne son chemin."""
        try:
            manifest = self._fetch_manifest() or (None if self.is_available else _FALLBACK)
            if manifest is not None:
                remote_version = int(manifest.get("version", 0))
                if (not self.is_available) or remote_version > self.installed_version():
                    logger.info(f"Téléchargement du modèle → version {remote_version}")
                    self._download_and_install(manifest, on_progress)
        except Exception as exc:
            logger.error(f"ensure_latest_sync : {exc}")
        return self.get_model_path()

    def _update_worker(self, on_progress, on_done) -> None:
        try:
            manifest = self._fetch_manifest() or (
                None if self.is_available else _FALLBACK
            )
            if manifest is None:
                # Modèle déjà présent, manifest injoignable → on garde l'existant
                if on_done:
                    on_done(self.get_model_path(), None)
                return

            remote_version = int(manifest.get("version", 0))
            need = (not self.is_available) or remote_version > self.installed_version()
            if not need:
                if on_done:
                    on_done(self.get_model_path(), None)
                return

            logger.info(f"Mise à jour du modèle → version {remote_version}")
            self._download_and_install(manifest, on_progress)
            if on_done:
                on_done(self.get_model_path(), None)
        except Exception as exc:
            logger.error(f"Auto-update modèle échoué : {exc}")
            if on_done:
                on_done(self.get_model_path(), str(exc))

    def _download_and_install(self, manifest: dict, on_progress) -> None:
        url    = manifest["url"]
        sha    = manifest.get("sha256", "")
        tmp    = MODELS_DIR / "defect_detector.onnx.part"
        self._download(url, tmp, on_progress)

        if sha:
            got = hashlib.sha256(tmp.read_bytes()).hexdigest()
            if got != sha:
                tmp.unlink(missing_ok=True)
                raise ValueError(f"SHA256 invalide : {got[:12]} != {sha[:12]}")

        tmp.replace(LOCAL_MODEL)
        meta = self._load_meta()
        meta["installed"] = {
            "version":  int(manifest.get("version", 0)),
            "sha256":   sha,
            "val_acc":  manifest.get("val_acc"),
            "updated":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._save_meta_raw(meta)
        logger.info(f"Modèle installé : v{meta['installed']['version']} (val_acc={manifest.get('val_acc')})")

    # ── Téléchargement bas niveau ───────────────────────────────────────────

    @staticmethod
    def _fetch_manifest() -> dict | None:
        # cache-buster (le CDN GitHub sert parfois une vieille version de l'asset)
        url = f"{MANIFEST_URL}?t={int(time.time())}"
        try:
            req = Request(url, headers={"User-Agent": "neoSlice-model/1.0"})
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug(f"Manifest injoignable : {exc}")
            return None

    @staticmethod
    def _download(url: str, dest: Path, on_progress: Callable | None) -> Path:
        req = Request(url, headers={"User-Agent": "neoSlice-defect-detector/1.0"})
        with urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with dest.open("wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total > 0:
                        on_progress(downloaded, total)
        return dest

    # ── Métadonnées ─────────────────────────────────────────────────────────

    def _save_meta_raw(self, meta: dict) -> None:
        MODEL_META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @staticmethod
    def _load_meta() -> dict:
        if MODEL_META_FILE.exists():
            try:
                return json.loads(MODEL_META_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def delete_model(self) -> None:
        LOCAL_MODEL.unlink(missing_ok=True)
        logger.info("Modèle local supprimé.")
