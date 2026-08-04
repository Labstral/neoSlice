# -*- coding: utf-8 -*-
"""neoGen — PROTOTYPE ISOLÉ (hors neoSlice) : objets 3D avancés.

Au-delà de l'extrusion plate : révolution, ajustements 2 pièces, profils
inclinés, booléens 3D purs.

  vase     surface de RÉVOLUTION ondulée (pente < 45° garantie)
  boite    boîte ronde + couvercle EMBOÎTANT (jeu 0.2 mm) — 3MF 2 corps
  support  support de téléphone (profil incliné, imprimable sans support)
  de       dé à jouer — cube arrondi moins 21 creux CONIQUES (45°, sans support)

Exemples :
  python objets.py --objet vase --hauteur 100 --diametre 60
  python objets.py --objet boite --diametre 50 --hauteur 30
  python objets.py --objet support
  python objets.py --objet de --taille 16

CE FICHIER NE DOIT JAMAIS ÊTRE INTÉGRÉ À neoSlice (projet à part, cf. LISEZMOI).
"""
from __future__ import annotations


import argparse
import sys

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon, MultiPolygon, box
from pathlib import Path

from core.neogen.geo_utils import union_solides

CHEV = 0.3   # chevauchement de fusion entre tranches (mm)

_MESHES = Path(__file__).parent / "meshes"


# ── MODÈLES FIGÉS embarqués (maillages fournis tels quels, non paramétriques) ─
def tour_temperature(echelle: float = 1.0) -> trimesh.Trimesh:
    """Tour de température de référence (PLA + PETG) : maillage validé, chargé
    tel quel depuis un STL embarqué. Une recette ne peut pas IMPORTER un modèle
    figé — d'où ce natif. `echelle` permet de l'agrandir/réduire (défaut 1:1)."""
    m = trimesh.load(str(_MESHES / "tour_temperature.stl"), process=True)
    if isinstance(m, trimesh.Scene):
        m = m.to_geometry()
    if echelle and abs(echelle - 1.0) > 1e-6:
        m.apply_scale(float(echelle))
    m.apply_translation(-m.bounds[0])                 # coin en 0
    c = (m.bounds[0] + m.bounds[1]) / 2
    m.apply_translation([-c[0], -c[1], 0])            # centré XY, base z=0
    return m


