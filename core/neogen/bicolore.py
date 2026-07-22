# -*- coding: utf-8 -*-
"""neoGen — BICOLORE : socle (couleur objet) + texte (couleur texte) en 2 corps.

Cœur PARTAGÉ par tous les objets à texte : à partir du socle 2D et du texte 2D
(ce que la plupart des builders ont déjà sous la main), produit deux corps
distincts et colorés selon le STYLE :
  • relief : le texte SAILLE de `ep_texte` au-dessus du socle plein ;
  • lisse  : le texte AFFLEURE (surface parfaitement lisse, distinction par la
             couleur seule — nécessite l'impression bicolore) ;
  • grave  : le texte est EN CREUX de ~0.6 mm sous la surface (sillon tactile).

La Scene à 2 corps est routée automatiquement en multicouleur (2 slots à
l'export) — voir core.neogen.catalogue.est_multicouleur.
"""
from __future__ import annotations

import trimesh
from shapely.geometry import MultiPolygon

_GROOVE = 0.6         # profondeur du sillon en mode « gravé » (mm)


def _hex_rgba(h: str) -> list[int]:
    h = (h or "#CCCCCC").lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255]


def _extrude_multi(poly, hauteur: float, z0: float) -> trimesh.Trimesh:
    """Extrude un (Multi)Polygon shapely en un corps, posé à z0."""
    geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    parts = [trimesh.creation.extrude_polygon(g, hauteur)
             for g in geoms if not g.is_empty]
    m = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    m.apply_translation((0, 0, z0))
    return m


def socle_texte(socle_2d, texte_2d, ep_socle: float, ep_texte: float,
                style: str = "relief", chevauchement: float = 0.2):
    """(socle 2D, texte 2D, épaisseurs, style) → (corps_socle, corps_texte) Trimesh
    NON colorés. `union_solides` (booléen réel) pour un socle étanche."""
    from core.neogen.geo_utils import union_solides
    style = style if style in ("relief", "grave", "lisse") else "relief"
    ep_texte = max(0.4, float(ep_texte))
    if style == "relief":
        socle = union_solides([_extrude_multi(socle_2d, ep_socle, 0.0)])
        texte = _extrude_multi(texte_2d, ep_texte + chevauchement,
                               ep_socle - chevauchement)
        return socle, texte
    # grave / lisse : le socle porte des ALVÉOLES là où va le texte
    ep_texte = min(ep_texte, ep_socle - 0.4)
    z_base = max(0.4, ep_socle - ep_texte)
    slab = _extrude_multi(socle_2d, z_base, 0.0)                  # dalle pleine
    murs = _extrude_multi(socle_2d.difference(texte_2d),          # grille autour du texte
                          ep_socle - z_base, z_base)
    socle = union_solides([slab, murs])
    h_txt = (ep_socle - z_base) - (_GROOVE if style == "grave" else 0.0)
    texte = _extrude_multi(texte_2d, max(0.4, h_txt), z_base)
    return socle, texte


def texte_cylindrique(text_2d, rayon: float, hauteur_relief: float = 1.0,
                      chevauchement: float = 0.25, subdiv: float = 1.2):
    """Enroule un texte 2D (centré ; x = circonférence, y = axe Z) sur la SURFACE
    d'un cylindre de rayon `rayon` (axe Z), en relief vers l'extérieur. Le maillage
    plat est subdivisé puis ses sommets sont mappés sur le cylindre → le texte
    épouse vraiment l'arrondi. Reste solidaire (chevauche la paroi de `chevauchement`)."""
    import numpy as np
    flat = _extrude_multi(text_2d, hauteur_relief + chevauchement, 0.0)
    try:
        flat = flat.subdivide_to_size(max(0.6, subdiv))
    except Exception:
        pass
    v = flat.vertices.copy()
    u, y, w = v[:, 0], v[:, 1], v[:, 2]          # w ∈ [0, relief+chev]
    r = rayon - chevauchement + w                # paroi ↔ sommet du relief
    theta = u / rayon                            # longueur d'arc → angle
    flat.vertices = np.column_stack([r * np.cos(theta), r * np.sin(theta), y])
    try:
        flat.fix_normals()
    except Exception:
        pass
    return flat


def scene(corps_socle, corps_texte, couleur_objet: str, couleur_texte: str
          ) -> trimesh.Scene:
    """2 corps colorés → Scene bicolore (routée en multicouleur : 2 slots export)."""
    a = corps_socle.copy(); a.visual.face_colors = _hex_rgba(couleur_objet)
    b = corps_texte.copy(); b.visual.face_colors = _hex_rgba(couleur_texte)
    s = trimesh.Scene()
    s.add_geometry(a, geom_name="objet")
    s.add_geometry(b, geom_name="texte")
    return s


def scene_socle_texte(socle_2d, texte_2d, ep_socle, ep_texte, style,
                      couleur_objet, couleur_texte, chevauchement=0.2,
                      origine_sol: bool = True) -> trimesh.Scene:
    """Raccourci : socle_2d + texte_2d → Scene bicolore prête (origine au sol)."""
    a, b = socle_texte(socle_2d, texte_2d, ep_socle, ep_texte, style, chevauchement)
    s = scene(a, b, couleur_objet, couleur_texte)
    if origine_sol:
        import trimesh as _tm
        fus = _tm.util.concatenate(list(s.geometry.values()))
        off = -fus.bounds[0]
        for g in s.geometry.values():
            g.apply_translation(off)
    return s
