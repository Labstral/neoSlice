# -*- coding: utf-8 -*-
"""neoGen — famille RESTAURATION (objets vendables par un imprimeur 3D).

Numéros de table, chevalets/porte-cartes, porte-menu, porte-addition,
marque-places, panneau « Réservé », porte-couverts. Tout est pensé imprimable
SANS support (bases plates, pentes ≥ 45°, reliefs soudés par union) et étanche.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union

from core.neogen.goodies import _extruder, texte_multilignes, CHEVAUCHEMENT
from core.neogen.geo_utils import union_solides
from core.neogen.formes import _texte_sur, _empreinte

CHEV = CHEVAUCHEMENT


def _texte_2d(txt: str, hauteur: float, police: str | None = None):
    mp = texte_multilignes(txt, hauteur, police=police)
    return unary_union(list(mp.geoms))


# ═══════════════════════════ NUMÉRO DE TABLE ════════════════════════════════
def numero_table(texte: str = "12", hauteur: float = 80, ep: float = 10,
                 police: str | None = None) -> trimesh.Trimesh:
    """Numéro de table AUTOPORTANT : chiffres épais dressés sur un socle plat
    lesté. Imprimé couché sur la face arrière -> aucun support. (Param nommé
    `texte` pour le pont catalogue ; contient le numéro.)"""
    num = (str(texte) or "12").strip()[:3]
    chiffres = _texte_2d(num, hauteur, police)
    minx, miny, maxx, maxy = chiffres.bounds
    # relie les chiffres par une petite barre basse (le « 1 » et le « 2 » ne
    # sont pas connectés sinon) + socle qui déborde pour la stabilité
    barre = box(minx - 4, miny, maxx + 4, miny + hauteur * 0.10)
    numero_2d = unary_union([chiffres, barre])
    numero_solide = union_solides(_extruder(numero_2d, ep))
    numero_solide.apply_transform(
        trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    numero_solide.apply_translation([0, 0, -float(numero_solide.bounds[0][2])])
    # socle plinthe : bloc élargi sous le numéro
    xw = (maxx - minx) + 24
    socle = trimesh.creation.box((xw, 30, 8))
    ymid = float(numero_solide.bounds[0][1] + numero_solide.bounds[1][1]) / 2
    socle.apply_translation([(minx + maxx) / 2, ymid, 8 / 2 - 1])
    piece = union_solides([numero_solide, socle])
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════ CHEVALET / PANCARTE DEBOUT ════════════════════════
def _pancarte_debout(texte: str, largeur: float, hauteur: float, ep: float,
                     prof_socle: float, grave: bool,
                     police: str | None) -> trimesh.Trimesh:
    """Plaque à texte dressée VERTICALE sur un socle lesté. Imprimée socle au
    plateau : le mur vertical n'a aucun surplomb, le texte est en façade."""
    plaque2d = box(-largeur / 2, 0, largeur / 2, hauteur)
    plaque2d = plaque2d.buffer(4, join_style=1).buffer(-4, join_style=1)
    plaque = union_solides(_extruder(plaque2d, ep))
    if texte:
        zone = box(-largeur / 2 + 6, 6, largeur / 2 - 6, hauteur - 6)
        plaque = _texte_sur(plaque, zone, texte, ep, grave, min(0.7, ep * 0.35),
                            0.85, police=police)
    plaque.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    plaque.apply_translation([0, 0, -float(plaque.bounds[0][2])])
    ymin = float(plaque.bounds[0][1])
    h_socle = max(6.0, ep + 3)
    socle = trimesh.creation.box((largeur + 8, prof_socle, h_socle))
    socle.apply_translation([0, ymin + prof_socle / 2 - ep - 2, h_socle / 2])
    piece = union_solides([plaque, socle])
    piece.apply_translation(-piece.bounds[0])
    return piece


def chevalet(largeur: float = 95, hauteur: float = 55, texte: str = "Réservé",
             grave: bool = False, police: str | None = None) -> trimesh.Trimesh:
    """Pancarte de table à texte (chevalet « Réservé », menu du jour…) :
    plaque verticale à texte en relief sur socle lesté. Sans support."""
    return _pancarte_debout(texte, largeur, hauteur, 4.0, 28.0, grave, police)


