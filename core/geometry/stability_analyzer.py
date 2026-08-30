from __future__ import annotations
import math
from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.spatial import ConvexHull
try:                        # scipy ≥ 1.8 : QhullError vit dans scipy.spatial
    from scipy.spatial import QhullError
except ImportError:         # repli anciennes versions (namespace déprécié)
    from scipy.spatial.qhull import QhullError


@dataclass
class StabilityResult:
    score: float             # 0.0 (très instable) → 1.0 (très stable)
    center_of_mass: np.ndarray
    footprint_area_mm2: float
    brim_recommendation_mm: float
    is_top_heavy: bool


def score_renversement(dist_edge_mm: float, com_height_mm: float,
                       hull_fill: float = 1.0, is_top_heavy: bool = False) -> float:
    """Score de stabilité 0→1 à partir de l'ANGLE DE RENVERSEMENT.

    SOURCE DE VÉRITÉ UNIQUE : appelée par `analyze_stability` (repli) ET par
    `layer_slicer._compute_stability` (chemin principal). Avant, chacun avait sa
    formule → la même pièce pouvait obtenir deux scores différents selon le
    chemin d'analyse emprunté (incohérence signalée par Emmanuel).

    - `dist_edge_mm`  : distance du CDM projeté au bord de l'empreinte
    - `com_height_mm` : hauteur du centre de masse au-dessus du plateau
    - `hull_fill`     : empreinte / boîte englobante XY (contact ponctuel = petit)
    """
    com_h = max(float(com_height_mm), 1e-6)
    angle = math.degrees(math.atan2(max(0.0, float(dist_edge_mm)), com_h))
    score = (angle - 8.0) / (35.0 - 8.0)        # 8° → instable, 35°+ → très stable
    score = float(np.clip(score, 0.05, 1.0))
    if hull_fill < 0.02:
        score = min(score, 0.15)                # contact quasi ponctuel
    elif hull_fill < 0.08:
        score = min(score, 0.35)
    if is_top_heavy:
        score *= 0.92
    return float(np.clip(score, 0.0, 1.0))


def brim_pour_score(score: float) -> float:
    """Brim conseillé selon la stabilité (même barème partout)."""
    if score < 0.30:
        return 10.0
    if score < 0.50:
        return 6.0
    if score < 0.65:
        return 4.0
    return 0.0


def analyze_stability(mesh: trimesh.Trimesh) -> StabilityResult:
    """Évalue la stabilité de la pièce dans son orientation actuelle.

    Modèle : ANGLE DE RENVERSEMENT — l'angle dont il faudrait incliner la pièce
    pour que son centre de masse sorte de l'empreinte au sol :

        tan(θ) = distance(CDM projeté, bord de l'empreinte) / hauteur du CDM

    C'est la mesure physique classique du basculement, et elle combine d'elle-même
    les trois facteurs qui comptent (taille d'empreinte, hauteur, position du CDM).
    L'ancien score « marge / rayon d'empreinte » ignorait la hauteur : une tour
    10×10×120 obtenait 0,40 (« moyen ») et une pièce plate à grande base 0,46 —
    incohérences signalées par Emmanuel.

    Repères : θ ≥ 35° = très stable ; θ ≈ 20° = correct ; θ ≤ 8° = instable ;
    CDM hors empreinte = la pièce bascule (score plancher).
    """
    com = mesh.center_mass
    com_xy = com[:2]

    z_min = mesh.bounds[0][2]
    z_max = mesh.bounds[1][2]
    height = z_max - z_min
    # Contact RÉEL : seuil absolu (première couche), pas un pourcentage de la
    # hauteur — sinon une sphère de 30 mm « pose » sur une calotte de 1,5 mm et
    # paraît stable alors qu'elle touche par un point.
    ground_threshold = z_min + max(0.3, min(1.0, height * 0.01))

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

    is_top_heavy = com[2] > height * 0.55

    if not com_inside:
        # CDM hors empreinte → la pièce bascule sous son propre poids
        score = 0.05
    else:
        bb_footprint = (float(mesh.bounding_box.extents[0])
                        * float(mesh.bounding_box.extents[1]))
        fill = footprint_area / bb_footprint if bb_footprint > 1e-6 else 1.0
        score = score_renversement(
            _point_to_polygon_distance(com_xy, hull_verts_2d),
            float(com[2] - z_min), fill, is_top_heavy)

    brim_mm = brim_pour_score(score)

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
