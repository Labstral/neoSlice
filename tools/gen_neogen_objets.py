# -*- coding: utf-8 -*-
"""Génère `neogen_objets.json` — la BASE d'objets neoGen téléchargeable.

But : ajouter/corriger des objets de la bibliothèque neoGen SANS republier
l'application. Le fichier produit est à téléverser sur la release d'assets
GitHub (`neoslice-assets`, tag `assistant-latest`), à côté de `neogen_cookbook.json`
et de la KB d'Oen. Les utilisateurs le reçoivent via
« Réglages → Gestion des modules → Mettre à jour la base ».

Chaque objet est un dict :
  id, fr, en, domaine, texte("aucun"|"optionnel"|"requis"), synonymes,
  params : [[id, fr, en, min, max, defaut, pas], ...]
  flags  : [[id, fr, en, defaut], ...]            (optionnel)
  choix  : [[id, fr, en, [[val,fr,en],...], defaut], ...]  (optionnel)
  code   : script géométrique du KIT neoGen (voir core/neogen/libre.py : API).
           Les noms de params deviennent des variables ; finir par piece = ...

Ce script VALIDE chaque objet exactement comme le fera l'app au téléchargement
(sandbox clos + vérificateur : étanche, un seul tenant, imprimable). Un objet
qui échoue est ÉCARTÉ et signalé — jamais publié.

Usage :  python tools/gen_neogen_objets.py
         (écrit tools/out/neogen_objets.json ; incrémenter VERSION à chaque MAJ)
"""
from __future__ import annotations

import base64
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def embed_mesh(chemin: str) -> dict:
    """Embarque un MODÈLE IMPORTÉ (3mf/STL/OBJ tout fait) dans la base, sans
    rebuild : renvoie le champ `mesh` à mettre dans un objet (à la place de
    `code`). Le maillage est chargé, ré-exporté en STL binaire compact, gzippé
    puis base64. L'app 0.1.8.4+ sait le recharger tel quel (posé, centré XY).

    Exemple d'objet importé (à ajouter dans OBJETS) :
        {"id": "ma_tour", "fr": "Ma tour", "en": "My tower",
         "domaine": "calibration", "texte": "aucun",
         "params": [["echelle", "Échelle", "Scale", 50, 150, 100, 5]],
         "mesh": embed_mesh(r"C:/chemin/vers/modele.3mf")}
    """
    import trimesh
    m = trimesh.load(chemin, force="mesh")
    if isinstance(m, trimesh.Scene):
        m = m.to_geometry()
    raw = m.export(file_type="stl")            # STL binaire
    if isinstance(raw, str):
        raw = raw.encode()
    return {"format": "stl",
            "gz_b64": base64.b64encode(gzip.compress(raw)).decode("ascii")}


VERSION = "2026-07-28k"
NOTES = "Nouveau : catégorie Calibration & tests (cube XYZ, trous, tolérance, parois, pont, retrait, 1re couche, surplombs, tour de température) + support de carte Raspberry Pi / Arduino."

# Catégories (domaines) NON natives définies par la base — permet d'ajouter une
# NOUVELLE catégorie neoGen SANS rebuild (fusionnées par catalogue.par_domaine).
DOMAINES = {
    "calibration": ("Calibration & tests", "Calibration & tests"),
}

# ── Objets à publier ────────────────────────────────────────────────────────
OBJETS = [
    {
        # REMPLACE l'objet natif « boite » (même id → override par la base). Ajoute
        # une case « Couvercle coulissant » (SANS rebuild) : cochée + forme
        # Rectangulaire → boîte coulissante avec Longueur ET Largeur réglables
        # (ces champs ne s'affichent qu'en Rectangulaire). Reproduit aussi
        # ronde/carrée/rectangulaire (couvercle à lèvre) via creuser + lèvre.
        "id": "boite",
        "fr": "Boîte + couvercle", "en": "Box + lid",
        "domaine": "maison", "texte": "aucun",
        "synonymes": "boite couvercle rangement ronde carree rectangulaire coulissant coulisse glissiere plumier tiroir rails rainure lid",
        "params": [
            ["taille", "Diamètre / côté", "Diameter / side", 18, 270, 50, 1],
            ["longueur", "Longueur", "Length", 28, 400, 90, 1],
            ["largeur", "Largeur", "Width", 20, 290, 60, 1],
            ["hauteur", "Hauteur", "Height", 10, 216, 30, 1],
            ["paroi", "Épaisseur des murs", "Wall thickness", 1.2, 5, 2.4, 0.2],
            ["jeu", "Jeu couvercle", "Lid clearance", 0.1, 0.5, 0.2, 0.1],
        ],
        "choix": [
            ["forme", "Forme", "Shape",
             [["ronde", "Ronde", "Round"], ["carree", "Carrée", "Square"],
              ["rectangulaire", "Rectangulaire", "Rectangular"]],
             "rectangulaire"],
            ["mesures", "Mesures", "Dimensions",
             [["int", "Intérieures (volume utile)", "Inner (usable)"],
              ["ext", "Extérieures (murs compris)", "Outer (with walls)"]],
             "int"],
        ],
        "flags": [
            ["coulissant", "Couvercle coulissant", "Sliding lid", False],
        ],
        "code": r'''
p = paroi
fond = paroi
Dt = taille
Lo = longueur
La = largeur
H = hauteur
if mesures == "int":
    # L'utilisateur a saisi les cotes INTÉRIEURES (le volume utile). On ajoute
    # les parois pour obtenir l'extérieur -> l'intérieur fait pile la taille voulue.
    Dt = Dt + 2 * p
    Lo = Lo + 2 * p
    La = La + 2 * p
    H = H + fond
    if coulissant:
        H = H + 5.5   # glissière + lèvre du dessus mangent la hauteur interne
if coulissant:
    # Couvercle COULISSANT. Dimensions selon la forme : Rectangulaire → Longueur
    # ET Largeur (les 2 champs sont visibles en Rectangulaire) ; sinon empreinte
    # carrée pilotee par « Diamètre / côté ».
    if forme == "rectangulaire":
        Lg = Lo
        Wd = La
    else:
        Lg = Dt
        Wd = Dt
    gh = 3.0
    gd = min(2.0, p - 0.4)   # profondeur de rainure < épaisseur de paroi
    corps = creuser(boite_3d(Lg, Wd, H), p)
    z1 = H - 2.5 - gh
    lo = Lg - p + 3
    cx = -(p + 3) / 2
    for sy in (1, -1):
        yc = sy * (Wd / 2 - p)
        corps = percer(corps, deplacer(boite_3d(lo, 2 * gd, gh), cx, yc, z1))
    corps = percer(corps, deplacer(boite_3d(3 * p, Wd - 2 * p + 2 * gd + 4, H), -Lg / 2, 0, z1))
    lw = (Wd - 2 * p) + 2 * gd - 2 * jeu
    ll = Lg - p - jeu
    lt = gh - jeu
    couvercle = deplacer(boite_3d(ll, lw, lt), 0, Wd + 16, 0)
    piece = scene(corps, couvercle)
elif forme == "ronde":
    d = Dt
    corps = creuser(cylindre(d, H), p)
    cap = extrusion(disque(d), fond)
    lip = tube(d - 2 * (p + jeu), d - 2 * (p + jeu) - 2 * p, 6)
    couvercle = deplacer(fusionner(cap, deplacer(lip, 0, 0, fond - 0.01)), 0, d + 16, 0)
    piece = scene(corps, couvercle)
else:
    if forme == "carree":
        Lx = Dt
        Wy = Dt
    else:
        Lx = Lo
        Wy = La
    rc = min(4.0, min(Lx, Wy) * 0.12)
    foot = rectangle_arrondi(Lx, Wy, rc)
    corps = creuser(extrusion(foot, H), p)
    lo = rectangle_arrondi(Lx - 2 * (p + jeu), Wy - 2 * (p + jeu), max(0.8, rc - p))
    li = rectangle_arrondi(Lx - 2 * (p + jeu) - 2 * p, Wy - 2 * (p + jeu) - 2 * p, max(0.5, rc - 2 * p))
    lip = percer(extrusion(lo, 6), deplacer(extrusion(li, 8), 0, 0, -1))
    cap = extrusion(foot, fond)
    couvercle = deplacer(fusionner(cap, deplacer(lip, 0, 0, fond - 0.01)), 0, Wy + 16, 0)
    piece = scene(corps, couvercle)''',
    },
    {
        # OVERRIDE de l'objet natif « photo_relief » (lithophanie) pour ajouter,
        # SANS rebuild, une case « Boîte lumineuse » : le couvercle devient une
        # lithophanie à plat qui clipse sur une boîte dimensionnée pour un module
        # LED rond Ø60 × 8 mm (anneau de centrage + trou câble USB). Décochée =
        # lithophanie normale, identique au natif.
        "id": "photo_relief",
        "fr": "Photo en relief / lithophanie", "en": "Photo relief / lithophane",
        "domaine": "perso", "texte": "aucun", "image": True,
        "synonymes": ("lithophanie photo relief lightbox boite lumineuse lampe led "
                      "backlit retroeclaire luminaire veilleuse cadre lumineux"),
        "params": [
            ["largeur", "Largeur", "Width", 40, 200, 100, 5],
            ["ep_min", "Épaisseur mini", "Min thickness", 0.4, 2, 0.8, 0.2],
            ["ep_max", "Épaisseur maxi", "Max thickness", 1.6, 6, 3.2, 0.2],
            ["profondeur", "Profondeur boîte (LED)", "Box depth (LED)", 10, 40, 12, 1],
        ],
        "flags": [
            ["cadre", "Cadre rigide", "Rigid frame", True],
            ["debout", "Debout (qualité lithophanie)", "Standing (lithophane quality)", True],
            ["lightbox", "Boîte lumineuse (LED Ø60)", "Light box (Ø60 LED)", False],
            ["sortie_arriere", "Sortie câble à l'arrière (dessous)", "Cable exit at back (underside)", False],
        ],
        "choix": [
            ["mode", "Mode", "Mode",
             [["lithophanie", "Lithophanie (rétro-éclairée)", "Lithophane (backlit)"],
              ["relief", "Relief décoratif", "Decorative relief"]],
             "lithophanie"],
        ],
        # Visibilité conditionnelle (pilotée par la base, appliquée par le formulaire) :
        # ces champs n'ont de sens qu'en mode Boîte lumineuse.
        "visible_si": {"profondeur": "lightbox", "sortie_arriere": "lightbox"},
        "cache_si": {"cadre": "lightbox"},
        "code": r'''
if lightbox:
    # COUVERCLE lithophanie A PLAT qui clipse sur une BOITE tenant un module LED
    # rond Ø60 x 8 mm (anneau de centrage + trou cable USB). Boite et couvercle
    # au MEME format que la lithophanie.
    litho = relief_image(image, largeur, ep_min, ep_max, "lithophanie", True, False)
    b = litho.bounds
    W = b[1][0] - b[0][0]
    Hy = b[1][1] - b[0][1]
    T = b[1][2] - b[0][2]
    cx = (b[0][0] + b[1][0]) / 2
    cy = (b[0][1] + b[1][1]) / 2
    litho = deplacer(litho, -cx, -cy, -b[0][2])   # centre en XY, base z=0
    p = 2.4
    fond = 3.0
    Dled = 60.0
    # profondeur intérieure réglable, mais JAMAIS < 10 mm (LED 8 mm + 2 mm de jeu)
    # pour que la LED ne touche pas le couvercle.
    prof = max(profondeur, 10.0)
    # La boite doit TOUJOURS pouvoir accueillir la LED Ø60 -> au moins
    # Dled + 2 parois + marge dans CHAQUE sens (gere les images larges/etroites).
    mini = Dled + 2 * p + 8
    Wb = max(W, mini)
    Hb = max(Hy, mini)
    if Wb - W > 0.5 or Hb - Hy > 0.5:
        # litho plus petite que la boite -> BORD plein autour d'elle pour que le
        # COUVERCLE fasse pile la taille de la boite (ils restent identiques).
        cadre = percer(extrusion(rectangle_arrondi(Wb, Hb, 3), T),
                       deplacer(extrusion(rectangle_arrondi(W - 1, Hy - 1, 1), T + 2), 0, 0, -1))
        litho = fusionner(litho, cadre)
    corps = creuser(boite_3d(Wb, Hb, prof + fond), p)
    corps = fusionner(corps, deplacer(tube(Dled + 4, Dled + 0.8, 5), 0, 0, fond))
    # Passage câble/plug : MÊME ouverture partout, dimensionnée pour un plug USB-A
    # MOULÉ (métal 12x4.5, boîtier ~14x7, surmoulage plastique compris) -> 16 mm
    # de large x 9 mm de haut. Ouverture dans l'anneau + rainure au fond + trou de
    # paroi, tous alignés, pour que le plug passe d'un bout à l'autre.
    ouv = 16.0
    # Ouverture de câble de TAILLE FIXE (ne grandit pas avec la boîte) : un gap
    # dans l'anneau (le câble sort de la LED) + un trou de sortie.
    corps = percer(corps, deplacer(boite_3d(ouv, 10, 7), 0, -(Dled / 2), fond - 0.5))
    if sortie_arriere:
        # sortie par l'ARRIÈRE (dessous) : trou dans le FOND collé au BORD BAS (côté
        # sortie) -> reste toujours proche du bas quelle que soit la taille de la
        # boîte, le câble descend bien quand on la pose sur le flanc.
        corps = percer(corps, deplacer(boite_3d(ouv, 12, fond + 8), 0, -(Hb / 2 - p - 7), -4))
    else:
        # sortie sur le CÔTÉ : trou fixe dans la paroi -Y, au ras du fond.
        corps = percer(corps, deplacer(boite_3d(ouv, 3 * p, 9), 0, -Hb / 2, fond))
    ext = rectangle_arrondi(Wb - 2 * p - 0.6, Hb - 2 * p - 0.6, 3)
    inn = rectangle_arrondi(Wb - 4 * p - 0.6, Hb - 4 * p - 0.6, 2)
    levre = percer(extrusion(ext, 5), deplacer(extrusion(inn, 7), 0, 0, -1))
    couvercle = fusionner(litho, deplacer(levre, 0, 0, -5))
    if debout:
        # case « Debout » cochée -> couvercle DEBOUT (qualité lithophanie), posé
        # à la verticale à côté de la boîte pour l'impression.
        couvercle = deplacer(poser_au_sol(tourner(couvercle, "x", 90)), 0, Hb + 30, 0)
    else:
        couvercle = deplacer(couvercle, 0, Hb + 25, 5)   # à plat à côté
    piece = scene(corps, couvercle)
else:
    piece = relief_image(image, largeur, ep_min, ep_max, mode, cadre, debout)''',
    },
    {
        "id": "passe_fil_bureau",
        "fr": "Passe-fil de bureau", "en": "Desk cable grommet",
        "domaine": "bureau", "texte": "aucun",
        "synonymes": "passe fil cable bureau trou oeillet grommet gestion cables collerette",
        "params": [
            ["d_trou_bureau", "Ø trou du bureau", "Desk hole ø", 20, 80, 40, 1],
            ["d_cables", "Ø passage des câbles", "Cable opening ø", 8, 60, 24, 1],
            ["hauteur", "Hauteur (épaisseur plateau)", "Height (desktop)", 8, 40, 18, 1],
        ],
        "code": (
            "col = cylindre(d_trou_bureau, hauteur)\n"
            "bride = cylindre(d_trou_bureau + 12, 3)\n"
            "corps = fusionner(col, bride)\n"
            "trou = deplacer(cylindre(d_cables, hauteur + 10), 0, 0, -2)\n"
            "piece = poser_au_sol(percer(corps, trou))"
        ),
    },
    {
        "id": "support_carte_electronique",
        "fr": "Support de carte (Raspberry Pi / Arduino)",
        "en": "Board holder (Raspberry Pi / Arduino)",
        "domaine": "bureau", "texte": "aucun",
        "synonymes": ("raspberry pi arduino carte electronique pcb support plots "
                      "entretoises standoff board holder mount plaque circuit"),
        "params": [
            ["longueur", "Longueur de la carte", "Board length", 20, 200, 85, 1],
            ["largeur", "Largeur de la carte", "Board width", 20, 150, 56, 1],
            ["entraxe_x", "Entraxe des trous (longueur)", "Hole spacing (length)", 10, 190, 58, 1],
            ["entraxe_y", "Entraxe des trous (largeur)", "Hole spacing (width)", 10, 140, 49, 1],
            ["d_trou", "Ø des vis", "Screw ø", 2, 6, 2.8, 0.1],
            ["hauteur_plot", "Hauteur des entretoises", "Standoff height", 3, 25, 6, 0.5],
        ],
        "code": (
            "ep = 2.5\n"
            "r = d_trou / 2 + 2.2\n"                       # paroi de l'entretoise
            "Lx = max(longueur, entraxe_x + 2 * r + 4)\n"  # base assez large pour les plots
            "Ly = max(largeur, entraxe_y + 2 * r + 4)\n"
            "corps = extrusion(rectangle_arrondi(Lx, Ly, 4), ep)\n"
            "for sx in (-1, 1):\n"
            "    for sy in (-1, 1):\n"
            "        px = sx * entraxe_x / 2\n"
            "        py = sy * entraxe_y / 2\n"
            "        corps = fusionner(corps, deplacer(cylindre(2 * r, ep + hauteur_plot), px, py, 0))\n"
            "for sx in (-1, 1):\n"
            "    for sy in (-1, 1):\n"
            "        px = sx * entraxe_x / 2\n"
            "        py = sy * entraxe_y / 2\n"
            "        corps = percer(corps, deplacer(cylindre(d_trou, ep + hauteur_plot + 6), px, py, -3))\n"
            "piece = poser_au_sol(corps)"
        ),
    },

    # ── CALIBRATION & TESTS (objets générés, réglables) ─────────────────────
    {
        "id": "calib_cube", "fr": "Cube de calibration XYZ", "en": "XYZ calibration cube",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "cube calibration xyz test dimension precision 20mm axes",
        "params": [["taille", "Taille du cube", "Cube size", 15, 40, 20, 1]],
        "code": r'''
t = taille
cube = boite_3d(t, t, t)
h = t * 0.5
x = deplacer(tourner(extrusion(texte_2d("X", h), 4), 'x', 90), 0, -(t/2 - 1.2), t/2)
cube = percer(cube, x)
y = deplacer(tourner(tourner(extrusion(texte_2d("Y", h), 4), 'x', 90), 'z', 90), (t/2 - 1.2), 0, t/2)
cube = percer(cube, y)
z = deplacer(extrusion(texte_2d("Z", h), 4), 0, 0, t - 1.2)
cube = percer(cube, z)
piece = poser_au_sol(cube)''',
    },
    {
        "id": "test_trous", "fr": "Test de trous (diamètres)", "en": "Hole size test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test trous diametre percage tolerance percer hole calibration",
        "params": [
            ["nb_trous", "Nombre de trous", "Number of holes", 3, 10, 6, 1],
            ["d_min", "Diamètre mini", "Min diameter", 1, 5, 2, 0.5],
            ["pas", "Écart entre diamètres", "Diameter step", 0.5, 2, 1, 0.5],
        ],
        "code": r'''
n = int(nb_trous)
dmax = d_min + (n - 1) * pas
esp = dmax + 6
Lp = n * esp
plaque = extrusion(rectangle_arrondi(Lp, dmax + 12, 3), 3)
for i in range(n):
    d = d_min + i * pas
    x = (i - (n - 1) / 2.0) * esp
    plaque = percer(plaque, deplacer(cylindre(d, 12), x, 0, -2))
piece = poser_au_sol(plaque)''',
    },
    {
        "id": "test_tolerance", "fr": "Test de tolérance / ajustement", "en": "Tolerance (fit) test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test tolerance jeu ajustement fit clearance calibration pion anneau",
        "params": [["nb", "Nombre de jeux", "Number of gaps", 3, 7, 5, 1]],
        "code": r'''
n = int(nb)
esp = 16
Lp = n * esp + 6
base = extrusion(rectangle_arrondi(Lp, 24, 3), 3)
for i in range(n):
    jeu = 0.1 + i * 0.1
    x = (i - (n - 1) / 2.0) * esp
    peg = deplacer(cylindre(6, 11), x, 0, 1.5)
    ring = deplacer(tube(6 + 2 * jeu + 4, 6 + 2 * jeu, 11), x, 0, 1.5)
    base = fusionner(base, peg, ring)
piece = poser_au_sol(base)''',
    },
    {
        "id": "test_parois", "fr": "Test d'épaisseur de parois", "en": "Wall thickness test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test parois epaisseur wall thickness mur calibration ligne",
        "params": [["nb", "Nombre de parois", "Number of walls", 3, 8, 5, 1]],
        "code": r'''
n = int(nb)
base = extrusion(rectangle_arrondi(n * 9 + 6, 24, 3), 3)
corps = base
for i in range(n):
    ep = 0.4 + i * 0.4
    x = (i - (n - 1) / 2.0) * 9
    corps = fusionner(corps, deplacer(boite_3d(ep, 18, 16), x, 0, 0))
piece = poser_au_sol(corps)''',
    },
    {
        "id": "test_pont", "fr": "Test de pont (bridging)", "en": "Bridging test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test pont bridging portee bridge calibration surplomb",
        "params": [
            ["portee", "Portée du pont", "Bridge span", 10, 60, 20, 1],
            ["hauteur", "Hauteur", "Height", 15, 40, 25, 1],
        ],
        "code": r'''
H = hauteur
p = portee
larg = 24
t = 6
g = deplacer(boite_3d(t, larg, H), -(p / 2 + t / 2), 0, 0)
d = deplacer(boite_3d(t, larg, H), (p / 2 + t / 2), 0, 0)
pont = deplacer(boite_3d(p + 2 * t, larg, 4), 0, 0, H - 4)
piece = poser_au_sol(fusionner(g, d, pont))''',
    },
    {
        "id": "test_retract", "fr": "Test de retrait (stringing)", "en": "Retraction (stringing) test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test retract retrait stringing fils oozing calibration tours",
        "params": [
            ["ecart", "Écart entre tours", "Gap between towers", 20, 80, 40, 1],
            ["hauteur", "Hauteur", "Height", 25, 70, 45, 1],
        ],
        "code": r'''
ec = ecart
base = extrusion(rectangle_arrondi(ec + 20, 16, 3), 2)
t1 = deplacer(cone(10, hauteur, 4), -ec / 2, 0, 1)
t2 = deplacer(cone(10, hauteur, 4), ec / 2, 0, 1)
piece = poser_au_sol(fusionner(base, t1, t2))''',
    },
    {
        "id": "test_premiere_couche", "fr": "Test de première couche", "en": "First layer test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test premiere couche adherence bed level nivellement plateau calibration",
        "params": [["taille", "Taille", "Size", 40, 120, 60, 5]],
        "code": r'''
t = taille
ep = 1.0
cadre = percer(extrusion(rectangle_arrondi(t, t, 4), ep),
               deplacer(extrusion(rectangle_arrondi(t - 6, t - 6, 3), ep + 2), 0, 0, -1))
b1 = deplacer(boite_3d(t - 6, 3, ep), 0, 0, ep / 2)
b2 = deplacer(boite_3d(3, t - 6, ep), 0, 0, ep / 2)
piece = poser_au_sol(fusionner(cadre, b1, b2))''',
    },
]


