from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from scipy.spatial.qhull import QhullError


@dataclass
class StabilityResult:
    score: float             # 0.0 (très instable) → 1.0 (très stable)
    center_of_mass: np.ndarray
    footprint_area_mm2: float
    brim_recommendation_mm: float
    is_top_heavy: bool


def analyze_stability(mesh: trimesh.Trimesh) -> StabilityResult:
    """Évalue la stabilité de la pièce dans son orientation actuelle.

    Logique :
    - Centre de masse projeté sur le plan Z=0
    - Comparé au convex hull de l'empreinte au sol
    - Distance relative au bord → score de stabilité
    """
    com = mesh.center_mass  # [x, y, z]
    com_xy = com[:2]

    # Empreinte : vertices proches du sol (Z < 5% de la hauteur)
    z_min = mesh.bounds[0][2]
    z_max = mesh.bounds[1][2]
    height = z_max - z_min
    ground_threshold = z_min + height * 0.05

    ground_verts = mesh.vertices[mesh.vertices[:, 2] <= ground_threshold]

    if len(ground_verts) < 3:
        # Pièce posée sur un seul point → très instable
        return StabilityResult(
            score=0.1,
            center_of_mass=com,
            footprint_area_mm2=0.0,
            brim_recommendation_mm=10.0,
            is_top_heavy=(com[2] > height * 0.6),
        )

    try:
        hull_2d = ConvexHull(ground_verts[:, :2])
    except (QhullError, Exception):
        # Vertices colinéaires (pièce posée sur une arête) → instable
        return StabilityResult(
            score=0.25,
            center_of_mass=com,
            footprint_area_mm2=0.0,
            brim_recommendation_mm=8.0,
            is_top_heavy=(com[2] > height * 0.6),
        )

    footprint_area = hull_2d.volume  # en 2D, .volume = aire

    # Distance du centre de masse au bord le plus proche du convex hull
    hull_verts_2d = ground_verts[hull_2d.vertices, :2]
    distances = _point_to_polygon_distance(com_xy, hull_verts_2d)
    max_inscribed_radius = _max_inscribed_radius(com_xy, hull_verts_2d)

    # Score : 1.0 si le CDM est bien centré, 0.0 si sur le bord
    if max_inscribed_radius > 0:
        score = min(1.0, distances / max_inscribed_radius)
    else:
        score = 0.5

    # Pièce haute et fine → instable (ratio hauteur/largeur)
    width = min(mesh.bounding_box.extents[:2])
    height_ratio = height / max(width, 1.0)
    if height_ratio > 3.0:
        score *= 0.6
    elif height_ratio > 2.0:
        score *= 0.8

    is_top_heavy = com[2] > height * 0.55

    brim_mm = 0.0
    if score < 0.3:
        brim_mm = 10.0
    elif score < 0.5:
        brim_mm = 6.0
    elif score < 0.65:
        brim_mm = 4.0

    return StabilityResult(
        score=float(np.clip(score, 0.0, 1.0)),
        center_of_mass=com,
        footprint_area_mm2=float(footprint_area),
        brim_recommendation_mm=brim_mm,
        is_top_heavy=bool(is_top_heavy),
    )


def _point_to_polygon_distance(point: np.ndarray, polygon: np.ndarray) -> float:
    """Distance minimale d'un point à un polygone convexe (positif = intérieur)."""
    min_dist = float("inf")
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        edge = b - a
        edge_len = np.linalg.norm(edge)
        if edge_len < 1e-10:
            continue
        t = np.clip(np.dot(point - a, edge) / edge_len**2, 0, 1)
        proj = a + t * edge
        dist = np.linalg.norm(point - proj)
        min_dist = min(min_dist, dist)
    return float(min_dist)


def _max_inscribed_radius(center: np.ndarray, polygon: np.ndarray) -> float:
    """Estimation du rayon maximal inscrit dans le polygone depuis le centre."""
    return _point_to_polygon_distance(center, polygon)
