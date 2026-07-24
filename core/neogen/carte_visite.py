# -*- coding: utf-8 -*-
"""neoGen — PERSONNALISATEUR DE CARTE DE VISITE.

Une carte = un socle (couleur de base) + des ÉLÉMENTS en relief (texte, logo),
chacun avec SA couleur. À l'export, chaque couleur devient un CORPS séparé du
3MF assigné à un slot de filament : dans le slicer, on retrouve autant de slots
que de couleurs, pré-remplis — il ne reste qu'à charger le bon filament.

Positionnement STRUCTURÉ (v1) : chaque élément a un alignement (gauche/centre/
droite × haut/milieu/bas) + un décalage fin X/Y. Fiable et rapide ; le
glisser-déposer libre pourra venir plus tard.

Repère : la carte est CENTRÉE en (0,0). x ∈ [-L/2, L/2], y ∈ [-H/2, H/2].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
from shapely.affinity import translate as _tr
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union

from loguru import logger

from core.neogen.goodies import _extruder, texte_multilignes, CHEVAUCHEMENT
from core.neogen.geo_utils import union_solides

CHEV = CHEVAUCHEMENT
MARGE = 4.0                                   # marge intérieure (mm)


@dataclass
class ElementTexte:
    texte: str = ""
    police: str | None = None
    hauteur: float = 4.0                      # hauteur de capitale (mm)
    espacement: float = 0.0                   # mm entre lettres (0 = normal)
    align_h: str = "centre"                   # gauche | centre | droite
    align_v: str = "milieu"                   # haut | milieu | bas
    dx: float = 0.0
    dy: float = 0.0
    relief: float = 0.6                        # hauteur (relief) ou profondeur (gravé)
    mode: str = "relief"                       # relief | grave | lisse
    couleur: str = "#111111"
    type: str = "texte"


@dataclass
class ElementLogo:
    chemin: str = ""
    largeur: float = 18.0
    align_h: str = "centre"
    align_v: str = "milieu"
    dx: float = 0.0
    dy: float = 0.0
    relief: float = 0.6
    couleur: str = "#111111"
    type: str = "logo"


@dataclass
class ElementTrait:
    longueur: float = 40.0
    epaisseur: float = 1.0
    orientation: str = "horizontal"           # horizontal | vertical
    align_h: str = "centre"
    align_v: str = "milieu"
    dx: float = 0.0
    dy: float = 0.0
    relief: float = 0.6
    couleur: str = "#111111"
    type: str = "trait"


@dataclass
class ElementCadre:
    largeur: float = 60.0
    hauteur: float = 35.0
    epaisseur: float = 1.5                     # épaisseur du trait du cadre (mm)
    align_h: str = "centre"
    align_v: str = "milieu"
    dx: float = 0.0
    dy: float = 0.0
    relief: float = 0.6
    couleur: str = "#111111"
    type: str = "cadre"


@dataclass
class CarteSpec:
    largeur: float = 85.0                     # format standard 85 × 55 mm
    hauteur: float = 55.0
    ep: float = 1.6
    rayon: float = 3.5                         # rayon des coins
    couleur_base: str = "#FFFFFF"
    elements: list = field(default_factory=list)


def _hex_rgba(h: str) -> list[int]:
    h = (h or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255]
    except ValueError:
        return [255, 255, 255, 255]


def _polygones(geom):
    """Extrait récursivement TOUS les Polygon d'une géométrie shapely (gère
    GeometryCollection : certaines polices produisent des géométries mixtes
    polygone+ligne qui, sinon, cassaient l'aperçu et la lithophanie)."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    out = []
    for g in getattr(geom, "geoms", []):
        out.extend(_polygones(g))
    return out


