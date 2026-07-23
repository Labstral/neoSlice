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
               marge_ratio: float = 0.7, police: str | None = None,
               style: str | None = None, couleur_objet: str | None = None,
               couleur_texte: str | None = None, rot_texte: float = 0.0,
               dx: float = 0.0, dy: float = 0.0):
    """Ajoute un texte sur la face supérieure plane d'une pièce. Le texte est
    centré sur la zone `emp` (puis décalé de dx/dy et tourné de rot_texte°).

    style : "relief" | "grave" | "lisse" (prioritaire sur le flag legacy `grave`).
    couleur_objet / couleur_texte : si fournis → Scene à 2 corps colorés (bicolore).
    rot_texte : rotation du texte en degrés (90 = parallèle à la longueur).
    dx / dy   : décalage du texte sur les axes X / Y (mm).
    """
    if not texte or not texte.strip():
        return piece
    from core.neogen import goodies as _g
    if _g.RELIEF_ACTIF is not None:              # réglage utilisateur « de session »
        hauteur_relief = max(0.3, float(_g.RELIEF_ACTIF))
    style = style if style in ("relief", "grave", "lisse") else ("grave" if grave else "relief")
    bicolore = bool(couleur_objet and couleur_texte)
    minx, miny, maxx, maxy = emp.bounds
    # zone disponible : dimensions ÉCHANGÉES si le texte est tourné à ±90° (il court
    # alors dans l'autre sens → il peut être bien plus grand).
    larg_fit = (maxx - minx) * marge_ratio
    haut_fit = (maxy - miny) * marge_ratio
    if int(round(rot_texte)) % 180 == 90:
        larg_fit, haut_fit = haut_fit, larg_fit
    txt = ajuster_dans(texte_multilignes(texte, police=police), larg_fit, haut_fit)
    if rot_texte:
        txt = shp_rotate(txt, rot_texte, origin=(0, 0))     # texte centré en (0,0)
    txt = translate(txt, xoff=(minx + maxx) / 2.0 + dx,
                    yoff=(miny + maxy) / 2.0 + dy)
    txt_u = unary_union(list(txt.geoms))

    if not bicolore:
        if style == "grave":
            prof = min(hauteur_relief, z_haut - 0.6)   # jamais traversant
            outil = union_solides(_extruder(txt_u, prof + 1.0, z_haut - prof))
            return trimesh.boolean.difference([piece, outil], engine="manifold")
        if style == "lisse":
            return piece                               # mono lisse = invisible : rien
        relief = union_solides(_extruder(txt_u, hauteur_relief + CHEV, z_haut - CHEV))
        return union_solides([piece, relief])

    # ── BICOLORE : corps « objet » + corps « texte » colorés ──────────────────
    from core.neogen.bicolore import scene as _bic_scene
    if style == "relief":
        objet = piece
        texte_body = union_solides(_extruder(txt_u, hauteur_relief + CHEV, z_haut - CHEV))
    else:
        prof = min(max(hauteur_relief, 0.8), z_haut - 0.6)
        outil = union_solides(_extruder(txt_u, prof + 2.0, z_haut - prof))
        objet = trimesh.boolean.difference([piece, outil], engine="manifold")
        h = prof - (0.6 if style == "grave" else 0.0)   # sillon si gravé, affleurant si lisse
        texte_body = union_solides(_extruder(txt_u, max(0.4, h), z_haut - prof))
    return _bic_scene(objet, texte_body, couleur_objet, couleur_texte)


# ═══════════════════════════════ CUISINE / MAISON ═══════════════════════════
def dessous_de_plat(forme: str = "rond", taille: float = 160, ep: float = 6,
                    ajoure: bool = True, motif: str = "nid_abeille") -> trimesh.Trimesh:
    """Dessous-de-plat épais. `motif` : nid_abeille (hexagones), rond (trous ronds)
    ou plein (sans ajour). Les alvéoles sont traversantes (économie + esthétique)."""
    motif = motif if motif in ("nid_abeille", "rond", "plein") else "nid_abeille"
    if not ajoure:
        motif = "plein"
    emp = _empreinte(forme, taille)
    plaque = emp
    if motif != "plein":
        pas, r_alv = 16.0, 6.2
        zone = emp.buffer(-8, join_style=1)
        trous = []
        minx, miny, maxx, maxy = zone.bounds
        j = 0
        y = miny
        while y <= maxy:
            x = minx + (pas / 2 if j % 2 else 0)
            while x <= maxx:
                alv = _empreinte("rond" if motif == "rond" else "hexagone", r_alv * 2)
                alv = translate(alv, xoff=x, yoff=y)
                if zone.contains(alv):
                    trous.append(alv)
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
                   texte: str = "", grave: bool = False, style: str | None = None,
                   couleur_objet: str | None = None, couleur_texte: str | None = None,
                   pos_z: float = 0.0, angle: float = 0.0):
    """Anneau de serviette : le texte ÉPOUSE le pourtour cylindrique (enroulé sur
    la surface, plus de rectangle plat à côté). `pos_z` monte/descend le texte,
    `angle` le fait tourner autour de l'anneau."""
    R_ext = diametre / 2 + ep
    ext = Point(0, 0).buffer(R_ext, resolution=96)
    anneau = ext.difference(Point(0, 0).buffer(diametre / 2, resolution=96))
    base = union_solides(_extruder(anneau, largeur))
    if not (texte or "").strip():
        base.apply_translation(-base.bounds[0])
        return base
    from core.neogen.goodies import RELIEF_ACTIF
    from core.neogen import bicolore as _bic
    arc_max = 2 * np.pi * R_ext * 0.55            # texte ≤ ~55 % du tour
    mp = ajuster_dans(texte_multilignes(str(texte)), arc_max, largeur * 0.5)
    mnx, mny, mxx, mxy = mp.bounds
    mp = translate(mp, xoff=-(mnx + mxx) / 2, yoff=-(mny + mxy) / 2)
    text_2d = unary_union(list(mp.geoms))
    relief = 1.0 if RELIEF_ACTIF is None else max(0.4, float(RELIEF_ACTIF))
    txt = _bic.texte_cylindrique(text_2d, R_ext, relief)
    txt.apply_translation([0, 0, largeur / 2 + pos_z])
    if angle:
        txt.apply_transform(trimesh.transformations.rotation_matrix(
            np.radians(angle), [0, 0, 1]))
    if couleur_objet and couleur_texte:
        s = _bic.scene(base, txt, couleur_objet, couleur_texte)
        fus = trimesh.util.concatenate(list(s.geometry.values()))
        off = -fus.bounds[0]
        for g in s.geometry.values():
            g.apply_translation(off)
        return s
    piece = union_solides([base, txt])
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
            grave: bool = False, style: str | None = None,
            couleur_objet: str | None = None, couleur_texte: str | None = None,
            pos_z: float = 0.0, angle: float = 0.0):
    """Gobelet / pot droit (pot à brosses à dents, à pinceaux…). Le texte ÉPOUSE la
    paroi cylindrique (enroulé, plus de bande plate). `pos_z` monte/descend le texte,
    `angle` le fait tourner autour du pot."""
    R = diametre / 2.0
    base = _recipient(_empreinte("rond", diametre), hauteur, 2.4, 3.0)
    if not (texte or "").strip():
        base.apply_translation(-base.bounds[0])
        return base
    from core.neogen.goodies import RELIEF_ACTIF
    from core.neogen import bicolore as _bic
    arc_max = 2 * np.pi * R * 0.5                  # texte ≤ ~50 % du tour
    h_txt = min(hauteur * 0.4, diametre * 0.6)
    mp = ajuster_dans(texte_multilignes(str(texte)), arc_max, h_txt)
    mnx, mny, mxx, mxy = mp.bounds
    mp = translate(mp, xoff=-(mnx + mxx) / 2, yoff=-(mny + mxy) / 2)
    text_2d = unary_union(list(mp.geoms))
    relief = 1.0 if RELIEF_ACTIF is None else max(0.4, float(RELIEF_ACTIF))
    txt = _bic.texte_cylindrique(text_2d, R, relief)
    txt.apply_translation([0, 0, hauteur * 0.5 + pos_z])
    if angle:
        txt.apply_transform(trimesh.transformations.rotation_matrix(
            np.radians(angle), [0, 0, 1]))
    if couleur_objet and couleur_texte:
        s = _bic.scene(base, txt, couleur_objet, couleur_texte)
        fus = trimesh.util.concatenate(list(s.geometry.values()))
        off = -fus.bounds[0]
        for g in s.geometry.values():
            g.apply_translation(off)
        return s
    piece = union_solides([base, txt])
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
            texte: str = "", grave: bool = True, style: str | None = None,
            couleur_objet: str | None = None, couleur_texte: str | None = None):
    """Plateau / vide-poche à rebord, option texte gravé au fond."""
    emp = _empreinte("rect", longueur, largeur)
    piece = _recipient(emp, rebord + 3, 2.4, 3.0)
    if texte:
        piece = _texte_sur(piece, emp.buffer(-8), texte, 3.0, grave, 0.8, 0.6,
                           style=style, couleur_objet=couleur_objet,
                           couleur_texte=couleur_texte)
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


