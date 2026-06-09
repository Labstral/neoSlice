"""Gestion du modèle ONNX — téléchargement, vérification intégrité, versioning."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Callable
from urllib.request import urlopen, Request
from urllib.error import URLError

from loguru import logger

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

MODELS_DIR = Path.home() / ".neoslice" / "models"
MODEL_FILENAME = "defect_detector_v1.onnx"
MODEL_META_FILE = MODELS_DIR / "model_meta.json"

# URL de téléchargement — pointe vers les GitHub Releases (même mécanisme que l'updater)
# La vraie URL sera définie lors de la première release du modèle.
_MODEL_DOWNLOAD_BASE = os.environ.get(
    "NEOSLICE_MODEL_URL",
    "https://github.com/Labstral/neoSlice/releases/download/models"
)
# URL directe v1 : https://github.com/Labstral/neoSlice/releases/download/models/defect_detector_v1.onnx

# SHA256 des modèles connus — mis à jour à chaque nouveau modèle entraîné.
# Format : { "filename": "sha256hex" }
KNOWN_CHECKSUMS: dict[str, str] = {
    "defect_detector_v1.onnx": "40824ad3063fc2a7cb15d88e3477c2769bf04f89e745d70d435e62fe7828f500",
}


class ModelManager:
    """Gère le cycle de vie du modèle ONNX de détection de défauts.

    Usage:
        mgr = ModelManager()
        path = mgr.get_model_path()   # bloquant si téléchargement nécessaire
        # ou async :
        mgr.ensure_model_async(on_progress=cb, on_done=cb)
    """

    def __init__(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def model_path(self) -> Path:
        return MODELS_DIR / MODEL_FILENAME

    @property
    def is_available(self) -> bool:
        return self.model_path.exists() and self._verify_checksum(self.model_path)

    def get_model_path(self) -> Path | None:
        """Retourne le chemin si le modèle est disponible, None sinon."""
        if self.is_available:
            return self.model_path
        return None

    def ensure_model_async(
        self,
        on_progress: Callable[[int, int], None] | None = None,
        on_done: Callable[[Path | None, str | None], None] | None = None,
    ) -> threading.Thread:
        """Télécharge le modèle en arrière-plan si nécessaire.

        Args:
            on_progress: callback(downloaded_bytes, total_bytes)
            on_done: callback(model_path_or_None, error_message_or_None)
        """
        t = threading.Thread(
            target=self._download_worker,
            args=(on_progress, on_done),
            daemon=True,
        )
        t.start()
        return t

    def _download_worker(
        self,
        on_progress: Callable | None,
        on_done: Callable | None,
    ) -> None:
        if self.is_available:
            if on_done:
                on_done(self.model_path, None)
            return

        url = f"{_MODEL_DOWNLOAD_BASE}/{MODEL_FILENAME}"
        try:
            path = self._download(url, self.model_path, on_progress)
            if not self._verify_checksum(path):
                path.unlink(missing_ok=True)
                raise ValueError("Checksum invalide — modèle corrompu ou modifié.")
            self._save_meta({"filename": MODEL_FILENAME, "url": url})
            logger.info(f"Modèle téléchargé et vérifié : {path}")
            if on_done:
                on_done(path, None)
        except Exception as exc:
            logger.error(f"Téléchargement modèle échoué : {exc}")
            if on_done:
                on_done(None, str(exc))

    @staticmethod
    def _download(url: str, dest: Path, on_progress: Callable | None) -> Path:
        req = Request(url, headers={"User-Agent": "neoSlice-defect-detector/1.0"})
        with urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536
            with dest.open("wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total > 0:
                        on_progress(downloaded, total)
        return dest

    @staticmethod
    def _verify_checksum(path: Path) -> bool:
        """Vérifie le SHA256. Retourne True si pas de checksum enregistré (modèle dev)."""
        expected = KNOWN_CHECKSUMS.get(path.name)
        if not expected:
            return path.exists()
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        ok = sha == expected
        if not ok:
            logger.warning(f"Checksum mismatch {path.name}: got {sha[:12]}..., expected {expected[:12]}...")
        return ok

    def _save_meta(self, meta: dict) -> None:
        existing = self._load_meta()
        existing[meta["filename"]] = meta
        MODEL_META_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    @staticmethod
    def _load_meta() -> dict:
        if MODEL_META_FILE.exists():
            try:
                return json.loads(MODEL_META_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def get_installed_version(self) -> str | None:
        meta = self._load_meta()
        entry = meta.get(MODEL_FILENAME)
        if entry:
            return entry.get("version", "v1")
        return None

    def delete_model(self) -> None:
        """Supprime le modèle local (pour forcer un re-téléchargement)."""
        self.model_path.unlink(missing_ok=True)
        logger.info("Modèle supprimé.")
