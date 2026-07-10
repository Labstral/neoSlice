# -*- coding: utf-8 -*-
"""neoGen — CRÉATION LIBRE : le modèle écrit un script géométrique, exécuté
dans un bac à sable strict, avec boucle d'auto-correction et cookbook.

Sécurité :
  - AUCUN import, exec, fichier, réseau : seules les fonctions du KIT sont
    disponibles (namespace clos, builtins vides, mots-clés interdits filtrés).
  - Chaque valeur produite est VÉRIFIÉE (étanche, posée, dimensions sensées).

Fiabilité (leçons des batteries 8B/14B) :
  - KIT POLYMORPHE : deplacer/tourner/fusionner/percer acceptent formes 2D ET
    volumes 3D (le modèle mélangeait les deux -> 3 échecs sur 12).
  - COOKBOOK : des solutions types écrites par un expert sont injectées dans
    le prompt selon la demande (similarité mots-clés) -> le modèle ADAPTE une
    solution juste au lieu d'inventer (bol, pyramide, jeton... corrigés).
  - Boucle : erreur d'exécution/vérification -> renvoyée au modèle (3 essais).

Modèle : qwen3:14b DÉDIÉ à neoGen (installé indépendamment d'Oen 8B via les
réglages — voir installation.py).
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon, MultiPolygon, box as shp_box
from shapely.ops import unary_union
from shapely.affinity import translate as shp_translate, rotate as shp_rotate

from core.assistant.engine import HOST
from core.neogen.geo_utils import union_solides

NEOGEN_MODEL = "qwen3:14b"
MAX_ESSAIS = 3
DOSSIER_SORTIES = Path.home() / ".neoslice" / "neogen"

_2D = (Polygon, MultiPolygon)


# ═══════════════════════════ KIT GÉOMÉTRIQUE (sandbox) ══════════════════════
def boite_3d(x: float, y: float, z: float) -> trimesh.Trimesh:
    m = trimesh.creation.box((x, y, z))
    m.apply_translation([0, 0, z / 2])
    return m


def cylindre(diametre: float, hauteur: float) -> trimesh.Trimesh:
    m = trimesh.creation.cylinder(radius=diametre / 2, height=hauteur, sections=96)
    m.apply_translation([0, 0, hauteur / 2])
    return m


def cone(d_bas: float, hauteur: float, d_haut: float = 0) -> trimesh.Trimesh:
    """Cône ou tronc de cône (d_haut > 0)."""
    if d_haut and d_haut > 0:
        prof = [(d_bas / 2, 0.0), (d_haut / 2, float(hauteur))]
        pts = [(0.0, 0.0)] + prof + [(0.0, float(hauteur)), (0.0, 0.0)]
        return trimesh.creation.revolve(np.array(pts), sections=96)
    return trimesh.creation.cone(radius=d_bas / 2, height=hauteur, sections=96)


def sphere(diametre: float) -> trimesh.Trimesh:
    m = trimesh.creation.icosphere(subdivisions=4, radius=diametre / 2)
    m.apply_translation([0, 0, diametre / 2])
    return m


def demi_sphere(diametre: float, creuse: float = 0.0) -> trimesh.Trimesh:
    """Dôme posé à plat ; `creuse` = épaisseur de paroi si bol (0 = plein)."""
    n = 48
    r = diametre / 2
    prof = [(float(r * np.cos(a)), float(r * np.sin(a)))
            for a in np.linspace(0, np.pi / 2, n)]
    if creuse and creuse > 0:
        ri = max(r - creuse, 1.0)
        interieur = [(float(ri * np.cos(a)), float(max(ri * np.sin(a), creuse)))
                     for a in np.linspace(np.pi / 2, 0, n)]
        pts = [(0.0, 0.0)] + prof + interieur + [(0.0, float(creuse)), (0.0, 0.0)]
    else:
        pts = [(0.0, 0.0)] + prof + [(0.0, 0.0)]
    return trimesh.creation.revolve(np.array(pts), sections=96)


def pyramide(cote: float, hauteur: float) -> trimesh.Trimesh:
    base = [(-cote / 2, -cote / 2, 0), (cote / 2, -cote / 2, 0),
            (cote / 2, cote / 2, 0), (-cote / 2, cote / 2, 0)]
    sommets = np.array(base + [(0, 0, hauteur)], dtype=float)
    faces = np.array([[0, 2, 1], [0, 3, 2], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
    return trimesh.Trimesh(vertices=sommets, faces=faces)


def tube(d_ext: float, d_int: float, hauteur: float) -> trimesh.Trimesh:
    ext = Point(0, 0).buffer(d_ext / 2, resolution=96)
    return extrusion(ext.difference(Point(0, 0).buffer(d_int / 2, resolution=96)), hauteur)


def prisme(cotes: int, diametre: float, hauteur: float) -> trimesh.Trimesh:
    a = np.linspace(0, 2 * np.pi, int(cotes), endpoint=False) + np.pi / int(cotes)
    return extrusion(Polygon([(np.cos(t) * diametre / 2, np.sin(t) * diametre / 2)
                              for t in a]), hauteur)


def rectangle_arrondi(x: float, y: float, rayon: float = 3):
    r = max(0.1, min(rayon, x / 2 - 0.1, y / 2 - 0.1))
    return shp_box(-(x / 2 - r), -(y / 2 - r), x / 2 - r, y / 2 - r).buffer(r, join_style=1)


def disque(diametre: float):
    return Point(0, 0).buffer(diametre / 2, resolution=96)


def etoile(branches: int, diametre: float):
    pts = []
    for i in range(int(branches) * 2):
        r = diametre / 2 if i % 2 == 0 else diametre / 2 * 0.45
        a = np.pi / 2 + i * np.pi / branches
        pts.append((np.cos(a) * r, np.sin(a) * r))
    return Polygon(pts)


def coeur(taille: float):
    from core.neogen.formes2 import _coeur_2d
    return _coeur_2d(taille)


def texte_2d(texte: str, hauteur_lettres: float):
    from core.neogen.goodies import texte_multilignes
    from shapely.affinity import scale as _sc
    mp = texte_multilignes(str(texte), 10.0)
    minx, miny, maxx, maxy = mp.bounds
    f = hauteur_lettres / (maxy - miny)
    return _sc(mp, xfact=f, yfact=f, origin=(0, 0))


def extrusion(forme_2d, hauteur: float, z: float = 0.0) -> trimesh.Trimesh:
    geoms = forme_2d.geoms if isinstance(forme_2d, MultiPolygon) else [forme_2d]
    sol = []
    for g in geoms:
        if g.is_empty or g.area < 1e-6:
            continue
        m = trimesh.creation.extrude_polygon(g, hauteur)
        if z:
            m.apply_translation([0, 0, z])
        sol.append(m)
    if not sol:
        raise ValueError("forme 2D vide")
    return trimesh.util.concatenate(sol)


def revolution(points_rz: list, sections: int = 96) -> trimesh.Trimesh:
    pts = [(float(r), float(z)) for r, z in points_rz]
    if pts[0][0] != 0:
        pts = [(0.0, pts[0][1])] + pts
    if pts[-1][0] != 0:
        pts = pts + [(0.0, pts[-1][1])]
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    m = trimesh.creation.revolve(np.array(pts), sections=sections)
    m.apply_translation([0, 0, -float(m.bounds[0][2])])
    return m


# ── Opérations POLYMORPHES (2D ou 3D — le modèle mélange, on tolère) ─────────
def deplacer(objet, dx: float = 0, dy: float = 0, dz: float = 0):
    if isinstance(objet, _2D):
        return shp_translate(objet, xoff=dx, yoff=dy)
    p = objet.copy()
    p.apply_translation([dx, dy, dz])
    return p


def tourner(objet, axe: str = "z", degres: float = 0):
    if isinstance(objet, _2D):
        return shp_rotate(objet, degres, origin=(0, 0))
    ax = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[str(axe).lower()]
    p = objet.copy()
    p.apply_transform(trimesh.transformations.rotation_matrix(np.radians(degres), ax))
    return p


def fusionner(*objets):
    objets = [o for o in objets if o is not None]
    if all(isinstance(o, _2D) for o in objets):
        u = unary_union(objets)
        return u
    vols = [o if not isinstance(o, _2D) else extrusion(o, 1.0) for o in objets]
    return union_solides(vols)


def percer(objet, outil):
    if isinstance(objet, _2D) and isinstance(outil, _2D):
        return objet.difference(outil)
    if isinstance(objet, _2D):
        raise ValueError("percer(2D, 3D) impossible : extrude d'abord la forme 2D "
                         "avec extrusion(forme, hauteur)")
    if isinstance(outil, _2D):
        h = float(objet.bounds[1][2] - objet.bounds[0][2]) + 20
        outil = extrusion(outil, h, float(objet.bounds[0][2]) - 10)
    return trimesh.boolean.difference([objet, outil], engine="manifold")


def creuser(objet: trimesh.Trimesh, paroi: float = 2.0) -> trimesh.Trimesh:
    """Évide un volume par le DESSUS (bol, pot...) en gardant fond et parois."""
    if isinstance(objet, _2D):
        return objet.difference(objet.buffer(-paroi))
    from trimesh.transformations import scale_matrix
    b = objet.bounds
    dims = b[1] - b[0]
    fx = max(0.05, 1 - 2 * paroi / max(dims[0], 1e-6))
    fy = max(0.05, 1 - 2 * paroi / max(dims[1], 1e-6))
    fz = max(0.05, 1 - paroi / max(dims[2], 1e-6))
    interieur = objet.copy()
    centre = (b[0] + b[1]) / 2
    t = np.eye(4)
    t[:3, :3] = np.diag([fx, fy, fz])
    interieur.apply_transform(t)
    nb = interieur.bounds
    interieur.apply_translation([centre[0] - (nb[0][0] + nb[1][0]) / 2,
                                 centre[1] - (nb[0][1] + nb[1][1]) / 2,
                                 (b[1][2] + 10) - nb[0][2] - (nb[1][2] - nb[0][2])
                                 + (nb[1][2] - nb[0][2])])
    # positionne l'intérieur : même XY, fond à paroi du bas, dépasse par le haut
    interieur.apply_translation([0, 0, (b[0][2] + paroi) - interieur.bounds[0][2]])
    haut = interieur.copy()
    haut.apply_translation([0, 0, 5])
    outil = union_solides([interieur, haut])
    return trimesh.boolean.difference([objet, outil], engine="manifold")


def repeter_cercle(objet: trimesh.Trimesh, n: int, rayon: float):
    """n copies réparties sur un cercle de rayon donné (autour de l'origine)."""
    copies = []
    for i in range(int(n)):
        a = 2 * np.pi * i / int(n)
        c = deplacer(objet, float(np.cos(a) * rayon), float(np.sin(a) * rayon), 0)
        copies.append(c)
    return fusionner(*copies)


def poser_au_sol(objet):
    if isinstance(objet, _2D):
        return objet
    p = objet.copy()
    p.apply_translation([0, 0, -float(p.bounds[0][2])])
    return p


API = {
    "boite_3d": boite_3d, "cylindre": cylindre, "cone": cone, "sphere": sphere,
    "demi_sphere": demi_sphere, "pyramide": pyramide, "tube": tube, "prisme": prisme,
    "rectangle_arrondi": rectangle_arrondi, "disque": disque, "etoile": etoile,
    "coeur": coeur, "texte_2d": texte_2d, "extrusion": extrusion,
    "revolution": revolution, "deplacer": deplacer, "tourner": tourner,
    "fusionner": fusionner, "percer": percer, "creuser": creuser,
    "repeter_cercle": repeter_cercle, "poser_au_sol": poser_au_sol,
    "abs": abs, "min": min, "max": max, "round": round, "range": range,
    "len": len, "float": float, "int": int, "list": list,
}

_DOC_API = """FONCTIONS DISPONIBLES (les SEULES autorisees, unites mm ; primitives POSEES sur le plateau z=0, centrees en 0,0) :
VOLUMES : boite_3d(x,y,z) ; cylindre(diametre,hauteur) ; cone(d_bas,hauteur,d_haut=0) ; sphere(d) ; demi_sphere(d, creuse=0) [creuse=paroi -> BOL] ; pyramide(cote,hauteur) ; tube(d_ext,d_int,hauteur) ; prisme(cotes,diametre,hauteur)
FORMES 2D : rectangle_arrondi(x,y,rayon) ; disque(d) ; etoile(branches,d) ; coeur(taille) ; texte_2d(texte,hauteur_lettres)
CONSTRUIRE : extrusion(forme2D,hauteur,z=0) -> volume ; revolution([(rayon,z),...]) -> volume tourne
OPERATIONS : deplacer(obj,dx,dy,dz) ; tourner(obj,'x'|'y'|'z',degres) ; fusionner(a,b,...) ; percer(piece,outil) ; creuser(piece,paroi) [evide par le dessus] ; repeter_cercle(obj,n,rayon) ; poser_au_sol(obj)"""

_SYSTEME_BASE = f"""Tu ecris un script Python MINIMAL qui construit UNE piece 3D imprimable, en n'utilisant QUE les fonctions du kit. Tu reponds UNIQUEMENT avec le code entre ```python et ```, rien d'autre.

{_DOC_API}

REGLES :
1. Le script DOIT finir par : piece = <resultat 3D>
2. Pas d'import, pas de fichier, rien hors du kit.
3. Les OPERATIONS 3D (percer, deplacer dz, creuser) s'appliquent a des VOLUMES : extrude d'abord les formes 2D avec extrusion(...).
4. Pour un trou TRAVERSANT, l'outil doit DEPASSER la piece.
5. cm -> mm (3 cm = 30). Respecte les DIMENSIONS demandees et les PROPORTIONS reelles de l'objet (un jeton est PLAT, un bol est CREUX et LARGE, un verre est plus haut que large).
6. Pense impression 3D : parois >= 1.2 mm, pas de porte-a-faux extreme.
7. Si on te renvoie une ERREUR, corrige ton script et renvoie-le EN ENTIER."""


# ═══════════════════════════════ COOKBOOK ═══════════════════════════════════
# Solutions types écrites et VALIDÉES par un expert. Injectées selon la
# demande (similarité mots-clés) : le modèle adapte au lieu d'inventer.
COOKBOOK = [
    ("bol saladier assiette creuse coupe recipient", "un bol de 12 cm de diametre",
     "piece = demi_sphere(120, creuse=2.4)"),
    ("pyramide", "une pyramide de 5 cm de cote",
     "piece = pyramide(50, 45)"),
    ("jeton poker caddie medaille piece plate disque", "un jeton de 40 mm",
     "# un jeton est PLAT : grand diametre, faible epaisseur\npiece = cylindre(40, 3.5)"),
    ("porte-savon savon drainage bac", "un porte-savon 10x7 cm avec drainage",
     "bac = boite_3d(100, 70, 20)\nbac = creuser(bac, 2)\n"
     "trou = cylindre(6, 60)\ntrous = fusionner(deplacer(trou,-25,0,-10), deplacer(trou,0,0,-10), deplacer(trou,25,0,-10))\n"
     "piece = percer(bac, trous)"),
    ("entonnoir", "un entonnoir de 8 cm vers 12 mm",
     "# tronc de cone creux + bec ; grande ouverture EN HAUT\n"
     "corps = cone(16, 55, 80)\nbec = tube(16, 12, 25)\n"
     "exterieur = fusionner(bec, deplacer(corps, 0, 0, 25))\n"
     "vide = fusionner(cylindre(12, 30), deplacer(cone(12.8, 56, 76.8), 0, 0, 24))\n"
     "piece = percer(exterieur, deplacer(vide, 0, 0, -2))"),
    ("support L equerre angle fixation", "un support en L de 5 cm avec trous de vis",
     "aile1 = boite_3d(50, 20, 4)\naile2 = deplacer(tourner(boite_3d(50, 20, 4), 'y', -90), 2, 0, 0)\n"
     "L = fusionner(aile1, aile2)\nvis = cylindre(4, 60)\n"
     "piece = percer(L, fusionner(deplacer(vis, 30, 0, -5), deplacer(tourner(vis,'y',90), -5, 0, 30)))"),
    ("gobelet verre tasse pot crayon", "un gobelet de 7 cm, 9 cm de haut",
     "piece = creuser(cylindre(70, 90), 2.4)"),
    ("vase", "un vase de 15 cm",
     "profil = [(30,0),(38,30),(25,75),(33,130),(36,150),(34,150),(31,132),(23,76),(36,32),(28,2)]\n"
     "piece = revolution(profil)"),
    ("anneau bague", "un anneau de 20 mm interieur",
     "piece = tube(28, 20, 5)"),
    ("rondelle washer", "une rondelle 24/8",
     "piece = tube(24, 8, 3)"),
    ("etoile decoration noel", "une etoile de 8 cm",
     "piece = extrusion(etoile(5, 80), 5)"),
    ("coeur amour saint-valentin", "un coeur de 6 cm",
     "piece = extrusion(coeur(60), 6)"),
    ("cube de texte lettre chiffre relief dessus", "un cube 25 mm avec un 7 en relief",
     "cube = boite_3d(25, 25, 25)\nchiffre = extrusion(texte_2d('7', 15), 1.5, 25 - 0.2)\n"
     "piece = fusionner(cube, chiffre)"),
    ("plateau tournant socle rond", "un socle rond de 10 cm",
     "piece = fusionner(cylindre(100, 4), cylindre(90, 8))"),
    ("crochet", "un crochet mural",
     "dos = boite_3d(6, 20, 60)\nbas = deplacer(boite_3d(35, 20, 6), 14.5, 0, 0)\n"
     "bout = deplacer(boite_3d(6, 20, 25), 29, 0, 5.8)\npiece = fusionner(dos, bas, bout)"),
    ("toupie", "une toupie",
     "piece = revolution([(2,0),(18,22),(20,30),(3,38),(3,46),(0,46)])"),
    ("haltere poids", "un haltere jouet",
     "d1 = sphere(35)\nd2 = deplacer(sphere(35), 80, 0, 0)\n"
     "barre = deplacer(tourner(cylindre(12, 80), 'y', 90), 0, 0, 17.5)\n"
     "piece = fusionner(d1, barre, d2)"),
    ("dome igloo demi-sphere", "un dome de 8 cm",
     "piece = demi_sphere(80)"),
    ("engrenage roue dentee", "une roue de 6 cm avec dents",
     "# approximation : disque + dents rectangulaires reparties\n"
     "roue = cylindre(52, 8)\ndent = deplacer(boite_3d(8, 6, 8), 28, 0, 0)\n"
     "dents = repeter_cercle(dent, 12, 0)\n"
     "piece = percer(fusionner(roue, dents), cylindre(8, 20))"),
    ("boite rangement couvercle", "une boite carree",
     "corps = creuser(boite_3d(60, 60, 30), 2)\npiece = corps"),
    ("tirelire cochon fente piece", "une tirelire simple",
     "corps = creuser(cylindre(80, 70), 2.4)\nfente = boite_3d(3, 40, 20)\n"
     "piece = percer(corps, deplacer(fente, 0, 0, 60))"),
    ("presse papier", "un presse-papier",
     "piece = fusionner(boite_3d(70, 50, 8), deplacer(demi_sphere(40), 0, 0, 7.8))"),
    ("support bague bijou cone", "un porte-bagues",
     "piece = fusionner(cylindre(60, 4), cone(24, 70))"),
    ("pied support tige", "un pied conique",
     "piece = cone(45, 40, 28)"),
    ("des de des a jouer", "un de de 16 mm",
     "# arretes arrondies impossibles ici : cube simple + creux coniques\n"
     "piece = boite_3d(16, 16, 16)"),
]

_MOTS = re.compile(r"[a-zà-ÿ0-9]+")


def _normaliser_mots(txt: str) -> set:
    txt = unicodedata.normalize("NFKD", txt.lower()).encode("ascii", "ignore").decode()
    return set(_MOTS.findall(txt)) - {"un", "une", "de", "des", "du", "le", "la",
                                      "les", "avec", "et", "en", "mm", "cm", "d",
                                      "l", "a", "au", "pour", "sur"}


def _exemples_pertinents(phrase: str, n: int = 2) -> list[tuple[str, str]]:
    mots = _normaliser_mots(phrase)
    scores = []
    for cles, demande, code in COOKBOOK:
        s = len(mots & _normaliser_mots(cles))
        if s > 0:
            scores.append((s, demande, code))
    scores.sort(key=lambda x: -x[0])
    return [(d, c) for _s, d, c in scores[:n]]


def _prompt_systeme(phrase: str) -> str:
    exemples = _exemples_pertinents(phrase)
    if not exemples:   # exemples génériques par défaut
        exemples = [("un cube de 30 mm perce d'un trou de 8 mm",
                     "cube = boite_3d(30, 30, 30)\ntrou = cylindre(8, 40)\npiece = percer(cube, trou)"),
                    ("un bol de 12 cm", "piece = demi_sphere(120, creuse=2.4)")]
    bloc = "\n\n".join(f'EXEMPLE — "{d}" :\n```python\n{c}\n```' for d, c in exemples)
    return _SYSTEME_BASE + "\n\n" + bloc


# ═══════════════════════ Sandbox, vérifications, boucle ═════════════════════
_INTERDIT = re.compile(
    r"\b(import|exec|eval|open|getattr|setattr|globals|locals|compile|input)\b|__")


def executer_sandbox(code: str) -> trimesh.Trimesh:
    if _INTERDIT.search(code):
        raise ValueError("mot-cle interdit dans le script")
    espace = {"__builtins__": {}}
    espace.update(API)
    exec(compile(code, "<neogen-libre>", "exec"), espace)   # noqa: S102 — clos
    piece = espace.get("piece")
    if piece is None:
        raise ValueError("le script doit se terminer par : piece = <resultat>")
    if isinstance(piece, _2D):
        raise ValueError("piece est une forme 2D : extrude-la avec extrusion(forme, hauteur)")
    if not isinstance(piece, trimesh.Trimesh):
        raise ValueError("piece doit etre un volume du kit")
    return piece


def verifier(piece: trimesh.Trimesh) -> str | None:
    if len(piece.faces) < 4:
        return "piece vide"
    if not piece.is_watertight:
        return "la piece n'est pas etanche (booleens invalides ?)"
    d = piece.bounds[1] - piece.bounds[0]
    if max(d) > 256 or min(d) < 0.8:
        return f"dimensions aberrantes : {d[0]:.0f}x{d[1]:.0f}x{d[2]:.0f} mm"
    if piece.bounds[0][2] > 0.5:
        return "la piece ne touche pas le plateau (utilise poser_au_sol)"
    return None


def _appel_modele(messages: list[dict], modele: str = NEOGEN_MODEL) -> str:
    corps = json.dumps({
        "model": modele, "messages": messages, "stream": False, "think": False,
        "options": {"num_ctx": 4096, "temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(f"http://{HOST}/api/chat", data=corps,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "")


def _extraire_code(txt: str) -> str | None:
    m = re.search(r"```(?:python)?\s*(.+?)```", txt, re.DOTALL)
    return m.group(1).strip() if m else None


def generer_libre(phrase: str, modele: str = NEOGEN_MODEL):
    """Boucle complète. Renvoie (piece|None, essais, journal)."""
    from core.neogen.pilote import _preparer_moteur
    _preparer_moteur()
    messages = [{"role": "system", "content": _prompt_systeme(phrase)},
                {"role": "user", "content": phrase}]
    journal = []
    for essai in range(1, MAX_ESSAIS + 1):
        rep = _appel_modele(messages, modele)
        code = _extraire_code(rep)
        if not code:
            messages += [{"role": "assistant", "content": rep},
                         {"role": "user", "content": "Reponds UNIQUEMENT avec le code entre ```python et ```."}]
            journal.append(f"essai {essai}: pas de code")
            continue
        try:
            piece = poser_au_sol(executer_sandbox(code))
            pb = verifier(piece)
            if pb is None:
                journal.append(f"essai {essai}: OK")
                return piece, essai, journal
            erreur = pb
        except Exception as exc:
            erreur = f"{type(exc).__name__}: {exc}"
        journal.append(f"essai {essai}: {erreur}")
        messages += [{"role": "assistant", "content": rep},
                     {"role": "user",
                      "content": f"ERREUR : {erreur}. RAPPEL : les operations 3D "
                                 f"(percer/deplacer/creuser) travaillent sur des VOLUMES ; "
                                 f"une forme 2D doit d'abord passer par extrusion(forme, "
                                 f"hauteur). Corrige et renvoie le script EN ENTIER."}]
    return None, MAX_ESSAIS, journal


def generer_et_exporter(phrase: str, modele: str = NEOGEN_MODEL):
    """Pour l'UI : génère et exporte. Renvoie (Path|None, journal)."""
    piece, _essais, journal = generer_libre(phrase, modele)
    if piece is None:
        return None, journal
    DOSSIER_SORTIES.mkdir(parents=True, exist_ok=True)
    mots = "_".join(list(_normaliser_mots(phrase))[:4]) or "piece"
    base = DOSSIER_SORTIES / f"libre_{mots[:40]}"
    piece.export(base.with_suffix(".stl"))
    try:
        piece.export(base.with_suffix(".3mf"))
        return base.with_suffix(".3mf"), journal
    except Exception:
        return base.with_suffix(".stl"), journal
