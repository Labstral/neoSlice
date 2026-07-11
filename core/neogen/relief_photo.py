# -*- coding: utf-8 -*-
"""neoGen — PHOTO EN RELIEF / LITHOPHANIE : une image devient une plaque 3D.

Principe lithophanie : l'ÉPAISSEUR module la lumière qui traverse la pièce
(imprimée en blanc/clair, éclairée par derrière) — zones SOMBRES de la photo
= matière ÉPAISSE (bloque la lumière), zones CLAIRES = matière FINE. Le
niveau de gris devient donc une carte de hauteurs, maillée en une plaque
ÉTANCHE (dessus en relief, fond plat, murs).

Mode « relief » : même carte de hauteurs mais pensée pour être VUE (pas
rétro-éclairée) : zones claires = hautes, sur un socle plein.

Impression : une lithophanie se sort DEBOUT (couches verticales = dégradés
nets) — c'est l'orientation par défaut, le cadre élargit l'assise. À plat
reste possible (flag) pour les reliefs décoratifs.
"""
from __future__ import annotations

import numpy as np
import trimesh

# Résolution max du maillage (pixels du grand côté). 256 ≈ 190k triangles :
# fin à l'impression, fluide dans le viewer.
_RES_MAX = 256


def _charger_gris(chemin: str) -> np.ndarray:
    """Image -> niveaux de gris 0..1 (0 = noir), lissée pour casser le bruit
    (le bruit devient des picots d'épaisseur à l'impression)."""
    import cv2
    from PIL import Image

    im = Image.open(chemin).convert("RGBA")
    arr = np.asarray(im).astype(np.float32)
    rgb, alpha = arr[..., :3], arr[..., 3:4] / 255.0
    # zones transparentes -> blanc (fines en lithophanie : invisibles)
    gris = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])
    gris = gris * alpha[..., 0] + 255.0 * (1.0 - alpha[..., 0])
    h, w = gris.shape
    f = _RES_MAX / max(h, w)
    if f < 1.0:
        gris = cv2.resize(gris, (max(2, int(w * f)), max(2, int(h * f))),
                          interpolation=cv2.INTER_AREA)
    gris = cv2.GaussianBlur(gris, (3, 3), 0)
    # normalisation douce : on étire sur les percentiles 1-99 (une photo terne
    # donnerait sinon une plaque presque plate, sans contraste)
    lo, hi = np.percentile(gris, 1.0), np.percentile(gris, 99.0)
    if hi - lo < 1e-3:
        raise ValueError("Image uniforme : rien à mettre en relief.")
    return np.clip((gris - lo) / (hi - lo), 0.0, 1.0)


def _plaque_heightfield(h_mm: np.ndarray, largeur: float) -> trimesh.Trimesh:
    """Carte de hauteurs (mm) -> plaque ÉTANCHE : dessus maillé, fond plat à
    z=0, murs périphériques. Construction directe des faces (rapide)."""
    ny, nx = h_mm.shape
    pas = largeur / (nx - 1)
    xs = np.arange(nx) * pas
    ys = (ny - 1 - np.arange(ny)) * pas          # ligne 0 de l'image = haut

    gx, gy = np.meshgrid(xs, ys)
    top = np.column_stack([gx.ravel(), gy.ravel(), h_mm.ravel()])
    bas = top.copy()
    bas[:, 2] = 0.0
    verts = np.vstack([top, bas])
    n = nx * ny                                   # offset des sommets du bas

    idx = np.arange(n).reshape(ny, nx)
    a = idx[:-1, :-1].ravel()
    b = idx[:-1, 1:].ravel()
    c = idx[1:, :-1].ravel()
    d = idx[1:, 1:].ravel()
    faces = [np.column_stack([a, d, b]), np.column_stack([a, c, d])]   # dessus
    faces += [np.column_stack([a + n, b + n, d + n]),                  # dessous
              np.column_stack([a + n, d + n, c + n])]
    # murs : 4 bords (chaque arête du contour relie dessus et dessous)
    for bord in (idx[0, :], idx[-1, ::-1], idx[:, 0][::-1], idx[:, -1]):
        e1, e2 = bord[:-1], bord[1:]
        faces += [np.column_stack([e1, e2, e2 + n]),
                  np.column_stack([e1, e2 + n, e1 + n])]
    m = trimesh.Trimesh(vertices=verts, faces=np.vstack(faces), process=True)
    m.fix_normals()
    return m


def photo_en_relief(image: str, largeur: float = 100.0, ep_min: float = 0.8,
                    ep_max: float = 3.2, mode: str = "lithophanie",
                    cadre: bool = True, debout: bool = True) -> trimesh.Trimesh:
    """Photo -> plaque en relief imprimable.

    mode « lithophanie » : sombre = épais (à rétro-éclairer, filament clair).
    mode « relief »      : clair = haut, sur socle plein de `ep_min` + 1.2 mm.
    `cadre` : bordure pleine hauteur (rigidité + assise du mode debout).
    `debout` : plaque dressée (qualité lithophanie) ; sinon posée à plat.
    """
    ep_min = max(0.4, float(ep_min))
    ep_max = max(ep_min + 0.6, float(ep_max))
    gris = _charger_gris(image)

    if mode == "relief":
        socle = ep_min + 1.2
        h_mm = socle + gris * (ep_max - ep_min)
    else:                                          # lithophanie
        h_mm = ep_max - gris * (ep_max - ep_min)   # sombre -> épais

    ny, nx = h_mm.shape
    pas = largeur / (nx - 1)
    if cadre:
        b = max(2, int(round(3.0 / pas)))          # bordure ~3 mm
        h_cadre = ep_max + 0.6
        h_mm[:b, :] = h_cadre
        h_mm[-b:, :] = h_cadre
        h_mm[:, :b] = h_cadre
        h_mm[:, -b:] = h_cadre

    piece = _plaque_heightfield(h_mm, largeur)
    if debout:
        # dressée face au spectateur (la lumière traverse) — le cadre fait
        # l'assise ; imprimer avec un brim.
        piece.apply_transform(
            trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    piece.apply_translation(-piece.bounds[0])
    return piece
