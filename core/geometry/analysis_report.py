from __future__ import annotations
from pydantic import BaseModel, Field, computed_field
from typing import Optional, Any


class Zone3D(BaseModel):
    point: list[float]
    thickness_mm: float
    severity: float  # 0.0 → 1.0


class AnalysisReport(BaseModel):
    # Overhangs
    overhang_severity: float = 0.0       # 0=aucun, 1=critique
    overhang_ratio: float = 0.0          # % de faces en surplomb
    max_overhang_angle: float = 0.0      # angle max détecté (degrés)

    # Orientation optimale (matrice 4x4 aplatie en liste)
    optimal_rotation: Optional[list[float]] = None
    orientation_score: float = 0.0       # qualité de l'orientation (0→1)
    orientation_improvement_pct: float = 0.0  # gain vs orientation actuelle (%)

    # Stabilité
    stability_score: float = 1.0         # 0=instable, 1=très stable
    center_of_mass: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    brim_recommendation_mm: float = 0.0

    # Fragilité
    has_fragile_zones: bool = False
    fragile_zones: list[Zone3D] = Field(default_factory=list)
    min_wall_thickness_mm: float = 99.0
    fragility_severity: float = 0.0       # 0=aucune fragilité, 1=critique

    # Géométrie
    bounding_box_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    volume_cm3: float = 0.0
    surface_area_cm2: float = 0.0
    is_large_flat_part: bool = False

    # Support
    support_needed: bool = False
    estimated_support_ratio: float = 0.0  # volume support / volume pièce
    has_floating_regions: bool = False    # composants sans contact avec le plateau
    projected_overhang_ratio: float = 0.0 # aire XY projetée en surplomb (méthode Bambu)

    # Orientation
    orientation_label: str = ""           # ex: "Z+", "X-", "Diagonal"

    # Configuration matérielle
    nozzle_diameter_mm: float = 0.4   # diamètre buse utilisé pour l'analyse

    # Meta
    analysis_time_ms: float = 0.0
    face_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    support_face_mask: Any = Field(default=None, exclude=True)  # ndarray bool — non sérialisé
    overhang_result: Any = Field(default=None, exclude=True)    # OverhangResult — non sérialisé

    @computed_field
    @property
    def overall_complexity(self) -> float:
        """Score global de complexité d'impression 0→1."""
        return min(1.0, (
            self.overhang_severity * 0.35
            + (1.0 - self.stability_score) * 0.20
            + self.fragility_severity * 0.30
            + self.estimated_support_ratio * 0.15
        ))

    @computed_field
    @property
    def summary_text(self) -> str:
        """Résumé lisible de l'analyse pour l'UI."""
        parts = []
        if self.overhang_severity > 0.6:
            parts.append("surplombs critiques")
        elif self.overhang_severity > 0.3:
            parts.append("surplombs modérés")
        if self.stability_score < 0.4:
            parts.append("stabilité faible")
        if self.has_fragile_zones:
            parts.append("zones fragiles détectées")
        if self.support_needed:
            parts.append("supports nécessaires")
        if not parts:
            return "Géométrie favorable à l'impression"
        return "Attention : " + ", ".join(parts)
