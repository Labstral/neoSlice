from __future__ import annotations
import time
from pathlib import Path

import numpy as np
import trimesh
from loguru import logger


class STLLoadError(Exception):
    pass


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

    # force="mesh" fonctionne pour STL/OBJ mais peut échouer sur 3MF (scènes complexes)
    if path.suffix.lower() == ".3mf":
        raw = trimesh.load(str(path))
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

    # Réparations automatiques — toujours appliquées
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fix_winding(mesh)
    if not mesh.is_watertight:
        logger.info("Mesh non-watertight — réparation automatique...")
        trimesh.repair.fill_holes(mesh)
    # Fusion des vertices très proches (artefacts export CAO)
    mesh.merge_vertices(merge_tex=False)
    unique_mask = trimesh.triangles.area(mesh.triangles) > 1e-10
    if not unique_mask.all():
        mesh.update_faces(unique_mask)
        logger.info(f"Faces dégénérées supprimées : {(~unique_mask).sum()}")

    if len(mesh.faces) == 0:
        raise STLLoadError("Le mesh est vide après réparation (aucune face valide).")

    # ── Vérification des unités (avertissement uniquement, jamais de rescale) ──
    # STL n'encode pas les unités. neoSlice ne redimensionne JAMAIS la pièce
    # pour garantir la fidélité dimensionnelle. Si les dimensions semblent
    # anormales, on log un avertissement pour le débogage.
    _max_extent = float(mesh.bounding_box.extents.max())
    if _max_extent < 1.0:
        logger.warning(
            f"Pièce très petite détectée (max extent = {_max_extent:.4f} mm). "
            f"Le STL est peut-être exporté en mètres — vérifier les unités dans le logiciel source."
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
