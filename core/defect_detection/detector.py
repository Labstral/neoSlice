"""Moteur d'inférence ONNX — détection de défauts d'impression 3D.

Architecture : EfficientNet-V2-S fine-tuné, exporté ONNX INT8 quantisé.
Input  : image RGB quelconque (PIL / numpy / chemin fichier)
Output : DiagnosticResult avec classe, confiance, embedding, remédiation
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from .defect_classes import (
    DefectClass,
    DiagnosticResult,
    Severity,
    DEFECT_DEFAULT_SEVERITY,
    REMEDIATION_RULES,
    build_diagnostic_message,
)
from .model_manager import ModelManager

# Ordre des classes — DOIT correspondre à l'ordre de sortie du modèle entraîné.
# Mis à jour lors de l'export du modèle (voir scripts/train_defect_model.py).
CLASS_ORDER: list[str] = [
    DefectClass.GOOD.value,
    DefectClass.STRINGING.value,
    DefectClass.WARPING.value,
    DefectClass.UNDER_EXTRUSION.value,
    DefectClass.OVER_EXTRUSION.value,
    DefectClass.LAYER_SHIFT.value,
    DefectClass.SPAGHETTI.value,
    DefectClass.PILLOWING.value,
    DefectClass.ELEPHANTS_FOOT.value,
    DefectClass.Z_WOBBLE.value,
]

# Normalisation ImageNet (utilisée lors de l'entraînement)
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Taille d'entrée — doit correspondre à INPUT_SIZE du training (224)
_INPUT_SIZE = 224

# Seuil de confiance minimum — en dessous, on retourne GOOD avec avertissement
_MIN_CONFIDENCE = 0.35


class DefectDetector:
    """Détecteur de défauts 3D par vision IA.

    Utilisation typique :
        detector = DefectDetector()
        if detector.is_ready:
            result = detector.analyze("photo.jpg")
            print(result.message_fr)
            # Appliquer les corrections :
            detector.apply_remediation(print_config, result)
    """

    def __init__(self, model_manager: ModelManager | None = None) -> None:
        self._mgr = model_manager or ModelManager()
        self._session = None          # onnxruntime.InferenceSession
        self._input_name: str = ""
        self._output_names: list[str] = []
        self._adaptation = None       # lazy import pour éviter sklearn au démarrage

    @property
    def is_ready(self) -> bool:
        if self._session is not None:
            return True
        return self._mgr.is_available

    def load(self) -> bool:
        """Charge le modèle ONNX en mémoire. Retourne True si succès."""
        try:
            import onnxruntime as ort
        except ImportError:
            logger.error("onnxruntime non installé. pip install onnxruntime")
            return False

        path = self._mgr.get_model_path()
        if path is None:
            logger.warning("Modèle ONNX absent — lancez ModelManager.ensure_latest_async()")
            return False

        try:
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                str(path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            logger.info(f"Modèle chargé : {path.name} — sorties : {self._output_names}")
            return True
        except Exception as exc:
            logger.error(f"Impossible de charger le modèle ONNX : {exc}")
            self._session = None
            return False

    def analyze(self, image_source: Any) -> DiagnosticResult:
        """Analyse une image et retourne un DiagnosticResult.

        Args:
            image_source: chemin str/Path, PIL.Image, ou numpy array HxWx3 uint8
        """
        if self._session is None:
            if not self.load():
                return self._unavailable_result()

        tensor, pil_img = self._preprocess(image_source)
        probs, embedding = self._run_inference(tensor)
        result = self._build_result(probs, embedding)

        # Couche d'adaptation locale (corrections utilisateur)
        adapted = self._apply_adaptation(embedding, result)
        return adapted

    def apply_remediation(self, print_config: Any, result: DiagnosticResult) -> None:
        """Applique les corrections du résultat sur un PrintConfig existant.

        Modifie print_config en place. Les deltas sont bornés aux minimums BS.
        """
        if result.defect == DefectClass.GOOD:
            return

        rules = result.remediation
        for key, value in rules.items():
            if key.startswith("_"):
                continue
            if key.startswith("delta_"):
                field = key[6:]  # retire "delta_"
                current = getattr(print_config, field, None)
                if current is not None:
                    new_val = current + value
                    # Clamping de sécurité
                    new_val = self._clamp_field(field, new_val)
                    setattr(print_config, field, new_val)
            else:
                if hasattr(print_config, key):
                    setattr(print_config, key, value)

    # ──────────────────────────────────────────────────────────────────────────
    # Preprocessing
    # ──────────────────────────────────────────────────────────────────────────

    def _preprocess(self, source: Any) -> tuple[np.ndarray, Any]:
        """Convertit n'importe quelle source en tensor [1,3,H,W] float32 normalisé."""
        try:
            from PIL import Image
        except ImportError:
            raise RuntimeError("Pillow requis : pip install Pillow")

        if isinstance(source, (str, Path)):
            img = Image.open(source).convert("RGB")
        elif hasattr(source, "convert"):
            img = source.convert("RGB")
        elif isinstance(source, np.ndarray):
            img = Image.fromarray(source.astype(np.uint8)).convert("RGB")
        else:
            raise TypeError(f"Type d'image non supporté : {type(source)}")

        img = img.resize((_INPUT_SIZE, _INPUT_SIZE), Image.LANCZOS)
        arr = np.array(img, dtype=np.float32) / 255.0          # [H,W,3]
        arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD           # normalize
        arr = arr.transpose(2, 0, 1)                            # [3,H,W]
        tensor = arr[np.newaxis, ...]                           # [1,3,H,W]
        return tensor, img

    # ──────────────────────────────────────────────────────────────────────────
    # Inférence
    # ──────────────────────────────────────────────────────────────────────────

    def _run_inference(self, tensor: np.ndarray) -> tuple[np.ndarray, list[float]]:
        """Lance l'inférence ONNX. Retourne (probs [N], embedding [D])."""
        outputs = self._session.run(self._output_names, {self._input_name: tensor})

        # Le modèle exporte 2 sorties : [logits/probs, embedding]
        # Si une seule sortie → pas d'embedding
        if len(outputs) >= 2:
            logits = outputs[0].squeeze()     # [N_classes]
            embedding_raw = outputs[1].squeeze().tolist()
        else:
            logits = outputs[0].squeeze()
            embedding_raw = []

        # Softmax si le modèle retourne des logits (pas de softmax dans le graphe)
        if logits.max() > 1.5 or logits.min() < -0.1:
            exp = np.exp(logits - logits.max())
            probs = exp / exp.sum()
        else:
            probs = logits  # déjà softmaxé

        return probs, embedding_raw

    # ──────────────────────────────────────────────────────────────────────────
    # Construction du résultat
    # ──────────────────────────────────────────────────────────────────────────

    def _build_result(self, probs: np.ndarray, embedding: list[float]) -> DiagnosticResult:
        all_probs = {cls: float(probs[i]) for i, cls in enumerate(CLASS_ORDER)}
        best_idx = int(np.argmax(probs))
        best_class_str = CLASS_ORDER[best_idx]
        confidence = float(probs[best_idx])

        # Seuil de confiance minimum
        if confidence < _MIN_CONFIDENCE:
            best_class_str = DefectClass.GOOD.value
            confidence = float(probs[CLASS_ORDER.index(DefectClass.GOOD.value)])

        defect = DefectClass(best_class_str)
        severity = DEFECT_DEFAULT_SEVERITY[defect]
        remediation = dict(REMEDIATION_RULES.get(defect, {}))
        stop = remediation.pop("_stop_print", False)
        hint = remediation.pop("_hint", None)
        if hint:
            remediation["_hint"] = hint  # re-ajoute hint pour l'UI

        message = build_diagnostic_message(defect, confidence, severity)

        return DiagnosticResult(
            defect=defect,
            confidence=confidence,
            severity=severity,
            all_probs=all_probs,
            remediation=remediation,
            message_fr=message,
            stop_print=bool(stop),
            embedding=embedding,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Adaptation locale (corrections utilisateur)
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_adaptation(self, embedding: list[float], result: DiagnosticResult) -> DiagnosticResult:
        """Applique la couche d'adaptation si disponible et entraînée."""
        if not embedding:
            return result
        try:
            from .adaptation import AdaptationLayer
            if self._adaptation is None:
                self._adaptation = AdaptationLayer()
            override = self._adaptation.predict(embedding)
            if override and override != result.defect.value:
                # Le modèle d'adaptation a une opinion différente — on la prend si confiant
                logger.debug(f"Adaptation override : {result.defect.value} → {override}")
                new_defect = DefectClass(override)
                new_severity = DEFECT_DEFAULT_SEVERITY[new_defect]
                new_remediation = dict(REMEDIATION_RULES.get(new_defect, {}))
                new_remediation.pop("_stop_print", None)
                stop = REMEDIATION_RULES.get(new_defect, {}).get("_stop_print", False)
                return DiagnosticResult(
                    defect=new_defect,
                    confidence=result.confidence,   # confiance ONNX maintenue
                    severity=new_severity,
                    all_probs=result.all_probs,
                    remediation=new_remediation,
                    message_fr=build_diagnostic_message(new_defect, result.confidence, new_severity),
                    stop_print=bool(stop),
                    embedding=embedding,
                )
        except Exception as exc:
            logger.debug(f"Adaptation non disponible : {exc}")
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Clamping de sécurité
    # ──────────────────────────────────────────────────────────────────────────

    _FIELD_MINS: dict[str, float] = {
        "outer_wall_speed": 15,
        "inner_wall_speed": 20,
        "infill_speed": 30,
        "bridge_speed": 15,
        "first_layer_speed": 15,
        "top_surface_speed": 20,
        "nozzle_temperature": 170,
        "bed_temperature": 0,
        "brim_width": 0,
        "top_shell_layers": 2,
        "bottom_shell_layers": 2,
        "wall_loops": 2,
        "elefant_foot_compensation": 0.0,
    }

    _FIELD_MAXS: dict[str, float] = {
        "nozzle_temperature": 300,
        "bed_temperature": 120,
        "brim_width": 30,
        "elefant_foot_compensation": 1.0,
        "outer_wall_speed": 200,
        "infill_speed": 500,
    }

    def _clamp_field(self, field: str, value: float) -> float:
        v = max(value, self._FIELD_MINS.get(field, value))
        v = min(v, self._FIELD_MAXS.get(field, v))
        return type(value)(v) if not isinstance(value, float) else round(v, 3)

    # ──────────────────────────────────────────────────────────────────────────
    # Résultat fallback si modèle absent
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _unavailable_result() -> DiagnosticResult:
        return DiagnosticResult(
            defect=DefectClass.GOOD,
            confidence=0.0,
            severity=Severity.NONE,
            all_probs={c: 0.0 for c in CLASS_ORDER},
            remediation={},
            message_fr="⚠️ Modèle IA non disponible — téléchargement requis.",
            stop_print=False,
        )
