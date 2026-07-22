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
                      police: str | None = None, style: str | None = None,
                      taille_police: float = 0.0, couleur_objet: str | None = None,
                      couleur_texte: str | None = None):
    """Grande pancarte de bienvenue (entrée de salle) : plaque verticale à
    texte sur socle lesté. Bicolore + style relief/gravé/lisse."""
    return _pancarte_debout(texte, largeur, hauteur, 4.5, 44.0, grave, police,
                            style=style, taille_police=taille_police,
                            couleur_objet=couleur_objet, couleur_texte=couleur_texte,
                            inclinaison=82.0)


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
                       grave: bool = False, police: str | None = None,
                       style: str | None = None, taille_police: float = 0.0,
                       couleur_objet: str | None = None, couleur_texte: str | None = None):
    """Marque-place / étiquette CŒUR debout : petit cœur à texte dressé sur un
    socle. Imprimé socle au plateau, cœur vertical -> sans support. Bicolore + style."""
    from shapely.affinity import translate as _tr, scale as _scale
    from core.neogen.goodies import texte_multilignes, ajuster_dans, RELIEF_ACTIF
    from core.neogen import bicolore as _bic
    ep = 4.0
    style = style if style in ("relief", "grave", "lisse") else ("grave" if grave else "relief")
    bicolore = bool(couleur_objet and couleur_texte)
    ep_texte = 0.6
    if RELIEF_ACTIF is not None:
        ep_texte = max(0.3, float(RELIEF_ACTIF))
    coeur = _coeur_2d(taille)
    minx, miny, maxx, maxy = coeur.bounds
    coeur = _tr(coeur, xoff=-(minx + maxx) / 2, yoff=-miny)   # x=0, base à y=0

    texte_2d = None
    if texte and str(texte).strip():
        zw, zh = taille * 0.64, taille * 0.44
        mp = texte_multilignes(str(texte), police=police)
        if taille_police and taille_police > 0:
            f = float(taille_police) / 10.0
            mp = _scale(mp, xfact=f, yfact=f, origin=(0, 0))
        mp = ajuster_dans(mp, zw, zh)
        mnx, mny, mxx, mxy = mp.bounds
        mp = _tr(mp, xoff=-(mnx + mxx) / 2, yoff=taille * 0.5 - (mny + mxy) / 2)
        texte_2d = unary_union(list(mp.geoms))

    if texte_2d is not None:
        heart_body, texte_body = _bic.socle_texte(coeur, texte_2d, ep, ep_texte, style)
    else:
        heart_body = union_solides(_extruder(coeur, ep))
        texte_body = None

    R = trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0])
    heart_body.apply_transform(R)
    if texte_body is not None:
        texte_body.apply_transform(R)
    dz = -float(heart_body.bounds[0][2])
    heart_body.apply_translation([0, 0, dz])
    if texte_body is not None:
        texte_body.apply_translation([0, 0, dz])

    # socle CENTRÉ sous le cœur (en X ET en profondeur Y) : le cœur, mince, est
    # placé au milieu du socle et non sur son bord avant.
    hb = heart_body.bounds
    hy = (hb[0][1] + hb[1][1]) / 2.0
    socle = trimesh.creation.box((taille + 10, 22, 7))
    socle.apply_translation([0, hy, 7 / 2])
    objet_body = union_solides([heart_body, socle])

    if bicolore and texte_body is not None:
        s = _bic.scene(objet_body, texte_body, couleur_objet, couleur_texte)
        fus = trimesh.util.concatenate(list(s.geometry.values()))
        off = -fus.bounds[0]
        for g in s.geometry.values():
            g.apply_translation(off)
        return s
    piece = union_solides([objet_body, texte_body]) if texte_body is not None else objet_body
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
