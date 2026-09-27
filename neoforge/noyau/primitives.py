# -*- coding: utf-8 -*-
"""Formes simples → solides OpenCascade, avec la sémantique de la console :
dimensions centrées sur l'origine, rotation X puis Y puis Z (degrés), puis
translation à la position."""
from __future__ import annotations

import math

from neoforge.noyau import occ as O
from neoforge.projet import contours as C

MINI = 0.05          # mm : en dessous, OpenCascade refuse la forme


def _trsf(pos, rot):
    t = O.gp_Trsf()
    t.SetTranslation(O.gp_Vec(float(pos[0]), float(pos[1]), float(pos[2])))
    origine = O.gp_Pnt(0, 0, 0)
    # t = T · Rz · Ry · Rx : appliqué à un point, Rx d'abord (comme la console)
    for axe, angle in ((O.gp_Dir(0, 0, 1), rot[2]), (O.gp_Dir(0, 1, 0), rot[1]),
                       (O.gp_Dir(1, 0, 0), rot[0])):
        if abs(float(angle)) > 1e-9:
            r = O.gp_Trsf()
            r.SetRotation(O.gp_Ax1(origine, axe), math.radians(float(angle)))
            t.Multiply(r)
    return t


def _extruder(points, vecteur):
    """Un contour fermé, poussé en ligne droite : sert au coin et au prisme."""
    contour = O.BRepBuilderAPI_MakePolygon()
    for x, y, z in points:
        contour.Add(O.gp_Pnt(float(x), float(y), float(z)))
    contour.Close()
    face = O.BRepBuilderAPI_MakeFace(contour.Wire()).Face()
    return O.BRepPrimAPI_MakePrism(face, O.gp_Vec(*[float(v) for v in vecteur])).Shape()


def _engrenage(forme, d):
    """Une roue dentée. Le contour vient de `projet/contours.py`, partagé avec
    l'aperçu rapide : les deux doivent montrer la MÊME dent."""
    pts = C.roue(int(getattr(forme, "cotes", 16)),
                 str(getattr(forme, "variante", "") or "droit"),
                 d[0] / 2.0, d[1] / 2.0)
    h = max(MINI, d[2])
    return _extruder([(x, y, -h / 2) for x, y in pts], (0, 0, h))


def _helice(rayon: float, pas: float, hauteur: float):
    """Une hélice de `hauteur` millimètres, d'un tour tous les `pas`.

    On la décrit comme une DROITE tracée sur un cylindre : dans le repère
    (angle, hauteur) de la surface cylindrique, une hélice est une ligne
    droite. C'est la construction exacte, et elle est instantanée."""
    surface = O.Geom_CylindricalSurface(
        O.gp_Ax3(O.gp_Pnt(0, 0, 0), O.gp_Dir(0, 0, 1)), rayon)
    ligne = O.Geom2d_Line(O.gp_Lin2d(O.gp_Pnt2d(0.0, 0.0),
                                     O.gp_Dir2d(2 * math.pi, pas)))
    longueur = (hauteur / pas) * math.sqrt((2 * math.pi) ** 2 + pas ** 2)
    arete = O.BRepBuilderAPI_MakeEdge(ligne, surface, 0.0, longueur).Edge()
    O.BRepLib.BuildCurves3d_s(arete)
    return O.BRepBuilderAPI_MakeWire(arete).Wire()


def _taraudage(forme, d):
    """L'outil d'un TROU FILETÉ : la forme d'une vis, à creuser dans la pièce.

    C'est un noyau cylindrique au diamètre intérieur, plus un filet hélicoïdal
    qui monte jusqu'au diamètre nominal. Creusé dans une pièce, il y laisse le
    pas de vis dans lequel une vraie vis se visse.

    ⚠️ LE point délicat : le filet doit PLONGER dans le noyau, et non l'effleurer.
    Un profil qui part exactement du rayon intérieur rend les deux surfaces
    tangentes, et un booléen sur des surfaces tangentes part en vrille. Mesuré :
    filet effleurant, la fusion coûte 7,4 secondes et échoue sur plusieurs
    diamètres (elle ne rend que le noyau, donc un trou lisse) ; filet plongeant
    jusqu'à 55 % du rayon, elle coûte 0,3 à 2,4 secondes et rend un solide
    VALIDE à toutes les tailles de M2 à M12.

    (Essayé et écarté : rendre les deux morceaux dans un assemblage pour percer
    d'un coup. C'est rapide, mais le résultat est topologiquement faux, avec un
    volume nul sur M2 et NÉGATIF sur M12. Et le noyau installé ici est allégé,
    il n'expose pas l'API à plusieurs outils qui aurait fait ça proprement.)
    """
    PLONGEE = 0.55            # part du rayon intérieur où commence le profil
    diametre = max(MINI, d[0])
    pas = max(0.15, float(getattr(forme, "pas", 1.0)))
    hauteur = max(MINI, d[2])
    r_mineur = max(MINI / 2, (diametre - 1.0825 * pas) / 2.0)
    r_majeur = diametre / 2.0
    # Le filet part un pas sous la pièce et la dépasse d'autant : sans cela le
    # premier et le dernier filet sont tronqués et la vis accroche mal.
    debut, montee = -pas, hauteur + 2 * pas
    profil = O.BRepBuilderAPI_MakePolygon()
    r_pied = r_mineur * PLONGEE
    for point in ((r_pied, 0.0, -pas / 2.0), (r_majeur, 0.0, 0.0),
                  (r_pied, 0.0, pas / 2.0)):
        profil.Add(O.gp_Pnt(*point))
    profil.Close()
    tuyau = O.BRepOffsetAPI_MakePipeShell(_helice(r_mineur, pas, montee))
    tuyau.Add(profil.Wire(), False, True)
    tuyau.SetMode(O.gp_Dir(0, 0, 1))
    tuyau.Build()
    tuyau.MakeSolid()
    filet = O.BRepBuilderAPI_Transform(
        tuyau.Shape(), _trsf([0, 0, debut - hauteur / 2.0], [0, 0, 0]), True).Shape()
    noyau = O.BRepPrimAPI_MakeCylinder(
        O.gp_Ax2(O.gp_Pnt(0, 0, -hauteur / 2.0 + debut), O.gp_Dir(0, 0, 1)),
        r_mineur, montee).Shape()
    fusion = O.BRepAlgoAPI_Fuse(noyau, filet)
    if not fusion.IsDone():
        return noyau              # au pire un trou lisse, jamais une erreur
    return fusion.Shape()


def _cadre(forme, d):
    """Cadre ou anneau : le CONTOUR seul, vide au milieu.

    Le contour extérieur est extrudé, puis le contour intérieur est retiré.
    Les deux viennent de `projet/contours.py`, partagé avec l'aperçu rapide."""
    h = max(MINI, d[2])
    bord = max(0.2, float(getattr(forme, "bord", 4.0)))
    rx, ry = d[0] / 2.0, d[1] / 2.0
    if forme.forme == "anneau":
        dehors, dedans = C.anneau(rx, ry, bord)
    else:
        dehors, dedans = C.cadre(int(getattr(forme, "cotes", 4)), rx, ry, bord)
    plein = _extruder([(x, y, -h / 2) for x, y in dehors], (0, 0, h))
    if dedans is None:
        return plein               # bord plus épais que la pièce : elle est pleine
    # L'outil intérieur dépasse des deux côtés, sinon il laisse une pellicule.
    trou = _extruder([(x, y, -h / 2 - 1.0) for x, y in dedans], (0, 0, h + 2.0))
    return O.BRepAlgoAPI_Cut(plein, trou).Shape()


def _prisme_elliptique(dx: float, dy: float, h: float):
    """Cylindre OVALE : une ellipse de diamètres dx et dy, poussée sur h.

    gp_Elips veut son GRAND rayon en premier et le place sur l'axe X de son
    repère : on oriente donc ce repère selon le plus grand des deux diamètres,
    sinon OpenCascade refuse la forme."""
    grand, petit = max(dx, dy) / 2.0, min(dx, dy) / 2.0
    majeur = O.gp_Dir(1, 0, 0) if dx >= dy else O.gp_Dir(0, 1, 0)
    repere = O.gp_Ax2(O.gp_Pnt(0, 0, -h / 2.0), O.gp_Dir(0, 0, 1), majeur)
    arete = O.BRepBuilderAPI_MakeEdge(O.gp_Elips(repere, grand, petit)).Edge()
    face = O.BRepBuilderAPI_MakeFace(O.BRepBuilderAPI_MakeWire(arete).Wire()).Face()
    return O.BRepPrimAPI_MakePrism(face, O.gp_Vec(0, 0, h)).Shape()


def solide(forme):
    """Solide OpenCascade d'une étape Forme (projet/modele.py)."""
    d = [max(MINI, float(v)) for v in forme.dim]
    if forme.forme == "cube":
        s = O.BRepPrimAPI_MakeBox(O.gp_Pnt(-d[0] / 2, -d[1] / 2, -d[2] / 2),
                                  d[0], d[1], d[2]).Shape()
    elif forme.forme == "sphere":
        s = O.BRepPrimAPI_MakeSphere(O.gp_Pnt(0, 0, 0), d[0] / 2).Shape()
    elif forme.forme == "tore":
        # d[0] = diamètre du cercle porteur, d[1] = diamètre du tube.
        s = O.BRepPrimAPI_MakeTorus(
            O.gp_Ax2(O.gp_Pnt(0, 0, 0), O.gp_Dir(0, 0, 1)),
            max(MINI, d[0] / 2), max(MINI, d[1] / 2)).Shape()
    elif forme.forme == "coin":
        # Une rampe : pleine hauteur en X négatif, nulle en X positif. On la
        # bâtit comme un triangle extrudé, ce qui est parfaitement prévisible.
        x, y, z = d[0] / 2, d[1] / 2, d[2] / 2
        s = _extruder([(-x, -y, -z), (x, -y, -z), (-x, -y, z)], (0, d[1], 0))
    elif forme.forme == "prisme":
        n = max(3, min(24, int(getattr(forme, "cotes", 6))))
        r, h = d[0] / 2, d[2]
        s = _extruder([(r * math.cos(2 * math.pi * k / n),
                        r * math.sin(2 * math.pi * k / n), -h / 2)
                       for k in range(n)], (0, 0, h))
    elif forme.forme == "engrenage":
        s = _engrenage(forme, d)
    elif forme.forme == "taraudage":
        s = _taraudage(forme, d)
    elif forme.forme in ("cadre", "anneau"):
        s = _cadre(forme, d)
    elif forme.forme == "cylindre" and abs(d[0] - d[1]) > 1e-6:
        # OVALE : le cylindre a deux diamètres (demande d'Emmanuel). On bâtit
        # une VRAIE ellipse, pas un cercle aplati par une mise à l'échelle : la
        # surface reste exacte, donc les arrondis et l'export aussi.
        s = _prisme_elliptique(d[0], d[1], d[2])
    else:
        h = d[2]
        axe = O.gp_Ax2(O.gp_Pnt(0, 0, -h / 2), O.gp_Dir(0, 0, 1))
        r_bas = d[0] / 2
        # Diamètre du haut : le cône accepte 0 (pointe), la console aussi.
        r_haut = r_bas if forme.forme == "cylindre" else max(0.0, float(forme.dim[1])) / 2
        if abs(r_bas - r_haut) < 1e-6:
            s = O.BRepPrimAPI_MakeCylinder(axe, r_bas, h).Shape()
        else:
            s = O.BRepPrimAPI_MakeCone(axe, r_bas, r_haut, h).Shape()
    return O.BRepBuilderAPI_Transform(s, _trsf(forme.pos, forme.rot), True).Shape()
