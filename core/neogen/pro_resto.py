# -*- coding: utf-8 -*-
"""neoGen — famille RESTAURATION (objets vendables par un imprimeur 3D).

Numéros de table, chevalets/porte-cartes, porte-menu, porte-addition,
marque-places, panneau « Réservé », porte-couverts. Tout est pensé imprimable
SANS support (bases plates, pentes ≥ 45°, reliefs soudés par union) et étanche.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union

from core.neogen.goodies import _extruder, texte_multilignes, CHEVAUCHEMENT
from core.neogen.geo_utils import union_solides
from core.neogen.formes import _texte_sur, _empreinte

CHEV = CHEVAUCHEMENT


def _texte_2d(txt: str, hauteur: float, police: str | None = None):
    mp = texte_multilignes(txt, hauteur, police=police)
    return unary_union(list(mp.geoms))


# ═══════════════════════════ NUMÉRO DE TABLE ════════════════════════════════
def numero_table(texte: str = "12", hauteur: float = 80, ep: float = 10,
                 police: str | None = None) -> trimesh.Trimesh:
    """Numéro de table AUTOPORTANT : chiffres épais dressés sur un socle plat
    lesté. Imprimé couché sur la face arrière -> aucun support. (Param nommé
    `texte` pour le pont catalogue ; contient le numéro.)"""
    num = (str(texte) or "12").strip()[:3]
    chiffres = _texte_2d(num, hauteur, police)
    minx, miny, maxx, maxy = chiffres.bounds
    # relie les chiffres par une petite barre basse (le « 1 » et le « 2 » ne
    # sont pas connectés sinon) + socle qui déborde pour la stabilité
    barre = box(minx - 4, miny, maxx + 4, miny + hauteur * 0.10)
    numero_2d = unary_union([chiffres, barre])
    numero_solide = union_solides(_extruder(numero_2d, ep))
    numero_solide.apply_transform(
        trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    numero_solide.apply_translation([0, 0, -float(numero_solide.bounds[0][2])])
    # socle plinthe : bloc élargi sous le numéro
    xw = (maxx - minx) + 24
    socle = trimesh.creation.box((xw, 30, 8))
    ymid = float(numero_solide.bounds[0][1] + numero_solide.bounds[1][1]) / 2
    socle.apply_translation([(minx + maxx) / 2, ymid, 8 / 2 - 1])
    piece = union_solides([numero_solide, socle])
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════ CHEVALET / PANCARTE DEBOUT ════════════════════════
def _pancarte_debout(texte: str, largeur: float, hauteur: float, ep: float,
                     prof_socle: float, grave: bool = False,
                     police: str | None = None, style: str | None = None,
                     taille_police: float = 0.0, couleur_objet: str | None = None,
                     couleur_texte: str | None = None, inclinaison: float = 90.0):
    """Plaque à texte dressée sur un socle lesté (chevalet / pancarte). `inclinaison`
    = angle de la plaque depuis l'horizontale (90 = vertical, <90 = penché vers
    l'arrière). Imprimée socle au plateau ; texte en façade, parfaitement centré.
    Bicolore + style relief/gravé/lisse + taille de texte réglable (0 = auto)."""
    from shapely.affinity import scale as _scale, translate as _tr
    from core.neogen.goodies import ajuster_dans, RELIEF_ACTIF
    from core.neogen import bicolore as _bic
    style = style if style in ("relief", "grave", "lisse") else ("grave" if grave else "relief")
    bicolore = bool(couleur_objet and couleur_texte)
    ep_texte = min(0.7, ep * 0.35)
    if RELIEF_ACTIF is not None:
        ep_texte = max(0.3, float(RELIEF_ACTIF))

    plaque2d = box(-largeur / 2, 0, largeur / 2, hauteur)
    plaque2d = plaque2d.buffer(4, join_style=1).buffer(-4, join_style=1)

    texte_2d = None
    if texte and str(texte).strip():
        zw, zh = largeur - 12, hauteur - 12
        mp = texte_multilignes(str(texte), police=police)     # hauteur de ligne ≈ 10 mm
        if taille_police and taille_police > 0:
            f = float(taille_police) / 10.0
            mp = _scale(mp, xfact=f, yfact=f, origin=(0, 0))
            mp = ajuster_dans(mp, zw, zh)                      # borne si trop grand
        else:
            mp = ajuster_dans(mp, zw * 0.85, zh * 0.85)        # ajustement auto
        minx, miny, maxx, maxy = mp.bounds
        # centré à ~55 % de la hauteur : le socle mange le bas, donc « milieu
        # visuel » de la plaque = un peu au-dessus du milieu géométrique.
        mp = _tr(mp, xoff=-(minx + maxx) / 2.0, yoff=hauteur * 0.55 - (miny + maxy) / 2.0)
        texte_2d = unary_union(list(mp.geoms))

    if texte_2d is not None:
        plaque_body, texte_body = _bic.socle_texte(plaque2d, texte_2d, ep, ep_texte, style)
    else:
        plaque_body = union_solides(_extruder(plaque2d, ep))
        texte_body = None

    R = trimesh.transformations.rotation_matrix(np.radians(inclinaison), [1, 0, 0])
    plaque_body.apply_transform(R)
    if texte_body is not None:
        texte_body.apply_transform(R)
    dz = -float(plaque_body.bounds[0][2])
    plaque_body.apply_translation([0, 0, dz])
    if texte_body is not None:
        texte_body.apply_translation([0, 0, dz])

    ymin = float(plaque_body.bounds[0][1])
    h_socle = max(6.0, ep + 3)
    socle = trimesh.creation.box((largeur + 8, prof_socle, h_socle))
    socle.apply_translation([0, ymin + prof_socle / 2 - ep - 2, h_socle / 2])
    objet_body = union_solides([plaque_body, socle])

    if bicolore and texte_body is not None:
        s = _bic.scene(objet_body, texte_body, couleur_objet, couleur_texte)
        fus = trimesh.util.concatenate(list(s.geometry.values()))
        off = -fus.bounds[0]
        for g in s.geometry.values():
            g.apply_translation(off)
        return s
    piece = union_solides([objet_body, texte_body]) if texte_body is not None else objet_body
    piece.apply_translation(-piece.bounds[0])
    return piece


def chevalet(largeur: float = 95, hauteur: float = 55, texte: str = "Réservé",
             grave: bool = False, police: str | None = None, style: str | None = None,
             taille_police: float = 0.0, couleur_objet: str | None = None,
             couleur_texte: str | None = None):
    """Pancarte de table à texte (chevalet « Réservé », menu du jour…) :
    plaque verticale à texte sur socle lesté. Sans support. Bicolore + style."""
    return _pancarte_debout(texte, largeur, hauteur, 4.0, 30.0, grave, police,
                            style=style, taille_police=taille_police,
                            couleur_objet=couleur_objet, couleur_texte=couleur_texte,
                            inclinaison=76.0)


# ═══════════════════════════ PORTE-MENU (fente) ═════════════════════════════
def porte_menu(largeur: float = 100, epaisseur_fente: float = 6,
               hauteur: float = 45) -> trimesh.Trimesh:
    """Socle lesté avec une FENTE verticale CENTRÉE : on y glisse un menu (carton/A5).
    La fente est ouverte vers le haut -> aucun surplomb ; sa largeur est réglable."""
    prof = 40.0
    base = box(-largeur / 2, -prof / 2, largeur / 2, prof / 2)
    base = base.buffer(4, join_style=1).buffer(-4, join_style=1)
    corps = union_solides(_extruder(base, hauteur))
    # fente : boîte débouchant en HAUT (au centre y=0), inclinée de 8° AUTOUR de son
    # ouverture (0,0,hauteur) → l'ouverture reste parfaitement centrée en profondeur.
    z_top, z_bot = hauteur + 3.0, hauteur * 0.32
    hb = z_top - z_bot
    fente = trimesh.creation.box((largeur * 0.82, epaisseur_fente, hb))
    fente.apply_translation([0, 0, (z_top + z_bot) / 2.0])
    fente.apply_transform(trimesh.transformations.rotation_matrix(
        np.radians(8), [1, 0, 0], point=[0, 0, hauteur]))
    piece = trimesh.boolean.difference([corps, fente], engine="manifold")
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ PORTE-ADDITION ═════════════════════════════════
def porte_addition(largeur: float = 130, hauteur: float = 90, ep: float = 4,
                   rebord: float = 6) -> trimesh.Trimesh:
    """Porte-addition = petit PLATEAU FIN redimensionnable (on y présente la note
    et le paiement) : fond plat à coins arrondis + rebord bas tout autour."""
    ext = box(-largeur / 2, -hauteur / 2, largeur / 2, hauteur / 2)
    ext = ext.buffer(4, join_style=1).buffer(-4, join_style=1)
    interieur = ext.buffer(-4.0, join_style=1)
    mur_2d = ext.difference(interieur)
    solides = _extruder(ext, ep)                       # fond
    if not mur_2d.is_empty:
        solides += _extruder(mur_2d, ep + max(1.0, rebord))   # rebord périphérique
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece


# ═══════════════════════════ MARQUE-PLACE ═══════════════════════════════════
def marque_place(texte: str = "Invité", largeur: float = 70, hauteur: float = 26,
                 grave: bool = False, police: str | None = None, style: str | None = None,
                 taille_police: float = 0.0, couleur_objet: str | None = None,
                 couleur_texte: str | None = None):
    """Marque-place nominatif DEBOUT : petite pancarte verticale sur socle.
    Bicolore + style relief/gravé/lisse. Imprimé sans support."""
    return _pancarte_debout(texte, largeur, hauteur, 3.0, 18.0, grave, police,
                            style=style, taille_police=taille_police,
                            couleur_objet=couleur_objet, couleur_texte=couleur_texte)


# ═══════════════════════════ PANNEAU « RÉSERVÉ » ════════════════════════════
def panneau_reserve(texte: str = "Réservé", largeur: float = 95, hauteur: float = 55,
                    grave: bool = False, police: str | None = None) -> trimesh.Trimesh:
    """Chevalet « Réservé » (ou tout autre texte) : pancarte inclinée."""
    return chevalet(largeur=largeur, hauteur=hauteur, texte=texte or "Réservé",
                    grave=grave, police=police)


# ═══════════════════════════ PORTE-COUVERTS ═════════════════════════════════
def porte_couverts(longueur: float = 180, largeur: float = 55,
                   hauteur: float = 45, colonnes: int = 2,
                   rangees: int = 1) -> trimesh.Trimesh:
    """Bac à couverts / serviettes : caisson ouvert à coins arrondis, divisé en
    une GRILLE de compartiments (`colonnes` × `rangees` réglables)."""
    p, fond = 2.4, 3.0
    colonnes, rangees = max(1, int(colonnes)), max(1, int(rangees))
    emp = _empreinte("rect", longueur, largeur)
    minx, miny, maxx, maxy = emp.bounds
    solides = _extruder(emp, fond)                                  # fond
    murs = emp.difference(emp.buffer(-p, join_style=1))
    solides += _extruder(murs, hauteur - fond + CHEV, fond - CHEV)  # murs extérieurs
    for i in range(1, colonnes):                                    # cloisons verticales
        x = minx + (maxx - minx) * i / colonnes
        sep = box(x - p / 2, miny + p, x + p / 2, maxy - p)
        solides += _extruder(sep, hauteur - fond + CHEV, fond - CHEV)
    for j in range(1, rangees):                                     # cloisons horizontales
        y = miny + (maxy - miny) * j / rangees
        sep = box(minx + p, y - p / 2, maxx - p, y + p / 2)
        solides += _extruder(sep, hauteur - fond + CHEV, fond - CHEV)
    piece = union_solides(solides)
    piece.apply_translation(-piece.bounds[0])
    return piece
