"""Pipeline de contribution opt-in — envoie les photos confirmées au pool central.

Principe :
  - L'utilisateur choisit d'activer la contribution dans les préférences.
  - À chaque confirmation/correction, la photo est marquée "à contribuer".
  - En arrière-plan (ou manuellement), les photos sont compressées et envoyées
    à l'endpoint de contribution (URL configurable via prefs ou env var).
  - Les photos envoyées sont marquées "contributed" pour éviter les doublons.

Confidentialité :
  - Aucune donnée personnelle n'est incluse.
  - Seulement : image + classe + confiance + type d'imprimante (optionnel).
  - L'utilisateur peut voir et supprimer ses contributions locales.
"""
from __future__ import annotations

import io
import json
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from loguru import logger

from .dataset_manager import DatasetManager

# URL de contribution — configurable via NEOSLICE_CONTRIBUTE_URL ou prefs
_DEFAULT_CONTRIBUTE_URL = ""  # À remplir lors de la mise en place du serveur
_BATCH_SIZE = 50              # max photos par envoi


class ContributionPipeline:
    """Gère l'envoi opt-in de photos annotées au pool d'entraînement.

    Usage :
        pipeline = ContributionPipeline()
        if pipeline.is_enabled:
            pipeline.contribute_async(on_done=callback)
    """

    def __init__(self) -> None:
        self._dataset = DatasetManager()

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
    def endpoint_url(self) -> str:
        import os
        from core.prefs import PREFS
        return (
            os.environ.get("NEOSLICE_CONTRIBUTE_URL")
            or PREFS.get("contribute_url", _DEFAULT_CONTRIBUTE_URL)
            or ""
        )

    def pending_count(self) -> int:
        return len(self._dataset.get_uncontributed_confirmed())

    def contribute_async(
        self,
        on_done: Callable[[int, str | None], None] | None = None,
    ) -> threading.Thread | None:
        """Lance la contribution en arrière-plan.

        Callback on_done(sent_count, error_or_None).
        """
        if not self.is_enabled:
            logger.debug("Contribution désactivée — rien à envoyer.")
            return None
        if not self.endpoint_url:
            logger.warning("Aucun endpoint de contribution configuré.")
            if on_done:
                on_done(0, "Endpoint non configuré")
            return None

        t = threading.Thread(
            target=self._contribute_worker,
            args=(on_done,),
            daemon=True,
        )
        t.start()
        return t

    def _contribute_worker(self, on_done: Callable | None) -> None:
        try:
            sent = self._send_batch()
            if on_done:
                on_done(sent, None)
        except Exception as exc:
            logger.error(f"Contribution échouée : {exc}")
            if on_done:
                on_done(0, str(exc))

    def _send_batch(self) -> int:
        samples = self._dataset.get_uncontributed_confirmed()
        if not samples:
            return 0

        batches = [samples[i:i+_BATCH_SIZE] for i in range(0, len(samples), _BATCH_SIZE)]
        total_sent = 0

        for batch in batches:
            payload = self._build_payload(batch)
            self._post(payload)
            hashes = [s["image_hash"] for s in batch]
            self._dataset.mark_contributed(hashes)
            total_sent += len(batch)
            logger.info(f"Contribution : {len(batch)} photos envoyées.")

        return total_sent

    def _build_payload(self, samples: list[dict]) -> bytes:
        """Construit un ZIP contenant les images + un manifest JSON."""
        buf = io.BytesIO()
        manifest = []

        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for s in samples:
                img_path = Path(s["image_path"])
                if not img_path.exists():
                    continue
                arcname = f"images/{s['image_hash']}{img_path.suffix}"
                zf.write(img_path, arcname)
                manifest.append({
                    "hash": s["image_hash"],
                    "file": arcname,
                    "label": s["true_class"],
                })
            zf.writestr(
                "manifest.json",
                json.dumps({
                    "version": "1",
                    "timestamp": datetime.utcnow().isoformat(),
                    "count": len(manifest),
                    "samples": manifest,
                }, indent=2),
            )

        return buf.getvalue()

    def _post(self, payload: bytes) -> None:
        req = Request(
            self.endpoint_url,
            data=payload,
            headers={
                "Content-Type": "application/zip",
                "User-Agent": "neoSlice-contribution/1.0",
                "X-neoSlice-Version": self._neoslice_version(),
            },
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            status = resp.getcode()
            if status not in (200, 201, 202):
                raise RuntimeError(f"Serveur a répondu {status}")

    @staticmethod
    def _neoslice_version() -> str:
        try:
            from version import __version__
            return __version__
        except Exception:
            return "unknown"
