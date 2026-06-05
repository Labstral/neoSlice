"""Structure de données pour les 3MF multi-objets Bambu Studio.

Conserve les informations de slots filament et la structure originale
pour un passthrough fidèle lors de l'export.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

try:
    import trimesh
except ImportError:
    trimesh = None


@dataclass
class MeshObject:
    """Un objet/partie dans un 3MF Bambu multi-couleurs."""
    object_id: str
    name: str
    extruder: int                          # slot AMS (1-4+)
    mesh: "trimesh.Trimesh"
    transform: np.ndarray = field(        # matrice 4×4
        default_factory=lambda: np.eye(4))
    plate_index: int = 0                  # plateau BS 0-based (0 = premier)


@dataclass
class ThreeMFData:
    """Résultat du chargement d'un 3MF multi-objets.

    - `combined_mesh` : tous les objets fusionnés → utilisé pour l'analyse
      (overhangs, stabilité…) exactement comme un mesh STL classique.
    - `objects` : liste des objets individuels avec leurs slots.
    - `source_path` : chemin du 3MF original pour passthrough à l'export.
    - `model_settings_xml` : contenu brut de model_settings.config.
    - `model_xml` : contenu brut de 3D/3dmodel.model.
    """
    combined_mesh: "trimesh.Trimesh"
    objects: list[MeshObject]
    source_path: Path
    model_settings_xml: str = ""
    model_xml: str = ""
    plate_count: int = 1
    modifier_meshes: "list[MeshObject]" = field(default_factory=list)

    @property
    def object_count(self) -> int:
        return len(self.objects)

    @property
    def slot_count(self) -> int:
        return len({o.extruder for o in self.objects})

    @property
    def is_multicolor(self) -> bool:
        return self.slot_count > 1

    def summary(self) -> str:
        parts = f"{self.object_count} objet(s)"
        if self.is_multicolor:
            parts += f" · {self.slot_count} couleur(s)"
        if self.plate_count > 1:
            parts += f" · {self.plate_count} plateaux"
        return parts
