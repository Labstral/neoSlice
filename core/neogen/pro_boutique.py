# -*- coding: utf-8 -*-
"""neoGen — famille BOUTIQUE & BUREAU PRO (objets vendables par un imprimeur).

Présentoir à gradins, serre-livres, présentoir à bijoux (arche), organiseur de
bureau, porte-cartes de visite, étiquette-prix. Imprimables sans support.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union

from core.neogen.goodies import _extruder, CHEVAUCHEMENT
from core.neogen.geo_utils import union_solides
from core.neogen.formes import _empreinte
from core.neogen.pro_resto import _pancarte_debout

CHEV = CHEVAUCHEMENT


# ═══════════════════════════ PRÉSENTOIR À GRADINS ══════════════════════════
def presentoir_gradins(largeur: float = 140, marches: int = 3,
                       prof_marche: float = 42, h_marche: float = 30) -> trimesh.Trimesh:
    """Présentoir en escalier (produits, mugs, savons…) : N marches pleines.
    Chaque contremarche est verticale, chaque marche horizontale -> aucun
    surplomb. Imprimé tel quel."""
    marches = int(max(2, min(5, marches)))
    solides = []
    for i in range(marches):
        # marche i : de la profondeur i*prof à l'arrière, hauteur (i+1)*h
        y0 = i * prof_marche
        h = (i + 1) * h_marche
        b = box(-largeur / 2, y0, largeur / 2, marches * prof_marche)
        b = b.buffer(2, join_style=1).buffer(-2, join_style=1)
        solides += _extruder(b, h)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ SERRE-LIVRES ══════════════════════════════════
def serre_livres(hauteur: float = 140, base: float = 120, ep: float = 5,
                 largeur: float = 100) -> trimesh.Trimesh:
    """Serre-livres en L : semelle plate (glisse sous les livres) + dosseret
    vertical, renforcé d'un gousset triangulaire. Profil en L extrudé sur la
    largeur, imprimé semelle au plateau -> sans support."""
    semelle = box(0, 0, base, ep)
    dos = box(0, 0, ep, hauteur)
    gousset = Polygon([(ep, ep), (ep + hauteur * 0.42, ep),
                       (ep, ep + hauteur * 0.42)])
    prof = unary_union([semelle, dos, gousset])
    piece = union_solides(_extruder(prof, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ PRÉSENTOIR À BIJOUX (arche) ════════════════════
def presentoir_bijoux(largeur: float = 120, hauteur: float = 130,
                      section: float = 12) -> trimesh.Trimesh:
    """Portique en arche sur socle : on y suspend colliers, bracelets, boucles.
    L'arche (demi-cercle) n'a aucune face < 45° -> impression sans support."""
    from core.neogen.libre import arche
    portique = arche(portee=largeur, hauteur=hauteur, section=section)
    # deux socles sous les pieds pour la stabilité
    socles = []
    for sx in (-largeur / 2, largeur / 2):
        s = trimesh.creation.box((section + 22, 44, 8))
        s.apply_translation([sx, 0, 4])
        socles.append(s)
    piece = union_solides([portique] + socles)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ ORGANISEUR DE BUREAU ══════════════════════════
def organiseur_bureau(longueur: float = 170, largeur: float = 90,
                      hauteur: float = 55) -> trimesh.Trimesh:
    """Organiseur de bureau : grand bac + petit bac + rangée de trous à stylos.
    Caisson à parois fines, séparateur, alvéoles cylindriques traversantes."""
    p, fond = 2.4, 3.0
    emp = _empreinte("rect", longueur, largeur)
    solides = _extruder(emp, fond)
    murs = emp.difference(emp.buffer(-p, join_style=1))
    solides += _extruder(murs, hauteur - fond + CHEV, fond - CHEV)
    # séparateur : coupe transversale au tiers
    xs = -longueur / 2 + longueur * 0.62
    sep = box(xs - p / 2, -largeur / 2 + p, xs + p / 2, largeur / 2 - p)
    solides += _extruder(sep, hauteur - fond + CHEV, fond - CHEV)
    piece = union_solides(solides)
    # rangée de 3 alvéoles à stylos dans le petit compartiment (côté droit)
    trous = []
    for j in range(3):
        c = trimesh.creation.cylinder(radius=7.5, height=hauteur * 3, sections=32)
        c.apply_translation([longueur / 2 - longueur * 0.19,
                             -largeur / 4 + j * (largeur / 4), hauteur])
        trous.append(c)
    piece = trimesh.boolean.difference([piece] + trous, engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ PORTE-CARTES DE VISITE ════════════════════════
def porte_cartes(largeur: float = 95, hauteur: float = 40) -> trimesh.Trimesh:
    """Présentoir à cartes de visite : socle à fente inclinée (les cartes se
    présentent face au client, légèrement inclinées vers l'arrière)."""
    prof = 45.0
    base = box(-largeur / 2, -prof / 2, largeur / 2, prof / 2)
    base = base.buffer(4, join_style=1).buffer(-4, join_style=1)
    corps = union_solides(_extruder(base, hauteur))
    fente = trimesh.creation.box((largeur * 0.8, 5.0, hauteur * 2))
    fente.apply_transform(trimesh.transformations.rotation_matrix(np.radians(15), [1, 0, 0]))
    fente.apply_translation([0, 4, hauteur + hauteur * 0.5 - 5])
    piece = trimesh.boolean.difference([corps, fente], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ ÉTIQUETTE-PRIX ════════════════════════════════
def etiquette_prix(texte: str = "9,90 €", largeur: float = 55, hauteur: float = 30,
                   grave: bool = False, police: str | None = None, style: str | None = None,
                   taille_police: float = 0.0, couleur_objet: str | None = None,
                   couleur_texte: str | None = None):
    """Petite étiquette-prix DEBOUT (rayon, marché, vitrine) : pancarte
    verticale à texte sur socle. Bicolore + style relief/gravé/lisse."""
    return _pancarte_debout(texte, largeur, hauteur, 3.0, 16.0, grave, police,
                            style=style, taille_police=taille_police,
                            couleur_objet=couleur_objet, couleur_texte=couleur_texte)