def pied_meuble(d_bas: float = 45, d_haut: float = 30, hauteur: float = 40,
                forme: str = "conique", trou_d: float = 0.0,
                trou_prof: float = 0.0) -> trimesh.Trimesh:
    """Pied / rehausse de meuble. `forme` : conique (tronconique d_bas→d_haut),
    cylindrique (droit ø d_bas) ou carre (prisme carré côté d_bas). Trou au SOMMET
    (`trou_d` diamètre, `trou_prof` profondeur ; 0 = pas de trou) pour visser/emboîter."""
    if forme == "carre":
        c = box(-d_bas / 2, -d_bas / 2, d_bas / 2, d_bas / 2)
        piece = union_solides(_extruder(c, hauteur))
    elif forme == "cylindrique":
        piece = _revolution_fermee([(d_bas / 2, 0), (d_bas / 2, hauteur)])
    else:  # conique
        piece = _revolution_fermee([(d_bas / 2, 0), (d_haut / 2, hauteur)])
    if trou_d > 0 and trou_prof > 0:
        prof = min(trou_prof, hauteur - 2)            # laisse au moins 2 mm de fond
        trou = trimesh.creation.cylinder(radius=trou_d / 2, height=prof + 2, sections=48)
        trou.apply_translation((0, 0, hauteur - prof / 2 + 1))   # débouche au sommet
        piece = trimesh.boolean.difference([piece, trou], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


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
                bord: float = 12, texte: str = "", grave: bool = True):
    """Cadre photo DEUX CORPS (3MF) : cadre à poche arrière + FOND qui
    S'EMBOÎTE — 6 ergots en légère interférence (~0.15 mm) pressent contre la
    paroi de la poche : tenue franche, fond amovible pour changer la photo.
    Le fond a un trou d'accroche murale et une encoche d'extraction.
    Construit FACE AVANT SUR LE DESSUS : le texte est sur la face visible
    (avant, il tombait dans l'épaisseur, invisible)."""
    ep_avant, h_poche, ep_fond = 2.4, 2.8, 2.0
    lp2, hp2 = largeur_photo / 2, hauteur_photo / 2
    ext = box(-(lp2 + bord), -(hp2 + bord), lp2 + bord, hp2 + bord)
    ext = ext.buffer(3, join_style=1).buffer(-3, join_style=1)
    fenetre = box(-(lp2 - 4), -(hp2 - 4), lp2 - 4, hp2 - 4)
    poche = box(-(lp2 + 0.5), -(hp2 + 0.5), lp2 + 0.5, hp2 + 0.5)
    solides = _extruder(ext.difference(poche), h_poche)          # anneau arrière
    solides += _extruder(ext.difference(fenetre), ep_avant + CHEV,
                         h_poche - CHEV)                          # face avant
    cadre = union_solides(solides)
    if texte:
        # Bande de texte CENTRÉE sur la bordure basse VISIBLE : de l'arête
        # extérieure (y_ext) jusqu'au bord de la fenêtre (y_fen). Avant, la bande
        # ne couvrait que la moitié EXTERNE de la bordure → texte trop bas.
        y_ext = -(hp2 + bord)        # arête extérieure basse du cadre
        y_fen = -(hp2 - 4)           # bord bas de la fenêtre (ouverture)
        cy = (y_ext + y_fen) / 2.0   # centre vertical de la bordure basse
        hb = bord - 2.0              # hauteur de bande (taille de texte conservée)
        bande = box(-lp2, cy - hb / 2.0, lp2, cy + hb / 2.0)
        cadre = _texte_sur(cadre, bande, texte, h_poche + ep_avant, grave, 0.8, 0.8)
    cadre.apply_translation(-cadre.bounds[0])

    # FOND : plaque au jeu 0.15/côté + 6 ergots (r 0.8, centre à 0.5 du bord
    # -> débord 0.3, soit 0.15 D'INTERFÉRENCE dans la poche = emboîtement).
    fond2d = box(-(lp2 + 0.35), -(hp2 + 0.35), lp2 + 0.35, hp2 + 0.35)
    ergots = [Point(cx, cy).buffer(0.8, resolution=24) for cx, cy in (
        (0, hp2 - 0.15),                                   # haut : centre
        (lp2 * 0.5, -(hp2 - 0.15)), (-lp2 * 0.5, -(hp2 - 0.15)),   # bas : de
        # part et d'autre de l'encoche d'extraction (au centre, elle l'avalait)
        (lp2 - 0.15, hp2 * 0.45), (lp2 - 0.15, -hp2 * 0.45),
        (-(lp2 - 0.15), hp2 * 0.45), (-(lp2 - 0.15), -hp2 * 0.45))]
    fond2d = unary_union([fond2d] + ergots)
    fond2d = fond2d.difference(Point(0, hp2 + 0.35 - 8).buffer(2.6, resolution=32))
    fond2d = fond2d.difference(Point(0, -(hp2 + 0.35)).buffer(6, resolution=32))
    fond = union_solides(_extruder(fond2d, ep_fond))
    fond.apply_translation(-fond.bounds[0])
    fond.apply_translation([float(cadre.bounds[1][0]) + 8.0, 0, 0])

    scene = trimesh.Scene()
    scene.add_geometry(cadre, node_name="cadre", geom_name="cadre")
    scene.add_geometry(fond, node_name="fond", geom_name="fond")
    return scene


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
                     texte: str = "Basilic", grave: bool = True, style: str | None = None,
                     couleur_objet: str | None = None, couleur_texte: str | None = None,
                     pos_x: float = 0.0, pos_y: float = 0.0):
    """Étiquette de plantation : piquet pointu + zone texte (tiers haut, loin de la
    pointe). `pos_x` / `pos_y` décalent le texte."""
    ep = 2.4
    zone = box(-largeur / 2, 0, largeur / 2, longueur * 0.45)
    pointe = Polygon([(-largeur / 2, 0), (largeur / 2, 0), (0, -longueur * 0.55)])
    emp = unary_union([zone, pointe]).buffer(1.5, join_style=1).buffer(-1.5, join_style=1)
    piece = union_solides(_extruder(emp, ep))
    if texte:
        zone_txt = box(-largeur / 2, longueur * 0.18, largeur / 2, longueur * 0.43)
        piece = _texte_sur(piece, zone_txt, texte, ep, grave, 0.8, 0.85,
                           style=style, couleur_objet=couleur_objet,
                           couleur_texte=couleur_texte, dx=pos_x, dy=pos_y)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════════ BUREAU / TECH ══════════════════════════════
