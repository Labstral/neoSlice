"""Moteur d'analyse par couches — simulation d'un slicer FDM basique.

Inspiré de l'approche PrusaSlicer / BambuStudio :
  Au lieu d'analyser les normales de faces (heuristique imprécise), on coupe
  le mesh en tranches horizontales et on compare couche par couche, exactement
  comme le fait un vrai slicer.

Algorithmes :
  1. SURPLOMBS  — différence ensembliste entre couche N et couche N-1 élargie
                  du seuil angulaire (45° par défaut = même règle que Bambu Studio).
                  → Élimine les faux positifs sur surfaces texturées.

  2. RÉGIONS FLOTTANTES — couche sans aucun contact avec les couches inférieures
                  (îlots non connectés au reste de la pièce).

  3. STABILITÉ  — empreinte réelle (polygone shapely) + projection CDM +
                  ratio hauteur/largeur d'empreinte effective.

  4. ÉPAISSEUR  — érosion binaire par bissection sur chaque couche N/ième
                  (1 couche sur N_WALL_SAMPLE), minimum global.

  5. VOLUME SUPPORT estimé — intégrale des zones en surplomb × hauteur couche.

Complexité : O(n_layers × shapely_ops) ≈ 1-6 s pour 100-200 couches.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
import trimesh
from loguru import logger

# ── Shapely (obligatoire pour les opérations de polygones 2D) ──────────────
try:
    from shapely.geometry import MultiPolygon, Point, Polygon
    from shapely.ops import unary_union
    from shapely.validation import make_valid
    _SHAPELY = True
except ImportError:
    _SHAPELY = False
    logger.warning("shapely non disponible — layer_slicer désactivé")

# ── Constantes ────────────────────────────────────────────────────────────────
_OVERHANG_ANGLE_DEG  = 45.0   # angle seuil Bambu Studio par défaut
_N_LAYERS_TARGET     = 150    # nombre de tranches d'analyse
_N_WALL_SAMPLE       = 6      # 1 couche sur N pour le calcul d'épaisseur
_WALL_SEARCH_MIN     = 0.2    # mm — limite basse épaisseur paroi
_WALL_SEARCH_MAX     = 30.0   # mm — limite haute épaisseur paroi
_WALL_SEARCH_ITERS   = 12     # itérations de bissection (précision ≈ 0.03 mm)
_FLOAT_DIST_FACTOR   = 3.0    # × threshold pour détecter les régions flottantes
_SECTION_TIMEOUT_S   = 8.0    # abandon si la section d'une couche prend trop longtemps


@dataclass
class LayerSliceResult:
    """Résultat de l'analyse complète par couches."""

    # ── Surplombs ──────────────────────────────────────────────────────────
    overhang_severity: float = 0.0        # 0=aucun → 1=extrême
    overhang_ratio: float = 0.0           # fraction de surface en surplomb
    projected_overhang_ratio: float = 0.0 # fraction XY en surplomb (pour support vol)
    has_floating_regions: bool = False
    max_overhang_angle_deg: float = 0.0   # angle max estimé

    # ── Stabilité ──────────────────────────────────────────────────────────
    stability_score: float = 0.5
    footprint_area_mm2: float = 0.0
    brim_recommendation_mm: float = 0.0
    is_top_heavy: bool = False
    center_of_mass: list = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # ── Épaisseur / fragilité ──────────────────────────────────────────────
    min_wall_thickness_mm: float = 99.0
    fragility_severity: float = 0.0
    has_fragile_zones: bool = False

    # ── Volume support ──────────────────────────────────────────────────────
    support_volume_ratio: float = 0.0
    support_needed: bool = False

    # ── Méta ───────────────────────────────────────────────────────────────
    layer_count: int = 0
    layer_pitch_mm: float = 0.0
    analysis_time_ms: float = 0.0
    fallback_used: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────────

