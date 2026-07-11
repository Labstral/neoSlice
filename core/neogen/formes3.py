# -*- coding: utf-8 -*-
"""neoGen — bibliothèque, lot 3 : COUVERTS et VISSERIE.

Couverts : cuillère, fourchette, couteau — une pièce plate imprimable à plat.

Visserie : vis à tête hexagonale + écrous, filetage ISO métrique GÉNÉRÉ EN
MAILLAGE (profil trapézoïdal 60°, pas normalisé, jeu d'ajustement calibré
impression FDM). Tailles proposées : M6, M8, M10, M12 — en dessous (M1-M5),
le filetage FDM en buse 0.4 n'est pas fiable, on ne les propose PAS
(décision produit : ne jamais générer une pièce vouée à l'échec).

  Vis  : r_majeur réduit de 0.10 mm (impression légèrement grasse)
  Écrou: alésage élargi de +0.25 mm  -> jeu radial total ~0.35 mm = vissage
         doux sur la plupart des imprimantes calibrées.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from core.neogen.geo_utils import union_solides
from core.neogen.goodies import _extruder, CHEVAUCHEMENT
from core.neogen.formes import _empreinte

CHEV = CHEVAUCHEMENT

# ── Table ISO (DIN 933/934) : D -> (pas, surplat tête/écrou, h tête, h écrou) ─
VISSERIE = {
    "M6":  (1.0,  10.0, 4.0, 5.0),
    "M8":  (1.25, 13.0, 5.3, 6.5),
    "M10": (1.5,  16.0, 6.4, 8.0),
    "M12": (1.75, 18.0, 7.5, 10.0),
}


# ═══════════════════════════════ FILETAGE ════════════════════════════════════
def _rayon_filet(phase: np.ndarray, r_min: float, r_maj: float) -> np.ndarray:
    """Profil de filet trapézoïdal : fond plat (15 %), flancs, crête plate
    (15 %) — proche ISO, robuste à l'impression."""
    t = 1.0 - 2.0 * np.abs(phase - 0.5)          # triangle 0..1..0
    t = np.clip((t - 0.15) / 0.70, 0.0, 1.0)     # écrête fond et crête
    return r_min + (r_maj - r_min) * t


def tige_filetee(d_nominal: float, longueur: float, pas: float,
                 jeu_radial: float = 0.0) -> trimesh.Trimesh:
    """Tige filetée VERTICALE posée en z=0 — maillage hélicoïdal étanche.
    jeu_radial > 0 : version élargie servant d'OUTIL pour percer un écrou."""
    r_maj = d_nominal / 2 + jeu_radial
    r_min = r_maj - 0.6134 * pas                  # hauteur de filet ISO
    ntheta = 60
    nz = max(8, int(longueur / pas * 22))         # ~22 anneaux par pas
    thetas = np.linspace(0, 2 * np.pi, ntheta, endpoint=False)
    zs = np.linspace(0, longueur, nz)

    verts = []
    for z in zs:
        phase = (z / pas - thetas / (2 * np.pi)) % 1.0
        r = _rayon_filet(phase, r_min, r_maj)
        for th, ri in zip(thetas, r):
            verts.append((ri * np.cos(th), ri * np.sin(th), z))
    verts.append((0.0, 0.0, 0.0))                 # centre bas
    verts.append((0.0, 0.0, longueur))            # centre haut
    i_bas, i_haut = len(verts) - 2, len(verts) - 1

    faces = []
    for iz in range(nz - 1):
        for it in range(ntheta):
            a = iz * ntheta + it
            b = iz * ntheta + (it + 1) % ntheta
            c = (iz + 1) * ntheta + it
            d = (iz + 1) * ntheta + (it + 1) % ntheta
            faces.append([a, b, d])
            faces.append([a, d, c])
    for it in range(ntheta):                      # chapeaux (anneaux plans)
        a, b = it, (it + 1) % ntheta
        faces.append([i_bas, b, a])
        h0 = (nz - 1) * ntheta
        faces.append([i_haut, h0 + a, h0 + b])

    m = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces),
                        process=True)
    m.fix_normals()
    return m


def vis_hex(taille: str = "M6", longueur: float = 30.0) -> trimesh.Trimesh:
    """Vis à tête hexagonale, imprimée tête au plateau (aucun support)."""
    d = float(taille.upper().lstrip("M"))
    pas, surplat, h_tete, _h_ecrou = VISSERIE[taille.upper()]
    tete = _extruder(_hexagone_surplat(surplat), h_tete)
    tige = tige_filetee(d - 0.20, longueur + CHEV, pas)   # -0.10 mm au rayon
    tige.apply_translation([0, 0, h_tete - CHEV])
    piece = union_solides(list(tete) + [tige])
    piece.apply_translation(-piece.bounds[0] * [0, 0, 1])
    return piece


def ecrou_hex(taille: str = "M6") -> trimesh.Trimesh:
    """Écrou hexagonal : prisme moins tige filetée élargie (+0.25 mm)."""
    d = float(taille.upper().lstrip("M"))
    pas, surplat, _h_tete, h_ecrou = VISSERIE[taille.upper()]
    corps = union_solides(_extruder(_hexagone_surplat(surplat), h_ecrou))
    outil = tige_filetee(d, h_ecrou + 4, pas, jeu_radial=0.25)
    outil.apply_translation([0, 0, -2])
    piece = trimesh.boolean.difference([corps, outil], engine="manifold")
    piece.apply_translation(-piece.bounds[0] * [0, 0, 1])
    return piece


def boulon(taille: str = "M6", longueur: float = 30.0) -> trimesh.Scene:
    """Vis + écrou côte à côte (3MF 2 corps) — le duo prêt à imprimer."""
    v = vis_hex(taille, longueur)
    e = ecrou_hex(taille)
    _pas, surplat, _ht, _he = VISSERIE[taille.upper()]
    e.apply_translation([surplat * 1.6, 0, 0])
    scene = trimesh.Scene()
    scene.add_geometry(v, node_name="vis", geom_name="vis")
    scene.add_geometry(e, node_name="ecrou", geom_name="ecrou")
    return scene


def _hexagone_surplat(surplat: float) -> Polygon:
    """Hexagone défini par son SURPLAT (cote clé plate), pointes latérales."""
    r = surplat / np.sqrt(3.0)                    # rayon circonscrit
    a = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    return Polygon([(np.cos(t) * r, np.sin(t) * r) for t in a])


# ═══════════════════════════════ COUVERTS ═══════════════════════════════════
def _capsule(demi_larg: float, y0: float, y1: float) -> Polygon:
    """Manche à bouts ARRONDIS : rectangle terminé par des demi-cercles
    (axe Y, centré en x=0)."""
    from shapely.geometry import LineString
    return LineString([(0, y0 + demi_larg), (0, y1 - demi_larg)]).buffer(
        demi_larg, quad_segs=24)


def _extruder_bombe(prof, ep: float, retrait: float = 0.8) -> list:
    """Extrusion aux arêtes hautes ADOUCIES : pleine section aux 2/3 de la
    hauteur, section érodée jusqu'au sommet (chanfrein ~ galbe imprimé).
    Le retrait crée un épaulement orienté vers le HAUT — aucun surplomb."""
    solides = _extruder(prof, ep * 0.7)
    haut = prof.buffer(-retrait, join_style=1)
    if not haut.is_empty:
        solides += _extruder(haut, ep - ep * 0.7 + CHEV, ep * 0.7 - CHEV)
    return solides


