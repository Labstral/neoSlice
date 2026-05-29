"""
Détection de zones de support par lancer de rayons verticaux.

Principe — identique à BambuStudio / PrusaSlicer :
  Pour chaque colonne XY de la pièce (grille régulière), on lance un rayon
  vertical depuis le plateau (Z=z_min) vers le haut et on traverse toute la
  pièce. Chaque face orientée vers le bas (surplomb potentiel) est examinée :
  si la distance entre elle et la matière solide immédiatement en dessous est
  supérieure au seuil de pont, elle nécessite un support.

Avantage sur l'analyse des normales seule :
  Une face inclinée supportée par de la matière en dessous (même si son angle
  dépasse 45°) ne sera PAS marquée comme nécessitant un support.
  Seules les faces réellement « dans le vide » sont détectées.
"""
from __future__ import annotations

import math
import numpy as np
import trimesh
from loguru import logger


_OVERHANG_ANGLE_DEG  = 45.0   # angle depuis l'horizontale (norme FDM)
_GAP_THRESHOLD_MM    = 0.5    # gap minimum sous une face pour la flaguer
_BRIDGE_SPAN_MM      = 12.0   # portée max d'un pont sans support (≈ Bambu)
_MAX_RAYS            = 8000   # limite le nombre de rayons pour la performance


def detect_support_by_raycast(
    mesh: trimesh.Trimesh,
    angle_threshold_deg: float = _OVERHANG_ANGLE_DEG,
    gap_threshold_mm: float = _GAP_THRESHOLD_MM,
) -> tuple[np.ndarray, float, float]:
    """Détecte les faces nécessitant un support par lancer de rayons verticaux.

    Returns
    -------
    face_mask : ndarray bool (n_faces,)
        True si la face est en surplomb réel (aucune matière à moins de
        gap_threshold_mm en dessous d'elle).
    overhang_ratio : float
        Fraction de la surface totale en surplomb.
    severity : float
        Score global 0 → 1.
    """
    b = mesh.bounds
    z_min  = float(b[0][2])
    z_max  = float(b[1][2])
    height = z_max - z_min

    if height < 0.1:
        return np.zeros(len(mesh.faces), dtype=bool), 0.0, 0.0

    # ── Grille adaptative — plafonnée à _MAX_RAYS rayons ─────────────────────
    footprint_x = float(b[1][0] - b[0][0])
    footprint_y = float(b[1][1] - b[0][1])
    ideal_n     = math.sqrt(_MAX_RAYS)
    grid_mm     = max(0.8, min(3.0, max(footprint_x, footprint_y) / ideal_n))

    x_vals = np.arange(b[0][0] + grid_mm / 2, b[1][0], grid_mm)
    y_vals = np.arange(b[0][1] + grid_mm / 2, b[1][1], grid_mm)
    xx, yy = np.meshgrid(x_vals, y_vals)
    origins    = np.column_stack([xx.ravel(), yy.ravel(),
                                  np.full(xx.size, z_min - 1.0)])
    directions = np.tile([0.0, 0.0, 1.0], (len(origins), 1))

    # ── Lancer de rayons ──────────────────────────────────────────────────────
    try:
        locs, idx_ray, idx_tri = mesh.ray.intersects_location(
            origins, directions, multiple_hits=True
        )
    except Exception as exc:
        logger.warning(f"Ray casting échoué : {exc}")
        return np.zeros(len(mesh.faces), dtype=bool), 0.0, 0.0

    if len(locs) == 0:
        return np.zeros(len(mesh.faces), dtype=bool), 0.0, 0.0

    # ── Seuil angulaire : sin(angle) car nz = sin(angle depuis horizontale) ──
    sin_thresh = math.sin(math.radians(angle_threshold_deg))

    # ── Grouper les hits par rayon et trier par Z ─────────────────────────────
    by_ray: dict[int, list[tuple[float, int]]] = {}
    for loc, r_i, f_i in zip(locs, idx_ray.astype(int), idx_tri.astype(int)):
        by_ray.setdefault(int(r_i), []).append((float(loc[2]), int(f_i)))

    face_normals = mesh.face_normals
    support_face_set: set[int] = set()

    for hits in by_ray.values():
        hits.sort(key=lambda h: h[0])

        # z_solid_top : hauteur maximale de matière solide traversée jusqu'ici
        # (= plateau au départ, puis mis à jour à chaque sortie de solide)
        z_solid_top = z_min
        inside      = False   # le rayon est-il actuellement dans la matière ?

        for z_hit, face_i in hits:
            nz = float(face_normals[face_i][2])

            if nz < -sin_thresh:
                # Face orientée vers le bas — surplomb potentiel
                gap = z_hit - z_solid_top
                if gap > gap_threshold_mm and not inside:
                    support_face_set.add(face_i)
                inside = True   # on entre dans la matière

            elif nz > sin_thresh:
                # Face orientée vers le haut — sortie de la matière solide
                z_solid_top = max(z_solid_top, z_hit)
                inside = False

    # ── Filtrer les ponts courts (≤ _BRIDGE_SPAN_MM) ────────────────────────
    if support_face_set:
        support_face_set = _filter_bridges(mesh, support_face_set, _BRIDGE_SPAN_MM)

    # ── Masque et métriques ──────────────────────────────────────────────────
    mask = np.zeros(len(mesh.faces), dtype=bool)
    for fi in support_face_set:
        mask[fi] = True

    face_areas  = mesh.area_faces
    total_area  = float(face_areas.sum())
    support_area = float(face_areas[mask].sum()) if mask.any() else 0.0
    ratio        = support_area / total_area if total_area > 0 else 0.0

    # Sévérité calibrée : ratio × projection verticale → comparable à l'ancien score
    top_mask = face_normals[:, 2] > 0.0
    footprint = float((face_areas[top_mask] * face_normals[top_mask, 2]).sum())
    proj_oh   = float((face_areas[mask] * np.abs(face_normals[mask, 2])).sum()) if mask.any() else 0.0
    proj_ratio = proj_oh / max(footprint, 1e-6)
    severity   = min(1.0, proj_ratio * 3.5)

    return mask, ratio, severity


