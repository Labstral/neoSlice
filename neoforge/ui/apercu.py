# -*- coding: utf-8 -*-
"""Le maillage de l'aperçu d'une forme, construit sans le noyau.

Pendant un geste, l'aperçu doit parfois être REFAIT (un cône dont les deux
diamètres changent ne se met pas à l'échelle). Passer par OpenCascade coûtait
alors plusieurs millisecondes par pas de souris ; ces primitives-là se
fabriquent en numpy en quelques dixièmes de milliseconde, et ce sont
exactement les mêmes formes (l'aperçu montre la primitive, pas le résultat des
opérations booléennes)."""
from __future__ import annotations

import numpy as np

RESOLUTION = 64


def _cercle(n: int) -> tuple[np.ndarray, np.ndarray]:
    a = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.cos(a), np.sin(a)


def _revolution(r_bas: float, r_haut: float, h: float,
                n: int = RESOLUTION) -> tuple[np.ndarray, np.ndarray]:
    """Cylindre (deux rayons égaux), cône tronqué, ou cône pointu (r_haut = 0),
    centré sur l'origine et dressé selon Z, comme les primitives du noyau."""
    cos, sin = _cercle(n)
    i = np.arange(n)
    suivant = (i + 1) % n
    points = [np.column_stack([r_bas * cos, r_bas * sin, np.full(n, -h / 2.0)])]
    faces = []
    pointu = r_haut <= 1e-6
    if pointu:
        sommet = n                                  # un seul point en haut
        points.append(np.array([[0.0, 0.0, h / 2.0]]))
        faces.append(np.column_stack([i, suivant, np.full(n, sommet)]))
        centres = sommet + 1
    else:
        haut = n + i
        points.append(np.column_stack([r_haut * cos, r_haut * sin,
                                       np.full(n, h / 2.0)]))
        faces.append(np.column_stack([i, suivant, n + suivant]))
        faces.append(np.column_stack([i, n + suivant, haut]))
        centres = 2 * n
        points.append(np.array([[0.0, 0.0, h / 2.0]]))
        # Couvercle du haut orienté vers le HAUT : dans l'autre sens il était
        # retourné (64 triangles sur 256), ce que le test d'orientation a
        # attrapé aussitôt, alors que je l'avais écarté par le raisonnement.
        faces.append(np.column_stack([np.full(n, centres), haut, n + suivant]))
        centres += 1
    points.append(np.array([[0.0, 0.0, -h / 2.0]]))   # centre du disque du bas
    faces.append(np.column_stack([np.full(n, centres), suivant, i]))
    return np.vstack(points), np.vstack(faces).astype(np.int64)


def _sphere(rayon: float, meridiens: int = 48, paralleles: int = 24):
    cos, sin = _cercle(meridiens)
    theta = np.linspace(0.0, np.pi, paralleles + 2)[1:-1]      # sans les pôles
    anneaux = []
    for t in theta:
        anneaux.append(np.column_stack([rayon * np.sin(t) * cos,
                                        rayon * np.sin(t) * sin,
                                        np.full(meridiens, rayon * np.cos(t))]))
    points = np.vstack(anneaux + [np.array([[0.0, 0.0, rayon]]),
                                  np.array([[0.0, 0.0, -rayon]])])
    nord, sud = len(points) - 2, len(points) - 1
    i = np.arange(meridiens)
    suivant = (i + 1) % meridiens
    # Triangles orientés VERS L'EXTÉRIEUR. Dans l'autre sens, la sphère est
    # retournée : l'élimination des faces arrière fait alors disparaître tout le
    # volume et il ne reste qu'un contour vert (retour d'Emmanuel, la sphère
    # sélectionnée n'était pas pleine comme les autres formes).
    faces = [np.column_stack([np.full(meridiens, nord), i, suivant])]
    for k in range(len(theta) - 1):
        haut, bas = k * meridiens, (k + 1) * meridiens
        faces.append(np.column_stack([haut + i, bas + i, bas + suivant]))
        faces.append(np.column_stack([haut + i, bas + suivant, haut + suivant]))
    dernier = (len(theta) - 1) * meridiens
    faces.append(np.column_stack([np.full(meridiens, sud), dernier + suivant,
                                  dernier + i]))
    return points, np.vstack(faces).astype(np.int64)


def _cube(dx: float, dy: float, dz: float):
    x, y, z = dx / 2.0, dy / 2.0, dz / 2.0
    points = np.array([[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z],
                       [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]], float)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    faces = []
    for a, b, c, d in quads:
        faces.append((a, b, c))
        faces.append((a, c, d))
    return points, np.array(faces, np.int64)


def _tore(grand: float, petit: float, n: int = 48, m: int = 20):
    """Anneau : `grand` est le rayon du cercle porteur, `petit` celui du tube."""
    u = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    v = np.linspace(0.0, 2 * np.pi, m, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")
    rayon = grand + petit * np.cos(V)
    points = np.column_stack([(rayon * np.cos(U)).ravel(),
                              (rayon * np.sin(U)).ravel(),
                              (petit * np.sin(V)).ravel()])
    i, j = np.meshgrid(np.arange(n), np.arange(m), indexing="ij")
    a = (i * m + j).ravel()
    b = (((i + 1) % n) * m + j).ravel()
    c = (((i + 1) % n) * m + (j + 1) % m).ravel()
    d = (i * m + (j + 1) % m).ravel()
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    return points, faces.astype(np.int64)


def _coin(dx: float, dy: float, dz: float):
    """Rampe : pleine hauteur en X négatif, nulle en X positif."""
    x, y, z = dx / 2.0, dy / 2.0, dz / 2.0
    points = np.array([[-x, -y, -z], [x, -y, -z], [-x, -y, z],
                       [-x, y, -z], [x, y, -z], [-x, y, z]], float)
    faces = np.array([[0, 1, 2], [3, 5, 4],            # les deux triangles
                      [0, 3, 4], [0, 4, 1],            # le dessous
                      [0, 5, 3], [0, 2, 5],            # le dos vertical
                      [1, 4, 5], [1, 5, 2]], np.int64)  # la pente
    return points, faces


def couper_maillage(V, F, plans):
    """Rogne le maillage par des demi-espaces, en le REFERMANT à chaque coupe.

    Une découpe posée après la forme en retire une moitié. L'aperçu, lui, montre
    la primitive entière : la moitié retirée restait donc peinte en surbrillance,
    absente de la pièce mais bien visible (retour d'Emmanuel). On applique ici
    les mêmes plans à l'aperçu.

    Le maillage est REFERMÉ et non simplement tronqué : ouvert, un aperçu
    translucide laisse voir son propre intérieur et redessine « un cube dans un
    cube ». Si la coupe ne laisse rien, on renvoie un maillage vide plutôt que de
    lever une erreur."""
    if not plans:
        return V, F
    import pyvista as pv

    F = np.asarray(F)
    if not len(F):
        return V, F
    vide = (np.zeros((0, 3), float), np.zeros((0, 3), np.int64))
    maillage = pv.PolyData(np.asarray(V, float),
                           np.column_stack([np.full(len(F), 3), F]).ravel())
    for normale, origine in plans:
        if maillage.n_points == 0:
            return vide
        try:
            maillage = maillage.clip_closed_surface(normal=tuple(normale),
                                                   origin=tuple(origine))
        except Exception:
            return V, F          # au pire l'aperçu entier, jamais de plantage
    if maillage.n_points == 0 or maillage.n_cells == 0:
        return vide
    maillage = maillage.triangulate()
    try:
        faces = np.asarray(maillage.regular_faces, np.int64)
    except Exception:
        faces = np.asarray(maillage.faces, np.int64).reshape(-1, 4)[:, 1:]
    if not len(faces):
        return vide
    return np.asarray(maillage.points, float), faces


def _prisme(exterieur, interieur, h: float) -> tuple[np.ndarray, np.ndarray]:
    """Contour extrudé sur `h`, centré sur l'origine.

    Avec un contour INTÉRIEUR (cadre, anneau), les deux boucles ont le même
    nombre de points et se correspondent une à une : le dessus et le dessous
    se ferment par un ruban entre elles. Sans contour intérieur, les couvercles
    se ferment en éventail depuis le centre, ce qui vaut pour toute forme
    étoilée vue de son centre, engrenage compris."""
    ext = np.asarray(exterieur, float)
    n = len(ext)
    i = np.arange(n)
    suivant = (i + 1) % n
    bas = np.column_stack([ext, np.full(n, -h / 2.0)])
    haut = np.column_stack([ext, np.full(n, h / 2.0)])
    points = [bas, haut]
    faces = [np.column_stack([i, suivant, n + suivant]),
             np.column_stack([i, n + suivant, n + i])]
    if interieur is None:
        centre = 2 * n
        points.append(np.array([[0.0, 0.0, h / 2.0], [0.0, 0.0, -h / 2.0]]))
        faces.append(np.column_stack([np.full(n, centre), n + i, n + suivant]))
        faces.append(np.column_stack([np.full(n, centre + 1), suivant, i]))
        return np.vstack(points), np.vstack(faces).astype(np.int64)
    ins = np.asarray(interieur, float)
    ib, ih = 2 * n + i, 3 * n + i
    points.append(np.column_stack([ins, np.full(n, -h / 2.0)]))
    points.append(np.column_stack([ins, np.full(n, h / 2.0)]))
    # paroi intérieure, tournée vers le trou
    faces.append(np.column_stack([ib, 3 * n + suivant, 2 * n + suivant]))
    faces.append(np.column_stack([ib, ih, 3 * n + suivant]))
    # couvercles en ruban entre les deux contours
    faces.append(np.column_stack([n + i, 3 * n + i, 3 * n + suivant]))
    faces.append(np.column_stack([n + i, 3 * n + suivant, n + suivant]))
    faces.append(np.column_stack([i, 2 * n + suivant, 2 * n + i]))
    faces.append(np.column_stack([i, suivant, 2 * n + suivant]))
    return np.vstack(points), np.vstack(faces).astype(np.int64)


def maillage_local(forme) -> tuple[np.ndarray, np.ndarray]:
    """Sommets et triangles de la forme, dans son repère propre (centrée sur
    l'origine, sans rotation) : c'est ce repère que l'aperçu transforme."""
    d = [max(0.0, float(v)) for v in forme.dim]
    if forme.forme == "cube":
        return _cube(max(d[0], 1e-3), max(d[1], 1e-3), max(d[2], 1e-3))
    if forme.forme == "sphere":
        return _sphere(max(d[0], 1e-3) / 2.0)
    if forme.forme == "tore":
        return _tore(max(d[0], 1e-3) / 2.0, max(d[1], 1e-3) / 2.0)
    if forme.forme == "coin":
        return _coin(max(d[0], 1e-3), max(d[1], 1e-3), max(d[2], 1e-3))
    if forme.forme == "prisme":
        rayon = max(d[0], 1e-3) / 2.0
        cotes = max(3, min(24, int(getattr(forme, "cotes", 6))))
        return _revolution(rayon, rayon, max(d[2], 1e-3), n=cotes)
    # ⚠️ Les formes ci dessous ont été ajoutées au NOYAU d'abord, et l'aperçu
    # rapide les a ignorées : elles retombaient sur le cas par défaut, un
    # cylindre. Emmanuel a donc vu « un rond vert au milieu du cadre », qui ne
    # suivait pas la taille. Le contour vient maintenant du module PARTAGÉ
    # `projet/contours.py`, exactement celui que le noyau découpe.
    from neoforge.projet import contours as C
    hauteur = max(d[2], 1e-3)
    if forme.forme in ("cadre", "anneau"):
        rx, ry = max(d[0], 1e-3) / 2.0, max(d[1], 1e-3) / 2.0
        bord = max(0.2, float(getattr(forme, "bord", 4.0)))
        dehors, dedans = (C.anneau(rx, ry, bord) if forme.forme == "anneau"
                          else C.cadre(int(getattr(forme, "cotes", 4)), rx, ry, bord))
        return _prisme(dehors, dedans, hauteur)
    if forme.forme == "engrenage":
        return _prisme(C.roue(int(getattr(forme, "cotes", 16)),
                              str(getattr(forme, "variante", "") or "droit"),
                              max(d[0], 1e-3) / 2.0, max(d[1], 1e-3) / 2.0),
                       None, hauteur)
    if forme.forme == "taraudage":
        # Le filet ne se voit pas à l'échelle d'un aperçu : un cylindre au bon
        # diamètre suffit, et il se construit en un clin d'œil.
        rayon = max(d[0], 1e-3) / 2.0
        return _revolution(rayon, rayon, hauteur)
    if forme.forme == "cylindre" and abs(d[0] - d[1]) > 1e-6:
        return _prisme(C.ellipse(max(d[0], 1e-3) / 2.0, max(d[1], 1e-3) / 2.0),
                       None, hauteur)
    r_bas = max(d[0], 1e-3) / 2.0
    r_haut = r_bas if forme.forme == "cylindre" else d[1] / 2.0
    return _revolution(r_bas, r_haut, hauteur)
