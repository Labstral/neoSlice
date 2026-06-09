"""Pipeline de contribution opt-in — envoie les photos confirmées au pool central.

Principe :
  - L'utilisateur donne son accord (une seule fois) via le dialog de diagnostic.
  - À chaque confirmation/correction, la photo est marquée "à contribuer".
  - En arrière-plan, les photos sont réduites (512px max), regroupées dans un ZIP
    et envoyées vers un bucket Supabase Storage.
  - Les photos envoyées sont marquées "contributed" pour éviter les doublons.

Backend : Supabase Storage
  - Un bucket dédié (defect-contributions) avec une règle RLS "insertion seule".
  - La clé anon de Supabase est publique par conception : elle ne permet QUE
    l'upload (pas la lecture ni la suppression) grâce à la policy.
  - Aucun serveur custom à maintenir : Supabase Storage EST l'endpoint.

Confidentialité :
  - Aucune donnée personnelle. Seulement : image réduite + classe + (option) modèle
    d'imprimante / type de filament.
  - Les photos sont downscalées à 512px avant envoi (≈40 Ko, illisible pour
    identifier un lieu, suffisant pour l'entraînement).
"""
from __future__ import annotations

import io
import json
import os
import secrets
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from loguru import logger

from .dataset_manager import DatasetManager

# ──────────────────────────────────────────────────────────────────────────────
# Configuration Supabase
# ──────────────────────────────────────────────────────────────────────────────
# La clé anon est PUBLIQUE par conception (conçue pour le code client). Avec une
# policy "insertion seule" sur le bucket, elle ne permet que l'upload.
# Remplies une fois le projet Supabase créé ; surchargables par variables d'env.

SUPABASE_URL    = os.environ.get("NEOSLICE_SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY    = os.environ.get("NEOSLICE_SUPABASE_KEY", "")
SUPABASE_BUCKET = os.environ.get("NEOSLICE_SUPABASE_BUCKET", "defect-contributions")

_BATCH_SIZE   = 50     # max photos par ZIP
_MAX_IMG_SIZE = 512    # côté max des images downscalées (px)
_JPEG_QUALITY = 85


class ContributionPipeline:
    """Gère l'envoi opt-in de photos annotées vers Supabase Storage.

    Usage :
        pipeline = ContributionPipeline()
        if pipeline.is_enabled:
            pipeline.contribute_async(on_done=callback)
    """

    def __init__(self) -> None:
        self._dataset = DatasetManager()

    # ── État ────────────────────────────────────────────────────────────────

    @property
    def is_enabled(self) -> bool:
        from core.prefs import PREFS
        return bool(PREFS.get("defect_contribute", False))

    def enable(self) -> None:
        from core.prefs import PREFS
        PREFS.set("defect_contribute", True)
        logger.info("Contribution activée.")

    def disable(self) -> None:
        from core.prefs import PREFS
        PREFS.set("defect_contribute", False)
        logger.info("Contribution désactivée.")

    @property
    def is_configured(self) -> bool:
        return bool(SUPABASE_URL and SUPABASE_KEY)

    def pending_count(self) -> int:
        return len(self._dataset.get_uncontributed_confirmed())

    # ── Envoi ─────────────────────────────────────────────────────────────────

    def contribute_async(
        self,
        on_done: Callable[[int, str | None], None] | None = None,
    ) -> threading.Thread | None:
        """Lance la contribution en arrière-plan. Callback on_done(sent, err)."""
        if not self.is_enabled:
            logger.debug("Contribution désactivée — rien à envoyer.")
            return None
        if not self.is_configured:
            # Backend pas encore configuré : les photos restent en file d'attente
            # locale et partiront dès que SUPABASE_URL/KEY seront renseignés.
            logger.debug(
                f"Supabase non configuré — {self.pending_count()} photo(s) en attente locale."
            )
            if on_done:
                on_done(0, None)
            return None

        t = threading.Thread(target=self._contribute_worker, args=(on_done,), daemon=True)
        t.start()
        return t

    def contribute_sync(self) -> int:
        """Envoi synchrone (pour tests). Retourne le nombre de photos envoyées."""
        return self._send_batches()

    def _contribute_worker(self, on_done: Callable | None) -> None:
        try:
            sent = self._send_batches()
            if on_done:
                on_done(sent, None)
        except Exception as exc:
            logger.error(f"Contribution échouée : {exc}")
            if on_done:
                on_done(0, str(exc))

    def _send_batches(self) -> int:
        samples = self._dataset.get_uncontributed_confirmed()
        if not samples:
            return 0

        batches = [samples[i:i + _BATCH_SIZE] for i in range(0, len(samples), _BATCH_SIZE)]
        total_sent = 0
        for batch in batches:
            payload = self._build_payload(batch)
            if payload is None:
                continue
            self._upload(payload)
            self._dataset.mark_contributed([s["image_hash"] for s in batch])
            total_sent += len(batch)
            logger.info(f"Contribution : {len(batch)} photo(s) envoyée(s) vers Supabase.")
        return total_sent

    # ── Construction du ZIP ─────────────────────────────────────────────────

    def _build_payload(self, samples: list[dict]) -> bytes | None:
        """ZIP des images downscalées + manifest JSON des labels."""
        buf = io.BytesIO()
        manifest = []

        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for s in samples:
                img_path = Path(s["image_path"])
                if not img_path.exists():
                    continue
                jpeg_bytes = self._downscale(img_path)
                if jpeg_bytes is None:
                    continue
                arcname = f"images/{s['true_class']}/{s['image_hash']}.jpg"
                zf.writestr(arcname, jpeg_bytes)
                manifest.append({
                    "hash":  s["image_hash"],
                    "file":  arcname,
                    "label": s["true_class"],
                })
            if not manifest:
                return None
            zf.writestr("manifest.json", json.dumps({
                "version":   "1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "app":       self._neoslice_version(),
                "count":     len(manifest),
                "samples":   manifest,
            }, indent=2))

        return buf.getvalue()

    @staticmethod
    def _downscale(path: Path) -> bytes | None:
        """Réduit l'image à _MAX_IMG_SIZE px (côté max) et la réencode en JPEG."""
        try:
            from PIL import Image
            img = Image.open(path).convert("RGB")
            w, h = img.size
            scale = _MAX_IMG_SIZE / max(w, h)
            if scale < 1.0:
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return out.getvalue()
        except Exception as exc:
            logger.debug(f"Downscale échoué pour {path.name} : {exc}")
            return None

    # ── Upload Supabase Storage ─────────────────────────────────────────────

    def _upload(self, payload: bytes) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        obj_path = f"batches/{ts}_{secrets.token_hex(8)}.zip"
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{obj_path}"

        req = Request(
            url,
            data=payload,
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type":  "application/zip",
                "x-upsert":      "false",
                "User-Agent":    f"neoSlice-contribution/{self._neoslice_version()}",
            },
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            status = resp.getcode()
            if status not in (200, 201):
                raise RuntimeError(f"Supabase a répondu {status}")

    @staticmethod
    def _neoslice_version() -> str:
        try:
            from version import __version__
            return __version__
        except Exception:
            return "unknown"
