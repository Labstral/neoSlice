# -*- coding: utf-8 -*-
"""neoGen — utilitaires géométrie communs (PROTOTYPE ISOLÉ, hors neoSlice).

`union_solides` : fusion booléenne RÉELLE (manifold3d) au lieu d'une simple
concaténation. Indispensable : la concaténation laisse des FACES INTERNES
orientées vers le bas (dessous du texte enfoui dans le socle) que l'analyse
de surplombs prend pour des surplombs fantômes. L'union vraie produit UN
solide étanche sans face interne -> analyse propre, impression propre.
"""
from __future__ import annotations

import trimesh


def union_solides(solides: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    """Union booléenne réelle des volumes (engine manifold). En cas d'échec
    (géométrie dégénérée), repli sur la concaténation (moins propre mais
    jamais bloquant)."""
    solides = [s for s in solides if s is not None and len(s.faces)]
    if not solides:
        raise ValueError("Aucun solide à fusionner.")
    if len(solides) == 1:
        return solides[0]
    try:
        piece = trimesh.boolean.union(solides, engine="manifold")
        if isinstance(piece, (list, tuple)):
            piece = trimesh.util.concatenate(piece)
        if piece.is_watertight:
            return piece            # union saine -> NE PAS y toucher
        # Union imparfaite : tentative de reparation (purge des lamelles
        # degenerees puis re-soudure). On ne garde que si ca la rend etanche.
        repare = piece.copy()
        repare.update_faces(repare.nondegenerate_faces(height=1e-6))
        repare.merge_vertices()
        repare.remove_unreferenced_vertices()
        if repare.is_watertight:
            return repare
    except Exception:
        pass
    return trimesh.util.concatenate(solides)
