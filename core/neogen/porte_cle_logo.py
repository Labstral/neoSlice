# -*- coding: utf-8 -*-
"""Porte-clé À PARTIR D'UN LOGO (SVG/PNG).

FORME (contour du porte-clé) :
  • contour  : suit les courbes du logo (offset lissé, trous remplis)
  • ovale / rectangle / rond / etiquette : plaque géométrique contenant le logo

STYLE (rendu du logo) :
  • lisse  : découpe — le logo est AJOURÉ dans la forme (silhouette / openwork)
  • relief : logo surélevé sur la forme
  • grave  : logo creusé dans la forme

Contour lissé via buffer shapely (aucun bord denté), trous remplis pour un dos
propre. Anneau (avec trou) soudé en haut.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon, MultiPolygon, box, Point
from shapely.affinity import scale as _scale, translate as _translate
from shapely.ops import unary_union

from core.neogen import logo as _L
from core.neogen.geo_utils import union_solides
from core.neogen.bicolore import _hex_rgba


def _colorier(m, hexc):
    m.visual.face_colors = _hex_rgba(hexc)
    return m


def _shape_2d(chemin: str, largeur: float):
    src = str(chemin)
    couches = (_L.charger_svg(src) if src.lower().endswith(".svg")
               else _L.charger_png(src, 1))
    couches = _L._normaliser(couches, float(largeur))
    geoms = [mp for _c, mp in couches if mp is not None and not mp.is_empty]
    if not geoms:
        raise ValueError("logo vide (image illisible ?)")
    return unary_union(geoms)


def _polys(g):
    return list(g.geoms) if isinstance(g, MultiPolygon) else [g]


def _remplir(g):
    """Bouche les trous : ne garde que le contour EXTÉRIEUR de chaque polygone."""
    return unary_union([Polygon(p.exterior) for p in _polys(g) if not p.is_empty])


def _extruder(shape2d, hauteur: float, z: float = 0.0):
    parts = []
    for p in _polys(shape2d):
        if p.is_empty:
            continue
        m = trimesh.creation.extrude_polygon(p, float(hauteur))
        if z:
            m.apply_translation([0.0, 0.0, float(z)])
        parts.append(m)
    return union_solides(parts)


def _ellipse(w, h, cx, cy):
    return _translate(_scale(Point(0, 0).buffer(0.5, resolution=72), w, h), cx, cy)


def _rrect(w, h, r, cx, cy):
    r = max(0.5, min(r, w / 2 - 0.1, h / 2 - 0.1))
    return _translate(box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, join_style=1),
                      cx, cy)


def _ellipse_contenante(shape, marge, rond=False):
    """Ellipse (ou cercle) qui CONTIENT vraiment le logo + la marge : on part de la
    boîte englobante puis on agrandit jusqu'à ce que TOUTES les pointes soient
    dedans (une ellipse se rétrécit aux extrémités → sinon le logo dépasse)."""
    target = shape.buffer(marge, join_style=1, cap_style=1)
    x0, y0, x1, y1 = target.bounds
    ecx, ecy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    a = max(1.0, (x1 - x0) / 2.0)
    b = max(1.0, (y1 - y0) / 2.0)
    if rond:
        a = b = max(a, b)
    pts = []
    for p in _polys(target):
        pts.extend(p.exterior.coords)
    arr = np.asarray(pts, dtype=float)
    k = (((arr[:, 0] - ecx) / a) ** 2 + ((arr[:, 1] - ecy) / b) ** 2).max()
    s = max(1.0, float(k) ** 0.5)
    return _ellipse(2 * a * s, 2 * b * s, ecx, ecy)


def _forme_plaque(forme, shape, W, H, cx, cy, marge):
    """Plaque 2D (dos plein) selon la FORME choisie."""
    if forme == "ovale":
        return _ellipse_contenante(shape, marge, rond=False)
    if forme == "rond":
        return _ellipse_contenante(shape, marge, rond=True)
    if forme == "rectangle":
        return _rrect(W + 2 * marge, H + 2 * marge, 3.0, cx, cy)
    if forme == "etiquette":
        return _rrect(W + 2 * marge, H + 2 * marge, min(W, H) * 0.28, cx, cy)
    # contour : suit les courbes du logo
    return _remplir(shape.buffer(marge, join_style=1, cap_style=1))


def construire(chemin, longueur: float = 50.0, socle: float = 3.0, trou: float = 4.5,
               style: str = "lisse", relief_h: float = 1.6, forme: str = "contour",
               marge: float = 2.0, couleur_objet: str = "#3B82F6",
               couleur_logo: str = "#111111"):
    socle = max(1.6, float(socle))
    trou = max(2.0, float(trou))
    relief_h = max(0.4, float(relief_h))
    marge = max(1.2, float(marge))

    shape = _shape_2d(chemin, longueur)              # logo 2D (avec ses ouvertures)
    minx, miny, maxx, maxy = shape.bounds
    W, H = maxx - minx, maxy - miny
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    plaque = _forme_plaque(forme, shape, W, H, cx, cy, marge)

    # Anneau + trou INTÉGRÉS au socle EN 2D (union/différence shapely = fiable, un
    # SEUL solide, AUCUNE interpénétration 3D). C'est l'interpénétration (logo/anneau
    # qui s'enfoncent) qui trompait le découpeur et créait un FAUX surplomb.
    x0, y0, x1, y1 = plaque.bounds
    ocx = (x0 + x1) / 2.0
    rd = trou + 4.0
    ryc = y1 + rd / 2.0 - 2.0                         # anneau au-dessus, chevauche 2 mm en 2D
    tab = Point(ocx, ryc).buffer(rd / 2.0, resolution=48)
    trou2d = Point(ocx, ryc).buffer(trou / 2.0, resolution=32)
    socle2d = plaque.union(tab).difference(trou2d)

    # Logo POSÉ NET sur le socle (pas d'interpénétration) : relief saillant, lisse
    # quasi-affleurant, gravé en creux (alvéole). Le socle est TOUJOURS présent.
    if style == "grave":
        gg = max(0.4, min(relief_h, socle - 0.8))
        socle_full = _extruder(socle2d, socle)
        recess = _extruder(shape, gg + 1.0, z=socle - gg)
        try:
            socle_mesh = socle_full.difference(recess)     # creux propre (1 solide)
        except Exception:
            socle_mesh = socle_full
        logo = _extruder(shape, gg - 0.3, z=socle - gg)     # inlay couleur en creux
    elif style == "relief":
        socle_mesh = _extruder(socle2d, socle)
        logo = _extruder(shape, relief_h, z=socle)
    else:                                                    # lisse (quasi affleurant)
        socle_mesh = _extruder(socle2d, socle)
        logo = _extruder(shape, 0.6, z=socle)

    # recadrage commun à l'origine (garde socle et logo alignés)
    allmin = np.minimum(socle_mesh.bounds[0], logo.bounds[0])
    socle_mesh.apply_translation(-allmin)
    logo.apply_translation(-allmin)

    # Mono-couleur si les 2 couleurs sont identiques, sinon Scene bicolore (2 slots).
    if str(couleur_objet).lower() == str(couleur_logo).lower():
        return union_solides([socle_mesh, logo])
    sc = trimesh.Scene()
    sc.add_geometry(_colorier(socle_mesh, couleur_objet), geom_name="socle")
    sc.add_geometry(_colorier(logo, couleur_logo), geom_name="logo")
    return sc
