# -*- coding: utf-8 -*-
"""neoGen — PROTOTYPE ISOLÉ (hors neoSlice) : catalogue de goodies personnalisés.

Formes disponibles (--forme) :
  badge      pastille ronde, texte relief/gravé, trou d'accroche optionnel
  sousverre  sous-verre ø90 avec rebord surélevé, texte gravé au centre
  plaque     plaque rectangulaire arrondie, texte MULTI-LIGNES (| = saut de
             ligne), trous de vis optionnels (--vis)
  magnet     pastille avec LOGEMENT D'AIMANT creusé au dos (--aimant D P)

Exemples :
  python goodies.py --forme badge --texte "Léa" --diametre 40 --trou
  python goodies.py --forme sousverre --texte "neoSlice"
  python goodies.py --forme plaque --texte "Bienvenue|chez Léa" --vis
  python goodies.py --forme magnet --texte "Léa" --aimant 10.2 2

Même technique déterministe que porte_cle.py (contours police -> shapely ->
extrusions trimesh, gravures/logements faits en 2D avant extrusion, pas de
booléens 3D). Sorties STL + 3MF dans sorties\\ -> à glisser dans neoSlice.

CE FICHIER NE DOIT JAMAIS ÊTRE INTÉGRÉ À neoSlice (projet à part, cf. LISEZMOI).
"""
from __future__ import annotations


import argparse
import re
import sys
import unicodedata
from functools import reduce
from pathlib import Path

import numpy as np
import trimesh
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely.affinity import translate, scale as shp_scale

from core.neogen.geo_utils import union_solides

POLICES = ["Arial Rounded MT Bold", "Arial Black", "Segoe UI Black", "Arial"]

CHEVAUCHEMENT = 0.2   # fusion des volumes au slicing (mm)


# ── Texte -> polygones (identique à porte_cle.py, éprouvé) ───────────────────
def _rings_vers_polygones(rings: list[np.ndarray]) -> MultiPolygon:
    polys = []
    for r in rings:
        if len(r) >= 3:
            p = Polygon(r)
            if p.is_valid and p.area > 1e-6:
                polys.append(p)
    if not polys:
        return MultiPolygon([])
    merged = reduce(lambda a, b: a.symmetric_difference(b), polys)
    merged = merged.buffer(0)
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    return merged


# Police "de session" : posée par catalogue.construire() pour que le choix
# atteigne TOUS les générateurs à texte (coquetier, trophée, jeton...) sans
# devoir threader un paramètre dans chaque signature. Un argument `police`
# explicite garde la priorité.
POLICE_ACTIVE: str | None = None


# Espacement des lettres « de session » (mm ajoutés entre chaque glyphe), posé
# par catalogue.construire() comme POLICE_ACTIVE — atteint tous les objets à
# texte. La carte de visite le passe en direct (par élément).
ESPACEMENT_ACTIF: float | None = None


def _ligne_espacee(texte: str, hauteur_mm: float, prop, esp: float) -> MultiPolygon:
    """Une ligne avec ESPACEMENT réglable : chaque glyphe est rendu et posé
    individuellement (avance = largeur du glyphe + `esp` mm)."""
    full = TextPath((0, 0), texte, size=100, prop=prop)
    fh = full.get_extents().height or 100.0
    f = hauteur_mm / fh                                  # échelle cohérente
    espace_mm = 0.30 * hauteur_mm                        # largeur d'une espace
    x = 0.0
    polys = []
    for ch in texte:
        if ch == " ":
            x += espace_mm + esp
            continue
        tp = TextPath((0, 0), ch, size=100, prop=prop)
        mp = _rings_vers_polygones([np.asarray(p) for p in tp.to_polygons()])
        if mp.is_empty:
            x += espace_mm + esp
            continue
        mp = shp_scale(mp, xfact=f, yfact=f, origin=(0, 0))
        minx, _miny, maxx, _maxy = mp.bounds
        mp = translate(mp, xoff=x - minx)                # colle le glyphe à x
        polys += list(mp.geoms) if isinstance(mp, MultiPolygon) else [mp]
        x += (maxx - minx) + esp                         # avance
    tout = unary_union(polys) if polys else MultiPolygon()
    if isinstance(tout, Polygon):
        tout = MultiPolygon([tout])
    if tout.is_empty:
        raise RuntimeError("texte vide après espacement")
    minx, miny, _, _ = tout.bounds
    return translate(tout, xoff=-minx, yoff=-miny)


def _ligne_texte(texte: str, hauteur_mm: float,
                 police: str | None = None,
                 espacement: float | None = None) -> MultiPolygon:
    """Une ligne de texte, hauteur donnée, coin bas-gauche en (0,0).
    `police` : famille de police préférée (repli sur POLICES si absente).
    `espacement` : mm entre lettres (repli sur ESPACEMENT_ACTIF)."""
    derniere_err = None
    police = police or POLICE_ACTIVE
    esp = ESPACEMENT_ACTIF if espacement is None else espacement
    essais = ([police] if police else []) + POLICES
    for police in essais:
        try:
            prop = FontProperties(family=police, weight="bold")
            if esp and float(esp) > 0:
                return _ligne_espacee(texte, hauteur_mm, prop, float(esp))
            tp = TextPath((0, 0), texte, size=100, prop=prop)
            mp = _rings_vers_polygones([np.asarray(p) for p in tp.to_polygons()])
            if mp.is_empty:
                continue
            minx, miny, maxx, maxy = mp.bounds
            f = hauteur_mm / (maxy - miny)
            mp = shp_scale(mp, xfact=f, yfact=f, origin=(minx, miny))
            minx, miny, _, _ = mp.bounds
            return translate(mp, xoff=-minx, yoff=-miny)
        except Exception as exc:
            derniere_err = exc
    raise RuntimeError(f"Impossible de vectoriser « {texte} » : {derniere_err}")


def texte_multilignes(texte: str, hauteur_ligne: float = 10.0,
                      police: str | None = None,
                      espacement: float | None = None) -> MultiPolygon:
    """Texte multi-lignes (séparateur « | »), lignes centrées, centre en (0,0)."""
    lignes = [l.strip() for l in texte.split("|") if l.strip()]
    if not lignes:
        raise ValueError("Texte vide.")
    interligne = hauteur_ligne * 1.45
    blocs = []
    for i, l in enumerate(lignes):
        mp = _ligne_texte(l, hauteur_ligne, police=police, espacement=espacement)
        minx, miny, maxx, maxy = mp.bounds
        # centre la ligne en X, empile en Y (1re ligne en haut)
        y = -(i * interligne)
        blocs.append(translate(mp, xoff=-(maxx - minx) / 2.0, yoff=y))
    tout = unary_union([g for b in blocs for g in b.geoms])
    if isinstance(tout, Polygon):
        tout = MultiPolygon([tout])
    minx, miny, maxx, maxy = tout.bounds
    return translate(tout, xoff=-(minx + maxx) / 2.0, yoff=-(miny + maxy) / 2.0)


def ajuster_dans(mp: MultiPolygon, larg_max: float, haut_max: float) -> MultiPolygon:
    """Met le bloc texte à l'échelle pour tenir dans larg_max × haut_max (centré)."""
    minx, miny, maxx, maxy = mp.bounds
    f = min(larg_max / (maxx - minx), haut_max / (maxy - miny))
    return shp_scale(mp, xfact=f, yfact=f, origin=(0, 0))


# ── Briques d'extrusion (relief / gravure / logement) ────────────────────────
def _extruder(geom, h: float, z: float = 0.0) -> list[trimesh.Trimesh]:
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


# Hauteur de relief / profondeur de gravure « de session » : posée par
# catalogue.construire() (comme POLICE_ACTIVE) pour que le réglage atteigne
# TOUS les objets à texte sans threader un paramètre dans chaque signature.
RELIEF_ACTIF: float | None = None


def socle_avec_texte(socle_2d, texte_2d, ep_socle: float, ep_texte: float,
                     grave: bool, poche_2d=None, prof_poche: float = 0.0,
                     recentrer: bool = True, style: str | None = None,
                     couleur_objet: str | None = None,
                     couleur_texte: str | None = None):
    """Assemble : socle (avec éventuelle POCHE creusée au DOS) + texte.
    Tout en tranches 2D extrudées -> pas de booléens 3D, toujours étanche.

    style : "relief" | "grave" | "lisse" (prioritaire sur le flag legacy `grave`).
    couleur_objet / couleur_texte : si fournis → Scene à 2 corps colorés (bicolore,
    2 slots à l'export) ; sinon maillage fusionné mono-couleur (compat)."""
    if RELIEF_ACTIF is not None:
        ep_texte = max(0.3, float(RELIEF_ACTIF))       # réglage utilisateur
    style = style if style in ("relief", "grave", "lisse") else ("grave" if grave else "relief")
    grave = (style == "grave")
    bicolore = bool(couleur_objet and couleur_texte)
    from core.neogen.geo_utils import union_solides

    # socle (+ poche éventuelle au dos) = corps « objet » ; texte = corps « texte »
    socle_solides, texte_solides = [], []
    z0 = 0.0
    if poche_2d is not None and prof_poche > 0:
        bas = socle_2d.difference(poche_2d)            # tranche du bas percée (poche au dos)
        socle_solides += _extruder(bas, prof_poche + CHEVAUCHEMENT, 0)
        z0 = prof_poche
    if style == "relief":
        socle_solides += _extruder(socle_2d, ep_socle - z0, z0)              # socle plein
        texte_solides += _extruder(texte_2d, ep_texte + CHEVAUCHEMENT,
                                   ep_socle - CHEVAUCHEMENT)                 # relief
    else:
        # grave / lisse : le socle porte des alvéoles là où va le texte
        ep_t = min(ep_texte, ep_socle - z0 - 0.4)
        z_base = ep_socle - ep_t
        socle_solides += _extruder(socle_2d, z_base - z0, z0)               # dalle
        socle_solides += _extruder(socle_2d.difference(texte_2d), ep_t, z_base)  # grille
        h_txt = ep_t - (0.6 if style == "grave" else 0.0)                   # sillon si gravé
        texte_solides += _extruder(texte_2d, max(0.4, h_txt), z_base)

    if bicolore:
        from core.neogen import bicolore as _bic
        socle = union_solides(socle_solides)
        texte = (union_solides(texte_solides) if len(texte_solides) > 1
                 else texte_solides[0])
        s = _bic.scene(socle, texte, couleur_objet, couleur_texte)
        if recentrer:
            import trimesh as _tm
            fus = _tm.util.concatenate(list(s.geometry.values()))
            off = -fus.bounds[0]
            for g in s.geometry.values():
                g.apply_translation(off)
        return s

    piece = union_solides(socle_solides + texte_solides)   # mono : union réelle
    if recentrer:
        piece.apply_translation(-piece.bounds[0])
    return piece


# ── Formes ────────────────────────────────────────────────────────────────────
def badge(texte: str = "", diametre: float = 40, ep: float = 3, ep_texte: float = 1.2,
          grave: bool = False, trou: float = 0.0, police: str | None = None,
          style: str | None = None, couleur_objet: str | None = None,
          couleur_texte: str | None = None):
    """Pastille ronde, texte centré ; trou d'accroche en haut si demandé."""
    disque = Point(0, 0).buffer(diametre / 2, resolution=96)
    if trou > 0:
        c = Point(0, diametre / 2 - trou / 2 - 2.0)
        disque = disque.difference(c.buffer(trou / 2, resolution=48))
        haut_max = diametre * 0.42
        dec_y = -diametre * 0.06
    else:
        haut_max = diametre * 0.52
        dec_y = 0.0
    if not (texte or "").strip():
        piece = union_solides(_extruder(disque, ep))
        piece.apply_translation(-piece.bounds[0])
        return piece
    txt = ajuster_dans(texte_multilignes(texte, police=police), diametre * 0.74, haut_max)
    txt = translate(txt, yoff=dec_y)
    return socle_avec_texte(disque, unary_union(list(txt.geoms)), ep, ep_texte, grave,
                            style=style, couleur_objet=couleur_objet,
                            couleur_texte=couleur_texte)


def sous_verre(texte: str = "", diametre: float = 90, ep: float = 3.6,
               rebord: float = 1.2, ep_texte: float = 0.8,
               police: str | None = None, couleur_objet: str | None = None,
               couleur_texte: str | None = None):
    """Sous-verre : disque + rebord périphérique surélevé, texte GRAVÉ au centre
    (surface plate = pose du verre, gravure = pas d'accroc). Toujours GRAVÉ (le
    relief ferait osciller le verre) mais BICOLORE possible (2 couleurs)."""
    import trimesh as _tm
    bicolore = bool(couleur_objet and couleur_texte)
    disque = Point(0, 0).buffer(diametre / 2, resolution=128)
    if (texte or "").strip():
        txt = ajuster_dans(texte_multilignes(texte, police=police),
                           diametre * 0.62, diametre * 0.5)
        # recentrer=False : repère centré en (0,0) pour aligner le rebord,
        # puis on recentre le TOUT à la fin.
        piece = socle_avec_texte(disque, unary_union(list(txt.geoms)), ep, ep_texte,
                                 grave=True, recentrer=False, style="grave",
                                 couleur_objet=couleur_objet, couleur_texte=couleur_texte)
    else:
        piece = union_solides(_extruder(disque, ep))
    if rebord > 0:  # anneau surélevé (extrusion séparée posée dessus)
        ext = Point(0, 0).buffer(diametre / 2, resolution=128)
        intr = Point(0, 0).buffer(diametre / 2 - 3.0, resolution=128)
        anneau = ext.difference(intr)
        rebord_solides = _extruder(anneau, rebord + CHEVAUCHEMENT, ep - CHEVAUCHEMENT)
        if bicolore and isinstance(piece, _tm.Scene):
            # rebord = même couleur que l'objet : on l'ajoute au corps « objet »
            from core.neogen import bicolore as _bic
            objet_g = union_solides([piece.geometry["objet"]] + rebord_solides)
            piece = _bic.scene(objet_g, piece.geometry["texte"],
                               couleur_objet, couleur_texte)
        else:
            piece = union_solides([piece] + rebord_solides)
    if isinstance(piece, _tm.Scene):
        fus = _tm.util.concatenate(list(piece.geometry.values()))
        off = -fus.bounds[0]
        for g in piece.geometry.values():
            g.apply_translation(off)
        return piece
    piece.apply_translation(-piece.bounds[0])
    return piece


def plaque(texte: str = "", largeur: float = 0, hauteur: float = 0, ep: float = 3,
           ep_texte: float = 1.5, grave: bool = False, vis: bool = False,
           police: str | None = None, style: str | None = None,
           couleur_objet: str | None = None, couleur_texte: str | None = None):
    """Plaque rectangulaire arrondie, texte multi-lignes (optionnel) ; vis en option."""
    avec_texte = bool((texte or "").strip())
    if avec_texte:
        txt = texte_multilignes(texte, police=police)
        minx, miny, maxx, maxy = txt.bounds
    else:
        minx = miny = 0.0
        maxx, maxy = 80.0, 30.0            # plaque nue : gabarit par défaut
    marge = 8.0 if vis else 5.0
    if largeur <= 0:
        largeur = (maxx - minx) + 2 * marge + (12 if vis else 0)
    if hauteur <= 0:
        hauteur = (maxy - miny) + 2 * marge
    r = min(4.0, hauteur / 4)
    base = box(-(largeur / 2 - r), -(hauteur / 2 - r),
               largeur / 2 - r, hauteur / 2 - r).buffer(r, join_style=1)
    if vis:  # 4 trous ø4 dans les coins
        d, inset = 4.0, 6.0
        for sx in (-1, 1):
            for sy in (-1, 1):
                c = Point(sx * (largeur / 2 - inset), sy * (hauteur / 2 - inset))
                base = base.difference(c.buffer(d / 2, resolution=36))
    if not avec_texte:
        piece = union_solides(_extruder(base, ep))
        piece.apply_translation(-piece.bounds[0])
        return piece
    zone_l = largeur - 2 * marge - (12 if vis else 0)
    txt = ajuster_dans(txt, zone_l, hauteur - 2 * marge)
    return socle_avec_texte(base, unary_union(list(txt.geoms)), ep, ep_texte, grave,
                            style=style, couleur_objet=couleur_objet,
                            couleur_texte=couleur_texte)


def magnet(texte: str = "", diametre: float = 35, ep: float = 4, ep_texte: float = 1.2,
           grave: bool = False, d_aimant: float = 10.2, prof_aimant: float = 2.0,
           police: str | None = None, style: str | None = None,
           couleur_objet: str | None = None, couleur_texte: str | None = None):
    """Pastille avec LOGEMENT d'aimant creusé au dos (aimant collé/inséré)."""
    if prof_aimant >= ep - 1.0:
        raise ValueError("Logement trop profond pour l'épaisseur (min 1 mm de paroi).")
    disque = Point(0, 0).buffer(diametre / 2, resolution=96)
    poche = Point(0, 0).buffer(d_aimant / 2, resolution=64)
    if not (texte or "").strip():
        return socle_avec_texte(disque, disque.buffer(-diametre), ep, 0.0, False,
                                poche_2d=poche, prof_poche=prof_aimant)
    txt = ajuster_dans(texte_multilignes(texte, police=police),
                       diametre * 0.74, diametre * 0.52)
    return socle_avec_texte(disque, unary_union(list(txt.geoms)), ep, ep_texte,
                            grave, poche_2d=poche, prof_poche=prof_aimant,
                            style=style, couleur_objet=couleur_objet,
                            couleur_texte=couleur_texte)