def _forme_element(el, spec: CarteSpec) -> MultiPolygon | None:
    """Contour 2D de l'élément, centré sur son propre repère (0,0)."""
    tp = getattr(el, "type", "texte")
    if tp == "trait":
        L = max(1.0, float(el.longueur))
        e = max(0.3, float(el.epaisseur))
        if getattr(el, "orientation", "horizontal") == "vertical":
            L, e = e, L
        return MultiPolygon([box(-L / 2, -e / 2, L / 2, e / 2)])
    if tp == "cadre":
        L = max(3.0, float(el.largeur))
        H = max(3.0, float(el.hauteur))
        e = max(0.3, min(float(el.epaisseur), min(L, H) / 2 - 0.2))
        cadre = box(-L / 2, -H / 2, L / 2, H / 2).difference(
            box(-L / 2 + e, -H / 2 + e, L / 2 - e, H / 2 - e))
        if isinstance(cadre, Polygon):
            cadre = MultiPolygon([cadre])
        return cadre if not cadre.is_empty else None
    if tp == "logo":
        if not el.chemin:
            return None
        from pathlib import Path as _P
        from core.neogen import logo as _L
        src = _P(el.chemin)
        couches = (_L.charger_svg(str(src)) if src.suffix.lower() == ".svg"
                   else _L.charger_png(str(src), 3))
        couches = _L._normaliser(couches, el.largeur)
        mp = unary_union([g for _c, m in couches for g in m.geoms])
    else:
        if not (el.texte or "").strip():
            return None
        mp = texte_multilignes(el.texte, el.hauteur, police=el.police,
                               espacement=getattr(el, "espacement", 0.0))
        mp = unary_union(list(mp.geoms))
    polys = _polygones(mp)                        # robuste aux GeometryCollection
    if not polys:
        return None
    return MultiPolygon(polys)


def _placer(mp, spec: CarteSpec, el) -> MultiPolygon:
    """Positionne `mp` sur la carte selon l'alignement + décalage de `el`, et
    le RECADRE dans la zone imprimable (jamais de relief qui déborde du bord)."""
    minx, miny, maxx, maxy = mp.bounds
    w, h = maxx - minx, maxy - miny
    cx0, cy0 = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    lim_x = spec.largeur / 2 - MARGE - w / 2
    lim_y = spec.hauteur / 2 - MARGE - h / 2
    tx = {"gauche": -lim_x, "centre": 0.0, "droite": lim_x}.get(el.align_h, 0.0)
    ty = {"bas": -lim_y, "milieu": 0.0, "haut": lim_y}.get(el.align_v, 0.0)
    tx = max(-lim_x, min(lim_x, tx + el.dx))
    ty = max(-lim_y, min(lim_y, ty + el.dy))
    mp = _tr(mp, xoff=tx - cx0, yoff=ty - cy0)
    zone = box(-spec.largeur / 2 + 1.0, -spec.hauteur / 2 + 1.0,
               spec.largeur / 2 - 1.0, spec.hauteur / 2 - 1.0)
    mp = mp.intersection(zone)
    if isinstance(mp, Polygon):
        mp = MultiPolygon([mp])
    return mp


def _socle_2d(spec: CarteSpec) -> Polygon:
    r = max(0.0, min(spec.rayon, min(spec.largeur, spec.hauteur) / 2 - 0.5))
    rect = box(-spec.largeur / 2, -spec.hauteur / 2,
               spec.largeur / 2, spec.hauteur / 2)
    return rect.buffer(-r, join_style=1).buffer(r, join_style=1)   # coins ronds


def _geoms(mp):
    return mp.geoms if isinstance(mp, MultiPolygon) else [mp]


def _prof_decoupe(mode: str, r: float, ep: float) -> float:
    """Profondeur du creux à retirer du socle (gravé) ou épaisseur de la couche
    couleur affleurante (lisse). Jamais traversant : on laisse >= 0.4 mm de fond."""
    if mode == "grave":
        return max(0.3, min(float(r), ep - 0.4))
    # lisse : couche couleur fine, affleurant le dessus
    return max(0.4, min(0.8, ep - 0.4))


def _corps_couleur(g, mode: str, r: float, ep: float, cut_ok: bool) -> list:
    """Solides colorés d'un footprint selon le mode.
    - relief : texte SURÉLEVÉ (posé sur le socle, chevauche pour souder).
    - lisse  : couche couleur AFFLEURANTE (le socle est creusé en dessous).
    - gravé  : fond coloré AU FOND du creux (le socle est creusé en dessous).
    Si la découpe du socle a échoué (cut_ok=False), on retombe sur du relief
    (toujours valide et visible) pour lisse/gravé."""
    if mode == "relief" or not cut_ok:
        return _extruder(g, max(0.3, float(r)) + CHEV, ep - CHEV)
    if mode == "lisse":
        t = _prof_decoupe("lisse", r, ep)
        return _extruder(g, t, ep - t)                 # affleurant : z = [ep-t, ep]
    d = _prof_decoupe("grave", r, ep)                  # gravé
    f = min(0.6, d)
    return _extruder(g, f, ep - d)                     # fond coloré : z = [ep-d, ep-d+f]