def pot_crayons(forme: str = "hexagone", diametre: float = 80,
                hauteur: float = 100, compartiments: bool = False,
                texte: str = "", grave: bool = False, style: str | None = None,
                couleur_objet: str | None = None, couleur_texte: str | None = None):
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
        piece = _texte_sur(piece, emp_b, texte, min(hauteur * 0.3, 26), grave, 1.0,
                           style=style, couleur_objet=couleur_objet,
                           couleur_texte=couleur_texte)
    piece.apply_translation(-piece.bounds[0])
    return piece


def porte_cartes(largeur: float = 100, fente: float = 2.5) -> trimesh.Trimesh:
    """Porte-cartes de visite : socle mince + rainure inclinée (15°) CENTRÉE, dont
    la largeur (`fente`) est réglable. Muret avant + dossier fins de part et d'autre."""
    prof, h = 44.0, 20.0
    xc = prof / 2.0                               # rainure CENTRÉE sur la profondeur
    fente = max(1.4, min(float(fente), 6.0))
    x_front, x_back = xc - fente / 2.0, xc + fente / 2.0
    base = box(0, 0, prof, 5)
    dossier = shp_rotate(box(x_back, 2, x_back + 4.0, h), -15, origin=(xc, 2))
    muret = shp_rotate(box(x_front - 4.0, 2, x_front, h * 0.5), -15, origin=(xc, 2))
    prof_2d = unary_union([base, dossier, muret])
    prof_2d = prof_2d.buffer(0.8, join_style=1).buffer(-0.8, join_style=1)
    piece = union_solides(_extruder(prof_2d, largeur))
    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece


def marque_page(longueur: float = 140, largeur: float = 35, ep: float = 1.6,
                texte: str = "", grave: bool = True, style: str | None = None,
                couleur_objet: str | None = None, couleur_texte: str | None = None,
                orientation: str = "perpendiculaire", pos_x: float = 0.0,
                pos_y: float = 0.0):
    """Marque-page fin à coin arrondi, texte relief/gravé/lisse.
    orientation : « perpendiculaire » (par défaut) ou « parallele » (texte le long
    de la longueur) ; pos_x / pos_y décalent le texte sur les deux axes."""
    ep = min(3.2, max(0.8, ep))
    emp = _empreinte("rect", largeur, longueur)
    piece = union_solides(_extruder(emp, ep))
    if texte:
        rot = 90.0 if orientation == "parallele" else 0.0
        piece = _texte_sur(piece, emp, texte, ep, grave, min(0.6, ep * 0.35), 0.8,
                           style=style, couleur_objet=couleur_objet,
                           couleur_texte=couleur_texte, rot_texte=rot,
                           dx=pos_x, dy=pos_y)
    piece.apply_translation(-piece.bounds[0])
    return piece


def clip_cable(d_cable: float = 5, vis: bool = True) -> trimesh.Trimesh:
    """Clip de câble type SELLE (saddle clamp), comme les modèles du commerce.

    Un socle plat (posé sur le plateau) surmonté d'une ARCHE demi-cylindrique qui
    enjambe le câble : le câble court PARALLÈLE au plateau, passe dans le tunnel de
    l'arche et repose sur le socle. Deux variantes :
      - vis=False  → « Tape » : socle symétrique sans trou (fixation adhésive) ;
      - vis=True   → « Screw » : le socle porte une patte laterale avec un trou de
                     vis VERTICAL pour le fixer sur un support.
    La taille est le diamètre du câble (ex. 4, 5, 6, 8, 10 mm). Un seul corps plein.
    """
    rot = trimesh.transformations.rotation_matrix
    r_cab = d_cable / 2.0
    r_in  = r_cab + 0.4                          # jeu autour du câble
    wall  = max(1.8, d_cable * 0.30)             # épaisseur de l'arche
    r_out = r_in + wall
    w     = max(3.8, d_cable * 0.55)             # largeur de la bande (arche) le long du câble (X)
    r_trou = 1.9                                 # rayon du trou de vis (≈ vis M3.5)
    # Le SOCLE est au moins assez large en X pour loger le trou de vis avec de la
    # matière autour (sinon, sur un petit clip, Ø trou ≈ largeur bande → il tranche
    # la patte en deux). L'arche, elle, reste une bande fine (largeur w).
    base_w = max(w, 2 * r_trou + 3.6)
    base_t = 2.2                                 # épaisseur du socle
    z_c   = base_t + r_in                        # centre du tunnel → sol = dessus du socle
    flange = 4.5                                 # débord du socle (surface d'appui/adhésif)
    tab    = 9.0                                 # patte du trou de vis (côté +Y)

    # ── Socle : arche centrée en y=0 ; côté +Y allongé (patte + trou) si vis ──
    y_neg = r_out + flange
    y_pos = (r_out + flange + tab) if vis else (r_out + flange)
    Ly = y_neg + y_pos
    yc = (y_pos - y_neg) / 2.0                    # recentre le socle sur l'arche
    socle = trimesh.creation.box((base_w, Ly, base_t))
    socle.apply_translation((0, yc, base_t / 2.0))

    # ── Arche : cylindre plein (r_out) + pilier de liaison, fusionnés au socle ──
    arche = trimesh.creation.cylinder(radius=r_out, height=w, sections=72)
    arche.apply_transform(rot(np.radians(90), [0, 1, 0]))       # axe → X (le long du câble)
    arche.apply_translation((0, 0, z_c))
    # Pilier plein du plateau jusqu'au centre du tunnel : garantit une jonction
    # SOLIDE arche↔socle a toutes les tailles (sinon, petit câble → arche qui
    # n'effleure le socle qu'en un mince liseré → boolean laisse un éclat détaché).
    pilier = trimesh.creation.box((w, 2 * r_out, z_c))
    pilier.apply_translation((0, 0, z_c / 2.0))
    solide = union_solides([socle, pilier, arche])

    negs = []
    # Tunnel du câble (traverse l'arche le long de X)
    tunnel = trimesh.creation.cylinder(radius=r_in, height=w + 2, sections=72)
    tunnel.apply_transform(rot(np.radians(90), [0, 1, 0]))
    tunnel.apply_translation((0, 0, z_c))
    negs.append(tunnel)
    # OUVERTURE D'INSERTION (essentielle — comme les clips du commerce) : fente
    # verticale du sommet de l'arche jusqu'au tunnel, PLUS ÉTROITE que le câble
    # (≈ 75 % du Ø) → le câble se CLIPSE par le dessus et reste retenu. Sans elle,
    # l'anneau est fermé et il faudrait enfiler le câble par le bout — inutilisable.
    fw = max(1.6, d_cable * 0.75)
    fente = trimesh.creation.box((w + 2, fw, r_out + 2))
    fente.apply_translation((0, 0, z_c + (r_out + 2) / 2.0))
    negs.append(fente)
    # Base plane : couper tout ce qui descend sous le plateau (l'arche pleine deborde
    # sous le socle pour les gros diametres) → dessous plat, imprimable a plat.
    sous = trimesh.creation.box((base_w * 3, Ly * 3, 20.0))
    sous.apply_translation((0, yc, -10.0))
    negs.append(sous)
    if vis:
        # Trou de vis VERTICAL dans la patte laterale
        y_trou = r_out + flange + tab / 2.0 + 1.0
        trou = trimesh.creation.cylinder(radius=r_trou, height=base_t + 4, sections=32)
        trou.apply_translation((0, y_trou, base_t / 2.0))
        negs.append(trou)

    piece = trimesh.boolean.difference([solide] + negs, engine="manifold")
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


