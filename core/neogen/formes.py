# -*- coding: utf-8 -*-
"""neoGen — bibliothèque de formes paramétriques (générateurs déterministes).

Chaque fonction produit UNE pièce trimesh étanche, posée sur le plateau,
pensée impression FDM (pentes ≥ 45°, parois ≥ 1.2 mm, gravures non
traversantes). Les recettes réutilisent les briques éprouvées :
  - tranches 2D extrudées (gravure/relief/poche SANS booléens 3D fragiles)
  - union manifold réelle (geo_utils.union_solides) -> zéro face interne
  - révolution pour les profils tournés (pots, pieds, coupes...)

Le catalogue (catalogue.py) expose ces générateurs avec leurs schémas de
paramètres pour le menu « Bibliothèque » de neoGen.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely.affinity import translate, rotate as shp_rotate

from core.neogen.geo_utils import union_solides
from core.neogen.goodies import (
    _extruder, socle_avec_texte, texte_multilignes, ajuster_dans, CHEVAUCHEMENT,
)

CHEV = CHEVAUCHEMENT


# ═══════════════════════════════════ Briques ════════════════════════════════
def _empreinte(forme: str, taille: float, taille2: float | None = None) -> Polygon:
    """Empreinte 2D : rond / carre / hexagone / rect (taille2 = profondeur)."""
    if forme == "carre":
        r = min(4.0, taille * 0.12)
        return box(-(taille / 2 - r), -(taille / 2 - r),
                   taille / 2 - r, taille / 2 - r).buffer(r, join_style=1)
    if forme == "hexagone":
        a = np.linspace(0, 2 * np.pi, 6, endpoint=False) + np.pi / 6
        return Polygon([(np.cos(t) * taille / 2, np.sin(t) * taille / 2) for t in a])
    if forme == "rect":
        y = taille2 or taille * 0.7
        r = min(4.0, taille * 0.08, y * 0.2)
        return box(-(taille / 2 - r), -(y / 2 - r),
                   taille / 2 - r, y / 2 - r).buffer(r, join_style=1)
    return Point(0, 0).buffer(taille / 2, resolution=96)


def _recipient(emp: Polygon, hauteur: float, paroi: float, fond: float,
               drainage: int = 0, d_drain: float = 6.0,
               conicite: float = 0.0) -> trimesh.Trimesh:
    """Récipient générique : empreinte creusée (fond plein + murs), option
    trous de drainage dans le fond, option évasement (conicité en degrés)."""
    solides = []
    fond_2d = emp
    if drainage > 0:
        trous = []
        if drainage == 1:
            trous = [Point(0, 0).buffer(d_drain / 2, resolution=32)]
        else:
            minx, miny, maxx, maxy = emp.bounds
            ray = min(maxx - minx, maxy - miny) * 0.28
            for i in range(drainage):
                a = 2 * np.pi * i / drainage
                trous.append(Point(np.cos(a) * ray, np.sin(a) * ray)
                             .buffer(d_drain / 2, resolution=32))
        fond_2d = emp.difference(unary_union(trous))
    solides += _extruder(fond_2d, fond)
    if conicite > 0:   # murs évasés : empilement de tranches (pente contrôlée)
        n = max(6, int(hauteur / 4))
        dz = (hauteur - fond) / n
        for i in range(n):
            z = fond + i * dz
            grossi = np.tan(np.radians(conicite)) * (z - fond)
            ext = emp.buffer(grossi, join_style=1)
            mur = ext.difference(ext.buffer(-paroi, join_style=1))
            solides += _extruder(mur, dz + CHEV, z - (CHEV if i else 0))
    else:
        mur = emp.difference(emp.buffer(-paroi, join_style=1))
        solides += _extruder(mur, hauteur - fond + CHEV, fond - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def _percer_3d(piece: trimesh.Trimesh, point, axe: str, d: float = 4.4,
               longueur: float | None = None) -> trimesh.Trimesh:
    """Perce un trou cylindrique le long de `axe` ('x'|'y'|'z'), centré sur
    `point` — à utiliser APRÈS extrusion/rotation. (Les perçages 2D dans le
    profil sortaient dans l'axe d'extrusion : ils TRANCHAIENT la pièce au
    lieu de traverser la face de fixation.) Traversant par défaut ;
    `longueur` limitée = trou borgne (centrer le point en conséquence)."""
    outil = trimesh.creation.cylinder(radius=d / 2, height=longueur or 500.0,
                                      sections=32)
    if axe == "x":
        outil.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    elif axe == "y":
        outil.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    outil.apply_translation(point)
    return trimesh.boolean.difference([piece, outil], engine="manifold")


def _revolution_fermee(profil_rz: list, sections: int = 96) -> trimesh.Trimesh:
    """Révolution d'un profil [(r, z), ...] fermé sur l'axe."""
    pts = [(float(r), float(z)) for r, z in profil_rz]
    if pts[0][0] != 0:
        pts = [(0.0, pts[0][1])] + pts
    if pts[-1][0] != 0:
        pts = pts + [(0.0, pts[-1][1])]
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    m = trimesh.creation.revolve(np.array(pts), sections=sections)
    m.apply_translation([0, 0, -float(m.bounds[0][2])])
    return m


def _texte_sur(piece: trimesh.Trimesh, emp: Polygon, texte: str, z_haut: float,
               grave: bool, hauteur_relief: float = 1.2,
               marge_ratio: float = 0.7, police: str | None = None) -> trimesh.Trimesh:
    """Ajoute un texte relief/gravé sur la face supérieure plane d'une pièce.
    Le texte est PARFAITEMENT CENTRÉ sur la zone `emp` (translation vers son
    centre — sans elle, toute zone décalée de l'origine décalait le texte)."""
    if not texte or not texte.strip():
        return piece
    minx, miny, maxx, maxy = emp.bounds
    txt = ajuster_dans(texte_multilignes(texte, police=police),
                       (maxx - minx) * marge_ratio, (maxy - miny) * marge_ratio)
    txt = translate(txt, xoff=(minx + maxx) / 2.0, yoff=(miny + maxy) / 2.0)
    txt_u = unary_union(list(txt.geoms))
    if grave:
        # gravure = on retire une fine tranche sup et on repose la tranche évidée
        prof = min(hauteur_relief, 1.0)
        outil = union_solides(_extruder(txt_u, prof + 1.0, z_haut - prof))
        return trimesh.boolean.difference([piece, outil], engine="manifold")
    relief = union_solides(_extruder(txt_u, hauteur_relief + CHEV, z_haut - CHEV))
    return union_solides([piece, relief])


# ═══════════════════════════════ CUISINE / MAISON ═══════════════════════════
def dessous_de_plat(forme: str = "rond", taille: float = 160, ep: float = 6,
                    ajoure: bool = True) -> trimesh.Trimesh:
    """Dessous-de-plat épais, option motif nid d'abeille ajouré (économie de
    matière + esthétique). Les alvéoles sont des hexagones traversants."""
    emp = _empreinte(forme, taille)
    plaque = emp
    if ajoure:
        pas, r_hex = 16.0, 6.2
        zone = emp.buffer(-8, join_style=1)
        trous = []
        minx, miny, maxx, maxy = zone.bounds
        j = 0
        y = miny
        while y <= maxy:
            x = minx + (pas / 2 if j % 2 else 0)
            while x <= maxx:
                h = _empreinte("hexagone", r_hex * 2)
                h = translate(h, xoff=x, yoff=y)
                if zone.contains(h):
                    trous.append(h)
                x += pas
            y += pas * 0.866
            j += 1
        if trous:
            plaque = emp.difference(unary_union(trous))
    piece = union_solides(_extruder(plaque, ep))
    piece.apply_translation(-piece.bounds[0])
    return piece


def repose_cuillere(longueur: float = 220, largeur: float = 90) -> trimesh.Trimesh:
    """Repose-cuillère : plat ovale à cuvette peu profonde + zone manche."""
    corps = Point(0, 0).buffer(1, resolution=96)
    from shapely.affinity import scale as shp_scale
    ovale = shp_scale(corps, xfact=largeur / 2, yfact=longueur / 2 * 0.55)
    manche = box(-largeur * 0.18, -longueur / 2 + 6, largeur * 0.18, 0)
    emp = unary_union([translate(ovale, yoff=longueur * 0.16), manche])
    emp = emp.buffer(3, join_style=1).buffer(-3, join_style=1)
    cuvette = translate(shp_scale(corps, xfact=largeur / 2 - 8, yfact=longueur / 2 * 0.55 - 8),
                        yoff=longueur * 0.16)
    solides = _extruder(emp, 4)                                     # semelle
    bord = emp.difference(cuvette)
    solides += _extruder(bord, 6 + CHEV, 4 - CHEV)                  # rebord
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def rond_serviette(diametre: float = 45, largeur: float = 30, ep: float = 2.4,
                   texte: str = "", grave: bool = False) -> trimesh.Trimesh:
    """Anneau de serviette, texte relief/gravé sur le pourtour ? Non : posé à
    plat, texte sur le CHANT supérieur (bande plate ajoutée)."""
    ext = Point(0, 0).buffer(diametre / 2 + ep, resolution=96)
    anneau = ext.difference(Point(0, 0).buffer(diametre / 2, resolution=96))
    piece = union_solides(_extruder(anneau, largeur))
    if texte:
        # méplat porte-texte sur le devant
        plat = box(-diametre * 0.32, -diametre / 2 - ep - 1.6,
                   diametre * 0.32, -diametre / 2 + 1)
        socle = union_solides(_extruder(plat, largeur))
        piece = union_solides([piece, socle])
        emp = box(-diametre * 0.32, -diametre / 2 - ep - 1.6, diametre * 0.32, -diametre / 2)
        piece = _texte_sur(piece, emp, texte, largeur, grave, 1.0)
    piece.apply_translation(-piece.bounds[0])
    return piece


def coquetier(hauteur: float = 45, texte: str = "", grave: bool = True) -> trimesh.Trimesh:
    """Coquetier : coupe à œuf (révolution), pied stable, cuvette ø40."""
    h = hauteur
    profil = [(14, 0), (16, 2), (10, h * 0.35), (18, h * 0.72), (21, h),
              (19.4, h), (16.5, h * 0.74), (14.5, h * 0.60)]
    piece = _revolution_fermee(profil)
    if texte:
        emp = _empreinte("rond", 30)
        piece = _texte_sur(piece, emp, texte, 2.0, True, 0.8)  # gravé sur pied ? non fiable
    return piece


def gobelet(diametre: float = 70, hauteur: float = 90, texte: str = "",
            grave: bool = False) -> trimesh.Trimesh:
    """Gobelet / pot droit (pot à brosses à dents, à pinceaux…)."""
    piece = _recipient(_empreinte("rond", diametre), hauteur, 2.4, 3.0)
    if texte:
        # texte en relief sur la paroi = risqué ; on grave le FOND ? Non —
        # bande porte-texte verticale à plat sur le devant :
        emp = box(-diametre * 0.35, -diametre / 2 - 1.4, diametre * 0.35, -diametre / 2 + 1)
        bande = union_solides(_extruder(emp, min(hauteur * 0.35, 30)))
        piece = union_solides([piece, bande])
        piece = _texte_sur(piece, emp, texte, min(hauteur * 0.35, 30), grave, 1.0)
    piece.apply_translation(-piece.bounds[0])
    return piece


def entonnoir(d_haut: float = 80, d_bas: float = 12, hauteur: float = 70,
              bec: float = 25) -> trimesh.Trimesh:
    """Entonnoir : cône creux + bec cylindrique (paroi 1.6 mm), canal
    TRAVERSANT (profil ANNEAU fermé — surtout pas refermé sur l'axe, sinon
    l'entonnoir est bouché !). Grande ouverture vers le haut, pente ≥ 45°."""
    p = 1.6
    r0 = max(d_bas / 2, 3)          # rayon du CANAL (intérieur du bec)
    r1 = d_haut / 2
    hc = max(hauteur - bec, (r1 - r0))              # pente >= 45 deg
    profil = np.array([
        (r0, 0), (r0, bec),                          # canal du bec
        (r1, bec + hc), (r1 + 2, bec + hc),          # cône int. + rebord
        (r1 + 2, bec + hc - 1), (r1 + 0.6, bec + hc - 2),
        (r0 + p, bec + 1), (r0 + p, 0),              # cône ext. + bec ext.
        (r0, 0),
    ], dtype=float)
    piece = trimesh.creation.revolve(profil, sections=96)
    piece.apply_translation([0, 0, -float(piece.bounds[0][2])])
    return piece


# ═════════════════════════════ RANGEMENT / MAISON ═══════════════════════════
def bac_compartiments(longueur: float = 140, largeur: float = 90,
                      hauteur: float = 35, cases_x: int = 3,
                      cases_y: int = 2) -> trimesh.Trimesh:
    """Organiseur à compartiments (vis, trombones, perles…)."""
    p, fond = 1.6, 2.0
    emp = _empreinte("rect", longueur, largeur)
    solides = _extruder(emp, fond)
    murs = emp.difference(emp.buffer(-p, join_style=1))
    # cloisons internes — soudées au cadre par un léger buffer aller-retour
    # (sans lui, la jonction cloison/mur laisse des lamelles -> non étanche)
    minx, miny, maxx, maxy = emp.bounds
    for i in range(1, max(1, int(cases_x))):
        x = minx + (maxx - minx) * i / cases_x
        murs = unary_union([murs, box(x - p / 2, miny, x + p / 2, maxy).intersection(emp)])
    for j in range(1, max(1, int(cases_y))):
        y = miny + (maxy - miny) * j / cases_y
        murs = unary_union([murs, box(minx, y - p / 2, maxx, y + p / 2).intersection(emp)])
    murs = murs.buffer(0.2, join_style=1).buffer(-0.2, join_style=1)
    solides += _extruder(murs, hauteur - fond + CHEV, fond - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def bac_empilable(longueur: float = 120, largeur: float = 90,
                  hauteur: float = 50) -> trimesh.Trimesh:
    """Bac ouvert empilable : murs droits + collerette ÉVASÉE sur les 8
    derniers mm (entonnoir). Le bas du bac suivant — même taille — s'y pose
    et s'auto-centre, jeu 0.3 mm. (L'ancienne lèvre RENTRANTE était plus
    petite que le fond : les bacs ne s'emboîtaient pas.) Évasement par
    tranches -> pente ~16°, aucun surplomb."""
    p, fond, evase_h, jeu = 2.0, 2.4, 8.0, 0.3
    emp = _empreinte("rect", longueur, largeur)
    solides = _extruder(emp, fond)
    murs = emp.difference(emp.buffer(-p, join_style=1))
    solides += _extruder(murs, hauteur - fond - evase_h + CHEV, fond - CHEV)
    n = 6
    dz = evase_h / n
    for i in range(n):
        z = hauteur - evase_h + i * dz
        ext = emp.buffer((p + jeu) * (i + 1) / n, join_style=1)
        mur = ext.difference(ext.buffer(-p, join_style=1))
        solides += _extruder(mur, dz + CHEV, z - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


def plateau(longueur: float = 200, largeur: float = 140, rebord: float = 12,
            texte: str = "", grave: bool = True) -> trimesh.Trimesh:
    """Plateau / vide-poche à rebord, option texte gravé au fond."""
    emp = _empreinte("rect", longueur, largeur)
    piece = _recipient(emp, rebord + 3, 2.4, 3.0)
    if texte:
        piece = _texte_sur(piece, emp.buffer(-8), texte, 3.0, True, 0.8, 0.6)
    return piece


def crochet_mural(hauteur: float = 60, profondeur: float = 35,
                  largeur: float = 20, vis: bool = True) -> trimesh.Trimesh:
    """Crochet mural en J : plaque murale + bras remontant. Imprimé à PLAT
    (couché sur le flanc) -> aucune fragilité de couches."""
    ep = 6.0
    # profil en J dans le plan XY (X = profondeur, Y = hauteur)
    dos = box(0, 0, ep, hauteur)
    bas = box(0, 0, profondeur, ep)
    remonte = box(profondeur - ep, 0, profondeur, hauteur * 0.45)
    prof = unary_union([dos, bas, remonte]).buffer(1.5, join_style=1).buffer(-1.5, join_style=1)
    piece = union_solides(_extruder(prof, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    if vis:
        # perçage 3D dans l'axe X : les vis traversent la PLAQUE MURALE
        # (dos, épaisseur ep) perpendiculairement au mur.
        for zv in (hauteur * 0.8, hauteur * 0.25):
            piece = _percer_3d(piece, [ep / 2, largeur / 2, zv], "x", d=4.4,
                               longueur=ep * 4)
    return piece


def poignee_meuble(entraxe: float = 96, saillie: float = 28,
                   section: float = 10) -> trimesh.Trimesh:
    """Poignée de meuble en U (entraxe standard 96/128 mm), trous M4 dans les
    pieds. Imprimée à plat (U couché) : solide."""
    L = entraxe + section * 2.4
    # profil U dans XY
    barre = box(-L / 2, saillie - section, L / 2, saillie)
    pied1 = box(-entraxe / 2 - section / 2, 0, -entraxe / 2 + section / 2, saillie)
    pied2 = box(entraxe / 2 - section / 2, 0, entraxe / 2 + section / 2, saillie)
    prof = unary_union([barre, pied1, pied2]).buffer(2, join_style=1).buffer(-2, join_style=1)
    piece = union_solides(_extruder(prof, section))
    piece.apply_translation(-piece.bounds[0])
    # trous M4 BORGNES dans l'axe Y : la vis entre par la face de montage
    # (y=0, dos du tiroir) et remonte DANS le pied — pas en travers.
    prof_trou = saillie * 0.6
    for xv in (L / 2 - entraxe / 2, L / 2 + entraxe / 2):
        piece = _percer_3d(piece, [xv, prof_trou / 2 - 1.0, section / 2], "y",
                           d=4.1, longueur=prof_trou + 2.0)
    return piece


def butee_porte(diametre: float = 40, hauteur: float = 25) -> trimesh.Trimesh:
    """Butée de porte tronconique, base large antidérapante."""
    return _revolution_fermee([(diametre / 2, 0), (diametre / 2 - 2, hauteur * 0.2),
                               (diametre / 2 - hauteur * 0.55, hauteur)])


def pied_meuble(d_bas: float = 45, d_haut: float = 30,
                hauteur: float = 40) -> trimesh.Trimesh:
    """Pied / rehausse de meuble tronconique plein."""
    return _revolution_fermee([(d_bas / 2, 0), (d_haut / 2, hauteur)])


def separateur_tiroir(longueur: float = 150, hauteur: float = 60,
                      ep: float = 2.4) -> trimesh.Trimesh:
    """Séparateur de tiroir : profil T renversé (base stable + lame)."""
    base = box(-longueur / 2, 0, longueur / 2, ep)
    semelle = box(-longueur / 2, 0, longueur / 2, 14)
    prof = unary_union([box(-longueur / 2, 0, longueur / 2, ep),
                        box(-longueur / 2, 0, longueur / 2, hauteur)
                        .intersection(box(-longueur / 2, 0, longueur / 2, hauteur))])
    # simple : lame verticale + semelle horizontale (T couché = extrusion du profil)
    lame = box(-ep / 2, 0, ep / 2, hauteur)
    pied = box(-9, 0, 9, ep * 1.4)
    prof = unary_union([lame, pied])
    piece = union_solides(_extruder(prof, longueur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


def cadre_photo(largeur_photo: float = 100, hauteur_photo: float = 150,
                bord: float = 12, texte: str = "", grave: bool = True) -> trimesh.Trimesh:
    """Cadre photo à feuillure arrière (la photo + un carton glissent dedans),
    à poser ou accrocher (trou au dos)."""
    ep_fond, ep_avant = 1.6, 2.4
    ext = box(-(largeur_photo / 2 + bord), -(hauteur_photo / 2 + bord),
              largeur_photo / 2 + bord, hauteur_photo / 2 + bord)
    ext = ext.buffer(3, join_style=1).buffer(-3, join_style=1)
    fenetre = box(-(largeur_photo / 2 - 4), -(hauteur_photo / 2 - 4),
                  largeur_photo / 2 - 4, hauteur_photo / 2 - 4)
    feuillure = box(-(largeur_photo / 2 + 0.5), -(hauteur_photo / 2 + 0.5),
                    largeur_photo / 2 + 0.5, hauteur_photo / 2 + 0.5)
    solides = _extruder(ext.difference(fenetre), ep_avant)                 # face avant
    solides += _extruder(ext.difference(feuillure), ep_fond + CHEV, ep_avant - CHEV)
    piece = union_solides(solides)
    if texte:
        bande = box(-(largeur_photo / 2), -(hauteur_photo / 2 + bord),
                    largeur_photo / 2, -(hauteur_photo / 2 + 2))
        piece = _texte_sur(piece, bande, texte, ep_avant, grave, 0.8, 0.8)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═════════════════════════════ SALLE DE BAIN / JARDIN ═══════════════════════
def porte_savon(longueur: float = 105, largeur: float = 75,
                hauteur: float = 22) -> trimesh.Trimesh:
    """Porte-savon : bac à rebord + trous de drainage — posé à plat, SANS
    pieds (les 4 cylindres rapportés apparaissaient comme des parasites et
    suspendaient le fond : que le porte-savon)."""
    emp = _empreinte("rect", longueur, largeur)
    piece = _recipient(emp, hauteur, 2.0, 2.4, drainage=6, d_drain=7)
    piece.apply_translation(-piece.bounds[0])
    return piece


def pot_fleur(diametre: float = 110, hauteur: float = 100, drainage: bool = True,
              soucoupe: bool = False) -> trimesh.Trimesh:
    """Pot de fleurs évasé (8°) en RÉVOLUTION lisse (pas de tranches en
    escalier), trous de drainage percés. Option : génère la SOUCOUPE assortie."""
    if soucoupe:
        d = diametre * 1.15
        return _recipient(_empreinte("rond", d), 14, 2.4, 3.0)
    p, fond = 2.4, 3.5
    r_haut = diametre / 2
    r_bas = max(r_haut - hauteur * np.tan(np.radians(8)), r_haut * 0.55)
    profil = [(r_bas, 0), (r_haut, hauteur), (r_haut - p, hauteur),
              (r_bas - p * 0.5, fond), (0, fond)]
    piece = _revolution_fermee(profil, sections=128)
    if drainage:
        trous = []
        for i in range(5):
            a = 2 * np.pi * i / 5
            c = trimesh.creation.cylinder(radius=4, height=fond * 4, sections=32)
            c.apply_translation([np.cos(a) * r_bas * 0.5,
                                 np.sin(a) * r_bas * 0.5, fond / 2])
            trous.append(c)
        piece = trimesh.boolean.difference(
            [piece, union_solides(trous)], engine="manifold")
    piece.apply_translation(-piece.bounds[0] * [0, 0, 1])
    return piece


def etiquette_plante(longueur: float = 120, largeur: float = 22,
                     texte: str = "Basilic", grave: bool = True) -> trimesh.Trimesh:
    """Étiquette de plantation : piquet pointu + zone texte. Le texte est
    posé dans le TIERS HAUT de la palette (loin de la pointe qui va en
    terre — avant il était centré et finissait près du sol)."""
    ep = 2.4
    zone = box(-largeur / 2, 0, largeur / 2, longueur * 0.45)
    pointe = Polygon([(-largeur / 2, 0), (largeur / 2, 0), (0, -longueur * 0.55)])
    emp = unary_union([zone, pointe]).buffer(1.5, join_style=1).buffer(-1.5, join_style=1)
    piece = union_solides(_extruder(emp, ep))
    if texte:
        zone_txt = box(-largeur / 2, longueur * 0.18, largeur / 2, longueur * 0.43)
        piece = _texte_sur(piece, zone_txt, texte, ep, grave, 0.8, 0.85)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════════ BUREAU / TECH ══════════════════════════════
def pot_crayons(forme: str = "hexagone", diametre: float = 80,
                hauteur: float = 100, compartiments: bool = False,
                texte: str = "", grave: bool = False) -> trimesh.Trimesh:
    """Pot à crayons (rond/carré/hexagonal), option séparateur en croix."""
    emp = _empreinte(forme, diametre)
    piece = _recipient(emp, hauteur, 2.0, 3.0)
    if compartiments:
        minx, miny, maxx, maxy = emp.bounds
        croix = unary_union([box(-1, miny, 1, maxy), box(minx, -1, maxx, 1)])
        croix = croix.intersection(emp.buffer(-1.5, join_style=1))
        sep = union_solides(_extruder(croix, hauteur * 0.75 + CHEV, 3.0 - CHEV))
        piece = union_solides([piece, sep])
    if texte:
        emp_b = box(-diametre * 0.32, -diametre / 2 - 1.4, diametre * 0.32, -diametre / 2 + 1)
        bande = union_solides(_extruder(emp_b, min(hauteur * 0.3, 26)))
        piece = union_solides([piece, bande])
        piece = _texte_sur(piece, emp_b, texte, min(hauteur * 0.3, 26), grave, 1.0)
    piece.apply_translation(-piece.bounds[0])
    return piece


def porte_cartes(largeur: float = 100) -> trimesh.Trimesh:
    """Porte-cartes de visite : socle + rainure inclinée (15°)."""
    prof, h = 45.0, 22.0
    base = box(0, 0, prof, 6)
    fente = shp_rotate(box(prof * 0.45, 2, prof * 0.45 + 3.2, h + 10), -15,
                       origin=(prof * 0.45, 2))
    dossier = shp_rotate(box(prof * 0.45 + 3.2, 2, prof * 0.45 + 8, h),
                         -15, origin=(prof * 0.45, 2))
    prof_2d = unary_union([base, dossier,
                           shp_rotate(box(prof * 0.45 - 5, 2, prof * 0.45, h * 0.55),
                                      -15, origin=(prof * 0.45, 2))])
    prof_2d = prof_2d.buffer(1, join_style=1).buffer(-1, join_style=1)
    piece = union_solides(_extruder(prof_2d, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


def marque_page(longueur: float = 140, largeur: float = 35, ep: float = 1.6,
                texte: str = "", grave: bool = True) -> trimesh.Trimesh:
    """Marque-page fin à coin arrondi, texte gravé — épaisseur réglable."""
    ep = min(3.2, max(0.8, ep))
    emp = _empreinte("rect", largeur, longueur)
    piece = union_solides(_extruder(emp, ep))
    if texte:
        piece = _texte_sur(piece, emp, texte, ep, grave, min(0.6, ep * 0.35), 0.8)
    piece.apply_translation(-piece.bounds[0])
    return piece


def clip_cable(d_cable: float = 5, vis: bool = True) -> trimesh.Trimesh:
    """Clip de câble en C + patte de vis (imprimé à plat)."""
    r = d_cable / 2 + 0.3
    ext = Point(0, r + 2).buffer(r + 2.2, resolution=64)
    intr = Point(0, r + 2).buffer(r, resolution=64)
    ouverture = box(-r * 0.7, r + 2, r * 0.7, r * 2 + 8)
    c = ext.difference(intr).difference(ouverture)
    patte = box(r + 1, 0, r + 12, 4.5)
    base = box(-r - 2.2, 0, r + 12, 2.2)
    prof = unary_union([c, patte, base]).buffer(0.8, join_style=1).buffer(-0.8, join_style=1)
    if vis:
        prof = prof.difference(Point(r + 7, 2.4).buffer(1.8, resolution=32))
    piece = union_solides(_extruder(prof, 10))
    piece.apply_translation(-piece.bounds[0])
    return piece


def passe_cable(d_trou_panneau: float = 60, ep_panneau: float = 18) -> trimesh.Trimesh:
    """Passe-câble de bureau (grommet) : ANNEAU traversant à collerette +
    entrée latérale. Profil en anneau — il ne se referme PAS sur l'axe
    (l'ancien profil créait un fond plein : le câble ne passait pas)."""
    j = 0.4
    r = d_trou_panneau / 2 - j
    r_int = max(r * 0.45, 8.0)                    # ouverture centrale du câble
    profil = np.array([
        (r + 6, 0), (r + 6, 2.4), (r, 2.4), (r, ep_panneau + 2.4),
        (r - 1.8, ep_panneau + 2.4), (r - 1.8, 2.4 + 1.8),
        (r_int, 2.4), (r_int, 0), (r + 6, 0),
    ])
    piece = trimesh.creation.revolve(profil, sections=96)
    fente = trimesh.creation.box((14, d_trou_panneau, ep_panneau * 3))
    fente.apply_translation([r, 0, 0])
    piece = trimesh.boolean.difference([piece, fente], engine="manifold")
    piece.apply_translation(-piece.bounds[0] * [0, 0, 1])
    return piece


def organiseur_forets(rangees: int = 3, colonnes: int = 8) -> trimesh.Trimesh:
    """Bloc porte-forets/embouts : grille de trous de diamètre croissant."""
    rangees, colonnes = int(rangees), int(colonnes)
    pas = 14.0
    L, P, H = colonnes * pas + 10, rangees * pas + 10, 28.0
    emp = _empreinte("rect", L, P)
    bloc = union_solides(_extruder(emp, H))
    trous = []
    for j in range(rangees):
        d = 3.0 + j * 2.5
        for i in range(colonnes):
            c = trimesh.creation.cylinder(radius=d / 2 + 0.25, height=H, sections=32)
            c.apply_translation([-L / 2 + 10 + i * pas, -P / 2 + 10 + j * pas, H - H / 2 + 6])
            trous.append(c)
    piece = trimesh.boolean.difference([bloc] + [union_solides(trous)], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


def equerre(taille: float = 80, ep: float = 4, vis: bool = True) -> trimesh.Trimesh:
    """Équerre de fixation 90° (L 3D) avec trous de vis et goussets."""
    a = box(0, 0, taille, ep)                       # aile horizontale (profil)
    b = box(0, 0, ep, taille)                       # aile verticale
    gousset = Polygon([(ep, ep), (taille * 0.55, ep), (ep, taille * 0.55)])
    prof = unary_union([a, b, gousset])
    largeur = 20.0
    piece = union_solides(_extruder(prof, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    if vis:
        # perçage 3D perpendiculaire à CHAQUE aile : vertical (z) dans l'aile
        # posée, horizontal (x) dans l'aile dressée.
        piece = _percer_3d(piece, [taille * 0.7, largeur / 2, ep / 2], "z",
                           d=4.4, longueur=ep * 4)
        piece = _percer_3d(piece, [ep / 2, largeur / 2, taille * 0.7], "x",
                           d=4.4, longueur=ep * 4)
    return piece


def rondelle(d_ext: float = 24, d_int: float = 8, ep: float = 3) -> trimesh.Trimesh:
    ext = Point(0, 0).buffer(d_ext / 2, resolution=64)
    piece = union_solides(_extruder(ext.difference(
        Point(0, 0).buffer(d_int / 2, resolution=64)), ep))
    piece.apply_translation(-piece.bounds[0])
    return piece


def entretoise(d_ext: float = 12, d_int: float = 5, hauteur: float = 15) -> trimesh.Trimesh:
    return rondelle(d_ext, d_int, hauteur)


def protege_coin(taille: float = 40, ep: float = 3) -> trimesh.Trimesh:
    """Protège-coin de table (3 plaques en coin, angles adoucis)."""
    t, e = taille, ep
    p1 = trimesh.creation.box((t, t, e)); p1.apply_translation([t / 2, t / 2, e / 2])
    p2 = trimesh.creation.box((t, e, t)); p2.apply_translation([t / 2, e / 2, t / 2])
    p3 = trimesh.creation.box((e, t, t)); p3.apply_translation([e / 2, t / 2, t / 2])
    piece = union_solides([p1, p2, p3])
    piece.apply_translation(-piece.bounds[0])
    return piece