def _placer_elements(spec: CarteSpec):
    """Retourne (elements_placés, prismes_de_découpe).
    elements_placés = [(index, mp, mode, r, couleur), ...] ;
    prismes_de_découpe = solides à retirer du socle (modes gravé + lisse)."""
    placs, decoupes = [], []
    for i, el in enumerate(spec.elements):
        mp = _forme_element(el, spec)
        if mp is None:
            continue
        mp = _placer(mp, spec, el)
        if mp.is_empty:
            continue
        mode = getattr(el, "mode", "relief")
        r = max(0.3, float(getattr(el, "relief", 0.6)))
        placs.append((i, mp, mode, r, el.couleur))
        if mode in ("grave", "lisse"):
            prof = _prof_decoupe(mode, r, spec.ep)
            for g in _geoms(mp):
                if g.area > 0:
                    decoupes += _extruder(g, prof + CHEV, spec.ep - prof)
    return placs, decoupes


def _socle_creuse(spec: CarteSpec, decoupes: list):
    """Socle extrudé, creusé des prismes gravé/lisse (booléen unique + repli).
    Retourne (socle_mesh, cut_ok)."""
    base = union_solides(_extruder(_socle_2d(spec), spec.ep))
    cut_ok = False
    if decoupes:
        try:
            trou = union_solides(decoupes)
            res = trimesh.boolean.difference([base, trou], engine="manifold")
            if res is not None and len(res.faces) and res.is_watertight:
                base, cut_ok = res, True
        except Exception:
            logger.warning("Carte : découpe gravé/lisse échouée → repli en relief")
    base.visual.face_colors = _hex_rgba(spec.couleur_base)
    return base, cut_ok


def construire(spec: CarteSpec):
    """Construit la carte -> (trimesh.Scene multi-corps, liste ordonnée des
    couleurs). Corps 0 = socle (couleur de base, creusé pour gravé/lisse) ; puis
    un corps par couleur d'élément. Chaque corps porte sa couleur visuelle."""
    placs, decoupes = _placer_elements(spec)
    base, cut_ok = _socle_creuse(spec, decoupes)

    par_couleur: dict[str, list] = {}
    for _i, mp, mode, r, coul in placs:
        par_couleur.setdefault(coul, []).append((mp, mode, r))

    scene = trimesh.Scene()
    scene.add_geometry(base, node_name="socle", geom_name="socle")
    couleurs = [spec.couleur_base]
    for i, (coul, items) in enumerate(par_couleur.items()):
        solides = []
        for mp, mode, r in items:
            for g in _geoms(mp):
                if g.area > 0:
                    solides += _corps_couleur(g, mode, r, spec.ep, cut_ok)
        if not solides:
            continue
        corps = union_solides(solides)
        corps.visual.face_colors = _hex_rgba(coul)
        scene.add_geometry(corps, node_name=f"couleur_{i+1}",
                           geom_name=f"couleur_{i+1}")
        if coul not in couleurs:
            couleurs.append(coul)
    return scene, couleurs


def construire_apercu(spec: CarteSpec):
    """Aperçu ÉDITEUR : socle (creusé pour gravé/lisse) + UN corps par ÉLÉMENT,
    nommés « socle » et « el_<i> ». Permet au viewer de déplacer chaque élément
    indépendamment. L'EXPORT utilise construire() (fusion par couleur = slots)."""
    placs, decoupes = _placer_elements(spec)
    base, cut_ok = _socle_creuse(spec, decoupes)

    scene = trimesh.Scene()
    scene.add_geometry(base, node_name="socle", geom_name="socle")
    for i, mp, mode, r, coul in placs:
        solides = [m for g in _geoms(mp) if g.area > 0
                   for m in _corps_couleur(g, mode, r, spec.ep, cut_ok)]
        if not solides:
            continue
        corps = union_solides(solides)
        corps.visual.face_colors = _hex_rgba(coul)
        scene.add_geometry(corps, node_name=f"el_{i}", geom_name=f"el_{i}")
    return scene


def construire_lithophanie(spec: CarteSpec, ep_base: float = 0.8,
                           contraste: float = 2.2, inverser: bool = False):
    """VRAIE lithophanie de la carte : plaque translucide FINE dont l'épaisseur
    module la lumière (fin = clair, épais = foncé), en une seule matière blanche.
    Retourne un mesh DEBOUT (vertical) prêt à poser sur le plateau.

    - ep_base : épaisseur mini (zones claires, laissent passer la lumière) ;
    - contraste : épaisseur AJOUTÉE aux zones foncées (relief) ;
    - inverser : design clair sur fond foncé (au lieu de foncé sur clair)."""
    ep_base = max(0.4, float(ep_base))
    contraste = max(0.4, float(contraste))
    socle = _socle_2d(spec)
    formes = []
    for el in spec.elements:
        mp = _forme_element(el, spec)
        if mp is None:
            continue
        mp = _placer(mp, spec, el)
        if not mp.is_empty:
            formes.append(mp)
    design = unary_union(formes) if formes else None

    solides = _extruder(socle, ep_base)            # plaque fine (fond)
    if design is not None:
        if inverser:
            # design = zones FINES (claires) → on épaissit TOUT SAUF le design
            haut = socle.difference(design)
            solides += _extruder(haut, contraste + CHEV, ep_base - CHEV)
        else:
            # design = zones ÉPAISSES (foncées) en relief
            for g in (design.geoms if isinstance(design, MultiPolygon) else [design]):
                if g.area > 0:
                    solides += _extruder(g, contraste + CHEV, ep_base - CHEV)
    mesh = union_solides(solides)
    mesh.visual.face_colors = [255, 255, 255, 255]
    # DEBOUT : une lithophanie s'imprime/s'affiche verticalement (la carte est
    # à plat dans le plan XY → rotation de 90° autour de X pour la mettre debout).
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2.0, [1, 0, 0]))
    mesh.apply_translation(-mesh.bounds[0])        # coin mini à l'origine (pose plateau)
    return mesh


def rendre_carte_image(spec: CarteSpec, chemin, px_par_mm: float = 8.0):
    """Rasterise le DESIGN de la carte en niveaux de gris (fond blanc = fin/clair,
    éléments noirs = épais/foncés) → image source pour la LITHOPHANIE standard
    (menu « Photo en relief / lithophanie » avec tous ses réglages)."""
    from PIL import Image, ImageDraw
    W = max(2, int(round(spec.largeur * px_par_mm)))
    H = max(2, int(round(spec.hauteur * px_par_mm)))
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)

    def _px(pt):
        x, y = pt[0], pt[1]
        return ((x + spec.largeur / 2.0) * px_par_mm,
                (spec.hauteur / 2.0 - y) * px_par_mm)

    for el in spec.elements:
        mp = _forme_element(el, spec)
        if mp is None:
            continue
        mp = _placer(mp, spec, el)
        for g in _polygones(mp):
            if g.is_empty or g.area <= 0:
                continue
            draw.polygon([_px(p) for p in g.exterior.coords], fill=0)
            for ring in g.interiors:
                draw.polygon([_px(p) for p in ring.coords], fill=255)
    # Épaissir légèrement le texte : les traits FINS (polices décoratives) sont
    # sinon effacés par le downscale + flou du générateur de lithophanie et
    # deviennent invisibles. ~0,15 mm de dilatation → visibles sans empâter.
    try:
        import cv2
        import numpy as _np
        r = max(1, int(round(px_par_mm * 0.15)))
        a = cv2.erode(_np.array(img), _np.ones((2 * r + 1, 2 * r + 1), _np.uint8))
        img = Image.fromarray(a)
    except Exception:
        pass
    img.save(str(chemin))
    return chemin


def generer_fichier_carte(spec: CarteSpec, litho: bool = False,
                          litho_params: dict | None = None):
    """Écrit la carte dans le dossier de sorties neoGen et renvoie le Path (.3mf)
    à CHARGER dans le pipeline normal (comme une pièce déposée). L'export final
    correct (imprimante/filament/paramètres → « Générer le 3MF ») est ensuite fait
    par le pipeline habituel, pas ici.

    En lithophanie : les couleurs sont retirées (matière unique translucide) et le
    fichier est nommé « lithophanie… » pour que l'app applique automatiquement son
    profil d'impression lithophanie au chargement."""
    import trimesh
    from core.neogen.pilote import DOSSIER_SORTIES
    DOSSIER_SORTIES.mkdir(parents=True, exist_ok=True)
    if litho:
        lp = litho_params or {}
        fusion = construire_lithophanie(
            spec, ep_base=float(lp.get("ep_base", 0.8)),
            contraste=float(lp.get("contraste", 2.2)),
            inverser=bool(lp.get("inverser", False)))
        base = DOSSIER_SORTIES / "lithophanie_carte"
    else:
        scene, _couleurs = construire(spec)
        # VRAIE UNION (pas concatenate) : sinon les DESSOUS des reliefs (faces
        # tournées vers le bas, à l'intérieur du socle) subsistent et sont comptés
        # comme des surplombs → « 23 % de surplombs » + supports inutiles sur une
        # carte plate. L'union booléenne supprime ces faces internes.
        fusion = union_solides(list(scene.geometry.values()))
        base = DOSSIER_SORTIES / "carte_visite"
    fusion.export(base.with_suffix(".stl"))
    return base.with_suffix(".stl")
