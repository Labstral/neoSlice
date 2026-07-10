# -*- coding: utf-8 -*-
"""neoGen — PROTOTYPE ISOLÉ (hors neoSlice) : logo (SVG ou PNG) -> objet 3D.

  SVG : vectoriel -> extrusion DIRECTE (bords parfaits à toute taille)
  PNG : quantification des couleurs (k-means) -> contours OpenCV -> polygones

Le logo est posé en relief sur un socle (badge rond, plaque, ou silhouette du
logo). Export : STL fusionné + 3MF MULTI-CORPS (socle + UN CORPS PAR COULEUR,
nommés logo_1_<hex>...) -> neoSlice peut attribuer un filament par corps
(export multicouleur).

Exemples :
  python logo.py --image chemin\\logo.svg --forme badge --diametre 45
  python logo.py --image chemin\\logo.png --forme plaque --couleurs 3
  python logo.py --image chemin\\logo.svg --forme silhouette --largeur 60

CE FICHIER NE DOIT JAMAIS ÊTRE INTÉGRÉ À neoSlice (projet à part, cf. LISEZMOI).
"""
from __future__ import annotations


import argparse
import re
import sys
import unicodedata
from functools import reduce
from pathlib import Path as FSPath

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely.affinity import scale as shp_scale, translate

SORTIES = FSPath(__file__).parent / "sorties"
CHEVAUCHEMENT = 0.2
AIRE_MIN_MM2 = 0.5          # ignore les poussières plus petites


# ── Utilitaires géométrie ─────────────────────────────────────────────────────
def _pair_impair(rings: list[np.ndarray]) -> MultiPolygon:
    """Anneaux -> polygones à trous (règle pair-impair, comme les polices)."""
    polys = []
    for r in rings:
        if len(r) >= 3:
            p = Polygon(r)
            if p.is_valid and p.area > 1e-9:
                polys.append(p)
    if not polys:
        return MultiPolygon([])
    merged = reduce(lambda a, b: a.symmetric_difference(b), polys).buffer(0)
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    return merged


def _normaliser(couches: list[tuple[str, MultiPolygon]], largeur_mm: float,
                min_trait: float = 0.6):
    """Met l'ENSEMBLE des couches à l'échelle (largeur cible), centré en (0,0),
    Y retourné (SVG et images ont l'axe Y vers le bas).

    min_trait : largeur moyenne minimale (mm) d'un élément pour être gardé —
    élimine les résidus de dégradés/lisérés trop fins pour être imprimés
    (largeur moyenne ~ 2*aire/périmètre pour une forme allongée)."""
    tout = unary_union([g for _, mp in couches for g in mp.geoms])
    minx, miny, maxx, maxy = tout.bounds
    f = largeur_mm / (maxx - minx)
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    out = []
    for coul, mp in couches:
        mp = shp_scale(translate(mp, xoff=-cx, yoff=-cy), xfact=f, yfact=-f, origin=(0, 0))
        gardes = []
        for g in mp.geoms:
            if g.area < AIRE_MIN_MM2:
                continue
            if min_trait > 0 and g.length > 0 and (2 * g.area / g.length) < min_trait:
                continue                      # trait trop fin -> inimprimable
            if min_trait > 0 and g.interiors:
                # SYMÉTRIE du filtre : un CREUX trop fin (empreinte d'un élément
                # supprimé, ex. fin soulignement) est REBOUCHÉ — sinon il reste
                # une fente dans la pièce. On garde les vrais trous (lettres...).
                trous_ok = []
                for i in g.interiors:
                    t = Polygon(i)
                    if t.area >= AIRE_MIN_MM2 and (2 * t.area / max(t.length, 1e-9)) >= min_trait:
                        trous_ok.append(i)
                g = Polygon(g.exterior, trous_ok)
            gardes.append(g)
        mp = MultiPolygon(gardes).buffer(0)
        if isinstance(mp, Polygon):
            mp = MultiPolygon([mp])
        if not mp.is_empty:
            out.append((coul, mp))
    return out


# ── SVG -> couches de couleur ────────────────────────────────────────────────
def charger_svg(chemin: str) -> list[tuple[str, MultiPolygon]]:
    """Chaque <path> SVG est échantillonné en polygones ; groupé par couleur."""
    from svgelements import SVG, Path as SPath, Shape
    svg = SVG.parse(chemin, reify=True)
    par_couleur: dict[str, list[np.ndarray]] = {}
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        try:
            path = SPath(el)
        except Exception:
            continue
        if len(path) == 0:
            continue
        fill = getattr(el, "fill", None)
        coul = (fill.hexrgb if fill is not None and fill.value is not None else "#000000")
        for sous in path.as_subpaths():
            sp = SPath(sous)
            L = sp.length(error=1e-3)
            if not L:
                continue
            n = max(24, min(400, int(L / 1.5)))
            pts = np.array([(p.real, p.imag) for p in (sp.point(i / n) for i in range(n + 1))
                            if p is not None])
            if len(pts) >= 3:
                par_couleur.setdefault(coul, []).append(pts)
    couches = []
    for coul, rings in par_couleur.items():
        mp = _pair_impair(rings)
        if not mp.is_empty:
            couches.append((coul, mp))
    if not couches:
        raise ValueError("Aucun tracé exploitable dans ce SVG.")
    return couches


# ── PNG -> couches de couleur ────────────────────────────────────────────────
def charger_png(chemin: str, n_couleurs: int = 3) -> list[tuple[str, MultiPolygon]]:
    """Quantifie les couleurs (k-means simple) puis vectorise chaque zone
    (contours OpenCV avec trous)."""
    import cv2
    from PIL import Image

    im = Image.open(chemin).convert("RGBA")
    if max(im.size) > 560:                       # assez fin, et rapide
        im.thumbnail((560, 560))
    arr = np.asarray(im).astype(np.int32)
    rgb, alpha = arr[..., :3], arr[..., 3]
    opaque = alpha > 128
    if not opaque.any():
        raise ValueError("Image entièrement transparente.")

    # k-means volontairement simple (numpy) sur les pixels opaques
    px = rgb[opaque].reshape(-1, 3).astype(np.float64)
    ech = px[np.random.default_rng(0).choice(len(px), min(20000, len(px)), replace=False)]
    # init : centroïdes répartis sur la luminance
    lum = ech.sum(axis=1)
    cent = np.array([ech[np.argsort(lum)[int(q * (len(ech) - 1))]]
                     for q in np.linspace(0.02, 0.98, n_couleurs)])
    for _ in range(12):
        d = ((ech[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for k in range(n_couleurs):
            if (lab == k).any():
                cent[k] = ech[lab == k].mean(axis=0)

    # étiquette chaque pixel opaque, une couche par couleur
    d = ((px[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
    labels_flat = d.argmin(axis=1)
    labels = np.full(opaque.shape, -1, dtype=np.int32)
    labels[opaque] = labels_flat

    couches = []
    noyau = np.ones((3, 3), np.uint8)
    for k in range(n_couleurs):
        masque = (labels == k).astype(np.uint8) * 255
        if masque.sum() == 0:
            continue
        # PAS de MORPH_OPEN : l'érosion COUPE les traits fins (liséré de logo
        # ouvert !). L'anti-poussière est fait par surface (AIRE_MIN_MM2).
        masque = cv2.morphologyEx(masque, cv2.MORPH_CLOSE, noyau)  # rebouche les micro-trous
        cont, hier = cv2.findContours(masque, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_L1)
        if hier is None:
            continue
        hier = hier[0]
        polys = []
        for i, c in enumerate(cont):
            if hier[i][3] != -1 or len(c) < 3:      # trous gérés via les enfants
                continue
            ext = c[:, 0, :].astype(float)
            trous = []
            j = hier[i][2]                          # premier enfant
            while j != -1:
                if len(cont[j]) >= 3:
                    trous.append(cont[j][:, 0, :].astype(float))
                j = hier[j][0]
            p = Polygon(ext, trous).buffer(0)
            if not p.is_empty:
                polys.append(p.simplify(0.6))
        if polys:
            mp = unary_union(polys)
            # Fermeture géométrique : ressoude les coupures de 1-2 px sur les
            # traits fins (liséré) sans épaissir le résultat final.
            mp = mp.buffer(1.6, join_style=1).buffer(-1.6, join_style=1)
            if isinstance(mp, Polygon):
                mp = MultiPolygon([mp])
            r, g, b = (int(v) for v in cent[k])
            couches.append((f"#{r:02X}{g:02X}{b:02X}", mp))
    if not couches:
        raise ValueError("Aucune zone de couleur exploitable dans ce PNG.")
    return couches


# ── Assemblage : socle + logo en relief (un corps par couleur) ───────────────
def _extruder(geom, h, z=0.0):
    geoms = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    out = []
    for g in geoms:
        if g.is_empty or g.area < 1e-6:
            continue
        m = trimesh.creation.extrude_polygon(g, h)
        if z:
            m.apply_translation([0, 0, z])
        out.append(m)
    return out


def _hex_rgba(coul: str):
    coul = coul.lstrip("#")
    return [int(coul[0:2], 16), int(coul[2:4], 16), int(coul[4:6], 16), 255]


def construire(couches, forme: str, diametre: float, largeur: float,
               ep_socle: float, ep_relief: float, marge: float = 3.0,
               epaissir: float = 0.0) -> tuple[trimesh.Scene, trimesh.Trimesh]:
    """Renvoie (scène multi-corps 'socle' + 'logo_<n>_<hex>', mesh FUSIONNÉ).

    Le mesh fusionné est construit par union de volumes FRANCHEMENT
    chevauchants (socle PLEIN + couleurs pleine hauteur) : l'union manifold
    est robuste (contrairement aux parois exactement coïncidentes du puzzle)
    -> un seul solide étanche, zéro paroi interne, analyse 100 % propre."""
    tout = unary_union([g for _, mp in couches for g in mp.geoms])
    minx, miny, maxx, maxy = tout.bounds
    l_logo, h_logo = maxx - minx, maxy - miny

    if forme == "badge":
        d = diametre or (max(l_logo, h_logo) + 2 * marge + 4)
        socle_2d = Point(0, 0).buffer(d / 2, resolution=96)
    elif forme == "plaque":
        l = largeur or (l_logo + 2 * marge + 4)
        h = h_logo + 2 * marge + 4
        r = min(4.0, h / 4)
        socle_2d = box(-(l / 2 - r), -(h / 2 - r), l / 2 - r, h / 2 - r).buffer(r, join_style=1)
    else:  # silhouette : le socle épouse le logo
        socle_2d = tout.buffer(marge, join_style=1)
        socle_2d = socle_2d.buffer(1.5, join_style=1).buffer(-1.5, join_style=1)
        if isinstance(socle_2d, MultiPolygon):        # garde le plus grand îlot
            socle_2d = max(socle_2d.geoms, key=lambda g: g.area)

    # STYLE TRAVERSANT : chaque couleur descend jusqu'au PLATEAU et le socle est
    # évidé de son empreinte (pièces de puzzle, comme les modèles multicouleurs
    # Bambu). Avantages : tous les corps touchent le plateau et AUCUNE face
    # n'est enfouie dans un autre volume -> pas de faux surplombs à l'analyse.
    empreintes = []
    corps_couleur = []
    for i, (coul, mp) in enumerate(couches, 1):
        if epaissir > 0:      # renforce les traits fins (mm ajoutés de chaque côté /2)
            mp = mp.buffer(epaissir / 2.0, join_style=1)
            if isinstance(mp, Polygon):
                mp = MultiPolygon([mp])
        mp_ok = MultiPolygon([g for g in mp.geoms
                              if g.intersects(socle_2d)]).intersection(socle_2d)
        if mp_ok.is_empty:
            continue
        mp_ok = mp_ok.difference(unary_union(empreintes)) if empreintes else mp_ok
        if mp_ok.is_empty:
            continue
        empreintes.append(mp_ok)
        corps_couleur.append((i, coul, mp_ok))

    scene = trimesh.Scene()
    socle_evide = socle_2d.difference(unary_union(empreintes)) if empreintes else socle_2d
    socle = trimesh.util.concatenate(_extruder(socle_evide, ep_socle))
    socle.visual.face_colors = [70, 70, 75, 255]
    scene.add_geometry(socle, node_name="socle", geom_name="socle")

    corps_meshes = []
    for i, coul, mp_ok in corps_couleur:
        corps = trimesh.util.concatenate(
            _extruder(mp_ok, ep_socle + ep_relief, 0))       # du plateau au sommet
        corps.visual.face_colors = _hex_rgba(coul)
        nom = f"logo_{i}_{coul.lstrip('#')}"
        scene.add_geometry(corps, node_name=nom, geom_name=nom)
        corps_meshes.append(corps)

    # Mesh FUSIONNÉ (pour le STL) : les empreintes couleur sont d'abord UNIES EN
    # 2D (shapely gère parfaitement l'adjacence texte/plaque), puis extrudées en
    # UN volume pleine hauteur -> union 3D de 2 volumes franchement chevauchants
    # (socle PLEIN + relief). Robuste : aucune paroi coïncidente pour manifold.
    from core.neogen.geo_utils import union_solides
    socle_plein = trimesh.util.concatenate(_extruder(socle_2d, ep_socle))
    # IMPORTANT : partir des couches ORIGINALES (pas des `empreintes` issues des
    # differences sequentielles, dont les frontieres communes laissent des
    # lamelles qui font echouer l'union manifold).
    relief_2d = unary_union([g for _, mp in couches for g in mp.geoms])
    relief_2d = relief_2d.intersection(socle_2d).buffer(0) if not relief_2d.is_empty else None
    if relief_2d is not None and not relief_2d.is_empty:
        # Nettoyage : simplification legere (contours PNG dentelés -> micro-aretes
        # qui font des lamelles a l'union manifold) + purge des micro-fragments.
        if isinstance(relief_2d, Polygon):
            relief_2d = MultiPolygon([relief_2d])
        relief_2d = MultiPolygon(
            [g.simplify(0.05) for g in relief_2d.geoms if g.area >= AIRE_MIN_MM2]
        ).buffer(0)
        if isinstance(relief_2d, Polygon):
            relief_2d = MultiPolygon([relief_2d])
    if relief_2d is not None and not relief_2d.is_empty:
        relief_vol = trimesh.util.concatenate(_extruder(relief_2d, ep_socle + ep_relief, 0))
        fusion = union_solides([socle_plein, relief_vol])
    else:
        fusion = socle_plein
    return scene, fusion
