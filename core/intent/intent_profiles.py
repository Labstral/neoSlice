from __future__ import annotations
from pydantic import BaseModel, Field


class IntentProfile(BaseModel):
    """Vecteur d'intentions normalisé 0.0 → 1.0.

    Chaque dimension représente à quel point l'utilisateur priorise cet aspect.
    Les scores ne s'excluent pas mutuellement — un utilisateur peut vouloir
    à la fois solidité et qualité de surface.
    """
    strength: float = Field(0.5, ge=0.0, le=1.0)
    speed: float = Field(0.5, ge=0.0, le=1.0)
    quality: float = Field(0.5, ge=0.0, le=1.0)
    filament_saving: float = Field(0.5, ge=0.0, le=1.0)
    outdoor_resistance: float = Field(0.0, ge=0.0, le=1.0)
    surface_finish: float = Field(0.5, ge=0.0, le=1.0)
    precision: float = Field(0.0, ge=0.0, le=1.0)       # tolérances dimensionnelles serrées
    silent: float = Field(0.0, ge=0.0, le=1.0)           # impression silencieuse (-40% vitesses)
    multicolor: float = Field(0.0, ge=0.0, le=1.0)       # impression multicolore AMS

    @property
    def dominant_intent(self) -> str:
        """Retourne le nom de l'intention la plus forte."""
        scores = {
            "strength": self.strength,
            "speed": self.speed,
            "quality": self.quality,
            "filament_saving": self.filament_saving,
            "outdoor_resistance": self.outdoor_resistance,
            "surface_finish": self.surface_finish,
            "precision": self.precision,
        }
        return max(scores, key=scores.get)

    @property
    def dominant_score(self) -> float:
        return max(
            self.strength, self.speed, self.quality,
            self.filament_saving, self.outdoor_resistance, self.surface_finish,
            self.precision,
        )

    def human_summary(self) -> str:
        """Résumé lisible de l'intention pour l'UI."""
        if self.dominant_score < 0.1:
            return "Standard"
        labels = {
            "strength": "Solidité maximale",
            "speed": "Impression rapide",
            "quality": "Meilleure qualité",
            "filament_saving": "Économie filament",
            "outdoor_resistance": "Résistance extérieur",
            "surface_finish": "Finition surface",
            "precision": "Précision dimensionnelle",
        }
        parts = [labels[self.dominant_intent]]
        if self.silent > 0.5:
            parts.append("silencieux")
        if self.multicolor > 0.5:
            parts.append("multicolore")
        return " · ".join(parts)
