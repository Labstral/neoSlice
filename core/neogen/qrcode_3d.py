# -*- coding: utf-8 -*-
"""QR code 3D fonctionnel (neoGen) — 100 % local.

Un QR code ne contient QUE du texte (une URL, un lien menu…) : c'est le téléphone
qui ouvre le lien au scan, neoSlice n'héberge rien. La matrice noir/blanc est
calculée hors-ligne par `segno` (pur Python), puis transformée en géométrie 3D
BICOLORE : une plaque de fond claire + les modules sombres en relief. À l'impression
2 couleurs (changement de filament à la hauteur des modules, ou AMS), le contraste
rend le QR scannable de façon fiable — comme un QR papier.

4 variantes :
  • plat_trous  : plaque carrée + 2 pattes rondes (haut/bas) avec trous traversants
                  (à visser à plat sur une table — le modèle vu au restaurant) ;
  • plat        : la même plaque, sans trous ;
  • presentoir  : QR monté sur un socle incliné (chevalet), posé sur un comptoir ;
  • porte_cle   : petite plaque QR + trou d'anneau.

Sortie : trimesh.Scene à 2 corps (« fond » clair, « modules » sombre) portant leurs
couleurs — même mécanisme multicouleur que la carte de visite / le logo.
"""
from __future__ import annotations

import numpy as np
import trimesh

# Couleurs par défaut (fond clair, modules sombres) — contraste maximal au scan.
_COUL_FOND = "#F2F2F2"
_COUL_MODULE = "#111111"
# Marge « quiet zone » autour du QR (obligatoire pour le scan) — en nb de modules.
_QUIET = 4
# Taille mini d'un module imprimé pour un scan fiable (mm).
_MODULE_MIN_MM = 1.4


def _hex_rgba(h: str) -> list[int]:
    h = h.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255]


def _matrice(url: str, error: str = "m") -> np.ndarray:
    """Matrice booléenne du QR (True = module sombre) via segno, hors-ligne."""
    import segno
    qr = segno.make(url, error=error)
    return np.array([[bool(c) for c in row] for row in qr.matrix], dtype=bool)


_CHEV = 0.2       # léger chevauchement relief (évite le z-fighting à l'union)
_GROOVE = 0.6     # profondeur du sillon en mode « creusé » (mm)


def _modules_2d(mat: np.ndarray, module_mm: float, quiet: int):
    """Union 2D (shapely) de tous les carrés sombres du QR — origine plaque en (0,0).
    Les carrés sont très légèrement dilatés (join carré) pour PONTER les modules qui
    ne se touchent qu'en diagonale (contact ponctuel = maillage non-manifold, non
    imprimable) : les modules deviennent des solides propres, étanches et scannables."""
    from shapely.geometry import box as _box
    from shapely.ops import unary_union
    eps = module_mm * 0.02                            # pont diagonal minimal (~2 %)
    n = mat.shape[0]
    carres = []
    for r in range(n):
        for c in range(n):
            if not mat[r, c]:
                continue
            cx = (quiet + c + 0.5) * module_mm       # ligne 0 en HAUT → inverser r
            cy = (quiet + (n - 1 - r) + 0.5) * module_mm
            h = module_mm / 2.0 + eps
            carres.append(_box(cx - h, cy - h, cx + h, cy + h))
    return unary_union(carres)


def _extrude_multi(poly, hauteur: float, z0: float) -> trimesh.Trimesh:
    """Extrude un (Multi)Polygon shapely en un corps unique, posé à z0."""
    from shapely.geometry import MultiPolygon
    geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    parts = [trimesh.creation.extrude_polygon(g, hauteur) for g in geoms if not g.is_empty]
    m = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    m.apply_translation((0, 0, z0))
    return m


def _fond_modules(mat: np.ndarray, module_mm: float, largeur: float,
                  ep_socle: float, ep_module: float, style: str, quiet: int
                  ) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Renvoie (plaque_fond, modules) selon le STYLE :
      • relief : modules SAILLANTS de `ep_module` au-dessus de la plaque ;
      • lisse  : modules AFFLEURANTS (surface lisse, distinction par la couleur seule) ;
      • creusé : modules EN CREUX de `_GROOVE` sous la surface (sillons tactiles).
    Deux corps distincts (fond clair / modules sombres) → bicolore à l'export."""
    from shapely.geometry import box as _box
    plaque_2d = _box(0, 0, largeur, largeur)
    modules_2d = _modules_2d(mat, module_mm, quiet)

    if style == "relief":
        fond = _extrude_multi(plaque_2d, ep_socle, 0.0)
        modules = _extrude_multi(modules_2d, ep_module + _CHEV, ep_socle - _CHEV)
        return fond, modules

    # lisse / creusé : la plaque a des ALVÉOLES (creux) là où sont les modules ;
    # les modules sombres viennent s'y loger (affleurants ou en retrait). Les parois
    # et les modules DÉBORDENT de _CHEV dans la dalle → leurs faces du dessous sont
    # INTERNES (enfouies) et non coïncidentes avec le dessus de la dalle : le
    # détecteur de surplombs (test « matière directement dessous ») les écarte alors
    # correctement (sinon faux surplombs sur un QR pourtant parfaitement plat).
    z_base = max(0.4, ep_socle - ep_module)
    slab = _extrude_multi(plaque_2d, z_base, 0.0)                 # dalle pleine dessous
    murs = _extrude_multi(plaque_2d.difference(modules_2d),        # parois claires (grille)
                          ep_socle - z_base + _CHEV, z_base - _CHEV)
    fond = trimesh.util.concatenate([slab, murs])
    h_top = ep_socle - (_GROOVE if style == "creuse" else 0.0)    # sommet des modules
    modules = _extrude_multi(modules_2d, max(0.4, h_top - (z_base - _CHEV)),
                             z_base - _CHEV)
    return fond, modules


def _pattes_a_vis(largeur: float, ep: float) -> list:
    """2 pattes rondes (haut/bas, centrées) percées d'un trou traversant, à souder
    à la plaque QR (modèle « à visser à plat »). Origine plaque coin (0,0)."""
    d_rond = largeur * 0.28
    d_trou, marge = 4.2, largeur * 0.06
    pattes = []
    for y in (largeur + d_rond / 2 - marge, -d_rond / 2 + marge):
        rond = trimesh.creation.cylinder(radius=d_rond / 2, height=ep, sections=48)
        rond.apply_translation((largeur / 2, y, ep / 2))
        trou = trimesh.creation.cylinder(radius=d_trou / 2, height=ep * 3, sections=32)
        trou.apply_translation((largeur / 2, y, ep / 2))
        pattes.append(rond.difference(trou))
    return pattes


def _patte_anneau(largeur: float, ep: float) -> trimesh.Trimesh:
    """Patte ronde + trou d'anneau au-dessus de la plaque (variante porte-clé)."""
    d_rond = largeur * 0.26
    y = largeur + d_rond / 2 - largeur * 0.05
    patte = trimesh.creation.cylinder(radius=d_rond / 2, height=ep, sections=48)
    patte.apply_translation((largeur / 2, y, ep / 2))
    trou = trimesh.creation.cylinder(radius=largeur * 0.05, height=ep * 3, sections=32)
    trou.apply_translation((largeur / 2, y, ep / 2))
    return patte.difference(trou)


def _coin_incline(largeur: float, angle_deg: float = 75.0) -> trimesh.Trimesh:
    """Coin plein (prisme à section triangulaire rectangle) posé À PLAT sur z=0,
    dont la face inclinée va de l'arête AVANT (y=0, z=0) à l'arête arrière-haute
    (y=D, z=H) à `angle_deg` depuis l'horizontale. La plaque QR, tournée du même
    angle autour de l'arête avant, se pose exactement sur cette face inclinée.
    Construction par sommets EXPLICITES (aucune rotation approximative)."""
    a = np.radians(angle_deg)
    D = largeur * np.cos(a)                       # profondeur de la base au sol
    H = largeur * np.sin(a)                       # hauteur arrière
    L = largeur
    v = np.array([
        [0, 0, 0], [0, D, 0], [0, D, H],          # face triangulaire x=0
        [L, 0, 0], [L, D, 0], [L, D, H],          # face triangulaire x=L
    ], dtype=float)
    f = np.array([
        [0, 2, 1], [3, 4, 5],                     # 2 caps triangulaires
        [0, 1, 4], [0, 4, 3],                     # base (z=0)
        [1, 2, 5], [1, 5, 4],                     # dos vertical (y=D)
        [0, 3, 5], [0, 5, 2],                     # hypoténuse (face inclinée)
    ], dtype=int)
    coin = trimesh.Trimesh(vertices=v, faces=f, process=True)
    trimesh.repair.fix_normals(coin)
    return coin


def qr_3d(url: str, taille: float = 70.0, variante: str = "plat_trous",
          epaisseur: float = 2.0, ep_module: float = 1.2, style: str = "relief",
          couleur_fond: str = _COUL_FOND, couleur_module: str = _COUL_MODULE,
          error: str = "m") -> trimesh.Scene:
    """Construit le QR code 3D BICOLORE. Renvoie une Scene à 2 corps colorés
    (« fond » clair + « modules » sombres) → 2 slots à l'export.
      • epaisseur : épaisseur de la plaque (mm) ;
      • style     : « relief » (modules saillants), « creuse » (sillons),
                    « lisse » (affleurant, contraste par la couleur seule).
    Le module est agrandi si besoin pour rester scannable (≥ ~1.4 mm)."""
    url = (url or "").strip() or "https://neoslice.app"
    mat = _matrice(url, error=error)
    n = int(mat.shape[0])
    total_modules = n + 2 * _QUIET

    # taille : garantir un module scannable
    taille = float(taille)
    if taille / total_modules < _MODULE_MIN_MM:
        taille = _MODULE_MIN_MM * total_modules
    module_mm = taille / total_modules
    largeur = taille                                 # plaque carrée (quiet zone incluse)

    style = style if style in ("relief", "creuse", "lisse") else "relief"
    ep_socle = float(epaisseur)
    porte_cle = (variante == "porte_cle")
    if porte_cle:
        ep_socle = max(ep_socle, 2.5)
    ep_socle = max(1.0, ep_socle)
    # en relief la hauteur module est libre ; sinon elle est bornée par la plaque
    if style != "relief":
        ep_module = min(float(ep_module), ep_socle - 0.4)
    ep_module = max(0.4, float(ep_module))

    # ── Plaque (claire) + modules (sombres) selon le STYLE ────────────────────
    fond, modules = _fond_modules(mat, module_mm, largeur, ep_socle, ep_module,
                                  style, _QUIET)

    # pattes de fixation selon la variante
    if variante == "plat_trous":
        fond = trimesh.util.concatenate([fond] + _pattes_a_vis(largeur, ep_socle))
    elif porte_cle:
        fond = trimesh.util.concatenate([fond, _patte_anneau(largeur, ep_socle)])

    corps_fond, corps_modules = fond, modules

    # ── Présentoir incliné : QR posé sur un coin à 75° (chevalet de comptoir) ──
    if variante == "presentoir":
        ang = 75.0
        coin = _coin_incline(largeur, ang)
        # tourner l'ensemble QR autour de l'arête avant (X, y=0, z=0) → il se pose
        # EXACTEMENT sur la face inclinée du coin (même angle, même arête).
        R = trimesh.transformations.rotation_matrix(np.radians(ang), [1, 0, 0],
                                                     point=[0, 0, 0])
        corps_fond = fond.copy(); corps_fond.apply_transform(R)
        corps_modules = modules.copy(); corps_modules.apply_transform(R)
        corps_fond = trimesh.util.concatenate([coin, corps_fond])   # coin = couleur fond

    corps_fond.visual.face_colors = _hex_rgba(couleur_fond)
    corps_modules.visual.face_colors = _hex_rgba(couleur_module)

    # Scene à 2 CORPS colorés : la route multicouleur neoGen l'affiche assemblée
    # (afficher_carte) et l'exporte en 2 slots (build_multicouleur / from_scene).
    scene = trimesh.Scene()
    scene.add_geometry(corps_fond, geom_name="fond")
    scene.add_geometry(corps_modules, geom_name="modules")
    return scene
