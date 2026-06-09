"""Couche d'adaptation locale — personnalise le modèle sur les corrections utilisateur.

Approche :
  - Les corrections de l'utilisateur sont stockées avec leurs embeddings ONNX.
  - Quand assez de données sont disponibles (MIN_SAMPLES), on entraîne un SVC léger
    sur ces embeddings. Le SVC agit comme un override sur le modèle de base.
  - Entraînement <1 seconde même sur 500 échantillons (sklearn SVC sur CPU).
  - Modèle de correction persisté dans ~/.neoslice/models/adaptation.pkl.
"""
from __future__ import annotations

import pickle
from pathlib import Path

from loguru import logger

from .dataset_manager import DatasetManager

ADAPTATION_MODEL_PATH = Path.home() / ".neoslice" / "models" / "adaptation.pkl"

# Minimums pour déclencher l'entraînement
MIN_TOTAL_SAMPLES = 20      # total d'échantillons confirmés
MIN_PER_CLASS     = 3       # minimum par classe pour qu'elle soit représentée


class AdaptationLayer:
    """Couche SVC entraînée sur les corrections utilisateur.

    Usage :
        layer = AdaptationLayer()
        override = layer.predict(embedding)
        if override:
            # utiliser override au lieu de la prédiction ONNX
    """

    def __init__(self) -> None:
        self._dataset = DatasetManager()
        self._clf = None
        self._load_persisted()

    @property
    def is_trained(self) -> bool:
        return self._clf is not None

    def predict(self, embedding: list[float]) -> str | None:
        """Retourne la classe overridée, ou None si pas de modèle / pas confiant."""
        if self._clf is None:
            return None
        try:
            import numpy as np
            X = np.array(embedding, dtype=np.float32).reshape(1, -1)
            proba = self._clf.predict_proba(X)[0]
            best_idx = int(proba.argmax())
            best_prob = float(proba[best_idx])
            # N'override que si l'adaptation est très confiante
            if best_prob >= 0.75:
                return self._clf.classes_[best_idx]
        except Exception as exc:
            logger.debug(f"Adaptation predict error : {exc}")
        return None

    def retrain_if_needed(self) -> bool:
        """Vérifie si un re-entraînement est nécessaire et le lance si oui.

        Retourne True si un nouveau modèle a été entraîné.
        """
        counts = self._dataset.count_confirmed_per_class()
        total = sum(counts.values())

        if total < MIN_TOTAL_SAMPLES:
            logger.debug(f"Adaptation : seulement {total}/{MIN_TOTAL_SAMPLES} échantillons.")
            return False

        valid_classes = {cls for cls, n in counts.items() if n >= MIN_PER_CLASS}
        if len(valid_classes) < 2:
            logger.debug("Adaptation : pas assez de classes représentées.")
            return False

        return self._train()

    def force_retrain(self) -> bool:
        """Force le re-entraînement, quelle que soit la quantité de données."""
        return self._train()

    def stats(self) -> dict:
        counts = self._dataset.count_confirmed_per_class()
        return {
            "trained": self.is_trained,
            "total_samples": sum(counts.values()),
            "per_class": counts,
            "model_path": str(ADAPTATION_MODEL_PATH) if ADAPTATION_MODEL_PATH.exists() else None,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Entraînement interne
    # ──────────────────────────────────────────────────────────────────────────

    def _train(self) -> bool:
        try:
            from sklearn.svm import SVC
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
            import numpy as np
        except ImportError:
            logger.warning("scikit-learn non installé — adaptation désactivée. pip install scikit-learn")
            return False

        X_raw, y = self._dataset.get_embeddings_for_training()
        if not X_raw:
            return False

        X = np.array(X_raw, dtype=np.float32)
        y_arr = np.array(y)

        # Filtre les classes avec trop peu d'exemples
        classes, counts = np.unique(y_arr, return_counts=True)
        valid_mask = np.isin(y_arr, classes[counts >= MIN_PER_CLASS])
        X, y_arr = X[valid_mask], y_arr[valid_mask]

        if len(np.unique(y_arr)) < 2:
            logger.debug("Adaptation : pas assez de classes après filtrage.")
            return False

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("svc", SVC(
                kernel="rbf",
                probability=True,
                C=10.0,
                gamma="scale",
                class_weight="balanced",
            )),
        ])

        try:
            pipeline.fit(X, y_arr)
            self._clf = pipeline
            self._persist()
            logger.info(
                f"Adaptation entraînée sur {len(X)} échantillons, "
                f"{len(np.unique(y_arr))} classes."
            )
            return True
        except Exception as exc:
            logger.error(f"Entraînement adaptation échoué : {exc}")
            return False

    def _persist(self) -> None:
        ADAPTATION_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ADAPTATION_MODEL_PATH.open("wb") as f:
            pickle.dump(self._clf, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.debug(f"Adaptation sauvegardée : {ADAPTATION_MODEL_PATH}")

    def _load_persisted(self) -> None:
        if not ADAPTATION_MODEL_PATH.exists():
            return
        try:
            with ADAPTATION_MODEL_PATH.open("rb") as f:
                self._clf = pickle.load(f)
            logger.debug("Adaptation chargée depuis le disque.")
        except Exception as exc:
            logger.warning(f"Impossible de charger l'adaptation : {exc}")
            self._clf = None