def _make_test_image() -> str:
    """Image d'essai (disque noir sur fond blanc) pour valider les recettes image."""
    import tempfile
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (240, 240), "white")
    ImageDraw.Draw(img).ellipse([50, 50, 190, 190], fill="black")
    path = Path(tempfile.gettempdir()) / "neogen_test_img.png"
    img.save(path)
    return str(path)


def main() -> int:
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts

    _IMAGE_TEST = _make_test_image()
    valides, ecartes = [], []
    for obj in OBJETS:
        try:
            if obj.get("mesh"):                    # MODÈLE IMPORTÉ (mesh embarqué)
                from core.neogen.objets_module import mesh_depuis_champ
                piece = mesh_depuis_champ(obj["mesh"])
                d = piece.bounds[1] - piece.bounds[0]
                if (len(piece.faces) and len(piece.faces) < 600_000
                        and float(min(d)) > 0.8 and float(max(d)) < 300.0):
                    valides.append(obj)
                    print(f"  OK   {obj['id']:20} {d[0]:.0f}x{d[1]:.0f}x{d[2]:.0f} mm "
                          f"(importé, {len(piece.faces)} faces)")
                else:
                    ecartes.append((obj["id"], "mesh hors bornes"))
                    print(f"  KO   {obj['id']:20} → mesh hors bornes")
                continue
            ns = _defauts(obj)
            if obj.get("texte", "aucun") != "aucun":
                ns["texte"] = "Test"
            if obj.get("image", False):
                ns["image"] = _IMAGE_TEST          # image d'essai pour valider le code
            piece = L.poser_au_sol(L.executer_sandbox(obj["code"], ns))
            err = L.verifier(piece)
            if err is None:
                valides.append(obj)
                import trimesh as _tm
                d = piece.bounds[1] - piece.bounds[0]
                if isinstance(piece, _tm.Scene):
                    n = len([g for g in piece.geometry.values() if hasattr(g, "faces")])
                    print(f"  OK   {obj['id']:20} {d[0]:.0f}x{d[1]:.0f}x{d[2]:.0f} mm "
                          f"({n} corps)")
                else:
                    print(f"  OK   {obj['id']:20} {d[0]:.0f}x{d[1]:.0f}x{d[2]:.0f} mm "
                          f"(watertight={piece.is_watertight})")
            else:
                ecartes.append((obj["id"], err))
                print(f"  KO   {obj['id']:20} → {err}")
        except Exception as e:
            ecartes.append((obj["id"], str(e)))
            print(f"  KO   {obj['id']:20} → EXCEPTION {e}")

    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "neogen_objets.json"
    doms_used = sorted({o.get("domaine") for o in valides if o.get("domaine")})
    domaines_out = [{"id": d, "fr": DOMAINES[d][0], "en": DOMAINES[d][1]}
                    for d in doms_used if d in DOMAINES]
    out.write_text(json.dumps({"version": VERSION, "notes": NOTES,
                               "domaines": domaines_out, "objets": valides},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(valides)} objet(s) valide(s), {len(ecartes)} ecarte(s).")
    print(f"-> {out}")
    print("  Televerse ce fichier sur la release d'assets (tag assistant-latest)"
          " sous le nom neogen_objets.json.")
    return 0 if not ecartes else 1


if __name__ == "__main__":
    raise SystemExit(main())
