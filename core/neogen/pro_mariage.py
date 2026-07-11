# -*- coding: utf-8 -*-
"""neoGen — famille MARIAGE & ÉVÉNEMENTIEL (objets vendables par un imprimeur).

Porte-alliances (cœur), panneau de bienvenue, cornet à pétales, marque-place
cœur, support de plan de table. Imprimables sans support, étanches.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from core.neogen.goodies import _extruder, CHEVAUCHEMENT
from core.neogen.geo_utils import union_solides
from core.neogen.formes import _texte_sur, _revolution_fermee
from core.neogen.formes2 import _coeur_2d
from core.neogen.pro_resto import _pancarte_debout

CHEV = CHEVAUCHEMENT


# ═══════════════════════════ PORTE-ALLIANCES (cœur) ═════════════════════════
def porte_alliances(taille: float = 80, ep: float = 7) -> trimesh.Trimesh:
    """Socle CŒUR avec un petit cône central qui reçoit les alliances. Cœur
    plein bombé sur les bords (rebord) + cône lisse au centre — impression à
    plat, aucun support."""
    from shapely.affinity import scale as _sc
    coeur = _coeur_2d(taille)
    # socle cœur + léger rebord (anneau surélevé sur le pourtour)
    solides = _extruder(coeur, ep)
    rebord = coeur.difference(coeur.buffer(-4.0, join_style=1))
    solides += _extruder(rebord, 2.0 + CHEV, ep - CHEV)
    piece = union_solides(solides)
    # cône central pour enfiler les alliances
    cx, cy = coeur.centroid.x, coeur.centroid.y
    cone = _revolution_fermee([(9, 0), (3.5, 20)])
    cone.apply_translation([cx, cy, ep - CHEV])
    piece = union_solides([piece, cone])
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ PANNEAU DE BIENVENUE ══════════════════════════
def panneau_bienvenue(texte: str = "Bienvenue", largeur: float = 130,
                      hauteur: float = 75, grave: bool = False,
                      police: str | None = None) -> trimesh.Trimesh:
    """Grande pancarte de bienvenue (entrée de salle) : plaque verticale à
    texte sur socle lesté."""
    return _pancarte_debout(texte, largeur, hauteur, 4.5, 40.0, grave, police)


# ═══════════════════════════ CORNET À PÉTALES ══════════════════════════════
def cone_petales(d_haut: float = 70, d_bas: float = 22,
                 hauteur: float = 95) -> trimesh.Trimesh:
    """Cornet à pétales / riz : cône tronqué CREUX (paroi 1.6 mm), large en
    haut, petit fond plat en bas (pose stable, impression sans support). Profil
    en anneau -> ne se referme pas sur l'axe."""
    paroi, fond = 1.8, 2.5
    r_h, r_b = d_haut / 2, d_bas / 2
    r_bi = max(r_b - paroi, 2.0)
    # profil (r, z) : mur extérieur -> rebord haut -> mur intérieur -> plancher
    # de cavité (à z=fond). _revolution_fermee referme proprement sur l'axe.
    profil = [(r_b, 0), (r_h, hauteur), (r_h - paroi, hauteur),
              (r_bi, fond), (0, fond)]
    piece = _revolution_fermee(profil, sections=120)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ MARQUE-PLACE CŒUR ═════════════════════════════
def coeur_marque_place(texte: str = "Merci", taille: float = 55,
                       grave: bool = False,
                       police: str | None = None) -> trimesh.Trimesh:
    """Marque-place / étiquette CŒUR debout : petit cœur à texte dressé sur un
    socle. Imprimé socle au plateau, cœur vertical -> sans support."""
    ep = 4.0
    coeur = _coeur_2d(taille)
    minx, miny, maxx, maxy = coeur.bounds
    # centrer le cœur sur x=0, base à y=0
    from shapely.affinity import translate as _tr
    coeur = _tr(coeur, xoff=-(minx + maxx) / 2, yoff=-miny)
    plaque = union_solides(_extruder(coeur, ep))
    if texte:
        zone = box(-taille * 0.32, taille * 0.28, taille * 0.32, taille * 0.72)
        plaque = _texte_sur(plaque, zone, texte, ep, grave, 0.6, 0.9, police=police)
    plaque.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    plaque.apply_translation([0, 0, -float(plaque.bounds[0][2])])
    ymin = float(plaque.bounds[0][1])
    socle = trimesh.creation.box((taille + 10, 20, 7))
    socle.apply_translation([0, ymin + 20 / 2 - ep - 2, 7 / 2])
    piece = union_solides([plaque, socle])
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ SUPPORT PLAN DE TABLE ═════════════════════════
def support_plan_table(largeur: float = 150, hauteur: float = 55,
                       ep_fente: float = 7) -> trimesh.Trimesh:
    """Socle large et lourd avec une FENTE : reçoit un panneau (plan de table,
    menu A4, ardoise). Fente ouverte vers le haut, légèrement inclinée."""
    prof = 55.0
    base = box(-largeur / 2, -prof / 2, largeur / 2, prof / 2)
    base = base.buffer(6, join_style=1).buffer(-6, join_style=1)
    corps = union_solides(_extruder(base, hauteur))
    fente = trimesh.creation.box((largeur * 0.85, ep_fente, hauteur * 2))
    fente.apply_transform(trimesh.transformations.rotation_matrix(np.radians(7), [1, 0, 0]))
    fente.apply_translation([0, 0, hauteur + hauteur * 0.5 - 7])
    piece = trimesh.boolean.difference([corps, fente], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece
