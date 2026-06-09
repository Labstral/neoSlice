"""Gestion de la base de données locale des photos de défauts.

Stocke les photos + corrections + embeddings dans ~/.neoslice/defect_photos/.
Utilisé par la couche d'adaptation et le pipeline de contribution.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from loguru import logger

PHOTOS_DIR = Path.home() / ".neoslice" / "defect_photos"
DB_PATH    = Path.home() / ".neoslice" / "defect_db.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_hash      TEXT UNIQUE NOT NULL,
    image_path      TEXT NOT NULL,
    predicted_class TEXT NOT NULL,
    confidence      REAL NOT NULL,
    corrected_class TEXT,           -- NULL si l'utilisateur confirme la prédiction
    confirmed       INTEGER DEFAULT 0,  -- 1 si l'utilisateur a validé
    timestamp       TEXT NOT NULL,
    contributed     INTEGER DEFAULT 0,  -- 1 si envoyé au pool central
    printer_model   TEXT,
    filament_type   TEXT
);

CREATE TABLE IF NOT EXISTS embeddings (
    image_hash      TEXT PRIMARY KEY,
    embedding_blob  BLOB NOT NULL     -- float32 array sérialisé en bytes
);

CREATE INDEX IF NOT EXISTS idx_photos_corrected ON photos(corrected_class);
CREATE INDEX IF NOT EXISTS idx_photos_confirmed ON photos(confirmed);
CREATE INDEX IF NOT EXISTS idx_photos_contributed ON photos(contributed);
"""


class DatasetManager:
    """Base de données locale des photos de défauts.

    Cycle de vie d'une photo :
    1. analyze()       → photo analysée, prédiction enregistrée
    2. confirm()/correct() → utilisateur valide ou corrige
    3. contribute()    → opt-in envoi au pool central
    """

    def __init__(self) -> None:
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ──────────────────────────────────────────────────────────────────────────
    # Ajout / Mise à jour
    # ──────────────────────────────────────────────────────────────────────────

    def record_prediction(
        self,
        image_path: str | Path,
        predicted_class: str,
        confidence: float,
        embedding: list[float] | None = None,
        printer_model: str = "",
        filament_type: str = "",
    ) -> str:
        """Enregistre une nouvelle prédiction. Retourne l'image_hash."""
        src = Path(image_path)
        img_hash = self._hash_file(src)

        # Copie la photo dans le stockage local
        dest = PHOTOS_DIR / f"{img_hash}{src.suffix}"
        if not dest.exists():
            shutil.copy2(src, dest)

        with self._db() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO photos
                    (image_hash, image_path, predicted_class, confidence, timestamp,
                     printer_model, filament_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (img_hash, str(dest), predicted_class, confidence,
                 datetime.utcnow().isoformat(), printer_model, filament_type),
            )
            if embedding:
                import struct
                blob = struct.pack(f"{len(embedding)}f", *embedding)
                conn.execute(
                    "INSERT OR REPLACE INTO embeddings (image_hash, embedding_blob) VALUES (?, ?)",
                    (img_hash, blob),
                )

        return img_hash

    def confirm_prediction(self, image_hash: str) -> None:
        """L'utilisateur confirme que la prédiction est correcte."""
        with self._db() as conn:
            conn.execute(
                "UPDATE photos SET confirmed=1 WHERE image_hash=?",
                (image_hash,),
            )
        logger.debug(f"Prédiction confirmée : {image_hash[:8]}")

    def correct_prediction(self, image_hash: str, correct_class: str) -> None:
        """L'utilisateur corrige la classe prédite."""
        with self._db() as conn:
            conn.execute(
                "UPDATE photos SET corrected_class=?, confirmed=1 WHERE image_hash=?",
                (correct_class, image_hash),
            )
        logger.debug(f"Correction : {image_hash[:8]} → {correct_class}")

    # ──────────────────────────────────────────────────────────────────────────
    # Lecture
    # ──────────────────────────────────────────────────────────────────────────

    def get_confirmed_samples(self) -> list[dict]:
        """Retourne tous les échantillons confirmés ou corrigés par l'utilisateur."""
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT image_hash, image_path, predicted_class, corrected_class, confidence
                FROM photos WHERE confirmed=1
                """
            ).fetchall()
        return [
            {
                "image_hash": r[0],
                "image_path": r[1],
                "true_class": r[3] if r[3] else r[2],
                "confidence": r[4],
            }
            for r in rows
        ]

    def get_embeddings_for_training(self) -> tuple[list[list[float]], list[str]]:
        """Retourne (embeddings, labels) pour les échantillons confirmés."""
        import struct
        confirmed = self.get_confirmed_samples()
        X, y = [], []
        with self._db() as conn:
            for sample in confirmed:
                row = conn.execute(
                    "SELECT embedding_blob FROM embeddings WHERE image_hash=?",
                    (sample["image_hash"],),
                ).fetchone()
                if row:
                    n = len(row[0]) // 4
                    emb = list(struct.unpack(f"{n}f", row[0]))
                    X.append(emb)
                    y.append(sample["true_class"])
        return X, y

    def get_uncontributed_confirmed(self) -> list[dict]:
        """Retourne les échantillons confirmés mais non encore envoyés."""
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT image_hash, image_path, predicted_class, corrected_class
                FROM photos WHERE confirmed=1 AND contributed=0
                """
            ).fetchall()
        return [
            {
                "image_hash": r[0],
                "image_path": r[1],
                "true_class": r[3] if r[3] else r[2],
            }
            for r in rows
        ]

    def mark_contributed(self, image_hashes: list[str]) -> None:
        with self._db() as conn:
            conn.executemany(
                "UPDATE photos SET contributed=1 WHERE image_hash=?",
                [(h,) for h in image_hashes],
            )

    def count_confirmed_per_class(self) -> dict[str, int]:
        """Retourne le nombre de confirmations par classe."""
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(corrected_class, predicted_class), COUNT(*)
                FROM photos WHERE confirmed=1
                GROUP BY COALESCE(corrected_class, predicted_class)
                """
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def total_photos(self) -> int:
        with self._db() as conn:
            return conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:32]

    def _init_db(self) -> None:
        with self._db() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