# ── TEST DE SURPLOMBS : bras courbé (quart de tour) à degrés gravés ──────────
def test_surplombs(largeur: float = 26.0, hauteur: float = 78.0,
                   ep: float = 4.0, angle_max: float = 70.0) -> trimesh.Trimesh:
    """Bras qui part vertical et bascule progressivement jusqu'à `angle_max`°
    d'inclinaison : la face INFÉRIEURE est le surplomb à tester. Lame MINCE
    (`ep`) dans l'épaisseur radiale, LARGE en Y (`largeur`). Les angles (10°,
    20°, …) sont GRAVÉS sur la face convexe extérieure (le « dessus »), pas sur
    le flanc. Posé sur un petit socle, imprimable tel quel."""
    from shapely.geometry import Polygon
    from core.neogen.geo_utils import union_solides
    from core.neogen.libre import texte_2d          # texte shapely centré à l'origine

    amax = float(angle_max)
    amax_r = np.radians(amax)
    R = float(hauteur) / amax_r                      # longueur d'arc = hauteur
    cx = R                                           # centre du cercle (x, z=0)
    r_out, r_in = R + ep / 2, R - ep / 2

    # profil latéral (vue de côté, plan XZ) = secteur annulaire LISSE + socle.
    # On prolonge le bras au-delà du dernier angle gravé (marge haute) pour que le
    # chiffre du sommet (70) ne soit pas coupé par l'extrémité.
    marge_haut = np.radians(9.0)
    ts = np.linspace(0.0, amax_r + marge_haut, 88)
    ext = [(cx - r_out * np.cos(t), r_out * np.sin(t)) for t in ts]
    inn = [(cx - r_in * np.cos(t), r_in * np.sin(t)) for t in ts[::-1]]
    pts = ext + inn
    pts += [(cx - r_in, 0.0), (cx - r_out - 6, 0.0)]   # descend au socle
    prof = Polygon(pts).buffer(0)
    bande = trimesh.creation.extrude_polygon(prof, largeur)      # épaisseur -> Z
    # profil (XY) dressé : Y(hauteur)->Z, Z(épaisseur)->Y
    bande.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    bande.apply_translation([0, largeur / 2, 0])                 # largeur centrée en Y
    # socle : semelle sous le pied
    socle = trimesh.creation.box(extents=[20, largeur, 4])
    socle.apply_translation([cx - r_out + 2, 0, 2])
    corps = union_solides([bande, socle])
    centre = np.array([cx, 0.0, 0.0])

    # gravure des angles sur la face convexe extérieure
    pas_arc = R * np.radians(10.0)                    # écart d'arc entre 2 stations
    h_txt = min(largeur * 0.34, pas_arc * 0.55)       # assez petit pour ne pas se toucher
    graveurs = []
    for d in range(10, int(amax) + 1, 10):
        tr = np.radians(float(d))
        p = np.array([R * (1 - np.cos(tr)), 0.0, R * np.sin(tr)])
        radial = (p - centre) / R                    # normale extérieure (convexe)
        tangente = np.array([np.sin(tr), 0.0, np.cos(tr)])   # vers la pointe
        g2d = texte_2d(str(d), h_txt)
        txt = trimesh.util.concatenate(_extruder(g2d, 2.0))
        txt.apply_translation([0, 0, -1.0])          # centré sur l'épaisseur de gravure
        # Repère de lecture, vu du DEHORS (regard = -radial), pointe en HAUT :
        #   X texte (droite du lecteur) = -Y monde ; Y texte (haut) = tangente vers
        #   la pointe ; Z texte (face lisible) = radial extérieur. Rotation propre
        #   (droitier) -> chiffres à l'endroit, pas en miroir.
        M = np.eye(4)
        M[:3, 0] = [0.0, -1.0, 0.0]
        M[:3, 1] = tangente
        M[:3, 2] = radial
        txt.apply_transform(M)
        txt.apply_translation(p + radial * (ep / 2))  # posé sur la peau extérieure
        graveurs.append(txt)
    if graveurs:
        corps = trimesh.boolean.difference(
            [corps, union_solides(graveurs)], engine="manifold")

    corps.apply_translation(-corps.bounds[0] * [0, 0, 1])   # base z=0
    c = (corps.bounds[0] + corps.bounds[1]) / 2
    corps.apply_translation([-c[0], -c[1], 0])              # centré XY
    return corps


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


# ── VASE : surface de révolution ondulée ─────────────────────────────────────
def vase(hauteur: float = 100, diametre: float = 60, paroi: float = 2.4,
         fond: float = 2.4, ondulations: int = 5, amplitude: float = 3.0) -> trimesh.Trimesh:
    """Profil sinusoïdal tourné autour de Z. La pente radiale est bornée à 40°
    (< 45°) pour imprimer SANS support ; amplitude réduite si nécessaire."""
    r0 = diametre / 2.0
    # pente max = amplitude * (2*pi*ondulations / hauteur) ; on borne a tan(40°)
    k = 2 * np.pi * max(0, int(ondulations)) / hauteur
    if k <= 0 or amplitude <= 0:            # 0 ondulation → vase lisse (pas de /0)
        k, amp = 1.0, 0.0
    else:
        amp = min(amplitude, np.tan(np.radians(40)) / k)

    def r_ext(z):
        return r0 + amp * np.sin(k * z)

    n = 160
    zs = np.linspace(0, hauteur, n)
    # profil FERMÉ : paroi extérieure (bas -> haut), retour intérieur, fond, axe
    ext = [(float(r_ext(z)), float(z)) for z in zs]
    intr = [(max(0.6, float(r_ext(z)) - paroi), float(z)) for z in zs[::-1] if z >= fond]
    profil = [(0.0, 0.0)] + ext + intr + [(0.0, float(fond)), (0.0, 0.0)]
    piece = trimesh.creation.revolve(np.array(profil), sections=128)
    piece.apply_translation(-piece.bounds[0] * [1, 1, 1] * [0, 0, 1])  # z=0 au sol
    return piece


# ── BOÎTE + COUVERCLE emboîtant (jeu d'ajustement) ───────────────────────────
def boite(diametre: float = 50, hauteur: float = 30, paroi: float = 2.0,
          fond: float = 2.0, jeu: float = 0.2, forme: str = "ronde",
          cote: float | None = None, longueur: float | None = None,
          largeur: float | None = None) -> trimesh.Scene:
    """Boîte + couvercle à lèvre, RONDE, CARRÉE ou RECTANGULAIRE (coins arrondis). La lèvre du
    couvercle entre DANS la boîte avec `jeu` mm par côté (ajustement doux).
    3MF 2 corps côte à côte. Les décalages intérieurs se font par buffer
    NÉGATIF de l'empreinte -> la même mécanique marche pour toute forme."""
    if forme == "rectangulaire":
        L = float(longueur or diametre)
        W = float(largeur or diametre)
        rc = min(4.0, min(L, W) * 0.12)               # coins arrondis
        emp = box(-(L / 2 - rc), -(W / 2 - rc),
                  L / 2 - rc, W / 2 - rc).buffer(rc, join_style=1)
    elif forme == "carree":
        c = float(cote or diametre)
        rc = min(4.0, c * 0.12)                       # coins arrondis
        emp = box(-(c / 2 - rc), -(c / 2 - rc),
                  c / 2 - rc, c / 2 - rc).buffer(rc, join_style=1)
    else:
        emp = Point(0, 0).buffer(diametre / 2.0, resolution=96)

    # corps : fond plein + murs (anneau = empreinte moins son retrait de paroi)
    anneau = emp.difference(emp.buffer(-paroi, join_style=1))
    corps = union_solides(
        _extruder(emp, fond) +
        _extruder(anneau, hauteur - fond + CHEV, fond - CHEV))
    corps.apply_translation(-corps.bounds[0])

    # couvercle : chapeau plein + lèvre en retrait de (paroi + jeu)
    levre_ext = emp.buffer(-(paroi + jeu), join_style=1)
    levre = levre_ext.difference(levre_ext.buffer(-paroi, join_style=1))
    couvercle = union_solides(
        _extruder(emp, fond) +
        _extruder(levre, 6.0 + CHEV, fond - CHEV))   # lèvre de 6 mm
    couvercle.apply_translation(-couvercle.bounds[0])
    larg = float(emp.bounds[2] - emp.bounds[0])
    couvercle.apply_translation([larg + 8, 0, 0])    # posé à côté sur le plateau

    scene = trimesh.Scene()
    scene.add_geometry(corps, node_name="boite_corps", geom_name="boite_corps")
    scene.add_geometry(couvercle, node_name="boite_couvercle", geom_name="boite_couvercle")
    return scene