# ═══════════════════════════ PORTE-MENU (fente) ═════════════════════════════
def porte_menu(largeur: float = 100, epaisseur_fente: float = 6,
               hauteur: float = 45) -> trimesh.Trimesh:
    """Socle lesté avec une FENTE verticale : on y glisse un menu (carton/A5).
    La fente est ouverte vers le haut -> aucun surplomb."""
    prof = 40.0
    base = box(-largeur / 2, -prof / 2, largeur / 2, prof / 2)
    base = base.buffer(4, join_style=1).buffer(-4, join_style=1)
    corps = union_solides(_extruder(base, hauteur))
    # fente : boîte verticale ouverte en haut, inclinée de 8° pour tenir le menu
    fente = trimesh.creation.box((largeur * 0.82, epaisseur_fente, hauteur * 2))
    fente.apply_transform(trimesh.transformations.rotation_matrix(np.radians(8), [1, 0, 0]))
    fente.apply_translation([0, 0, hauteur + hauteur * 0.5 - 6])
    piece = trimesh.boolean.difference([corps, fente], engine="manifold")
    piece.apply_translation(-piece.bounds[0] * [0, 0, 1])
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ PORTE-ADDITION ═════════════════════════════════
def porte_addition(largeur: float = 95, hauteur: float = 60) -> trimesh.Trimesh:
    """Présentoir à addition : plaquette inclinée sur pied, avec une lèvre
    basse qui retient le ticket/la note. Imprimé sur le dos -> sans support."""
    ep = 4.0
    a = np.radians(68)
    cot = 1.0 / np.tan(a)
    # profil (X profondeur, Y hauteur) : dos incliné + pied + lèvre avant
    dos = Polygon([(0, 0), (ep / np.sin(a), 0),
                   (hauteur * cot + ep / np.sin(a), hauteur),
                   (hauteur * cot, hauteur)])
    pied = box(0, 0, hauteur * cot + 30, ep)
    levre = box(hauteur * cot + 22, 0, hauteur * cot + 30, 12)
    prof = unary_union([dos, pied, levre]).buffer(1.0, join_style=1).buffer(-1.0, join_style=1)
    piece = union_solides(_extruder(prof, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ MARQUE-PLACE ═══════════════════════════════════
def marque_place(texte: str = "Invité", largeur: float = 70, hauteur: float = 26,
                 grave: bool = False, police: str | None = None) -> trimesh.Trimesh:
    """Marque-place nominatif DEBOUT : petite pancarte verticale sur socle,
    texte en relief ou gravé. Imprimé sans support."""
    return _pancarte_debout(texte, largeur, hauteur, 3.0, 18.0, grave, police)


# ═══════════════════════════ PANNEAU « RÉSERVÉ » ════════════════════════════
def panneau_reserve(texte: str = "Réservé", largeur: float = 95, hauteur: float = 55,
                    grave: bool = False, police: str | None = None) -> trimesh.Trimesh:
    """Chevalet « Réservé » (ou tout autre texte) : pancarte inclinée."""
    return chevalet(largeur=largeur, hauteur=hauteur, texte=texte or "Réservé",
                    grave=grave, police=police)


# ═══════════════════════════ PORTE-COUVERTS ═════════════════════════════════
def porte_couverts(longueur: float = 180, largeur: float = 55,
                   hauteur: float = 45) -> trimesh.Trimesh:
    """Bac à couverts / serviettes de table : caisson ouvert à deux
    compartiments (séparateur central), coins arrondis."""
    p, fond = 2.4, 3.0
    emp = _empreinte("rect", longueur, largeur)
    solides = _extruder(emp, fond)
    murs = emp.difference(emp.buffer(-p, join_style=1))
    solides += _extruder(murs, hauteur - fond + CHEV, fond - CHEV)
    sep = box(-p / 2, -largeur / 2 + p, p / 2, largeur / 2 - p)
    solides += _extruder(sep, hauteur - fond + CHEV, fond - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece
