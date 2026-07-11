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
def cuillere(longueur: float = 180, largeur: float = 42) -> trimesh.Trimesh:
    """Cuillère UNE PIÈCE imprimée à plat : cuvette elliptique peu profonde à
    fond plat (imprimable) + manche plat fusionné dans la paroi."""
    from core.neogen.libre import demi_sphere
    bol = demi_sphere(largeur, creuse=2.0)
    t = np.eye(4)
    t[1, 1] = 1.35                                # allonge la cuvette
    t[2, 2] = 0.62                                # l'aplatit
    bol.apply_transform(t)
    bol.apply_translation([0, 0, -float(bol.bounds[0][2])])
    l_bol = float(bol.bounds[1][1] - bol.bounds[0][1])
    manche_l = longueur - l_bol + 8               # 8 mm de recouvrement
    manche = _extruder(box(-5.5, 0, 5.5, manche_l), 3.2)
    m = union_solides(manche)
    m.apply_translation([0, float(bol.bounds[1][1]) - 8, 0])
    piece = union_solides([bol, m])
    piece.apply_translation(-piece.bounds[0])
    return piece


def fourchette(longueur: float = 185, largeur_tete: float = 27) -> trimesh.Trimesh:
    """Fourchette plate 4 dents (une pièce, 3 mm, imprimée à plat)."""
    l_tete = 52.0
    tete = box(-largeur_tete / 2, 0, largeur_tete / 2, l_tete)
    # 3 fentes -> 4 dents (fentes arrondies, fermées côté manche)
    pas_d = largeur_tete / 4.0
    fentes = []
    for i in range(3):
        x = -largeur_tete / 2 + pas_d * (i + 1)
        fentes.append(box(x - 1.6, -2, x + 1.6, l_tete * 0.62).buffer(0.8))
    manche = box(-5.5, l_tete - 6, 5.5, longueur)
    prof = unary_union([tete, manche]).difference(unary_union(fentes))
    prof = prof.buffer(2.2, join_style=1).buffer(-2.2, join_style=1)
    piece = union_solides(_extruder(prof, 3.0))
    piece.apply_translation(-piece.bounds[0])
    return piece


def couteau(longueur: float = 190) -> trimesh.Trimesh:
    """Couteau de table plat (lame arrondie non coupante, une pièce)."""
    l_lame = longueur * 0.45
    lame = Polygon([(-11, 0), (9, 0), (11, l_lame * 0.35), (9, l_lame * 0.8),
                    (2, l_lame), (-9, l_lame * 0.9), (-11, l_lame * 0.3)])
    lame = lame.buffer(2.5, join_style=1).buffer(-2.5, join_style=1)
    manche = box(-6, l_lame - 8, 6, longueur).buffer(2, join_style=1).buffer(-2, join_style=1)
    prof = unary_union([lame, manche])
    piece = union_solides(_extruder(prof, 2.8))
    piece.apply_translation(-piece.bounds[0])
    return piece
