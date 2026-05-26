from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import trimesh

from .overhang_detector import analyze_overhangs
from .stability_analyzer import analyze_stability


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


# Orientations de base à tester (directions vers le bas du plateau)
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


def optimize_orientation(
    mesh: trimesh.Trimesh,
    n_fibonacci: int = 32,
    weights: dict | None = None,
) -> OrientationResult:
    """Trouve l'orientation optimale parmi les candidats de base + Fibonacci.

    Retourne la transformation à appliquer au mesh pour l'imprimer
    dans la meilleure orientation possible.
    """
    w = weights or {
        "overhang":       0.35,
        "stability":      0.25,
        "support_volume": 0.15,
        "flat_base":      0.25,  # bonus pour surface plate en contact avec le plateau
    }

    candidates: list[tuple[str, np.ndarray]] = list(_BASE_DIRECTIONS.items())

    # Directions Fibonacci pour couvrir l'espace uniformément
    fib_dirs = _fibonacci_sphere(n_fibonacci)
    for i, d in enumerate(fib_dirs):
        candidates.append((f"Fib{i}", d))

    best: OrientationResult | None = None
    baseline_score: float = 0.0

    for label, up_direction in candidates:
        rot = _rotation_to_align_up(up_direction)
        rotated = mesh.copy()
        rotated.apply_transform(rot)
        rotated.apply_translation(-rotated.bounds[0])  # poser sur Z=0

        overhang   = analyze_overhangs(rotated, smooth=False, check_floating=False)
        stability  = analyze_stability(rotated)
        support_vol = _estimate_support_ratio(rotated, overhang)
        flat_base  = _flat_base_score(rotated)

        score = (
            w["overhang"]       * (1.0 - overhang.severity)
            + w["stability"]    * stability.score
            + w["support_volume"] * (1.0 - support_vol)
            + w["flat_base"]    * flat_base
        )

        if label == "Z+":
            baseline_score = score

        friendly_label = _friendly_label(label, up_direction)
        result = OrientationResult(
            rotation_matrix=rot,
            overhang_score=overhang.severity,
            stability_score=stability.score,
            support_volume_ratio=support_vol,
            total_score=score,
            direction_label=friendly_label,
        )

        if best is None or score > best.total_score:
            best = result

    # Calcul de l'amélioration vs orientation actuelle (Z+)
    if best is not None and baseline_score > 0:
        best.baseline_score = baseline_score
        best.improvement_pct = max(0.0, (best.total_score - baseline_score) / baseline_score * 100)
    elif best is not None:
        best.baseline_score = baseline_score
        best.improvement_pct = 0.0

    return best


def _friendly_label(label: str, direction: np.ndarray) -> str:
    """Traduit les labels techniques en termes compréhensibles."""
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
    # Fibonacci : mapper vers le côté dominant
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
    return trimesh.geometry.align_vectors(z, up)


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


def _estimate_support_ratio(mesh: trimesh.Trimesh, overhang) -> float:
    """Estime le ratio volume_support / volume_pièce (heuristique rapide)."""
    if not overhang.critical_face_mask.any():
        return 0.0
    # Heuristique : ratio de faces en surplomb × facteur de hauteur moyenne
    return float(min(1.0, overhang.overhang_ratio * 2.0))


def _flat_base_score(mesh: trimesh.Trimesh) -> float:
    """Score 0-1 : qualité du contact plat avec le plateau de construction.

    1.0 = base parfaitement plate (grand socle horizontal au sol).
    0.0 = seule une arête ou une pointe touche le plateau.

    Ce terme évite que l'algorithme suggère de pencher une pièce à
    socle plat sous prétexte de réduire marginalement les surplombs.
    """
    z_min = float(mesh.bounds[0][2])
    height = float(mesh.bounds[1][2] - z_min)
    if height < 1e-6:
        return 0.0

    # Tolérance : 2 % de la hauteur (min 0.3 mm, max 1.5 mm)
    tol = max(0.3, min(1.5, height * 0.02))

    centers_z  = mesh.triangles_center[:, 2]
    normals_z  = mesh.face_normals[:, 2]
    face_areas = mesh.area_faces

    # Faces dans la zone de contact avec le plateau
    near_floor = centers_z <= z_min + tol

    if not near_floor.any():
        return 0.0

    floor_area = float(face_areas[near_floor].sum())
    if floor_area < 1e-6:
        return 0.0

    # Faces plates orientées vers le bas (normale ~[0,0,-1], angle < 25° de la verticale)
    flat_down = near_floor & (normals_z < -0.9)
    flat_area = float(face_areas[flat_down].sum())

    # Ratio : quelle fraction de la zone de contact est réellement plate ?
    return min(1.0, flat_area / floor_area)
