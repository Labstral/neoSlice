from __future__ import annotations
import math
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

    Score basé sur :
    - Le centre de masse projeté est-il dans l'empreinte au sol ?
    - Quelle marge par rapport au bord (normalisée par la taille de l'empreinte) ?
    - Ratio hauteur/empreinte (pièce haute et fine = instable)
    - Surface d'empreinte relative à la boîte englobante (base courbe/pointue)
    """
    com = mesh.center_mass
    com_xy = com[:2]

    z_min = mesh.bounds[0][2]
    z_max = mesh.bounds[1][2]
    height = z_max - z_min
    ground_threshold = z_min + height * 0.05

    ground_verts = mesh.vertices[mesh.vertices[:, 2] <= ground_threshold]

    if len(ground_verts) < 3:
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
        return StabilityResult(
            score=0.2,
            center_of_mass=com,
            footprint_area_mm2=0.0,
            brim_recommendation_mm=8.0,
            is_top_heavy=(com[2] > height * 0.6),
        )

    footprint_area = hull_2d.volume  # en 2D, .volume = aire
    hull_verts_2d = ground_verts[hull_2d.vertices, :2]

    # ── Le centre de masse est-il au-dessus de l'empreinte ? ──────────────────
    # hull.equations : chaque ligne [nx, ny, c] telle que nx*x + ny*y + c <= 0 pour l'intérieur
    eqs = hull_2d.equations
    com_inside = bool(np.all(eqs[:, :2] @ com_xy + eqs[:, 2] <= 1e-6))

    if not com_inside:
        # CDM hors empreinte → la pièce bascule sous son propre poids
        score = 0.05
    else:
        # Marge entre CDM et bord le plus proche
        dist_to_edge = _point_to_polygon_distance(com_xy, hull_verts_2d)
        # Rayon caractéristique de l'empreinte : √(aire/π) = rayon d'un cercle équivalent
        char_radius = math.sqrt(footprint_area / math.pi) if footprint_area > 1e-6 else 1.0
        # Score : 0 = CDM sur le bord, 1 = CDM bien centré dans l'empreinte
        score = min(1.0, dist_to_edge / max(char_radius, 1.0))

    # ── Pénalité : empreinte réelle petite par rapport à la boîte englobante ──
    # Une base courbe ou pointue n'offre qu'un petit contact avec le plateau
    bb_footprint = float(mesh.bounding_box.extents[0]) * float(mesh.bounding_box.extents[1])
    if bb_footprint > 1e-6:
        footprint_fill = footprint_area / bb_footprint
        if footprint_fill < 0.10:
            score *= 0.30   # base quasi-ponctuelle ou linéaire
        elif footprint_fill < 0.25:
            score *= 0.55   # très petite empreinte courbe
        elif footprint_fill < 0.45:
            score *= 0.78   # empreinte réduite

    # ── Pénalité : ratio hauteur/largeur d'empreinte (pièce haute et fine) ────
    effective_width = math.sqrt(footprint_area) if footprint_area > 1e-6 else 1.0
    height_ratio = height / max(effective_width, 1.0)
    if height_ratio > 3.0:
        score *= 0.45
    elif height_ratio > 2.0:
        score *= 0.70
    elif height_ratio > 1.5:
        score *= 0.88

    # ── Pénalité : CDM haut = pièce top-heavy ─────────────────────────────────
    is_top_heavy = com[2] > height * 0.55
    if is_top_heavy:
        score *= 0.85

    brim_mm = 0.0
    if score < 0.30:
        brim_mm = 10.0
    elif score < 0.50:
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
    """Distance minimale d'un point aux arêtes d'un polygone convexe."""
    min_dist = float("inf")
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        edge = b - a
        edge_len = np.linalg.norm(edge)
        if edge_len < 1e-10:
            continue
        t = np.clip(np.dot(point - a, edge) / edge_len ** 2, 0, 1)
        proj = a + t * edge
        dist = np.linalg.norm(point - proj)
        min_dist = min(min_dist, dist)
    return float(min_dist) if min_dist < float("inf") else 0.0
