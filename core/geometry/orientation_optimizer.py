from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from scipy.spatial.qhull import QhullError


@dataclass
class OrientationResult:
    rotation_matrix: np.ndarray   # matrice 4x4 de transformation
    overhang_score: float         # 0=bon, 1=mauvais (moins de surplombs)
    stability_score: float        # 0=mauvais, 1=bon
    support_volume_ratio: float   # 0=bon (peu de support), 1=mauvais
    total_score: float            # score global (plus haut = meilleur)
    direction_label: str          # ex: "Z+", "X-", "Diagonal"
    baseline_score: float = 0.0   # score de l'orientation Z+ (actuelle)
    improvement_pct: float = 0.0  # amélioration vs orientation actuelle (%)


_BASE_DIRECTIONS = {
    "Z+": np.array([0.0, 0.0, 1.0]),
    "Z-": np.array([0.0, 0.0, -1.0]),
    "X+": np.array([1.0, 0.0, 0.0]),
    "X-": np.array([-1.0, 0.0, 0.0]),
    "Y+": np.array([0.0, 1.0, 0.0]),
    "Y-": np.array([0.0, -1.0, 0.0]),
    "XZ+": np.array([0.707, 0.0, 0.707]),
    "XZ-": np.array([0.707, 0.0, -0.707]),
}

_OVERHANG_COS = np.cos(np.radians(45.0))   # cos(45°) ≈ 0.707


def optimize_orientation(
    mesh: trimesh.Trimesh,
    n_fibonacci: int = 24,
    weights: dict | None = None,
) -> OrientationResult:
    """Trouve l'orientation optimale parmi les candidats de base + Fibonacci.

    Utilise des heuristiques numpy légères (pas de ray-casting) pour évaluer
    chaque orientation — suffisant pour comparer des orientations relatives.
    """
    w = weights or {
        "overhang":       0.25,
        "stability":      0.18,
        "support_volume": 0.10,
        "flat_base":      0.20,
        "height":         0.27,
    }

    # Pré-calcul unique des propriétés du mesh
    normals   = mesh.face_normals          # (F, 3)
    areas     = mesh.area_faces            # (F,)
    verts     = mesh.vertices              # (V, 3)
    com       = mesh.center_mass           # (3,)
    extents   = mesh.bounding_box.extents  # (3,)
    _max_dim  = float(max(extents))
    total_area = float(areas.sum()) + 1e-9

    candidates: list[tuple[str, np.ndarray]] = list(_BASE_DIRECTIONS.items())
    fib_dirs = _fibonacci_sphere(n_fibonacci)
    for i, d in enumerate(fib_dirs):
        candidates.append((f"Fib{i}", d))

    best: OrientationResult | None = None
    baseline_score: float = 0.0

    for label, up_direction in candidates:
        rot4 = _rotation_to_align_up(up_direction)
        rot3 = rot4[:3, :3]

        # Rotation des normales et sommets (numpy, pas de copie trimesh)
        r_normals = normals @ rot3.T    # (F, 3) — chaque normale rotée
        r_verts   = verts   @ rot3.T   # (V, 3) — sommets rotés
        r_com     = rot3 @ com          # (3,)

        # Normaliser Z → poser sur le plateau (z_min = 0)
        z_min_r = float(r_verts[:, 2].min())
        r_verts_z = r_verts[:, 2] - z_min_r
        r_com_z   = float(r_com[2]) - z_min_r
        height_mm = float(r_verts_z.max())

        overhang_r  = _fast_overhang(r_normals, areas, total_area)
        stability_r = _fast_stability(r_verts, r_verts_z, r_com, r_com_z,
                                      height_mm, extents)
        flat_r      = _fast_flat_base(r_normals, areas, r_verts_z)
        height_score = 1.0 - min(1.0, height_mm / (_max_dim + 1e-9))

        score = (
            w["overhang"]       * (1.0 - overhang_r)
            + w["stability"]    * stability_r
            + w["support_volume"] * (1.0 - overhang_r)   # proxy rapide
            + w["flat_base"]    * flat_r
            + w["height"]       * height_score
        )

        if label == "Z+":
            baseline_score = score

        friendly_label = _friendly_label(label, up_direction)
        result = OrientationResult(
            rotation_matrix=rot4,
            overhang_score=overhang_r,
            stability_score=stability_r,
            support_volume_ratio=overhang_r,
            total_score=score,
            direction_label=friendly_label,
        )

        if best is None or score > best.total_score:
            best = result

    if best is not None and baseline_score > 0:
        best.baseline_score = baseline_score
        best.improvement_pct = max(0.0, (best.total_score - baseline_score) / baseline_score * 100)
    elif best is not None:
        best.baseline_score = baseline_score
        best.improvement_pct = 0.0

    return best


# ── Heuristiques rapides (numpy uniquement) ───────────────────────────────────

def _fast_overhang(r_normals: np.ndarray, areas: np.ndarray, total_area: float) -> float:
    """Ratio de surface en surplomb — heuristique normales (pas de ray-casting)."""
    # Faces avec nz < -cos(45°) → pointent vers le bas de plus de 45°
    critical = r_normals[:, 2] < -_OVERHANG_COS
    if not critical.any():
        return 0.0
    return float(np.clip(areas[critical].sum() / total_area, 0.0, 1.0))


def _fast_stability(
    r_verts: np.ndarray,
    r_verts_z: np.ndarray,
    r_com: np.ndarray,
    r_com_z: float,
    height_mm: float,
    extents: np.ndarray,
) -> float:
    """Score de stabilité — ConvexHull de l'empreinte (scipy, rapide)."""
    if height_mm < 1e-6:
        return 0.85

    ground_mask = r_verts_z <= height_mm * 0.05
    ground_xy   = r_verts[ground_mask, :2]

    if len(ground_xy) < 3:
        return 0.05

    try:
        hull = ConvexHull(ground_xy)
        footprint_area = float(hull.volume)   # volume = aire en 2D
    except (QhullError, Exception):
        return 0.2

    com_xy = r_com[:2]

    # CDM dans l'empreinte convexe ?
    eqs = hull.equations   # [nx, ny, c] tq nx*x + ny*y + c <= 0 (intérieur)
    inside = bool(np.all(eqs[:, :2] @ com_xy + eqs[:, 2] <= 1e-6))

    if not inside:
        base_score = 0.05
    else:
        import math
        hull_verts_2d = ground_xy[hull.vertices]
        dist_edge = _point_to_convex_distance(com_xy, hull_verts_2d)
        char_r = math.sqrt(footprint_area / math.pi) if footprint_area > 1e-6 else 1.0
        base_score = float(np.clip(dist_edge / max(char_r, 1.0), 0.0, 1.0))

    # Pénalité : empreinte vs boîte englobante
    bb_xy = float(extents[0]) * float(extents[1])
    if bb_xy > 1e-6:
        fill = footprint_area / bb_xy
        if fill < 0.08:
            base_score *= 0.20
        elif fill < 0.20:
            base_score *= 0.45
        elif fill < 0.40:
            base_score *= 0.70

    # Pénalité : ratio hauteur/empreinte
    import math
    eff_w = math.sqrt(footprint_area) if footprint_area > 1e-6 else 1.0
    h_ratio = height_mm / max(eff_w, 1.0)
    if h_ratio > 4.0:
        base_score *= 0.30
    elif h_ratio > 3.0:
        base_score *= 0.45
    elif h_ratio > 2.0:
        base_score *= 0.65
    elif h_ratio > 1.5:
        base_score *= 0.85

    # Pénalité top-heavy
    if r_com_z > height_mm * 0.60:
        base_score *= 0.80

    return float(np.clip(base_score, 0.0, 1.0))


def _fast_flat_base(r_normals: np.ndarray, areas: np.ndarray, r_verts_z: np.ndarray) -> float:
    """Score de planéité de la base (normales vers le bas proches du sol)."""
    if r_verts_z.max() < 1e-6:
        return 0.0

    height = float(r_verts_z.max())
    # trimesh.triangles_center non disponible ici — on approxime par r_verts_z min
    # Utiliser le min Z des sommets pour approximer les faces au sol
    # (pas de centroïde de triangle disponible sans copie mesh)
    # Heuristique : faces avec normale nz < -0.9 (quasi-horizontales vers le bas)
    flat_down = r_normals[:, 2] < -0.9
    if not flat_down.any():
        return 0.0

    total = float(areas.sum()) + 1e-9
    return float(np.clip(areas[flat_down].sum() / total, 0.0, 1.0))


def _point_to_convex_distance(point: np.ndarray, polygon: np.ndarray) -> float:
    """Distance minimale d'un point aux arêtes d'un polygone convexe."""
    min_dist = float("inf")
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        edge = b - a
        edge_len_sq = float(np.dot(edge, edge))
        if edge_len_sq < 1e-10:
            continue
        t = float(np.clip(np.dot(point - a, edge) / edge_len_sq, 0, 1))
        proj = a + t * edge
        dist = float(np.linalg.norm(point - proj))
        min_dist = min(min_dist, dist)
    return min_dist if min_dist < float("inf") else 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _friendly_label(label: str, direction: np.ndarray) -> str:
    _LABELS = {
        "Z+": "Actuelle (Z+)",
        "Z-": "Retourner à 180°",
        "X+": "Pivoter 90° sur Y",
        "X-": "Pivoter -90° sur Y",
        "Y+": "Pivoter 90° sur X",
        "Y-": "Pivoter -90° sur X",
        "XZ+": "Diagonal 45° (XZ)",
        "XZ-": "Diagonal -45° (XZ)",
    }
    if label in _LABELS:
        return _LABELS[label]
    d = direction / (np.linalg.norm(direction) + 1e-9)
    ax = int(np.argmax(np.abs(d)))
    sign = "+" if d[ax] >= 0 else "-"
    axis_name = ["X", "Y", "Z"][ax]
    return f"Incliné vers {axis_name}{sign}"


def _rotation_to_align_up(up: np.ndarray) -> np.ndarray:
    """Génère une matrice 4x4 pour aligner 'up' avec Z+."""
    up = up / np.linalg.norm(up)
    z = np.array([0.0, 0.0, 1.0])
    if np.allclose(up, z):
        return np.eye(4)
    if np.allclose(up, -z):
        return trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    return trimesh.geometry.align_vectors(up, z)


def _fibonacci_sphere(n: int) -> list[np.ndarray]:
    """Distribution uniforme de N points sur la demi-sphère supérieure."""
    golden = (1.0 + np.sqrt(5.0)) / 2.0
    dirs = []
    for i in range(n):
        theta = np.arccos(1.0 - 2.0 * (i + 0.5) / n)
        phi = 2.0 * np.pi * i / golden
        x = np.sin(theta) * np.cos(phi)
        y = np.sin(theta) * np.sin(phi)
        z = np.cos(theta)
        if z >= 0:
            dirs.append(np.array([x, y, z]))
    return dirs