def analyze_by_layers(
    mesh: trimesh.Trimesh,
    nozzle_diameter_mm: float = 0.4,
    overhang_angle_deg: float = _OVERHANG_ANGLE_DEG,
) -> LayerSliceResult:
    """Analyse complète d'un mesh par simulation de couches FDM.

    Remplace analyze_overhangs + analyze_stability + detect_fragility en un
    seul passage plus précis et plus rapide (pas de faux positifs sur textures).
    """
    if not _SHAPELY:
        return LayerSliceResult(fallback_used=True)

    t0 = time.perf_counter()

    z_min = float(mesh.bounds[0][2])
    z_max = float(mesh.bounds[1][2])
    height = z_max - z_min

    if height < 0.5:
        logger.warning("Mesh trop plat pour l'analyse par couches — fallback stabilité directe.")
        # Pièce quasi-plate : très stable sur le plateau
        r = LayerSliceResult(fallback_used=True)
        try:
            from scipy.spatial import ConvexHull
            from scipy.spatial.qhull import QhullError
            ground_verts = mesh.vertices[mesh.vertices[:, 2] <= float(mesh.bounds[0][2]) + height * 0.2]
            if len(ground_verts) >= 3:
                hull = ConvexHull(ground_verts[:, :2])
                fp_area = float(hull.volume)
                bb_xy = float(mesh.bounding_box.extents[0]) * float(mesh.bounding_box.extents[1])
                fill = fp_area / bb_xy if bb_xy > 1e-6 else 0.5
                r.stability_score = float(np.clip(0.70 + fill * 0.30, 0.0, 1.0))
            else:
                r.stability_score = 0.85
        except Exception:
            r.stability_score = 0.85
        com = mesh.center_mass
        r.center_of_mass = com.tolist()
        b = mesh.bounds
        r.footprint_area_mm2 = float((b[1][0] - b[0][0]) * (b[1][1] - b[0][1]))
        return r

    # ── Pitch d'analyse : vise _N_LAYERS_TARGET couches ────────────────────
    # Limite à 100 couches pour les très grandes pièces (>20s sinon)
    n_layers_target = min(_N_LAYERS_TARGET, max(30, int(3000 / (height + 1))))
    pitch = max(0.3, height / n_layers_target)
    n_layers = max(10, int(height / pitch))
    pitch = height / n_layers  # recalcul exact

    # Hauteurs de coupe (évite les bords exacts pour les meshes non-watertight)
    z_levels = z_min + pitch * (np.arange(n_layers) + 0.5)

    result = LayerSliceResult(layer_count=n_layers, layer_pitch_mm=pitch)

    # ── Couper le mesh en une seule passe ──────────────────────────────────
    try:
        sections = mesh.section_multiplane(
            plane_origin=[0.0, 0.0, 0.0],
            plane_normal=[0.0, 0.0, 1.0],
            heights=z_levels,
        )
    except Exception as exc:
        logger.warning(f"section_multiplane échoué : {exc}")
        result.fallback_used = True
        return result

    # ── Convertir chaque section en géométrie shapely ──────────────────────
    # Simplifier les polygones complexes pour accélérer les opérations buffer/diff.
    # Tolérance 0.3mm : invisible sur les résultats mais divise par 3-5 le nb de sommets.
    _SIMPLIFY_TOL = 0.3
    layer_geoms: list[tuple[float, object]] = []  # (z, shapely_geom | None)
    for z, sec in zip(z_levels, sections):
        geom = _section_to_shapely(sec)
        if geom is not None and geom.length > 400:
            # Polygone complexe : simplifier avant les opérations shapely
            simplified = geom.simplify(_SIMPLIFY_TOL, preserve_topology=True)
            if not simplified.is_empty:
                geom = simplified
        layer_geoms.append((z, geom))

    valid_count = sum(1 for _, g in layer_geoms if g is not None)
    if valid_count < 2:
        logger.warning("Moins de 2 couches valides — mesh dégénéré ou vide.")
        result.fallback_used = True
        return result

    # ── Analyse couche par couche ──────────────────────────────────────────
    overhang_threshold = pitch / math.tan(math.radians(overhang_angle_deg))
    float_threshold = overhang_threshold * _FLOAT_DIST_FACTOR

    total_area = 0.0
    total_overhang_area = 0.0
    total_projected_ov = 0.0
    floating_layers = 0
    min_wall = _WALL_SEARCH_MAX
    wall_sample_idx = 0

    prev_geom = None
    prev_valid_z = None

    for i, (z, geom) in enumerate(layer_geoms):
        if geom is None:
            prev_geom = None
            prev_valid_z = None
            continue

        area = geom.area
        total_area += area

        # ── Surplomb par rapport à la couche précédente ───────────────────
        if prev_geom is None:
            overhang_area = 0.0
            # Région flottante : couche qui démarre en l'air
            if z > z_min + pitch * 2.5:
                floating_layers += 1
                result.has_floating_regions = True
        else:
            # Zone supportée = couche précédente dilatée du seuil angulaire
            try:
                supported = prev_geom.buffer(overhang_threshold, resolution=8)
                overhang_geom = geom.difference(supported)
                overhang_area = 0.0 if overhang_geom.is_empty else overhang_geom.area

                # Région flottante : couche complètement hors de portée
                if geom.disjoint(prev_geom.buffer(float_threshold, resolution=4)):
                    floating_layers += 1
                    result.has_floating_regions = True
            except Exception:
                overhang_area = 0.0

        total_overhang_area += overhang_area
        if area > 1e-6:
            total_projected_ov += min(1.0, overhang_area / area) * area

        # ── Épaisseur de paroi (échantillon 1/N_WALL_SAMPLE) ──────────────
        wall_sample_idx += 1
        if wall_sample_idx % _N_WALL_SAMPLE == 0:
            w = _min_wall_thickness(geom)
            if w < min_wall:
                min_wall = w

        prev_geom = geom
        prev_valid_z = z

    # ── Calcul de la couche sol (empreinte pour stabilité) ─────────────────
    ground_geoms = [g for z, g in layer_geoms if z <= z_min + pitch * 3 and g is not None]

    # ── Agrégation des résultats ───────────────────────────────────────────
    _compute_overhang_metrics(result, total_area, total_overhang_area,
                               total_projected_ov, pitch, mesh)
    _compute_stability(result, mesh, ground_geoms, height)
    _compute_fragility(result, min_wall, nozzle_diameter_mm)
    _compute_support_volume(result, total_overhang_area, total_area, pitch, mesh)

    result.analysis_time_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        f"Analyse couches : {n_layers} couches × {pitch:.2f}mm | "
        f"surplomb={result.overhang_severity:.0%} | "
        f"stabilité={result.stability_score:.0%} | "
        f"paroi_min={result.min_wall_thickness_mm:.1f}mm | "
        f"{result.analysis_time_ms:.0f}ms"
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────────────────────────────────────