# ── SUPPORT DE TÉLÉPHONE : profil incliné extrudé ────────────────────────────
def support_tel(largeur: float = 70, angle_deg: float = 65, ep: float = 8,
                hauteur: float = 92) -> trimesh.Trimesh:
    """Support téléphone / TABLETTE : dossier en coin dont la face avant est une
    RAMPE DROITE sur toute sa longueur (l'appareil s'y appuie), petite lèvre
    de retenue à l'avant et cuvette où repose le bas. Aucune fente, aucune
    collerette : un seul profil convexe, imprimable posé sur sa base. `largeur`
    et `hauteur` du dossier réglables (tablette = plus large / plus haut)."""
    a = np.radians(angle_deg)
    cot = 1.0 / np.tan(a)                      # recul horizontal par mm de hauteur
    h = float(hauteur)                         # hauteur du dossier
    y_cuv = 6.0                                # fond de la cuvette d'appui
    x_lip0, x_lip1 = 0.0, 8.0                  # lèvre de retenue (avant)
    h_lip = 15.0
    x_ramp = 20.0                              # départ de la rampe droite
    x_apex = x_ramp + h * cot                  # sommet du dossier
    x_back = x_apex + 22.0                     # pied arrière au sol
    # profil (X = profondeur, Y = hauteur), sens antihoraire — UNE rampe droite
    # unique de (x_ramp, y_cuv) à (x_apex, h) : aucune cassure.
    prof = Polygon([
        (x_lip0, 0.0), (x_lip0, h_lip), (x_lip1, h_lip), (x_lip1, y_cuv),
        (x_ramp, y_cuv), (x_apex, h), (x_back, h * 0.34), (x_back, 0.0),
    ])
    prof = prof.buffer(1.5, join_style=1).buffer(-1.5, join_style=1)   # angles doux
    if isinstance(prof, MultiPolygon):
        prof = max(prof.geoms, key=lambda g: g.area)
    piece = trimesh.util.concatenate(_extruder(prof, largeur))
    # profil en XY -> on le dresse : la hauteur (Y) devient verticale (Z)
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


# ── DÉ À JOUER : booléens 3D purs (creux coniques imprimables) ───────────────
_PIPS = {   # positions (u, v) par valeur, grille -1/0/+1
    1: [(0, 0)],
    2: [(-1, -1), (1, 1)],
    3: [(-1, -1), (0, 0), (1, 1)],
    4: [(-1, -1), (-1, 1), (1, -1), (1, 1)],
    5: [(-1, -1), (-1, 1), (0, 0), (1, -1), (1, 1)],
    6: [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 0), (1, 1)],
}
# faces du dé : (valeur, normale, axes u/v) — 1 opposé à 6, 2-5, 3-4 (somme 7)
_FACES = [
    (1, [0, 0, 1]), (6, [0, 0, -1]),
    (2, [1, 0, 0]), (5, [-1, 0, 0]),
    (3, [0, 1, 0]), (4, [0, -1, 0]),
]


def de_a_jouer(taille: float = 16.0) -> trimesh.Trimesh:
    """VRAI dé : arêtes et coins arrondis PARTOUT (enveloppe convexe de 8
    sphères aux coins = cube adouci exact), MOINS creux coniques (parois ~48°
    -> imprimable sans support, contrairement à des creux sphériques)."""
    r_coin = taille * 0.12
    d = taille / 2 - r_coin
    spheres = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                s = trimesh.creation.icosphere(subdivisions=3, radius=r_coin)
                s.apply_translation([sx * d, sy * d, sz * d])
                spheres.append(s)
    cube = trimesh.util.concatenate(spheres).convex_hull   # cube arrondi exact

    r_pip, h_pip = taille * 0.11, taille * 0.13   # cône ~50° (imprimable)
    ecart = taille * 0.26
    cones = []
    for val, normale in _FACES:
        n = np.array(normale, float)
        # base orthonormée (u, v) de la face
        u = np.array([0, 0, 1.0]) if abs(n[2]) < 0.5 else np.array([1.0, 0, 0])
        u = np.cross(n, u); u /= np.linalg.norm(u)
        v = np.cross(n, u)
        centre_face = n * (taille / 2)
        for (gu, gv) in _PIPS[val]:
            c = trimesh.creation.cone(radius=r_pip, height=h_pip, sections=48)
            # cone : base en z=0, pointe en z=h -> on le retourne pour pointer DANS le dé
            c.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
            c.apply_translation([0, 0, 0.05])     # base légèrement HORS de la face
            # aligne +z du cone sur -n (pointe vers l'intérieur)
            align = trimesh.geometry.align_vectors([0, 0, -1], -n)
            c.apply_transform(align)
            c.apply_translation(centre_face + u * (gu * ecart) + v * (gv * ecart))
            cones.append(c)
    creux = union_solides(cones)
    piece = trimesh.boolean.difference([cube, creux], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece
