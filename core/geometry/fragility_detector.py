"""Détection des zones fragiles — voxel solide + EDT 3D.

Algorithme principal :
  1. Voxelisation SOLIDE avec padding extérieur (Z-ray parity).
  2. EDT 3D → dist_mm[x,y,z] = distance à la surface la plus proche.
  3. Axe médian ROBUSTE = maximums locaux du champ EDT (filtre 3×3×3)
     filtrés à dist_voxels > _MIN_MEDIAL_DIST pour exclure les coins
     et arêtes géométriques aigus (EDT=1-2) qui ne sont pas des parois
     fragiles. Fallback sur axe médian complet pour les pièces très fines.
  4. Sévérité CONTINUE via blend P50/P10 de l'épaisseur :
       global_sev = 0.5 × sev(P10_t) + 0.5 × sev(P50_t)
     P50 = médiane (robuste), P10 = queue fine (sensibilité).
     Calibration (plaque mince) :
       0.5 mm → ~84 %   0.8 mm → ~68 %   1.2 mm → ~47 %
       1.5 mm → ~27 %   2.0 mm → ~13 %   5.0 mm →  ~0 %
  5. Zones fragiles (< seuil critique) : clustering 3D + filtrage.
     Les zones au niveau du plateau d'impression (Z ≤ z_min + plate_tol)
     sont exclues — elles sont soutenues par le plateau, pas fragiles.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import trimesh
from loguru import logger
from scipy import ndimage

from .analysis_report import Zone3D

# ── Constantes ────────────────────────────────────────────────────────────────
_PADDING_VOXELS  = 3     # voxels False autour du mesh (EDT boundary)
_SIG_K           = 2.2  # pente de la sigmoïde

# Facteurs relatifs au diamètre de buse (calibrés sur Bambu 0.4 mm) :
#   _F_MIN_SAFE  × D_buse = épaisseur seuil (3 parois)        → 1.2 mm à 0.4 mm
#   _F_SIG_T0    × D_buse = centre sigmoïde (50 % sévérité)  → 1.35 mm à 0.4 mm
#   _F_SPIKE     × D_buse = seuil fallback raycast             → 2.0 mm à 0.4 mm
_F_MIN_SAFE = 3.0
_F_SIG_T0   = 3.375
_F_SPIKE    = 5.0

# Buse par défaut si non précisée (0.4 mm standard Bambu)
_DEFAULT_NOZZLE_MM = 0.4

# Distance EDT minimale pour l'axe médian robuste
_MIN_MEDIAL_DIST = 2.0


# ── Fonction de sévérité continue ─────────────────────────────────────────────

def _t_to_sev(
    t_mm: "np.ndarray | float",
    sig_t0: float = _F_SIG_T0 * _DEFAULT_NOZZLE_MM,
) -> "np.ndarray | float":
    """Épaisseur de paroi (mm) → sévérité [0, 1].

    sig_t0 = centre de la sigmoïde = _F_SIG_T0 × diamètre buse.
    Exemples pour buse 0.4 mm (sig_t0=1.35) :
      0.4 mm→0.90   0.8 mm→0.75   1.2 mm→0.55   2.0 mm→0.20   5.0 mm→0.00
    Pour buse 0.6 mm (sig_t0=2.025) : seuils ×1.5 — pièce fine = 1.8 mm.
    """
    t = np.asarray(t_mm, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(np.clip(_SIG_K * (t - sig_t0), -500.0, 500.0)))


# ── Dataclass résultat ────────────────────────────────────────────────────────

@dataclass
class FragilityResult:
    has_fragile_zones: bool
    fragile_zones: list[Zone3D]
    min_thickness_mm: float
    severity: float  # 0.0 → 1.0 continu


# ── API publique ───────────────────────────────────────────────────────────────

def detect_fragility(
    mesh: trimesh.Trimesh,
    n_samples: int = 2000,
    nozzle_diameter_mm: float = _DEFAULT_NOZZLE_MM,
    fast: bool = False,
) -> FragilityResult:
    """fast=True réduit la résolution voxel (~8x plus rapide) pour les previews."""
    """Détecte les zones fragiles en tenant compte du diamètre de buse.

    Les seuils d'épaisseur sont calculés relativement à la buse :
      seuil sûr     = _F_MIN_SAFE × nozzle  (3 parois)
      centre sigm.  = _F_SIG_T0   × nozzle  (50 % de sévérité)
    """
    nozzle  = float(np.clip(nozzle_diameter_mm, 0.1, 1.2))
    min_t   = _F_MIN_SAFE * nozzle   # ex: 1.2 mm à 0.4 mm
    sig_t0  = _F_SIG_T0   * nozzle   # ex: 1.35 mm à 0.4 mm
    spike_t = _F_SPIKE    * nozzle   # ex: 2.0 mm à 0.4 mm

    # ── Détection rapide par aire moyenne des faces ────────────────────────
    # Les structures de fils/lattices ont des milliers de micro-triangles
    # (aire moyenne très petite). Une pièce solide a de grandes faces.
    # Seuil : si aire_moy < (nozzle × 2)² → structure probablement fine.
    try:
        _n_faces = len(mesh.faces)
        if _n_faces > 100:
            _total_sa = float(mesh.area)
            _avg_face_area = _total_sa / _n_faces  # mm²/face
            # Seuil : aire d'une face sur structure fine ≈ (nozzle*2)² / 2
            _area_threshold = (nozzle * 2.0) ** 2  # ex: 0.64 mm² à 0.4mm buse
            if _avg_face_area < _area_threshold:
                # Aires très petites = micro-géométrie = fils/lattice = fragile
                _area_sev = float(np.clip(
                    1.0 - _avg_face_area / _area_threshold, 0.0, 1.0
                ))
                # Également SA/V si watertight (complément)
                if mesh.is_watertight:
                    _vol = abs(float(mesh.volume))
                    if _vol > 0:
                        _mean_t = 2.0 * _vol / max(_total_sa, 1e-6)
                        if _mean_t < sig_t0:
                            _area_sev = max(_area_sev,
                                            float(np.clip(1.0 - _mean_t/sig_t0, 0.0, 1.0)))

                if _area_sev > 0.3:
                    _est_t = max(0.1, nozzle * (1.0 - _area_sev))
                    logger.debug(f"Thin-struct: avg_face={_avg_face_area:.3f}mm² "
                                 f"(thresh={_area_threshold:.3f}) → sev={_area_sev:.2f}")
                    return FragilityResult(
                        has_fragile_zones=True,
                        fragile_zones=[],
                        min_thickness_mm=_est_t,
                        severity=_area_sev,
                    )
    except Exception:
        pass

    bb      = mesh.bounding_box.extents
    max_dim = float(max(bb))
    pitch   = float(np.clip(max_dim / 200.0, 0.20, 0.80))

    try:
        result = _detect_voxel_edt(mesh, pitch, min_t, sig_t0)
        if result is not None:
            # Combiner avec l'estimation SA/V si disponible
            return result
    except Exception:
        logger.warning("Voxelisation EDT échouée — fallback raycast")

    return _detect_raycast(mesh, n_samples, min_t, sig_t0, spike_t)


# ── Méthode principale : voxel solide + EDT + axe médian ──────────────────────

def _detect_voxel_edt(
    mesh: trimesh.Trimesh,
    pitch: float,
    min_thickness_mm: float,
    sig_t0: float = _F_SIG_T0 * _DEFAULT_NOZZLE_MM,
) -> FragilityResult | None:

    # ── 1. Voxelisation solide avec padding ──────────────────────────────
    solid = _parity_solid_voxelize(mesh, pitch)
    if solid is None:
        return None
    grid, bb_min = solid
    if not grid.any():
        return None

    # ── 2. EDT 3D ────────────────────────────────────────────────────────
    dist_voxels = ndimage.distance_transform_edt(grid)
    dist_mm     = dist_voxels * pitch

    # ── 3. Axe médian robuste = maximums locaux du champ EDT ─────────────
    # On exclut les voxels à dist_voxels ≤ _MIN_MEDIAL_DIST : ce sont les
    # arêtes/coins géométriques (ex: arêtes d'une pyramide, pointe d'un cône)
    # qui ne représentent pas de fragilité structurelle FDM réelle.
    # Fallback sur l'axe médian complet pour les pièces entièrement fines.
    footprint    = np.ones((3, 3, 3), dtype=bool)
    max_in_nbhd  = ndimage.maximum_filter(dist_voxels, footprint=footprint)
    medial_raw   = grid & (dist_voxels >= max_in_nbhd) & (dist_voxels > 0)
    medial_mask  = medial_raw & (dist_voxels > _MIN_MEDIAL_DIST)
    if not medial_mask.any():
        medial_mask = medial_raw  # pièce très fine → pas d'artefact à filtrer

    if medial_mask.any():
        # Correction quantification : EDT centre-à-centre, -pitch sur l'épaisseur.
        t_medial = np.maximum(pitch * 0.5, dist_mm[medial_mask] * 2.0 - pitch)

        # Score global = blend P50 (médiane robuste) + P10 (queue fine sensible).
        # Robuste aux coins/arêtes géométriques car ils représentent < 10 %
        # de l'axe médian d'une pièce solide → P10 et P50 restent dans le
        # matériau épais.
        p50_t      = float(np.percentile(t_medial, 50))
        p10_t      = float(np.percentile(t_medial, 10))
        global_sev = float(np.clip(
            0.5 * float(_t_to_sev(p50_t, sig_t0)) + 0.5 * float(_t_to_sev(p10_t, sig_t0)),
            0.0, 1.0,
        ))
        min_t_medial = float(t_medial.min())
    else:
        global_sev   = 0.0
        min_t_medial = float(dist_mm[grid].max() * 2.0) if grid.any() else 99.0

    # ── 4. Masque des zones fragiles (sous le seuil critique) ────────────
    # dist_voxels > 0.5 : exclut la couche de voxels de bord
    thin_raw = grid & (dist_mm < min_thickness_mm / 2.0) & (dist_voxels > 0.5)

    # Filtre anti-faux-positifs : dilate les zones épaisses (26-connexité)
    # et soustrait pour ne garder que les zones vraiment fines.
    # Epsilon : évite que dist_mm = seuil + flottant (ex. 0.6000000000000001)
    # ne classe les voxels-limites dans thick_interior → les effaçant par dilatation.
    _THICK_EPS     = 1e-9
    thick_interior = grid & (dist_mm > min_thickness_mm / 2.0 + _THICK_EPS)
    if thick_interior.any():
        dilation_r    = int(np.ceil(min_thickness_mm / 2.0 / pitch)) + 2
        struct        = ndimage.generate_binary_structure(3, 3)
        thick_dilated = ndimage.binary_dilation(
            thick_interior, structure=struct, iterations=dilation_r
        )
        thin_mask = thin_raw & ~thick_dilated
    else:
        thin_mask = thin_raw

    has = bool(thin_mask.any())
    if not has:
        return FragilityResult(False, [], min_t_medial, global_sev)

    # ── 5. Clustering des zones fragiles ─────────────────────────────────
    labeled, n_zones = ndimage.label(thin_mask)
    fragile_zones: list[Zone3D] = []

    # Exclusion des zones au niveau du plateau d'impression :
    # les arêtes/coins du bas (sur le lit d'impression) sont soutenues
    # par le plateau et ne sont pas des zones fragiles au sens FDM.
    z_min_world = float(mesh.bounds[0][2])
    z_height    = float(mesh.bounds[1][2] - z_min_world)
    plate_tol   = max(0.1, z_height * 0.005)

    for zone_id in range(1, n_zones + 1):
        zone_mask = labeled == zone_id
        if int(zone_mask.sum()) < 3:
            continue

        zone_idx   = np.argwhere(zone_mask)
        zone_t_mm  = dist_mm[zone_mask] * 2.0
        thinnest_i = int(np.argmin(zone_t_mm))
        thinnest   = zone_idx[thinnest_i]

        world_pt = bb_min + (thinnest + 0.5) * pitch
        wall_t   = float(zone_t_mm[thinnest_i])

        # Ignorer les zones posées sur le plateau (soutenues, pas fragiles)
        if world_pt[2] < z_min_world + plate_tol:
            continue

        fragile_zones.append(Zone3D(
            point=world_pt.tolist(),
            thickness_mm=round(wall_t, 3),
            severity=round(float(_t_to_sev(wall_t, sig_t0)), 3),
        ))
        if len(fragile_zones) >= 50:
            break

    if not fragile_zones:
        return FragilityResult(False, [], min_t_medial, global_sev)

    # global_sev calculé depuis l'axe médian robuste (étape 3).
    return FragilityResult(
        has_fragile_zones=True,
        fragile_zones=fragile_zones,
        min_thickness_mm=min_t_medial,
        severity=global_sev,
    )


# ── Voxelisation solide par parité des rayons Z ───────────────────────────────

def _parity_solid_voxelize(
    mesh: trimesh.Trimesh,
    pitch: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Voxelisation solide via lancer de rayons + parité.

    Pour chaque colonne (X,Y), lance un rayon selon +Z et marque True les voxels
    entre chaque paire d'intersections (entrée/sortie du mesh).
    Le grid est padded de _PADDING_VOXELS voxels False de chaque côté,
    garantissant que l'EDT a toujours des voxels False hors du mesh.

    Returns (grid_bool, bb_min_world) ou None si échec.
    """
    PAD = _PADDING_VOXELS

    bb     = mesh.bounds
    bb_min = bb[0] - PAD * pitch
    bb_max = bb[1] + PAD * pitch
    sizes  = np.ceil((bb_max - bb_min) / pitch).astype(int) + 1
    nx, ny, nz = int(sizes[0]), int(sizes[1]), int(sizes[2])

    if nx * ny * nz > 50_000_000:
        return None

    x_c = bb_min[0] + (np.arange(nx) + 0.5) * pitch
    y_c = bb_min[1] + (np.arange(ny) + 0.5) * pitch
    xx, yy = np.meshgrid(x_c, y_c, indexing='ij')
    n_rays = nx * ny

    z_start = float(bb_min[2] - pitch)
    ray_ori = np.column_stack([xx.ravel(), yy.ravel(), np.full(n_rays, z_start)])
    ray_dir = np.zeros((n_rays, 3), dtype=np.float64)
    ray_dir[:, 2] = 1.0

    try:
        hit_locs, hit_ray_ids, _ = mesh.ray.intersects_location(
            ray_origins    = ray_ori,
            ray_directions = ray_dir,
            multiple_hits  = True,
        )
    except Exception:
        logger.warning("Raycast voxelisation échoué")
        return None

    if len(hit_locs) == 0:
        return None

    grid = np.zeros((nx, ny, nz), dtype=bool)

    sort_idx   = np.argsort(hit_ray_ids)
    sorted_ids = hit_ray_ids[sort_idx]
    sorted_z   = hit_locs[sort_idx, 2]

    boundaries = np.concatenate(
        [[0], np.where(np.diff(sorted_ids))[0] + 1, [len(sorted_ids)]]
    )

    for k in range(len(boundaries) - 1):
        s, e   = int(boundaries[k]), int(boundaries[k + 1])
        ray_id = int(sorted_ids[s])
        ix     = ray_id // ny
        iy     = ray_id % ny

        z_hits = np.sort(sorted_z[s:e])

        for m in range(0, len(z_hits) - 1, 2):
            z0, z1 = z_hits[m], z_hits[m + 1]
            iz0 = max(0,      int(np.floor((z0 - bb_min[2]) / pitch)))
            iz1 = min(nz - 1, int(np.ceil ((z1 - bb_min[2]) / pitch)))
            if iz0 <= iz1:
                grid[ix, iy, iz0 : iz1 + 1] = True

    if int(grid.sum()) < 5:
        return None

    return grid, bb_min


# ── Fallback : raycast multi-directionnel ─────────────────────────────────────

def _detect_raycast(
    mesh: trimesh.Trimesh,
    n_samples: int,
    min_thickness_mm: float,
    sig_t0: float = _F_SIG_T0 * _DEFAULT_NOZZLE_MM,
    spike_threshold_mm: float = _F_SPIKE * _DEFAULT_NOZZLE_MM,
) -> FragilityResult:
    """Méthode de secours si la voxelisation échoue.

    Lance des rayons depuis la surface pour mesurer l'épaisseur locale.
    Collecte toutes les mesures et applique la sigmoïde pour la sévérité continue.
    """
    sample_pts, face_idx = trimesh.sample.sample_surface(mesh, count=n_samples)
    normals = mesh.face_normals[face_idx]
    n       = len(sample_pts)

    fragile_zones: list[Zone3D]   = []
    all_thicknesses: list[float]  = []
    min_t = 99.0

    # Mesure par rayon normal inversé (épaisseur dans la direction normale)
    try:
        hits, ray_ids, _ = mesh.ray.intersects_location(
            ray_origins    = sample_pts + normals * 0.01,
            ray_directions = -normals,
            multiple_hits  = False,
        )
        for hp, ridx in zip(hits, ray_ids):
            t = float(np.linalg.norm(hp - sample_pts[ridx]))
            all_thicknesses.append(t)
            if t < min_t:
                min_t = t
            if t < min_thickness_mm:
                fragile_zones.append(Zone3D(
                    point=sample_pts[ridx].tolist(),
                    thickness_mm=round(t, 3),
                    severity=round(float(_t_to_sev(t, sig_t0)), 3),
                ))
    except Exception:
        logger.warning("Raycast normal échoué dans fallback")

    # Mesures cross-section (détection des spikes et épines)
    interior = sample_pts - normals * 0.15
    for ax in range(2):
        for sign in (1.0, -1.0):
            d = np.zeros(3); d[ax] = sign
            try:
                hits_ax, ids_ax, _ = mesh.ray.intersects_location(
                    ray_origins    = interior,
                    ray_directions = np.tile(d, (n, 1)),
                    multiple_hits  = False,
                )
                for hp, ridx in zip(hits_ax, ids_ax):
                    cross = float(np.linalg.norm(hp - interior[ridx])) + 0.15
                    all_thicknesses.append(cross)
                    if cross < min_t:
                        min_t = cross
                    if cross < spike_threshold_mm:
                        fragile_zones.append(Zone3D(
                            point=sample_pts[ridx].tolist(),
                            thickness_mm=round(cross, 3),
                            severity=round(float(_t_to_sev(cross, sig_t0)), 3),
                        ))
            except Exception:
                logger.debug(f"Raycast cross-section ax={ax} sign={sign} échoué")
                continue

    # Score global : blend P50/P10 de l'épaisseur (cohérent avec la méthode EDT)
    if all_thicknesses:
        t_arr  = np.array(all_thicknesses, dtype=np.float64)
        p50_t  = float(np.percentile(t_arr, 50))
        p10_t  = float(np.percentile(t_arr, 10))
        global_sev = float(np.clip(
            0.5 * float(_t_to_sev(p50_t, sig_t0)) + 0.5 * float(_t_to_sev(p10_t, sig_t0)),
            0.0, 1.0,
        ))
    else:
        global_sev = 0.0

    return FragilityResult(
        has_fragile_zones=len(fragile_zones) > 0,
        fragile_zones=fragile_zones[:50],
        min_thickness_mm=min_t if min_t < 99 else 0.0,
        severity=global_sev,
    )