def _section_to_shapely(section) -> "Polygon | MultiPolygon | None":
    """Convertit une section trimesh Path2D en géométrie shapely."""
    if section is None:
        return None
    try:
        polys = section.polygons_full
        if not polys:
            return None
        geom = unary_union([make_valid(p) for p in polys if p is not None and not p.is_empty])
        return geom if not geom.is_empty else None
    except Exception:
        return None


def _min_wall_thickness(geom: "Polygon | MultiPolygon") -> float:
    """Épaisseur minimale de paroi par érosion bissection (shapely buffer négatif).

    Principe : si on érode de -d/2, le polygone disparaît quand d < épaisseur_min.
    Bissection pour trouver ce seuil avec précision ≈ 0.03 mm.
    """
    if geom is None or geom.is_empty:
        return _WALL_SEARCH_MAX

    try:
        # Vérifie d'abord si la pièce est globalement fine
        lo = _WALL_SEARCH_MIN / 2
        hi = _WALL_SEARCH_MAX / 2

        # Borne haute : érosion maximale (évite de chercher trop loin)
        test_hi = geom.buffer(-hi)
        if not test_hi.is_empty:
            return _WALL_SEARCH_MAX  # parois très épaisses

        for _ in range(_WALL_SEARCH_ITERS):
            mid = (lo + hi) / 2
            eroded = geom.buffer(-mid)
            if eroded.is_empty:
                hi = mid
            else:
                lo = mid

        return float((lo + hi))  # diamètre ≈ 2 × rayon d'érosion
    except Exception:
        return _WALL_SEARCH_MAX


def _compute_overhang_metrics(
    result: LayerSliceResult,
    total_area: float,
    total_overhang_area: float,
    total_projected_ov: float,
    pitch: float,
    mesh: trimesh.Trimesh,
) -> None:
    """Calcule les métriques de surplomb normalisées."""
    if total_area < 1e-6:
        return

    ratio = total_overhang_area / total_area
    result.overhang_ratio = float(np.clip(ratio, 0.0, 1.0))
    result.projected_overhang_ratio = float(np.clip(total_projected_ov / total_area, 0.0, 1.0))

    # Sévérité : sigmoïde centrée sur 25% de surplomb (empirique FDM)
    # 0% surplomb → 0.0  |  25% → 0.5  |  60%+ → ~1.0
    k = 8.0
    t0 = 0.22
    severity = 1.0 / (1.0 + math.exp(-k * (ratio - t0)))
    severity = max(0.0, (severity - 1.0 / (1.0 + math.exp(k * t0))) )
    result.overhang_severity = float(np.clip(severity, 0.0, 1.0))

    # Angle max estimé à partir du ratio (heuristique géométrique)
    if ratio > 0.01:
        result.max_overhang_angle_deg = float(min(89.0, math.degrees(math.asin(min(0.99, ratio * 2)))))


def _compute_stability(
    result: LayerSliceResult,
    mesh: trimesh.Trimesh,
    ground_geoms: list,
    height: float,
) -> None:
    """Stabilité basée sur l'empreinte réelle et la projection du CDM."""
    if not ground_geoms:
        result.stability_score = 0.1
        result.brim_recommendation_mm = 10.0
        return

    try:
        footprint = unary_union(ground_geoms)
        footprint = make_valid(footprint)
        footprint_area = footprint.area
        result.footprint_area_mm2 = float(footprint_area)

        com = mesh.center_mass
        result.center_of_mass = com.tolist()
        com_pt = Point(float(com[0]), float(com[1]))

        # Utiliser la coque convexe de l'empreinte pour le test de basculement.
        # Physique correcte : une pièce est stable si son CDM projeté est dans
        # l'enveloppe convexe des points de contact (ex: cadre, anneau, 4 pieds
        # → stable même si le CDM est au-dessus du vide intérieur).
        footprint_hull = footprint.convex_hull
        hull_area = footprint_hull.area if not footprint_hull.is_empty else footprint_area

        inside = footprint_hull.contains(com_pt)

        if not inside:
            base_score = 0.05
        else:
            # Marge CDM → bord de la coque convexe
            dist_edge = footprint_hull.boundary.distance(com_pt)
            char_r = math.sqrt(hull_area / math.pi) if hull_area > 1e-6 else 1.0
            base_score = float(np.clip(dist_edge / max(char_r, 1.0), 0.0, 1.0))

        # ── Pénalité : empreinte convexe vs boîte englobante ────────────────
        # Pénalise les bases réellement minuscules (figurines, pièces coniques),
        # PAS les pièces creuses ou à pieds dont la coque convexe est grande.
        bb_xy = float(mesh.bounding_box.extents[0]) * float(mesh.bounding_box.extents[1])
        if bb_xy > 1e-6:
            hull_fill = hull_area / bb_xy
            if hull_fill < 0.08:
                base_score *= 0.20   # base quasi-ponctuelle (pointe, figurine)
            elif hull_fill < 0.20:
                base_score *= 0.45
            elif hull_fill < 0.40:
                base_score *= 0.70

        # ── Pénalité : ratio hauteur / largeur effective ────────────────────
        eff_width = math.sqrt(footprint_area) if footprint_area > 1e-6 else 1.0
        h_ratio = height / max(eff_width, 1.0)
        if h_ratio > 4.0:
            base_score *= 0.30
        elif h_ratio > 3.0:
            base_score *= 0.45
        elif h_ratio > 2.0:
            base_score *= 0.65
        elif h_ratio > 1.5:
            base_score *= 0.85

        # ── Pénalité : pièce top-heavy ──────────────────────────────────────
        z_min = float(mesh.bounds[0][2])
        is_top_heavy = float(com[2]) > (z_min + height * 0.60)
        result.is_top_heavy = is_top_heavy
        if is_top_heavy:
            base_score *= 0.80

        result.stability_score = float(np.clip(base_score, 0.0, 1.0))

        # Recommandation brim
        s = result.stability_score
        if s < 0.25:
            result.brim_recommendation_mm = 10.0
        elif s < 0.45:
            result.brim_recommendation_mm = 6.0
        elif s < 0.60:
            result.brim_recommendation_mm = 4.0

    except Exception as exc:
        logger.warning(f"Calcul stabilité échoué : {exc}")
        result.stability_score = 0.3
        result.brim_recommendation_mm = 6.0


def _compute_fragility(
    result: LayerSliceResult,
    min_wall: float,
    nozzle_mm: float,
) -> None:
    """Sévérité de fragilité basée sur l'épaisseur minimale de paroi."""
    result.min_wall_thickness_mm = float(np.clip(min_wall, 0.0, _WALL_SEARCH_MAX))

    # Seuil sûr = 3 passages de buse (même règle que fragility_detector.py)
    safe_threshold = 3.0 * nozzle_mm    # ex: 1.2 mm pour buse 0.4 mm
    sig_center = 2.0 * nozzle_mm        # centre sigmoïde : 2×buse = 50 % sévérité
    k = 3.0                             # pente plus raide pour une discrimination nette

    if min_wall >= _WALL_SEARCH_MAX * 0.9:
        # N'a pas été mesuré (toutes les couches épaisses) → pas fragile
        result.fragility_severity = 0.0
        result.has_fragile_zones = False
        return

    sev = 1.0 / (1.0 + math.exp(k * (min_wall - sig_center)))
    result.fragility_severity = float(np.clip(sev, 0.0, 1.0))
    result.has_fragile_zones = min_wall < safe_threshold


def _compute_support_volume(
    result: LayerSliceResult,
    total_overhang_area: float,
    total_area: float,
    pitch: float,
    mesh: trimesh.Trimesh,
) -> None:
    """Estime le ratio de volume de support nécessaire."""
    # Volume support ≈ Σ(overhang_area_i) × pitch × densité_support (30%)
    support_vol_mm3 = total_overhang_area * pitch * 0.30

    mesh_vol = abs(float(mesh.volume)) if abs(float(mesh.volume)) > 1e-6 else 1.0
    ratio = support_vol_mm3 / mesh_vol
    result.support_volume_ratio = float(np.clip(ratio, 0.0, 1.0))
    result.support_needed = (
        result.has_floating_regions
        or result.overhang_severity > 0.005
        or result.support_volume_ratio > 0.005
    )