def joint(type_joint: str = "plat", d_ext: float = 30, d_int: float = 20,
          epaisseur: float = 3) -> trimesh.Trimesh:
    """Joint d'étanchéité. `type_joint` :
      • plat    : anneau plat (Ø ext / Ø int, épaisseur = hauteur extrudée) ;
      • torique : O-ring (section arrondie ; Ø ext / int donnent l'anneau,
                  épaisseur = hauteur du cordon, section aplatie si ≠ diamètre).
    """
    d_ext = max(d_ext, d_int + 1.0)
    if type_joint == "torique":
        R = (d_ext + d_int) / 4.0                 # rayon de la ligne médiane
        r_rad = max(0.6, (d_ext - d_int) / 4.0)   # demi-largeur radiale du cordon
        tor = trimesh.creation.torus(R, r_rad, major_sections=96, minor_sections=32)
        vsemi = max(0.6, float(epaisseur) / 2.0)  # demi-hauteur verticale (aplatit)
        if abs(vsemi - r_rad) > 1e-3:
            tor.apply_scale([1.0, 1.0, vsemi / r_rad])
        tor.apply_translation(-tor.bounds[0] * [0, 0, 1])   # posé sur z=0
        return tor
    # plat : anneau extrudé
    ext = Point(0, 0).buffer(d_ext / 2, resolution=96)
    anneau = ext.difference(Point(0, 0).buffer(d_int / 2, resolution=96))
    piece = union_solides(_extruder(anneau, float(epaisseur)))
    piece.apply_translation(-piece.bounds[0])
    return piece


def protege_coin(taille: float = 40, ep: float = 3) -> trimesh.Trimesh:
    """Protège-coin de table (3 plaques en coin, angles adoucis)."""
    t, e = taille, ep
    p1 = trimesh.creation.box((t, t, e)); p1.apply_translation([t / 2, t / 2, e / 2])
    p2 = trimesh.creation.box((t, e, t)); p2.apply_translation([t / 2, e / 2, t / 2])
    p3 = trimesh.creation.box((e, t, t)); p3.apply_translation([e / 2, t / 2, t / 2])
    piece = union_solides([p1, p2, p3])
    piece.apply_translation(-piece.bounds[0])
    return piece