def cuillere(longueur: float = 180, largeur: float = 40) -> trimesh.Trimesh:
    """Cuillère v2 « taillée dans la masse » : cuvette elliptique PEU PROFONDE
    creusée dans un plateau (fond plat -> impression à plat, zéro surplomb :
    la cavité n'a que des faces orientées vers le haut), col plein fusionné
    PLEINE HAUTEUR (jonction solide), manche à bout rond."""
    from shapely.affinity import scale as shp_scale, translate as shp_translate
    from shapely.geometry import Point
    h_bol, ep_manche, prof_cuv = 7.0, 4.5, 5.4
    rx = largeur / 2.0
    bol2d = shp_scale(Point(0, 0).buffer(rx, quad_segs=48), xfact=1.0, yfact=1.42)
    l_bol = rx * 1.42 * 2
    bol2d = shp_translate(bol2d, yoff=l_bol / 2)          # cuvette de y=0 à l_bol
    col = Polygon([(-8.0, l_bol * 0.62), (8.0, l_bol * 0.62),
                   (5.0, l_bol + 14.0), (-5.0, l_bol + 14.0)])
    manche = _capsule(5.5, l_bol + 6.0, longueur)
    prof2d = unary_union([bol2d, col, manche])
    prof2d = prof2d.buffer(2.0, join_style=1).buffer(-2.0, join_style=1)
    haut2d = unary_union([bol2d, col]).intersection(
        box(-rx - 2, -2, rx + 2, l_bol + 6.0))
    piece = union_solides(
        _extruder(prof2d, ep_manche)
        + _extruder(haut2d, h_bol - ep_manche + CHEV, ep_manche - CHEV))
    # cuvette : demi-ellipsoïde soustrait PAR LE DESSUS (fond restant 1.6 mm)
    cav = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    cav.apply_scale([rx - 2.2, (rx - 2.2) * 1.42, prof_cuv])
    cav.apply_translation([0, l_bol / 2, h_bol])
    piece = trimesh.boolean.difference([piece, cav], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


def fourchette(longueur: float = 185, largeur_tete: float = 26) -> trimesh.Trimesh:
    """Fourchette v2 : 4 dents à POINTES effilées (triangles au bout), paume
    trapézoïdale, manche à bout rond, chants supérieurs adoucis."""
    ep, n_dents, l_dent, l_pointe = 3.2, 4, 20.0, 9.0
    w_dent = largeur_tete / (n_dents + (n_dents - 1) * 0.55)
    w_fente = w_dent * 0.55
    dents = []
    for i in range(n_dents):
        x = -largeur_tete / 2 + i * (w_dent + w_fente) + w_dent / 2
        dents.append(Polygon([
            (x - w_dent / 2, l_pointe), (x, 0.0),          # la pointe
            (x + w_dent / 2, l_pointe),
            (x + w_dent / 2, l_pointe + l_dent + 4),
            (x - w_dent / 2, l_pointe + l_dent + 4),
        ]))
    y_palme = l_pointe + l_dent
    palme = Polygon([(-largeur_tete / 2, y_palme), (largeur_tete / 2, y_palme),
                     (largeur_tete / 2 - 1.5, y_palme + 14),
                     (5.5, y_palme + 26), (-5.5, y_palme + 26),
                     (-largeur_tete / 2 + 1.5, y_palme + 14)])
    manche = _capsule(5.5, y_palme + 20, longueur)
    prof = unary_union(dents + [palme, manche])
    prof = prof.buffer(0.7, join_style=1).buffer(-0.7, join_style=1)
    piece = union_solides(_extruder_bombe(prof, ep, retrait=0.8))
    piece.apply_translation(-piece.bounds[0])
    return piece


def couteau(longueur: float = 190) -> trimesh.Trimesh:
    """Couteau v2 : lame à BISEAU sur le dessus (3 étages érodés = tranchant
    doux, non dangereux mais qui coupe le beurre), manche à bout rond galbé."""
    ep, l_lame = 2.8, longueur * 0.45
    lame = Polygon([(-11, 0), (7, 0), (10, l_lame * 0.30), (9, l_lame * 0.78),
                    (2, l_lame), (-9, l_lame * 0.92), (-11, l_lame * 0.30)])
    lame = lame.buffer(2.5, join_style=1).buffer(-2.5, join_style=1)
    manche = _capsule(6.0, l_lame - 10, longueur)
    solides = _extruder(unary_union([lame, manche]), 1.2)
    solides += _extruder(unary_union([lame.buffer(-1.1, join_style=1), manche]),
                         1.0, 1.0)
    solides += _extruder(unary_union([lame.buffer(-2.2, join_style=1),
                                      manche.buffer(-0.9, join_style=1)]),
                         ep - 1.8, 1.8)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece
