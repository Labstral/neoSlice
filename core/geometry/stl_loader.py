from __future__ import annotations
import time
from pathlib import Path

import numpy as np
import trimesh
from loguru import logger


class STLLoadError(Exception):
    pass


# fill_holes est extrêmement lent sur les maillages complexes non-watertight.
# On le saute dès 100k faces. process=False (pas de merge_vertices) seulement
# au-dessus de 1M faces — en dessous la topologie doit rester correcte pour l'analyse.
_FACE_SKIP_FILL_HOLES = 100_000
_FACE_SKIP_PROCESS    = 1_000_000


def _estimate_stl_faces(path: Path) -> int:
    """Estime le nombre de faces d'un fichier STL binaire via sa taille."""
    try:
        size = path.stat().st_size
        # Format binaire : 80 header + 4 count + N*50 bytes
        if size > 84:
            return int((size - 84) / 50)
    except Exception:
        pass
    return 0


def load_stl(path: Path) -> trimesh.Trimesh:
    """Charge, valide et normalise un fichier STL.

    Retourne un Trimesh centré sur l'origine, orienté avec Z vers le haut,
    posé sur le plan Z=0.
    """
    t0 = time.perf_counter()
    logger.info(f"Chargement STL : {path.name}")

    if not path.exists():
        raise STLLoadError(f"Fichier introuvable : {path.name}")
    if path.suffix.lower() not in (".stl", ".obj", ".3mf"):
        raise STLLoadError(f"Format non supporté : {path.suffix}")

    # Estimation avant chargement — adapte le niveau de traitement à la taille
    _is_stl = path.suffix.lower() == ".stl"
    _estimated_faces = _estimate_stl_faces(path) if _is_stl else 0
    _skip_process    = _estimated_faces > _FACE_SKIP_PROCESS
    _skip_fill_holes = _estimated_faces > _FACE_SKIP_FILL_HOLES
    if _skip_process:
        logger.info(
            f"Mesh très grand (~{_estimated_faces:,} faces) — "
            "chargement rapide sans réparations (process=False)."
        )
    elif _skip_fill_holes:
        logger.info(
            f"Mesh large (~{_estimated_faces:,} faces) — "
            "fill_holes désactivé."
        )

    if path.suffix.lower() == ".3mf":
        raw = trimesh.load(str(path))
    elif _skip_process:
        # process=False seulement pour les très grands meshes (> 1M faces) :
        # évite merge_vertices sur 10M+ vertices (prend des minutes).
        raw = trimesh.load(str(path), force="mesh", process=False)
    else:
        raw = trimesh.load(str(path), force="mesh")

    # Si la scène contient plusieurs objets, on les fusionne
    if isinstance(raw, trimesh.Scene):
        meshes = [g for g in raw.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise STLLoadError("Aucun mesh valide trouvé dans le fichier.")
        mesh = trimesh.util.concatenate(meshes)
        logger.warning(f"Scène multi-objets fusionnée ({len(meshes)} objets).")
    elif isinstance(raw, trimesh.Trimesh):
        mesh = raw
    else:
        raise STLLoadError("Format de fichier non reconnu.")

    if len(mesh.faces) == 0:
        raise STLLoadError("Le mesh est vide (aucune face).")

    if not _skip_process:
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fix_winding(mesh)
        if not _skip_fill_holes and not mesh.is_watertight:
            logger.info("Mesh non-watertight — réparation automatique...")
            trimesh.repair.fill_holes(mesh)
        mesh.merge_vertices(merge_tex=False)
        unique_mask = trimesh.triangles.area(mesh.triangles) > 1e-10
        if not unique_mask.all():
            mesh.update_faces(unique_mask)
            logger.info(f"Faces dégénérées supprimées : {(~unique_mask).sum()}")

    if len(mesh.faces) == 0:
        raise STLLoadError("Le mesh est vide après réparation (aucune face valide).")

    # ── Détection et correction des unités ──────────────────────────────────
    # STL n'encode pas les unités. Si les coordonnées semblent être en mètres
    # (max extent < 1.0) mais auraient du sens en mm (×1000 → 1–500 mm),
    # on corrige automatiquement. Ce n'est pas un redimensionnement géométrique
    # mais une correction d'unité (cas typique : export Fusion 360 en mètres).
    _max_extent = float(mesh.bounding_box.extents.max())
    if _max_extent < 1.0:
        _scaled_mm = _max_extent * 1000.0
        if 1.0 <= _scaled_mm <= 500.0:
            mesh.apply_scale(1000.0)
            logger.warning(
                f"STL en mètres détecté (max extent = {_max_extent:.4f} m) — "
                f"converti automatiquement en mm (×1000 → {_scaled_mm:.1f} mm)."
            )
        else:
            logger.warning(
                f"Pièce très petite détectée (max extent = {_max_extent:.4f} mm). "
                f"Vérifier les unités dans le logiciel source."
            )
    elif _max_extent > 500.0:
        logger.warning(
            f"Pièce très grande détectée (max extent = {_max_extent:.1f} mm). "
            f"Le STL est peut-être exporté dans une unité non-mm."
        )

    # Normalisation : poser sur Z=0, centrer sur XY
    mesh.apply_translation(-mesh.bounds[0])               # coin min → origine
    center_xy = [(mesh.bounds[1][0]) / 2, (mesh.bounds[1][1]) / 2, 0]
    mesh.apply_translation([-center_xy[0], -center_xy[1], 0])

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        f"STL chargé en {elapsed:.1f}ms — "
        f"{len(mesh.vertices)} vertices, {len(mesh.faces)} faces, "
        f"watertight={mesh.is_watertight}"
    )
    return mesh


def mesh_info(mesh: trimesh.Trimesh) -> dict:
    """Retourne un dict de métadonnées rapides sur le mesh."""
    bb = mesh.bounding_box.extents
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "bounding_box_mm": bb.tolist(),
        "volume_cm3": abs(mesh.volume) / 1000,
        "surface_area_cm2": mesh.area / 100,
        "is_watertight": mesh.is_watertight,
    }
