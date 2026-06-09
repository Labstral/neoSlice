"""Détection de défauts d'impression 3D par vision IA — neoSlice."""
from .defect_classes import DefectClass, Severity, DiagnosticResult
from .detector import DefectDetector
from .model_manager import ModelManager

__all__ = ["DefectClass", "Severity", "DiagnosticResult", "DefectDetector", "ModelManager"]