def support_face_colors(mesh: trimesh.Trimesh, mask: np.ndarray) -> np.ndarray:
    """Couleurs RGBA par face pour la visualisation des zones de support.

    Gris  = surface correctement supportée.
    Jaune = surplomb modéré (45°–60° depuis horizontal).
    Rouge = surplomb critique nécessitant un support.
    """
    n = len(mesh.faces)
    colors = np.full((n, 4), [142, 155, 173, 255], dtype=np.uint8)  # gris bleuté

    if not mask.any():
        return colors

    normals = mesh.face_normals
    z_down  = np.array([0.0, 0.0, -1.0])
    cos_vals = np.clip(normals @ z_down, -1.0, 1.0)
    angles   = np.degrees(np.arccos(cos_vals))   # angle depuis Z-down (0° = plat ↓)

    # Parmi les faces en surplomb : classer par sévérité angulaire
    mild_mask   = mask & (angles <= 60.0)   # 45°–60° depuis horizontal → orange
    severe_mask = mask & (angles < 45.0)    # > 60° depuis horizontal  → rouge

    colors[mild_mask]   = [212, 168, 32, 255]   # jaune ocre
    colors[severe_mask] = [204, 32, 16, 255]    # rouge

    return colors


# ── Bridge filter ─────────────────────────────────────────────────────────────

def _filter_bridges(
    mesh: trimesh.Trimesh,
    support_faces: set[int],
    max_span_mm: float,
) -> set[int]:
    """Retire les faces en surplomb dont la portée est imprimable en pont.

    Un cluster de faces est considéré comme un pont si son étendue maximale
    dans au moins une direction est ≤ max_span_mm ET qu'il possède des
    faces non-surplomb (ancres) des deux côtés dans cette direction.
    """
    if not support_faces:
        return support_faces

    n = len(mesh.faces)
    adj = mesh.face_adjacency
    arr = np.array(sorted(support_faces), dtype=np.int64)
    s_set = set(arr.tolist())

    # Composantes connexes des faces en surplomb
    both_in = np.isin(adj[:, 0], arr) & np.isin(adj[:, 1], arr)
    edges   = adj[both_in]

    label = {fi: fi for fi in s_set}   # initialisation union-find triviale
    for a, b in edges:
        ra, rb = _find(label, a), _find(label, b)
        if ra != rb:
            label[rb] = ra

    clusters: dict[int, list[int]] = {}
    for fi in s_set:
        root = _find(label, fi)
        clusters.setdefault(root, []).append(fi)

    centroids = mesh.triangles_center

    # Pour chaque cluster, tester si c'est un pont dans 4 directions
    keep = set()
    for comp in clusters.values():
        comp_xy = centroids[comp, :2]

        # Ancres = voisins non-surplomb du cluster
        comp_set = set(comp)
        a_side   = adj[:, 0]
        b_side   = adj[:, 1]
        boundary = (np.isin(a_side, arr) ^ np.isin(b_side, arr))
        if boundary.any():
            be = adj[boundary]
            ov_a = np.isin(be[:, 0], arr)
            anc = np.where(ov_a, be[:, 1], be[:, 0])
            anchor_xy = centroids[anc, :2]
        else:
            anchor_xy = None

        is_bridge = False
        if anchor_xy is not None and len(anchor_xy) >= 2:
            for angle_deg in (0.0, 45.0, 90.0, 135.0):
                d = np.array([math.cos(math.radians(angle_deg)),
                              math.sin(math.radians(angle_deg))])
                cp = comp_xy   @ d
                ap = anchor_xy @ d
                span = float(cp.max() - cp.min())
                if span > max_span_mm:
                    continue
                tol = min(2.0, span * 0.15)
                if (ap < cp.min() + tol).any() and (ap > cp.max() - tol).any():
                    is_bridge = True
                    break

        if not is_bridge:
            keep.update(comp)

    return keep


def _find(label: dict, x: int) -> int:
    while label[x] != x:
        label[x] = label[label[x]]
        x = label[x]
    return x
