# -*- coding: utf-8 -*-
"""Solide OpenCascade → maillage triangulaire ÉTANCHE (numpy).

OpenCascade triangule chaque face séparément : les sommets des coutures entre
faces sont dupliqués. On les SOUDE (quantification à 1e-4 mm) : vérifié sur
boîte percée + congés, sphère, fusion cylindre+sphère, cône pointu → étanche,
orienté, accepté par manifold3d."""
from __future__ import annotations

import numpy as np

from neoforge.noyau import occ as O

SOUDURE = 1e-4        # mm


def finesse(forme) -> tuple[float, float]:
    """Déviations linéaire (mm) et angulaire (rad) selon la taille de la pièce :
    lisse à l'impression sans exploser le nombre de triangles."""
    (x0, y0, z0), (x1, y1, z1) = O.boite(forme)
    diag = float(np.linalg.norm([x1 - x0, y1 - y0, z1 - z0]))
    return min(0.05, max(0.005, diag / 2000.0)), 0.2


def _par_face(forme) -> list[tuple[np.ndarray, np.ndarray]]:
    """Triangulation de CHAQUE face, séparément, sommets soudés à l'INTÉRIEUR de
    la face seulement (cela referme la couture d'une sphère ou d'un cylindre,
    sans mêler la face à ses voisines)."""
    lin, ang = finesse(forme)
    O.nettoyer_maillage(forme)
    O.BRepMesh_IncrementalMesh(forme, lin, False, ang, True)
    morceaux = []
    ex = O.TopExp_Explorer(forme, O.TopAbs_FACE)
    while ex.More():
        f = O.face(ex.Current())
        loc = O.TopLoc_Location()
        tri = O.triangulation(f, loc)
        if tri is not None:
            tr = loc.Transformation()
            n = tri.NbNodes()
            pts = np.empty((n, 3))
            for i in range(1, n + 1):
                p = tri.Node(i).Transformed(tr)
                pts[i - 1] = (p.X(), p.Y(), p.Z())
            inverse = f.Orientation() == O.TopAbs_REVERSED
            m = tri.NbTriangles()
            tris = np.empty((m, 3), np.int64)
            for i in range(1, m + 1):
                a, b, c = tri.Triangle(i).Get()
                tris[i - 1] = (a, c, b) if inverse else (a, b, c)
            morceaux.append(souder(pts, tris - 1))
        ex.Next()
    return morceaux


def _assembler(morceaux) -> tuple[np.ndarray, np.ndarray]:
    V, F, off = [], [], 0
    for pts, tris in morceaux:
        V.append(pts)
        F.append(tris + off)
        off += len(pts)
    if not V:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    return np.vstack(V), np.vstack(F)


def _solides(forme) -> list:
    """Les corps distincts de la pièce (une découpe qui garde les deux morceaux
    en produit deux)."""
    out = []
    ex = O.TopExp_Explorer(forme, O.TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def trianguler(forme) -> tuple[np.ndarray, np.ndarray]:
    """(sommets float64 N×3, faces int64 M×3), normales vers l'extérieur. C'est
    le maillage ÉTANCHE, celui de l'export et du calcul de volume.

    La soudure se fait PAR SOLIDE, jamais d'un corps à l'autre : les deux
    moitiés d'une découpe se touchent exactement au plan de coupe, et une
    soudure globale les collait en un maillage non manifold, annoncé comme
    « pièce pas fermée, l'impression sera ratée » (constaté au pilote). Chaque
    corps doit rester un volume fermé de son côté."""
    corps = _solides(forme)
    if len(corps) <= 1:
        return souder(*_assembler(_par_face(forme)))
    return _assembler([souder(*_assembler(_par_face(s))) for s in corps])


def trianguler_affichage(forme) -> tuple[np.ndarray, np.ndarray]:
    """Le maillage pour l'ÉCRAN : chaque face garde ses propres sommets.

    L'ombrage lisse ne moyenne alors les normales qu'à l'intérieur d'une face,
    jamais d'une face à sa voisine. Avec un maillage soudé partout, la normale
    du bord d'une cuvette se mélangeait à celle du plan, et cette normale de
    travers s'étalait le long des grands triangles en éventail : une étoile de
    stries barrait toute la surface plane (retour d'Emmanuel, cuvette creusée
    à la sphère). Le maillage étanche reste, lui, celui de l'export."""
    return _assembler(_par_face(forme))


def souder(V: np.ndarray, F: np.ndarray, tol: float = SOUDURE):
    q = np.round(V / tol).astype(np.int64)
    _u, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.ravel()
    Vn = np.zeros((int(inv.max()) + 1, 3))
    Vn[inv] = V
    Fn = inv[F]
    garde = (Fn[:, 0] != Fn[:, 1]) & (Fn[:, 1] != Fn[:, 2]) & (Fn[:, 0] != Fn[:, 2])
    return Vn, Fn[garde]


def polyligne(e, n_courbe: int = 32) -> np.ndarray:
    """Points d'une arête pour l'afficher et la cliquer (2 points si droite)."""
    c = O.BRepAdaptor_Curve(e)
    u0, u1 = c.FirstParameter(), c.LastParameter()
    n = 2 if c.GetType() == O.GeomAbs_Line else n_courbe
    pts = np.empty((n, 3))
    for i, u in enumerate(np.linspace(u0, u1, n)):
        p = c.Value(float(u))
        pts[i] = (p.X(), p.Y(), p.Z())
    return pts
