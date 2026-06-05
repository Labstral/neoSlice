"""
Détection de surplombs — algorithme aligné sur Bambu Studio / PrusaSlicer.

Pipeline :
  1. Lissage des normales via multiplication matricielle sparse (scipy)
  2. Filtre angulaire à 45° depuis l'horizontale
  3. Exclusion du plateau de construction
  4. Composantes connexes scipy (C, rapide même sur 1M+ faces)
  5. Filtre surface minimale par cluster
  6. Détection de ponts : test directionnel 4 axes (méthode BridgeDetector Bambu)
  7. Détection de régions flottantes : composants mesh sans contact Z_min
  8. Métriques : ratio surface, aire XY projetée (≈ Bambu), sévérité

Paramètres smooth/check_floating séparables pour le mode rapide
utilisé par l'optimiseur d'orientation (évite 32 × 5 s par analyse).
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components as _scipy_cc

# ── Paramètres (calibrés sur Benchy / Bishop réels) ─────────────────────────
SUPPORT_THRESHOLD_DEG: float = 45.0   # angle depuis l'horizontale (norme FDM)
_MIN_CLUSTER_AREA_MM2: float = 8.0    # surface minimale d'un cluster à signaler (~3×3 mm)
_MAX_BRIDGE_SPAN_MM: float = 12.0    # portée max en pont (~10-15 mm Bambu)
_SMOOTH_WEIGHT: float = 0.25          # contribution voisin au lissage


@dataclass
class OverhangResult:
    severity: float                # 0 → 1, score global
    overhang_ratio: float          # fraction surface en surplomb / surface totale
    projected_ratio: float         # fraction aire XY projetée (≈ méthode Bambu)
    max_angle_deg: float           # angle max depuis l'horizontale (°)
    critical_face_mask: np.ndarray # masque booléen par face (filtré — pour métriques)
    has_floating_regions: bool     # composant mesh sans contact plateau
    display_mask: np.ndarray = None  # masque brut sans filtre pont — pour la visu couleur


def analyze_overhangs(
    mesh: trimesh.Trimesh,
    angle_threshold_deg: float = SUPPORT_THRESHOLD_DEG,
    smooth: bool = True,
    check_floating: bool = True,
) -> OverhangResult:
    """Détecte les faces en surplomb selon la méthode Bambu Studio / PrusaSlicer.

    smooth=False / check_floating=False pour le mode rapide de l'optimiseur
    d'orientation (évite de multiplier le coût par 32 orientations).
    """
    # ── Calcul anticipé des aires (nécessaire pour le filtre de cluster adaptatif) ──
    face_areas = mesh.area_faces
    total_area = float(face_areas.sum())
    # Seuils adaptatifs à la taille de la pièce
    # min_cluster_area : 0.2% de la surface totale, borné entre 0.5 et 8 mm²
    min_cluster_area = min(max(0.5, total_area * 0.002), _MIN_CLUSTER_AREA_MM2)
    # max_bridge : 40% de la dimension max, borné à _MAX_BRIDGE_SPAN_MM
    # Évite que toute une petite pièce soit classée "pont" et ses surplombs ignorés
    max_bridge_adaptive = min(_MAX_BRIDGE_SPAN_MM, float(mesh.bounding_box.extents.max()) * 0.4)

    # ── 1. Lissage des normales (sparse matmul, rapide même sur 1M+ faces) ──
    if smooth:
        normals = _smooth_face_normals(mesh, iters=2)
    else:
        normals = mesh.face_normals.copy()

    # ── 2. Filtre angulaire ──────────────────────────────────────────────────
    z_down = np.array([0.0, 0.0, -1.0])
    cos_vals = np.clip(normals @ z_down, -1.0, 1.0)
    angles_from_zdown = np.degrees(np.arccos(cos_vals))
    cutoff = 90.0 - angle_threshold_deg       # 45° pour threshold=45°
    mask = angles_from_zdown < cutoff

    # ── 3. Exclusion plateau ─────────────────────────────────────────────────
    z_min = float(mesh.bounds[0][2])
    z_height = float(mesh.bounds[1][2] - z_min)
    # Tolérance adaptative. Bornée à 35% de z_height pour ne pas masquer les vrais surplombs
    # de pièces basses (ex: liner poubelle 9mm, coques iPhone 10mm).
    _aspect = z_height / max(float(mesh.bounding_box.extents[0]),
                              float(mesh.bounding_box.extents[1]), 1.0)
    # Pièces hautes (aspect ≥ 0.4) : tolérance standard. Plates : un peu plus généreuse.
    _base_tol = 5.0 if _aspect < 0.4 else 3.0
    plate_tol = min(
        max(_base_tol, z_height * 0.08),
        z_height * 0.35,  # jamais plus de 35% de la hauteur totale
    )
    face_centroids = mesh.triangles_center
    on_plate = (
        (face_centroids[:, 2] <= z_min + plate_tol)
        & (normals[:, 2] < -0.20)
    )
    mask = mask & ~on_plate

    # Note: le filtre internal_flat a été retiré — il excluait incorrectement
    # le dessous de modèles plats (coques, plaques) qui ont aussi nz ≈ -1.0.

    # ── 4-6. Clustering scipy + filtre surface + ponts ───────────────────────
    display_mask = mask.copy()   # masque brut avant filtre pont — pour la visu
    if mask.any():
        mask = _filter_clusters_and_bridges(
            mesh, normals, mask,
            min_area=min_cluster_area,
            max_bridge=max_bridge_adaptive,
        )

    # ── 7. Régions flottantes ────────────────────────────────────────────────
    has_floating = _detect_floating_regions(mesh) if check_floating else False

    # ── 8. Métriques ─────────────────────────────────────────────────────────

    overhang_area = float(face_areas[mask].sum()) if mask.any() else 0.0
    ratio = overhang_area / total_area if total_area > 0 else 0.0

    # Aire XY projetée : pondération par |normal_z|
    # → les faces presque horizontales comptent davantage (comme Bambu)
    top_mask = normals[:, 2] > 0.0
    total_footprint = float((face_areas[top_mask] * normals[top_mask, 2]).sum())
    overhang_proj = float(
        (face_areas[mask] * np.abs(normals[mask, 2])).sum()
    ) if mask.any() else 0.0
    projected_ratio = overhang_proj / max(total_footprint, 1e-6)

    # Sévérité : max entre la méthode projetée (Bambu) et le ratio de faces
    # Le ratio de faces évite d'afficher 0% quand il y a des surplombs réels
    # mais une petite surface projetée (ex: arêtes fines, petits overhangs locaux)
    severity = min(1.0, max(projected_ratio * 3.0, ratio * 0.6))

    max_angle = 0.0
    if mask.any():
        worst = float(angles_from_zdown[mask].min())
        max_angle = 90.0 - worst

    return OverhangResult(
        severity=severity,
        overhang_ratio=ratio,
        projected_ratio=projected_ratio,
        max_angle_deg=max_angle,
        critical_face_mask=mask,
        has_floating_regions=has_floating,
        display_mask=display_mask,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _smooth_face_normals(mesh: trimesh.Trimesh, iters: int = 2) -> np.ndarray:
    """Lisse les normales via sparse matmul — O(E) en C, rapide sur grands meshes.

    Chaque normale reçoit une contribution _SMOOTH_WEIGHT de chacun de ses voisins.
    Réduit le bruit de tessellation sans déformer la géométrie perçue.
    """
    n = len(mesh.faces)
    adj = mesh.face_adjacency  # (E, 2)

    # Matrice d'adjacence sparse (pondérée par _SMOOTH_WEIGHT)
    row = np.concatenate([adj[:, 0], adj[:, 1]])
    col = np.concatenate([adj[:, 1], adj[:, 0]])
    data = np.full(len(row), _SMOOTH_WEIGHT, dtype=np.float32)
    A = csr_matrix((data, (row, col)), shape=(n, n), dtype=np.float32)

    normals = mesh.face_normals.astype(np.float32)
    for _ in range(iters):
        accum = normals + A.dot(normals)          # sparse matmul, vectorisé en C
        lengths = np.linalg.norm(accum, axis=1, keepdims=True)
        normals = accum / np.maximum(lengths, 1e-9)

    return normals.astype(np.float64)


def _filter_clusters_and_bridges(
    mesh: trimesh.Trimesh,
    normals: np.ndarray,
    mask: np.ndarray,
    min_area: float,
    max_bridge: float,
) -> np.ndarray:
    """Clustering via scipy connected_components + filtre surface + test pont.

    Remplace le BFS Python (lent sur 100k+ faces) par du C via scipy.
    L'identification des ancres et le test de pont restent en numpy vectorisé.
    """
    n = len(mesh.faces)
    face_areas = mesh.area_faces
    centroids = mesh.triangles_center
    adj = mesh.face_adjacency  # (E, 2) — arêtes partagées

    # ── Composantes connexes des faces en surplomb ───────────────────────────
    both_ov = mask[adj[:, 0]] & mask[adj[:, 1]]
    ov_edges = adj[both_ov]

    if len(ov_edges) > 0:
        r = np.concatenate([ov_edges[:, 0], ov_edges[:, 1]])
        c = np.concatenate([ov_edges[:, 1], ov_edges[:, 0]])
        g = csr_matrix((np.ones(len(r), np.uint8), (r, c)), shape=(n, n))
        _, labels = _scipy_cc(g, directed=False)
    else:
        labels = np.arange(n)

    # ── Ancres vectorisées ───────────────────────────────────────────────────
    # Arêtes où une seule face est en surplomb → face non-surplomb = "ancre"
    ov_a = mask[adj[:, 0]]
    ov_b = mask[adj[:, 1]]
    boundary = ov_a ^ ov_b                        # exactement une face en surplomb
    if boundary.any():
        be = adj[boundary]
        ov_side = ov_a[boundary]
        ov_face   = np.where(ov_side, be[:, 0], be[:, 1])
        anc_face  = np.where(ov_side, be[:, 1], be[:, 0])
        ov_lbl_b  = labels[ov_face]               # label cluster → ancre
    else:
        ov_lbl_b = np.array([], dtype=np.int64)
        anc_face = np.array([], dtype=np.int64)

    # ── Traitement par cluster ───────────────────────────────────────────────
    ov_idx = np.where(mask)[0]
    ov_labels = labels[ov_idx]
    unique_labels = np.unique(ov_labels)

    result_mask = np.zeros(n, dtype=bool)

    for lbl in unique_labels:
        comp_arr = ov_idx[ov_labels == lbl]

        # Filtre 1 : surface trop petite (artefact)
        if float(face_areas[comp_arr].sum()) < min_area:
            continue

        # Filtre 2 : pont imprimable
        lbl_anc_mask = ov_lbl_b == lbl
        if lbl_anc_mask.any():
            anchor_xy = centroids[anc_face[lbl_anc_mask], :2]
        else:
            anchor_xy = None   # pas d'ancres → certainement pas un pont

        if anchor_xy is not None and _is_bridgeable(
            centroids[comp_arr, :2], anchor_xy, max_bridge
        ):
            continue

        result_mask[comp_arr] = True

    return result_mask


def _is_bridgeable(comp_xy: np.ndarray, anchor_xy: np.ndarray, max_span: float) -> bool:
    """Test directionnel inspiré du BridgeDetector de Bambu Studio.

    4 directions (0°, 45°, 90°, 135°). Si le span du cluster ≤ max_span
    ET des ancres existent des deux côtés → pont imprimable sans support.
    """
    for angle_deg in (0.0, 45.0, 90.0, 135.0):
        rad = np.radians(angle_deg)
        d = np.array([np.cos(rad), np.sin(rad)])

        comp_proj   = comp_xy   @ d
        anchor_proj = anchor_xy @ d

        c_min, c_max = float(comp_proj.min()), float(comp_proj.max())
        span = c_max - c_min
        if span > max_span:
            continue

        tol = min(2.0, span * 0.15)
        if (anchor_proj < c_min + tol).any() and (anchor_proj > c_max - tol).any():
            return True

    return False


def _detect_floating_regions(mesh: trimesh.Trimesh) -> bool:
    """Détecte les composants mesh sans contact avec le plateau (Z_min).

    Correspond exactement à l'avertissement "régions flottantes" de Bambu Studio :
    tout composant entièrement au-dessus du plateau ne peut pas tenir sans supports.
    """
    z_min = float(mesh.bounds[0][2])
    z_height = float(mesh.bounds[1][2] - z_min)
    tol = max(0.5, z_height * 0.02)

    try:
        components = mesh.split(only_watertight=False)
    except Exception:
        return False

    if len(components) <= 1:
        return False

    for comp in components:
        if float(comp.bounds[0][2]) > z_min + tol:
            return True

    return False


def overhang_face_colors(mesh: trimesh.Trimesh, result: OverhangResult) -> np.ndarray:
    """Tableau RGBA par face — sévérité continue encodée dans le canal R.

    Canal R = sévérité [0→255] pour les faces en surplomb détectées.
    Canal G = 128 sur les faces sûres (distingue sev=0 overhang de face safe).
    Décodé par Viewer3D.colorize_overhangs() via cmap jaune→orange→rouge.

    Sévérité : 1.0 = plafond pur (face vers le bas), 0.0 = seuil 45° ou en-dessous.
    """
    # Normales lissées depuis le résultat si disponibles, sinon brutes
    normals = mesh.face_normals
    z_down = np.array([0.0, 0.0, -1.0])
    cos_down = np.clip(normals @ z_down, -1.0, 1.0)
    angle_from_down = np.degrees(np.arccos(cos_down))  # 0°=plafond pur, 90°=mur, 180°=sol

    # Sévérité brute linéaire : 1.0 à 0° (plafond), 0.0 à 45° (seuil)
    sev_raw = np.clip((45.0 - angle_from_down) / 45.0, 0.0, 1.0)

    # Courbe non-linéaire (puissance 0.55) : transitions visuelles claires.
    #   ~43° (sev_raw=0.05) → sev~0.20 (jaune clair)
    #   ~30° (sev_raw=0.33) → sev~0.56 (orange)
    #   ~10° (sev_raw=0.78) → sev~0.85 (rouge-orange)
    #    0° (sev_raw=1.00)  → sev=1.00 (rouge)
    sev_curved = np.power(sev_raw, 0.55)

    # critical_face_mask pour les couleurs 3D (post-filtrage pont/cluster).
    # Évite de montrer les surplombs bridgeables (bords de socle, plafonds de trous hexagonaux)
    # en orange/rouge alors qu'ils ne nécessitent pas de support.
    # display_mask reste utilisé pour la JAUGE (cohérence numérique).
    critical = result.critical_face_mask

    sev = np.where(
        critical & (sev_raw > 0.04),
        np.maximum(sev_curved, 0.20),
        0.0,
    )

    colors = np.zeros((len(mesh.faces), 4), dtype=np.uint8)
    colors[:, 3] = 255
    colors[:, 0] = (sev * 255).astype(np.uint8)   # R = sévérité encodée
    colors[~critical, 1] = 128                      # G=128 = marqueur face sûre
    return colors
