# -*- coding: utf-8 -*-
"""neoGen — bibliothèque de formes, lot 2 : déco, jeux, cuisine créative.

Même contrat que formes.py : pièces étanches, posées au sol, imprimables.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from shapely.affinity import rotate as shp_rotate

from core.neogen.geo_utils import union_solides
from core.neogen.goodies import _extruder, texte_multilignes, CHEVAUCHEMENT
from core.neogen.formes import (
    _empreinte, _revolution_fermee, _texte_sur, _recipient,
)

CHEV = CHEVAUCHEMENT


# ═══════════════════════════════ DÉCO / PERSO ═══════════════════════════════
def _etoile_2d(branches: int, d_ext: float, ratio: float = 0.45) -> Polygon:
    pts = []
    for i in range(branches * 2):
        r = d_ext / 2 if i % 2 == 0 else d_ext / 2 * ratio
        a = np.pi / 2 + i * np.pi / branches
        pts.append((np.cos(a) * r, np.sin(a) * r))
    return Polygon(pts)


def _coeur_2d(taille: float) -> Polygon:
    """Cœur paramétrique (2 disques + pointe), largeur = taille."""
    r = taille / 4
    g = Point(-r, r * 0.9).buffer(r * 1.08, resolution=64)
    d = Point(r, r * 0.9).buffer(r * 1.08, resolution=64)
    pointe = Polygon([(-taille / 2, r * 0.8), (taille / 2, r * 0.8), (0, -taille / 2)])
    c = unary_union([g, d, pointe])
    return c.buffer(1, join_style=1).buffer(-1, join_style=1)


def ornement_etoile(diametre: float = 80, branches: int = 5, ep: float = 4,
                    suspension: bool = True, texte: str = "",
                    grave: bool = True) -> trimesh.Trimesh:
    """Étoile déco (sapin, guirlande) avec trou de suspension."""
    emp = _etoile_2d(int(branches), diametre)
    if suspension:
        _minx, _miny, _maxx, maxy = emp.bounds
        emp = emp.difference(Point(0, maxy - 4).buffer(1.8, resolution=32))
    piece = union_solides(_extruder(emp, ep))
    if texte:
        piece = _texte_sur(piece, _empreinte("rond", diametre * 0.45), texte, ep, grave, 0.8)
    piece.apply_translation(-piece.bounds[0])
    return piece


def coeur_deco(taille: float = 70, ep: float = 5, suspension: bool = False,
               texte: str = "", grave: bool = False) -> trimesh.Trimesh:
    """Cœur déco / cadeau, texte relief ou gravé."""
    emp = _coeur_2d(taille)
    if suspension:
        _minx, _miny, _maxx, maxy = emp.bounds
        emp = emp.difference(Point(0, maxy - 4).buffer(1.8, resolution=32))
    piece = union_solides(_extruder(emp, ep))
    if texte:
        piece = _texte_sur(piece, _empreinte("rond", taille * 0.5), texte, ep, grave, 1.0)
    piece.apply_translation(-piece.bounds[0])
    return piece


def lettre_3d(caractere: str = "A", hauteur: float = 100,
              ep: float = 15) -> trimesh.Trimesh:
    """Lettre ou chiffre géant autoportant (déco étagère, initiale)."""
    car = (caractere or "A").strip()[:3]
    mp = texte_multilignes(car, hauteur)
    piece = union_solides(_extruder(unary_union(list(mp.geoms)), ep))
    piece.apply_translation(-piece.bounds[0])
    return piece


def numero_maison(numero: str = "12", hauteur: float = 120) -> trimesh.Trimesh:
    """Numéro de maison : chiffres en relief sur plaque à trous de vis."""
    mp = texte_multilignes(str(numero), hauteur * 0.55)
    minx, miny, maxx, maxy = mp.bounds
    emp = box(minx - 14, miny - 12, maxx + 14, maxy + 12)
    emp = emp.buffer(4, join_style=1).buffer(-4, join_style=1)
    emp = emp.difference(Point(minx - 7, (miny + maxy) / 2).buffer(2.2, resolution=32))
    emp = emp.difference(Point(maxx + 7, (miny + maxy) / 2).buffer(2.2, resolution=32))
    solides = _extruder(emp, 4)
    solides += _extruder(unary_union(list(mp.geoms)), 3 + CHEV, 4 - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def trophee(hauteur: float = 120, texte: str = "", grave: bool = False) -> trimesh.Trimesh:
    """Trophée coupe (révolution) sur socle carré, bande porte-texte."""
    h = hauteur
    coupe = _revolution_fermee([
        (h * 0.16, 0), (h * 0.16, h * 0.04), (h * 0.05, h * 0.08),
        (h * 0.035, h * 0.30), (h * 0.10, h * 0.45), (h * 0.16, h * 0.62),
        (h * 0.17, h * 0.80), (h * 0.155, h * 0.80), (h * 0.145, h * 0.62),
        (h * 0.085, h * 0.46), (h * 0.05, h * 0.34),
    ])
    socle_emp = _empreinte("carre", h * 0.38)
    socle = union_solides(_extruder(socle_emp, h * 0.07))
    coupe.apply_translation([0, 0, h * 0.07 - CHEV])
    piece = union_solides([socle, coupe])
    if texte:
        bande = box(-h * 0.17, -h * 0.19 - 1.6, h * 0.17, -h * 0.19 + 1)
        piece = union_solides([piece] + _extruder(bande, h * 0.055))
        piece = _texte_sur(piece, bande, texte, h * 0.055, grave, 0.8)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════════ JEUX / LOISIRS ═════════════════════════════
def jeton(diametre: float = 40, ep: float = 3.6, texte: str = "",
          grave: bool = True) -> trimesh.Trimesh:
    """Jeton (poker, caddie) : disque + anneau décoratif en léger relief."""
    emp = _empreinte("rond", diametre)
    solides = _extruder(emp, ep - 0.8)
    anneau = Point(0, 0).buffer(diametre / 2, resolution=96).difference(
        Point(0, 0).buffer(diametre / 2 - 2.5, resolution=96))
    centre = Point(0, 0).buffer(diametre / 2 - 4.5, resolution=96)
    haut = unary_union([anneau, centre])
    solides += _extruder(haut, 0.8 + CHEV, ep - 0.8 - CHEV)
    piece = union_solides(solides)
    if texte:
        piece = _texte_sur(piece, _empreinte("rond", diametre * 0.62), texte, ep, grave, 0.8)
    piece.apply_translation(-piece.bounds[0])
    return piece


def socle_figurine(forme: str = "rond", diametre: float = 60, hauteur: float = 8,
                   texte: str = "", grave: bool = True) -> trimesh.Trimesh:
    """Socle de figurine à base élargie, texte sur le bandeau avant."""
    emp = _empreinte(forme, diametre)
    solides = _extruder(emp.buffer(2, join_style=1), hauteur * 0.4)
    solides += _extruder(emp, hauteur * 0.6 + CHEV, hauteur * 0.4 - CHEV)
    piece = union_solides(solides)
    if texte:
        bande = box(-diametre * 0.35, -diametre / 2 - 2, diametre * 0.35,
                    -diametre / 2 + diametre * 0.2)
        piece = _texte_sur(piece, bande, texte, hauteur, grave, 0.8, 0.85)
    piece.apply_translation(-piece.bounds[0])
    return piece


def pion_jeu(hauteur: float = 40) -> trimesh.Trimesh:
    """Pion de jeu de société (profil tourné)."""
    h = hauteur
    return _revolution_fermee([
        (h * 0.28, 0), (h * 0.28, h * 0.08), (h * 0.12, h * 0.22),
        (h * 0.09, h * 0.45), (h * 0.16, h * 0.58), (h * 0.09, h * 0.68),
        (h * 0.14, h * 0.86), (h * 0.02, h),
    ])


def porte_cartes_jeu(largeur: float = 250, rangees: int = 3) -> trimesh.Trimesh:
    """Support de cartes à jouer : rainures inclinées en gradins."""
    base = box(0, 0, rangees * 22 + 10, 5)
    prof2d = [base]
    for i in range(int(rangees)):
        x0 = 8 + i * 22
        prof2d.append(shp_rotate(box(x0, 4.9, x0 + 3, 5 + 24), -12, origin=(x0, 5)))
    prof = unary_union(prof2d).buffer(0.8, join_style=1).buffer(-0.8, join_style=1)
    piece = union_solides(_extruder(prof, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ CUISINE CRÉATIVE / DIVERS ══════════════════════
def emporte_piece(forme: str = "coeur", taille: float = 70) -> trimesh.Trimesh:
    """Emporte-pièce à biscuits : bande de rigidité + lame fine."""
    if forme == "coeur":
        emp = _coeur_2d(taille)
    elif forme == "etoile":
        emp = _etoile_2d(5, taille)
    else:
        emp = _empreinte(forme, taille)
    lame = emp.buffer(1.0, join_style=1).difference(emp)
    renfort = emp.buffer(3.2, join_style=1).difference(emp)
    solides = _extruder(renfort, 5)
    solides += _extruder(lame, 13 + CHEV, 5 - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def tire_fermeture(longueur: float = 30, texte: str = "") -> trimesh.Trimesh:
    """Tirette de fermeture éclair (zipper pull) avec trou d'attache."""
    emp = _empreinte("rect", longueur, longueur * 0.45)
    minx, miny, maxx, maxy = emp.bounds
    emp = emp.difference(Point(minx + 4, 0).buffer(2.0, resolution=32))
    piece = union_solides(_extruder(emp, 2.4))
    if texte:
        zone = box(minx + 8, miny, maxx - 2, maxy)
        piece = _texte_sur(piece, zone, texte, 2.4, True, 0.6, 0.8)
    piece.apply_translation(-piece.bounds[0])
    return piece


def regle(longueur: float = 150, largeur: float = 25) -> trimesh.Trimesh:
    """Règle avec graduations gravées (traits longs tous les 10 mm)."""
    ep = 2.4
    emp = box(0, 0, longueur, largeur)
    solides = _extruder(emp, ep - 0.6)
    grads = []
    x = 0.0
    while x <= longueur + 0.1:
        haut = 8 if (round(x) % 10 == 0) else 4.5
        grads.append(box(x - 0.35, largeur - haut, x + 0.35, largeur))
        x += 5.0
    haut_2d = emp.difference(unary_union(grads))
    solides += _extruder(haut_2d, 0.6 + CHEV, ep - 0.6 - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def range_cable(diametre: float = 70, largeur: float = 30) -> trimesh.Trimesh:
    """Bobine range-câble : 2 flasques + noyau, fente d'insertion."""
    d, l = diametre, largeur
    f1 = trimesh.creation.cylinder(radius=d / 2, height=3, sections=96)
    f1.apply_translation([0, 0, 1.5])
    f2 = f1.copy()
    f2.apply_translation([0, 0, l - 3])
    noyau = trimesh.creation.cylinder(radius=d / 2 - 12, height=l, sections=96)
    noyau.apply_translation([0, 0, l / 2])
    piece = union_solides([f1, noyau, f2])
    fente = trimesh.creation.box((4, d, l * 0.5))
    fente.apply_translation([d / 2 - 8, 0, l / 2])
    piece = trimesh.boolean.difference([piece, fente], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


def oeuf_pied(hauteur: float = 55) -> trimesh.Trimesh:
    """Présentoir à œuf / balle sur pied (révolution évasée)."""
    h = hauteur
    return _revolution_fermee([
        (h * 0.35, 0), (h * 0.33, h * 0.06), (h * 0.10, h * 0.28),
        (h * 0.08, h * 0.55), (h * 0.30, h * 0.82), (h * 0.36, h),
        (h * 0.33, h), (h * 0.26, h * 0.84), (h * 0.055, h * 0.58),
    ])


def cale_porte(longueur: float = 90, hauteur: float = 30) -> trimesh.Trimesh:
    """Cale de porte (coin, angle ~18°)."""
    prof = Polygon([(0, 0), (longueur, 0), (longueur, 3), (8, hauteur), (0, hauteur)])
    prof = prof.buffer(1, join_style=1).buffer(-1, join_style=1)
    piece = union_solides(_extruder(prof, 35))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece
