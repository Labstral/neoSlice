# -*- coding: utf-8 -*-
"""neoGen — PERSONNALISATEUR DE CARTE DE VISITE.

Une carte = un socle (couleur de base) + des ÉLÉMENTS en relief (texte, logo),
chacun avec SA couleur. À l'export, chaque couleur devient un CORPS séparé du
3MF assigné à un slot de filament : dans le slicer, on retrouve autant de slots
que de couleurs, pré-remplis — il ne reste qu'à charger le bon filament.

Positionnement STRUCTURÉ (v1) : chaque élément a un alignement (gauche/centre/
droite × haut/milieu/bas) + un décalage fin X/Y. Fiable et rapide ; le
glisser-déposer libre pourra venir plus tard.

Repère : la carte est CENTRÉE en (0,0). x ∈ [-L/2, L/2], y ∈ [-H/2, H/2].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
from shapely.affinity import translate as _tr
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union

from core.neogen.goodies import _extruder, texte_multilignes, CHEVAUCHEMENT
from core.neogen.geo_utils import union_solides

CHEV = CHEVAUCHEMENT
MARGE = 4.0                                   # marge intérieure (mm)


@dataclass
class ElementTexte:
    texte: str = ""
    police: str | None = None
    hauteur: float = 4.0                      # hauteur de capitale (mm)
    align_h: str = "centre"                   # gauche | centre | droite
    align_v: str = "milieu"                   # haut | milieu | bas
    dx: float = 0.0
    dy: float = 0.0
    relief: float = 0.6
    couleur: str = "#111111"
    type: str = "texte"


@dataclass
class ElementLogo:
    chemin: str = ""
    largeur: float = 18.0
    align_h: str = "centre"
    align_v: str = "milieu"
    dx: float = 0.0
    dy: float = 0.0
    relief: float = 0.6
    couleur: str = "#111111"
    type: str = "logo"


@dataclass
class CarteSpec:
    largeur: float = 85.0                     # format standard 85 × 55 mm
    hauteur: float = 55.0
    ep: float = 1.6
    rayon: float = 3.5                         # rayon des coins
    couleur_base: str = "#FFFFFF"
    elements: list = field(default_factory=list)


def _hex_rgba(h: str) -> list[int]:
    h = (h or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255]
    except ValueError:
        return [255, 255, 255, 255]


def _forme_element(el, spec: CarteSpec) -> MultiPolygon | None:
    """Contour 2D de l'élément, centré sur son propre repère (0,0)."""
    if getattr(el, "type", "texte") == "logo":
        if not el.chemin:
            return None
        from pathlib import Path as _P
        from core.neogen import logo as _L
        src = _P(el.chemin)
        couches = (_L.charger_svg(str(src)) if src.suffix.lower() == ".svg"
                   else _L.charger_png(str(src), 3))
        couches = _L._normaliser(couches, el.largeur)
        mp = unary_union([g for _c, m in couches for g in m.geoms])
    else:
        if not (el.texte or "").strip():
            return None
        mp = texte_multilignes(el.texte, el.hauteur, police=el.police)
        mp = unary_union(list(mp.geoms))
    if isinstance(mp, Polygon):
        mp = MultiPolygon([mp])
    return mp if not mp.is_empty else None


def _placer(mp, spec: CarteSpec, el) -> MultiPolygon:
    """Positionne `mp` sur la carte selon l'alignement + décalage de `el`, et
    le RECADRE dans la zone imprimable (jamais de relief qui déborde du bord)."""
    minx, miny, maxx, maxy = mp.bounds
    w, h = maxx - minx, maxy - miny
    cx0, cy0 = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    lim_x = spec.largeur / 2 - MARGE - w / 2
    lim_y = spec.hauteur / 2 - MARGE - h / 2
    tx = {"gauche": -lim_x, "centre": 0.0, "droite": lim_x}.get(el.align_h, 0.0)
    ty = {"bas": -lim_y, "milieu": 0.0, "haut": lim_y}.get(el.align_v, 0.0)
    tx = max(-lim_x, min(lim_x, tx + el.dx))
    ty = max(-lim_y, min(lim_y, ty + el.dy))
    mp = _tr(mp, xoff=tx - cx0, yoff=ty - cy0)
    zone = box(-spec.largeur / 2 + 1.0, -spec.hauteur / 2 + 1.0,
               spec.largeur / 2 - 1.0, spec.hauteur / 2 - 1.0)
    mp = mp.intersection(zone)
    if isinstance(mp, Polygon):
        mp = MultiPolygon([mp])
    return mp


def _socle_2d(spec: CarteSpec) -> Polygon:
    r = max(0.0, min(spec.rayon, min(spec.largeur, spec.hauteur) / 2 - 0.5))
    rect = box(-spec.largeur / 2, -spec.hauteur / 2,
               spec.largeur / 2, spec.hauteur / 2)
    return rect.buffer(-r, join_style=1).buffer(r, join_style=1)   # coins ronds


def construire(spec: CarteSpec):
    """Construit la carte -> (trimesh.Scene multi-corps, liste ordonnée des
    couleurs). Corps 0 = socle (couleur de base) ; puis un corps par couleur
    d'élément (fusion des reliefs de cette couleur). Chaque corps porte sa
    couleur visuelle (aperçu viewer)."""
    socle = _socle_2d(spec)
    base = union_solides(_extruder(socle, spec.ep))
    base.visual.face_colors = _hex_rgba(spec.couleur_base)

    # regrouper les reliefs par couleur (ordre de première apparition)
    par_couleur: dict[str, list] = {}
    for el in spec.elements:
        mp = _forme_element(el, spec)
        if mp is None:
            continue
        mp = _placer(mp, spec, el)
        if mp.is_empty:
            continue
        par_couleur.setdefault(el.couleur, []).append((mp, el.relief))

    scene = trimesh.Scene()
    scene.add_geometry(base, node_name="socle", geom_name="socle")
    couleurs = [spec.couleur_base]
    for i, (coul, items) in enumerate(par_couleur.items()):
        solides = []
        for mp, relief in items:
            r = max(0.3, float(relief))
            for g in (mp.geoms if isinstance(mp, MultiPolygon) else [mp]):
                if g.area > 0:
                    # relief posé SUR le socle (chevauche pour souder)
                    solides += _extruder(g, r + CHEV, spec.ep - CHEV)
        if not solides:
            continue
        corps = union_solides(solides)
        corps.visual.face_colors = _hex_rgba(coul)
        scene.add_geometry(corps, node_name=f"couleur_{i+1}",
                           geom_name=f"couleur_{i+1}")
        if coul not in couleurs:
            couleurs.append(coul)
    return scene, couleurs
