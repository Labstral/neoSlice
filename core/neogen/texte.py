# -*- coding: utf-8 -*-
"""neoGen — PROTOTYPE ISOLÉ (hors neoSlice) : porte-clé avec prénom en relief.

Génère un porte-clé imprimable (STL + 3MF) à partir d'une simple phrase :
    python porte_cle.py "un porte-clé avec écrit Léa, 5 cm"
    python porte_cle.py --texte "Léa" --longueur 50

Technique 100 % déterministe (aucune IA pour la géométrie) :
  1. Contours vectoriels du texte (matplotlib TextPath, police épaisse Windows)
  2. Polygones shapely (règle pair-impair pour les trous des lettres a, e, o…)
  3. Socle = enveloppe arrondie du texte + languette percée (trou fait en 2D
     par différence shapely AVANT extrusion -> pas besoin de booléens 3D)
  4. Extrusions trimesh : socle 3 mm + texte 1.6 mm posé dessus (chevauchement
     0.2 mm pour que le slicer fusionne les volumes)
  5. Export STL + 3MF -> à glisser dans neoSlice comme n'importe quel fichier.

CE FICHIER NE DOIT JAMAIS ÊTRE INTÉGRÉ À neoSlice (décision : projet à part,
supprimable sans résidu -> tout vit dans C:\\neoGen_proto).
"""
from __future__ import annotations

import io
import sys as _sys
if hasattr(_sys.stdout, "buffer"):  # console Windows cp1252 -> UTF-8
    _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")

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
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union


# Polices épaisses (les lettres fines cassent à l'impression) — la 1re dispo gagne.
POLICES = ["Arial Rounded MT Bold", "Arial Black", "Segoe UI Black", "Arial"]

# ── Paramètres par défaut (mm) ────────────────────────────────────────────────
EP_SOCLE = 3.0        # épaisseur du socle
EP_TEXTE = 1.6        # hauteur du relief du texte
CHEVAUCHEMENT = 0.2   # le texte plonge de 0.2 mm dans le socle (fusion au slicing)
MARGE = 3.0           # marge du socle autour du texte
D_TROU = 4.5          # diamètre du trou d'anneau
LONGUEUR_DEFAUT = 50  # longueur cible du porte-clé (mm)


def _rings_vers_polygones(rings: list[np.ndarray]) -> MultiPolygon:
    """Contours de glyphes -> polygones à trous (règle pair-impair via
    différences symétriques successives, suffisante pour les lettres)."""
    polys = []
    for r in rings:
        if len(r) >= 3:
            p = Polygon(r)
            if p.is_valid and p.area > 1e-6:
                polys.append(p)
    if not polys:
        return MultiPolygon([])
    merged = reduce(lambda a, b: a.symmetric_difference(b), polys)
    merged = merged.buffer(0)  # répare d'éventuelles auto-intersections
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    return merged


def contours_texte(texte: str, hauteur_mm: float) -> MultiPolygon:
    """Contours 2D du texte, mis à l'échelle pour une hauteur de capitale donnée."""
    derniere_err = None
    for police in POLICES:
        try:
            prop = FontProperties(family=police, weight="bold")
            tp = TextPath((0, 0), texte, size=100, prop=prop)
            rings = [np.asarray(p) for p in tp.to_polygons()]
            mp = _rings_vers_polygones(rings)
            if mp.is_empty:
                continue
            minx, miny, maxx, maxy = mp.bounds
            echelle = hauteur_mm / (maxy - miny)
            mp = MultiPolygon([
                Polygon(
                    [( (x - minx) * echelle, (y - miny) * echelle ) for x, y in p.exterior.coords],
                    [[( (x - minx) * echelle, (y - miny) * echelle ) for x, y in i.coords]
                     for i in p.interiors],
                ) for p in mp.geoms
            ])
            return mp
        except Exception as exc:  # police absente -> suivante
            derniere_err = exc
    raise RuntimeError(f"Impossible de vectoriser le texte : {derniere_err}")


def construire_porte_cle(texte: str, longueur_mm: float = LONGUEUR_DEFAUT,
                         ep_socle: float = EP_SOCLE, ep_texte: float = EP_TEXTE,
                         d_trou: float = D_TROU, marge: float = MARGE,
                         grave: bool = False) -> trimesh.Trimesh:
    """Socle arrondi + languette percée + texte en relief (ou gravé) -> un maillage.

    TOUT est paramétrable (c'est ce qu'Oen pilotera) :
      ep_socle : épaisseur du socle (mm)     ep_texte : hauteur du relief (mm)
      d_trou   : diamètre du trou d'anneau   marge    : socle autour du texte
      grave    : True = texte CREUSÉ dans le socle au lieu d'être en relief
    """
    if ep_socle < 1.2:
        raise ValueError("Socle trop fin (< 1.2 mm) : fragile à l'impression.")
    if grave and ep_texte >= ep_socle - 0.6:
        ep_texte = max(0.4, ep_socle - 0.8)   # gravure bornée : jamais traversante

    # 1) Texte d'abord à hauteur arbitraire, remis à l'échelle pour la longueur cible.
    mp = contours_texte(texte, hauteur_mm=10.0)
    minx, miny, maxx, maxy = mp.bounds
    l_texte = maxx - minx
    # longueur totale = languette (~1.2*d_trou*2) + marge + texte + marge
    l_languette = d_trou * 2.4
    l_dispo = longueur_mm - l_languette - 2 * marge
    if l_dispo <= 5:
        raise ValueError("Longueur trop petite pour ce texte.")
    facteur = l_dispo / l_texte
    hauteur_texte = 10.0 * facteur
    hauteur_texte = min(hauteur_texte, 14.0)          # évite un porte-clé géant
    mp = contours_texte(texte, hauteur_mm=hauteur_texte)
    minx, miny, maxx, maxy = mp.bounds

    # 2) Socle : enveloppe du texte arrondie (buffer) + pastille percée à gauche.
    corps = unary_union([g for g in mp.geoms]).buffer(marge, join_style=1)
    corps = corps.buffer(1.2, join_style=1).buffer(-1.2, join_style=1)  # lisse
    cx = minx - marge - d_trou * 0.2                   # centre pastille à gauche
    cy = (miny + maxy) / 2.0
    centre_trou = Point(cx - d_trou * 0.7, cy)
    pastille = centre_trou.buffer(max(d_trou * 1.2, d_trou / 2 + 2.5), resolution=48)
    socle_2d = unary_union([corps, pastille])
    trou = centre_trou.buffer(d_trou / 2.0, resolution=48)
    socle_2d = socle_2d.difference(trou)

    solides = []
    if grave:
        # Texte CREUSÉ : différence 2D socle - texte sur la hauteur de gravure,
        # + tranche pleine dessous (le tout SANS booléens 3D).
        texte_2d = unary_union([g for g in mp.geoms])
        haut_2d = socle_2d.difference(texte_2d)
        for g in (haut_2d.geoms if isinstance(haut_2d, MultiPolygon) else [haut_2d]):
            m = trimesh.creation.extrude_polygon(g, ep_texte + CHEVAUCHEMENT)
            m.apply_translation([0, 0, ep_socle - ep_texte - CHEVAUCHEMENT])
            solides.append(m)
        for g in (socle_2d.geoms if isinstance(socle_2d, MultiPolygon) else [socle_2d]):
            solides.append(trimesh.creation.extrude_polygon(g, ep_socle - ep_texte))
    else:
        # 3) Extrusions : socle plein + texte posé en relief.
        geoms = socle_2d.geoms if isinstance(socle_2d, MultiPolygon) else [socle_2d]
        for g in geoms:
            solides.append(trimesh.creation.extrude_polygon(g, ep_socle))
        for g in mp.geoms:                             # texte en relief
            m = trimesh.creation.extrude_polygon(g, ep_texte + CHEVAUCHEMENT)
            m.apply_translation([0, 0, ep_socle - CHEVAUCHEMENT])
            solides.append(m)

    from core.neogen.geo_utils import union_solides
    piece = union_solides(solides)   # union RÉELLE : zéro face interne (faux surplombs)
    piece.apply_translation(-piece.bounds[0])          # origine en (0,0,0)
    return piece


def _mm(phrase: str, motif: str) -> float | None:
    """Cherche « <motif> ... N mm/cm » dans la phrase et renvoie la valeur en mm."""
    m = re.search(r"(?:" + motif + r")[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*(cm|mm)?", phrase, re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v * 10 if (m.group(2) or "mm").lower() == "cm" else v


def extraire_params(phrase: str) -> dict:
    """Extraction naïve depuis une phrase FR (le vrai produit passera par Oen) :
    - texte entre guillemets, ou après « écrit / marqué / avec le nom »
    - longueur (« 5 cm »), trou (« trou de 6 mm »), relief (« relief de 1 mm »),
      socle (« socle de 4 mm »), gravé (« gravé » au lieu de relief)."""
    p: dict = {}
    texte = None
    m = re.search(r"[\"«']([^\"»']{1,20})[\"»']", phrase)
    if m:
        texte = m.group(1).strip()
    if not texte:
        m = re.search(r"(?:écrit|ecrit|marqué|marque|nom|prénom|prenom)\s+([A-Za-zÀ-ÿ0-9' -]{1,20})",
                      phrase, re.IGNORECASE)
        if m:
            texte = m.group(1).strip().rstrip(",.").split(",")[0].strip()
    if not texte:
        raise ValueError("Je n'ai pas trouvé le texte à mettre en relief "
                         "(mettez-le entre guillemets, ex. : porte-clé \"Léa\").")
    p["texte"] = texte

    # Dimensions ciblées d'abord (trou/relief/socle), puis longueur = mesure restante.
    p["d_trou"] = _mm(phrase, r"trou")
    p["ep_texte"] = _mm(phrase, r"relief|hauteur de texte|texte en relief de")
    p["ep_socle"] = _mm(phrase, r"socle|base|plaque")
    p["grave"] = bool(re.search(r"grav[ée]", phrase, re.IGNORECASE))
    phrase_sans = re.sub(r"(trou|relief|socle|base|plaque)[^0-9]{0,20}\d+(?:[.,]\d+)?\s*(cm|mm)?",
                         " ", phrase, flags=re.IGNORECASE)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(cm|mm)", phrase_sans, re.IGNORECASE)
    if m:
        v = float(m.group(1).replace(",", "."))
        p["longueur"] = v * 10 if m.group(2).lower() == "cm" else v
    return p


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "piece"
