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


VERSION = "2026-09-27"
NOTES = "Deux nouveautés. Le RANGEMENT DE JEU de société, un insert à la taille de votre boîte, avec au choix un logement de cartes et son échancrure pour attraper le paquet, des godets ronds pour les jetons, ou des cases pour les meeples (idée de Sébastien). Et la PANCARTE DE PORTE à suspendre à la poignée, avec votre texte en relief ou gravé, sur plusieurs lignes, et au choix un trou fermé ou un crochet ouvert (idée de Pierre)."

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
# GARDE-FOU validation : la vérification de la base (téléchargement) exécute la
# recette SANS image (seul l'utilisateur en choisit une). On rend alors une
# pièce-témoin saine ; le vrai rendu exige la photo. NE PAS retirer — sans lui,
# photo_relief est écarté à la validation download (NameError sur `image`).
try:
    _img = image
except:
    _img = None
if _img is None:
    piece = extrusion(rectangle_arrondi(largeur, largeur * 0.75, 3), ep_max)
elif lightbox:
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
    {
        # Bac compatible GRIDFINITY — le système de rangement modulaire 42 mm le
        # plus imprimé de la communauté. Pieds au profil officiel APPROCHÉ par
        # étages inscrits dans le chanfrein 45° (marches de ≤ 0,72 mm, coins
        # arrondis dégressifs) : le bac se clipse dans toute baseplate Gridfinity
        # standard. Lèvre d'empilage droite (bacs empilables), séparateurs par
        # découpe de poches (cloisons = épaisseur de paroi), trous à aimants
        # Ø 6,5 × 2 mm optionnels aux quatre coins de chaque cellule (entraxe 26).
        "id": "gridfinity",
        "fr": "Bac Gridfinity", "en": "Gridfinity bin",
        "domaine": "maison", "texte": "aucun",
        "synonymes": "gridfinity bac rangement modulaire tiroir organiseur "
                     "organisateur atelier vis casier baseplate bin 42 compartiment "
                     "separateur empilable stackable storage",
        # Dimensions LIBRES en mm (retour Emmanuel : pas d'« unités de 42 mm »,
        # on choisit exactement la valeur voulue). La compatibilité Gridfinity
        # est automatique : autant de pieds standard 42 mm que la semelle en
        # accueille, centrés. ids « cases_* » = COMPTES (pas de suffixe mm).
        "params": [
            ["longueur", "Longueur", "Length", 15, 250, 84, 1],
            ["largeur", "Largeur", "Width", 15, 250, 42, 1],
            ["hauteur", "Hauteur", "Height", 12, 120, 42, 1],
            ["cases_x", "Cases en longueur", "Compartments lengthwise", 1, 6, 1, 1],
            ["cases_y", "Cases en largeur", "Compartments widthwise", 1, 6, 1, 1],
            ["paroi", "Épaisseur des parois", "Wall thickness", 1.0, 2.4, 1.2, 0.2],
        ],
        "code": r'''
PAS = 42.0
L = longueur
La = largeur
H = hauteur
fond = 2.0

# ── Pieds standard Gridfinity sous la semelle : AUTANT que la surface en
# accueille (grille 42 mm centrée) — le bac garde des dimensions LIBRES tout en
# se clipsant dans une baseplate. Un pied standard fait 41,5 mm carré : si le
# bac est plus étroit dans UN sens, il passe en FOND PLAT (bac libre, sans
# accroche). Chanfreins 45° approchés par étages INSCRITS dans le profil
# officiel (35,6 -> 37,2 -> 41,5 sur 4,75 mm de haut).
a_pieds = (L >= PAS - 0.5) and (La >= PAS - 0.5)
base_z = 4.75 if a_pieds else 0.0
pieds = []
if a_pieds:
    nx = max(1, plancher((L + 0.5) / PAS))
    ny = max(1, plancher((La + 0.5) / PAS))
    # Pied au profil officiel EXACT et LISSE (retour Emmanuel : l'approximation
    # en marches faisait un vilain escalier). Chaque chanfrein 45° d'un carré
    # arrondi = décomposition exacte de la surface d'offset : un cœur droit au
    # gabarit bas + 4 rampes triangulaires sur les côtés + 4 troncs de cône aux
    # coins (le rayon de coin grandit avec la largeur : r = 3,75 − (41,5−w)/2).
    etapes = [(0.0, 0.8, 35.6, 37.2),      # chanfrein bas 0,8 mm
              (0.8, 1.8, 37.2, 37.2),      # section droite 1,8 mm
              (2.6, 2.15, 37.2, 41.5)]     # chanfrein haut 2,15 mm
    morceaux_pied = []
    for z0, h, w_b, w_t in etapes:
        r_b = 3.75 - (41.5 - w_b) / 2
        r_t = 3.75 - (41.5 - w_t) / 2
        morceaux_pied.append(extrusion(rectangle_arrondi(w_b, w_b, r_b), h, z0))
        if w_t - w_b < 0.01:
            continue
        t = (w_t - w_b) / 2
        Lb = w_b - 2 * r_b
        tri = polygone([(w_b / 2, 0), (w_b / 2 + t, h), (w_b / 2, h)])
        rampe = deplacer(tourner(extrusion(tri, Lb), "x", 90), 0, Lb / 2, 0)
        for ang in (0, 90, 180, 270):
            morceaux_pied.append(deplacer(tourner(rampe, "z", ang), 0, 0, z0))
        cc = w_b / 2 - r_b
        for sx in (1, -1):
            for sy in (1, -1):
                morceaux_pied.append(deplacer(cone(2 * r_b, h, 2 * r_t),
                                              sx * cc, sy * cc, z0))
    pied = fusionner(*morceaux_pied)
    for ix in range(nx):
        for iy in range(ny):
            pieds.append(deplacer(pied, (ix - (nx - 1) / 2.0) * PAS,
                                  (iy - (ny - 1) / 2.0) * PAS, 0))

# ── Corps aux dimensions EXACTES demandées, bord supérieur net
corps = extrusion(rectangle_arrondi(L, La, 3.75), H - base_z, base_z)
piece = fusionner(*(pieds + [corps])) if pieds else corps

# ── Poches intérieures (les cloisons restantes = séparateurs), creusées
# jusqu'au bord -> flancs parfaitement lisses du fond au sommet.
r_int = max(0.8, 3.75 - paroi)
cxn = int(cases_x)
cyn = int(cases_y)
Wi = L - 2 * paroi
Hi = La - 2 * paroi
pw = (Wi - (cxn - 1) * paroi) / cxn
ph = (Hi - (cyn - 1) * paroi) / cyn
poches = []
for i in range(cxn):
    for j in range(cyn):
        px = -Wi / 2 + i * (pw + paroi) + pw / 2
        py = -Hi / 2 + j * (ph + paroi) + ph / 2
        poches.append(deplacer(rectangle_arrondi(pw, ph, r_int), px, py))
outil = extrusion(fusionner(*poches) if len(poches) > 1 else poches[0],
                  H - base_z - fond + 6.0, base_z + fond)
piece = poser_au_sol(percer(piece, outil))''',
    },
    {
        "id": "bac_empilable",
        "fr": "Bac empilable", "en": "Stackable bin",
        "domaine": "maison", "texte": "aucun",
        "synonymes": "bac empilable rangement caisse bin ajoure grillage nid "
                     "abeille alveole trous poignee prise panier",
        "params": [
            ["longueur", "Longueur", "Length", 60, 220, 120, 5],
            ["largeur", "Largeur", "Width", 50, 180, 90, 5],
            ["hauteur", "Hauteur", "Height", 25, 100, 50, 5],
        ],
        "flags": [["poignees", "Poignées (prise en main)", "Hand grips", False]],
        "choix": [["motif", "Parois", "Walls",
                   [["plein", "Pleines", "Solid"],
                    ["nid_abeille", "Nid d'abeille", "Honeycomb"],
                    ["rond", "Trous ronds", "Round holes"]], "plein"],
                  ["style_poignee", "Forme des poignées", "Grip shape",
                   [["alveolee", "Encoche nid d'abeille", "Honeycomb notch"],
                    ["ovale", "Encoche arrondie", "Rounded notch"],
                    ["fermee_alveolee", "Trou nid d'abeille", "Honeycomb hole"],
                    ["fermee_ovale", "Trou ovale", "Oval hole"]], "alveolee"]],
        # Parois ajourées + poignées : suggestion de Nicolas (2026-09-20).
        # Le fond, les angles et la collerette d'empilage restent PLEINS :
        # ce sont eux qui tiennent la pile. Hexagone pointe en haut (flancs
        # à 60°) et poignée ELLIPTIQUE : rien à ponter à l'impression.
        "code": r'''
p = 2.0
fond = 2.4
evase_h = 8.0
jeu = 0.3
eps = 0.01
L = longueur
La = largeur
H = hauteur
r_ext = min(4.0, L * 0.08, La * 0.2)

# Corps : fond plein, murs droits, puis collerette EVASEE en 6 tranches.
# Le bas du bac suivant se pose dedans et s'auto-centre (jeu 0,3 mm).
morceaux = [extrusion(rectangle_arrondi(L, La, r_ext), fond)]
mur2d = percer(rectangle_arrondi(L, La, r_ext),
               rectangle_arrondi(L - 2 * p, La - 2 * p, max(0.5, r_ext - p)))
morceaux.append(extrusion(mur2d, H - fond - evase_h + eps, fond - eps))
n_tr = 6
dz = evase_h / n_tr
for i in range(n_tr):
    d = (p + jeu) * (i + 1) / n_tr
    anneau = percer(rectangle_arrondi(L + 2 * d, La + 2 * d, r_ext + d),
                    rectangle_arrondi(L + 2 * d - 2 * p, La + 2 * d - 2 * p,
                                      max(0.5, r_ext + d - p)))
    morceaux.append(extrusion(anneau, dz + eps, H - evase_h + i * dz - eps))
piece = fusionner(*morceaux)

# Bande de paroi DROITE percable : au dessus du fond, sous la collerette, et
# en retrait des angles. Fond, angles et collerette restent PLEINS.
marge = 8.0
marge_v = 4.0
z0 = fond + marge_v
z1 = H - evase_h - marge_v
haut_v = z1 - z0
zc = (z0 + z1) / 2.0

if (motif != "plein" or poignees) and haut_v >= 6.5:
    # Alveoles DIMENSIONNEES sur la bande : a pas fige, une paroi n'en logeait
    # qu'une seule rangee.
    rangs = max(1, int(round(haut_v / 11.0)))
    pas = haut_v / max(0.84, 0.866 * rangs - 0.02)
    pas = max(6.0, min(pas, 22.0))
    r_alv = pas * 0.42
    ecart_v = pas * 0.866

    cote_prise = "x" if L >= La else "y"
    prise = None
    Lp = 0.0
    Hp = 0.0
    if poignees:
        cote_u = La if cote_prise == "x" else L
        Lp = max(35.0, min(cote_u * 0.55, cote_u - 2 * marge))
        Hp = max(10.0, min(haut_v * 0.8, 32.0))
        # DEUX familles de poignee, au choix (Emmanuel, 2026-09-21) :
        #  - ENCOCHE ouverte sur le haut : la paroi est decoupee jusqu'au bord,
        #    collerette comprise, et on passe les doigts PAR DESSUS le bord
        #    (c'est ce que montre l'image de Nicolas) ;
        #  - TROU ferme : l'ancienne poignee, entierement dans la paroi droite,
        #    on enfile la main dedans.
        # Chacune existe en nid d'abeille (meme langage visuel que les parois)
        # et en arrondi.
        ouverte = style_poignee in ("alveolee", "ovale")
        arrondie = style_poignee in ("ovale", "fermee_ovale")
        if Lp > 12.0 and Hp > 8.0:
            if ouverte:
                # PROFONDEUR de l'encoche sous le bord : de quoi passer les
                # doigts, pas plus. Calculee depuis Hp, elle descendait a 35 mm
                # sur un bac de 50 et devorait presque tout le petit cote (vu
                # au rendu).
                prof_encoche = min(max(16.0, haut_v * 0.6), 26.0)
                z_bas = max(fond + 10.0, H - prof_encoche)  # jamais pres du fond
                Hp = min(Hp, max(8.0, (H - z_bas) * 0.9))
                v_fond = (z_bas + Hp / 2.0) - zc
            else:
                # Trou ferme : centre sur la bande percable, donc a distance
                # egale du fond et de la collerette.
                v_fond = 0.0
            if arrondie:
                forme_p = ellipse(Lp, Hp)
            else:
                # Une cellule du nid d'abeille ETIREE, pointe en haut : rien a
                # ponter a l'impression, comme l'ellipse.
                pts_p = []
                for t in range(6):
                    ang = 30.0 + t * 60.0
                    pts_p.append((cos(ang) * Lp / 2.0, sin(ang) * Hp / 2.0))
                forme_p = polygone(pts_p)
            prise = deplacer(forme_p, 0, v_fond)
            if ouverte:
                # La decoupe droite part du CENTRE de la forme et monte au dela
                # du bord : la moitie haute de la forme disparait avec elle.
                monte = (H + 6.0) - (v_fond + zc)
                fente = polygone([(-Lp / 2.0, 0.0), (Lp / 2.0, 0.0),
                                  (Lp / 2.0, monte), (-Lp / 2.0, monte)])
                prise = fusionner(prise, deplacer(fente, 0, v_fond))

    outils = []
    for selon in ("y", "x"):
        long_u = L if selon == "y" else La
        demi = La / 2.0 if selon == "y" else L / 2.0
        util = long_u - 2 * marge
        dessins = []
        if motif != "plein" and util > 2 * r_alv and haut_v >= 2 * r_alv - 0.001:
            # On COMPTE ce qui tient puis on CENTRE : sinon le dernier trou ne
            # retombe pas a la meme distance de l'autre bord et le motif penche.
            n_rangs = int((haut_v - 2 * r_alv) / ecart_v) + 1
            n_cols = int((util - 2 * r_alv) / pas) + 1
            for j in range(n_rangs):
                v = (j - (n_rangs - 1) / 2.0) * ecart_v
                # Une rangee sur deux compte une alveole de MOINS, centree elle
                # aussi : elle tombe alors pile entre celles d'en dessous.
                nc = n_cols if j % 2 == 0 else n_cols - 1
                if nc < 1:
                    continue
                for k in range(nc):
                    u = (k - (nc - 1) / 2.0) * pas
                    if motif == "rond":
                        forme = disque(r_alv * 2)
                    else:
                        pts = []
                        for t in range(6):
                            # ATTENTION : cos/sin du KIT prennent des DEGRES.
                            # En radians, les 6 points se tassaient sur un
                            # demi-degre et l'hexagone valait 0,0016 mm2 : le
                            # percage ne retirait RIEN (mesure).
                            ang = 30.0 + t * 60.0
                            pts.append((cos(ang) * r_alv, sin(ang) * r_alv))
                        forme = polygone(pts)
                    dessins.append(deplacer(forme, u, v))
        if prise is not None and selon == cote_prise:
            # On ecarte les alveoles que la prise effleure : sinon il reste des
            # eclats de paroi de moins d'un millimetre tout autour.
            # La garde epouse l'ENCOCHE entiere, pas seulement sa partie
            # arrondie : sinon les alveoles bordant la decoupe droite
            # laisseraient des eclats de paroi de moins d'un millimetre.
            garde = deplacer(ellipse(Lp + 6.0, Hp + 6.0), 0, v_fond)
            if ouverte:
                monte_g = (H + 8.0) - (v_fond + zc)
                garde = fusionner(garde, deplacer(polygone(
                    [(-Lp / 2.0 - 3.0, 0.0), (Lp / 2.0 + 3.0, 0.0),
                     (Lp / 2.0 + 3.0, monte_g),
                     (-Lp / 2.0 - 3.0, monte_g)]), 0, v_fond))
            restants = []
            for dessin in dessins:
                if percer(dessin, garde).area > dessin.area * 0.999:
                    restants.append(dessin)
            dessins = restants
            dessins.append(prise)
        if len(dessins) > 0:
            ep = p + 4.0
            plaque = tourner(extrusion(fusionner(*dessins), ep), "x", 90)
            for bord in (-demi, demi):
                if selon == "y":
                    outils.append(deplacer(plaque, 0, bord + ep / 2.0, zc))
                else:
                    outils.append(deplacer(tourner(plaque, "z", 90),
                                           bord - ep / 2.0, 0, zc))
    if len(outils) > 0:
        piece = percer(piece, fusionner(*outils))

piece = poser_au_sol(piece)
''',
    },
    {
        "id": "cheville",
        "fr": "Cheville de meuble", "en": "Furniture dowel",
        "domaine": "atelier", "texte": "aucun",
        "synonymes": "cheville tourillon goujon baton batonnet bois meuble kit "
                     "assemblage dowel pin raccord montage etagere",
        "params": [
            ["diametre", "Diamètre", "Diameter", 4, 16, 8, 0.5],
            ["longueur", "Longueur", "Length", 12, 80, 35, 1],
        ],
        "flags": [["cannelures", "Cannelures (évacuation de la colle)",
                   "Glue flutes", True]],
        # Demande de Nicolas (2026-09-21) : les batonnets des meubles en kit,
        # « 1 diametre et 1 longueur ». Imprimee DEBOUT : le diametre sort rond
        # et juste, ce qui est tout l'enjeu pour entrer dans un trou perce.
        "code": r'''
r = diametre / 2.0
# Chanfrein aux DEUX bouts : la cheville se presente toute seule dans le trou,
# et le bourrelet de premiere couche ne gene plus l'entree.
c = min(1.5, diametre * 0.18)
piece = revolution([(r - c, 0.0), (r, c), (r, longueur - c), (r - c, longueur)])

if cannelures:
    # Rainures longitudinales, comme les vraies chevilles de menuiserie : elles
    # laissent la colle et l'air REMONTER au lieu d'etre chasses vers le fond.
    # Elles traversent les chanfreins de PART EN PART : arretees au pied du
    # chanfrein, elles etaient bouchees aux deux bouts et ne debouchaient sur
    # rien, donc l'air restait piege au fond du trou (retour de Nicolas, capture
    # a l'appui). Elles depassent donc d'un millimetre de chaque cote.
    prof = max(0.35, diametre * 0.07)
    outils = []
    for i in range(6):
        ang = i * 60.0
        outils.append(deplacer(cylindre(prof * 2.4, longueur + 2.0),
                               cos(ang) * (r + prof * 0.5),
                               sin(ang) * (r + prof * 0.5), -1.0))
    piece = percer(piece, fusionner(*outils))

piece = poser_au_sol(piece)
''',
    },
    {
        "id": "pancarte_porte",
        "fr": "Pancarte de porte", "en": "Door hanger",
        "domaine": "maison", "texte": "optionnel",
        "synonymes": "pancarte porte poignee suspendre panneau plaque signaletique "
                     "ne pas deranger reunion chambre bureau door hanger sign "
                     "accroche texte message",
        "params": [
            ["largeur", "Largeur", "Width", 55, 140, 85, 5],
            ["hauteur", "Hauteur", "Height", 110, 250, 210, 5],
            ["epaisseur", "Épaisseur", "Thickness", 2, 8, 3, 0.5],
            ["diametre_trou", "Diamètre du trou", "Hole diameter", 25, 70, 40, 1],
            ["taille_texte", "Taille du texte", "Text size", 8, 90, 30, 1],
            ["relief_texte", "Relief ou creux du texte", "Text depth", 0.4, 3.0, 1.0, 0.1],
        ],
        "flags": [
            # ⚠️ Ce drapeau DOIT s'appeler « grave » : sans lui, l'interface
            # ajoute d'office sa propre case « Gravé » pour tout objet à texte,
            # et cette case là n'arriverait PAS dans la recette (la validation
            # d'installation ne connaît que les options déclarées). L'objet
            # serait écarté au premier clic sur la case.
            ["grave", "Texte gravé (creux)", "Engraved text", False],
        ],
        "choix": [["suspension", "Accroche", "Hanger",
                   [["trou", "Trou fermé", "Closed hole"],
                    ["crochet", "Crochet ouvert", "Open hook"]], "trou"]],
        # Idée de Pierre Mathez (formulaire du site, 2026-09-26) : « pancarte à
        # suspendre à la poignée de porte, avec possibilité de mettre un texte,
        # relief ou creux ».
        #
        # Cotes de la pancarte d'hôtel : 85 × 210 mm, trou de 40 mm, qui passe
        # sur une béquille comme sur la plupart des boutons. Le texte s'écrit
        # sur PLUSIEURS LIGNES en les séparant par une barre verticale, par
        # exemple « NE PAS | DÉRANGER ».
        "code": r'''
ep = max(1.6, epaisseur)
larg = max(40.0, largeur)
haut = max(80.0, hauteur)

# Coins arrondis : une pancarte à angles vifs accroche et se fend au coin.
r_coin = min(14.0, larg * 0.16, haut * 0.08)
plaque_2d = rectangle_arrondi(larg, haut, r_coin)

# Le trou de poignée, en haut, avec une bande PLEINE au dessus de lui : c'est
# elle qui porte tout le poids, elle ne doit jamais devenir un fil.
d_trou = max(18.0, min(diametre_trou, larg - 24.0, haut * 0.45))
marge_haut = max(9.0, d_trou * 0.30)
y_trou = haut / 2.0 - marge_haut - d_trou / 2.0
outil = deplacer(disque(d_trou), 0.0, y_trou)

if suspension == "crochet":
    # CROCHET OUVERT : l'accroche débouche sur le CÔTÉ, à mi hauteur du trou.
    # La pancarte se glisse sur la poignée d'un geste horizontal et le poids la
    # plaque ensuite au fond du crochet : elle ne peut pas retomber toute seule,
    # alors qu'une ouverture par le BAS la ferait glisser, et une ouverture par
    # le HAUT n'a aucun intérêt puisque le trou passe déjà sur la béquille.
    # ⚠️ Le crochet se dessine d'UN SEUL TENANT, et non en réunissant un disque
    # et un couloir. Cette réunion là créait des micro segments là où le
    # couloir croisait les facettes du disque : contour valide en 2D, mais
    # 393 sommets dont des longueurs quasi nulles, et la plaque extrudée
    # n'était plus étanche (mesuré : 14 corps au lieu d'un). En posant nous
    # mêmes chaque sommet, le problème ne peut pas naître.
    bouche = 30.0                      # demi angle de l'ouverture, en degrés
    r_trou = d_trou / 2.0
    gauche = -larg / 2.0 - 2.0
    pts = [(gauche, y_trou + r_trou * sin(bouche))]
    for k in range(49):
        ang = (180.0 - bouche) - (360.0 - 2.0 * bouche) * k / 48.0
        pts.append((r_trou * cos(ang), y_trou + r_trou * sin(ang)))
    pts.append((gauche, y_trou - r_trou * sin(bouche)))
    outil = polygone(pts)
plaque_2d = percer(plaque_2d, outil)
piece = extrusion(plaque_2d, ep)

# Le texte occupe TOUT ce qui reste sous le trou, et rien de plus.
# Les lignes se séparent par une barre verticale OU par un vrai retour à la
# ligne : l'interface passera bientôt à un champ multi lignes, et une pancarte
# écrite avec la touche Entrée doit se construire pareil.
lignes = str(texte).replace("\r", "").replace("\n", "|")
if len(lignes.replace("|", " ").strip()) > 0:
    zone_haut = y_trou - d_trou / 2.0 - 8.0
    zone_bas = -haut / 2.0 + 9.0
    dispo_h = max(5.0, zone_haut - zone_bas)
    dispo_l = max(10.0, larg - 18.0)
    h_txt = min(taille_texte, dispo_h)
    bloc = texte_2d(lignes, h_txt)
    # On réduit JUSQU'À CE QUE ça tienne vraiment. Une seule réduction, à la
    # proportion, laissait déborder : mesuré, une ligne de 38 lettres sortait
    # encore à 100 mm de large sur une pancarte de 85, et les lettres tombées
    # hors de la plaque faisaient une pièce en cinq morceaux. Rogner aurait
    # coupé des lettres, laisser déborder aurait donné une pièce inimprimable.
    for _essai in range(4):
        bords = bloc.bounds
        large_txt = max(0.01, bords[2] - bords[0])
        if large_txt <= dispo_l:
            break
        h_txt = max(1.5, h_txt * dispo_l / large_txt * 0.98)
        bloc = texte_2d(lignes, h_txt)
    bloc = deplacer(bloc, 0.0, (zone_haut + zone_bas) / 2.0)
    # Jamais plus profond que la plaque : il doit rester au moins 0,8 mm de
    # fond, sinon la gravure perce la pancarte de part en part.
    prof = max(0.3, min(relief_texte, ep - 0.8))
    if grave:
        piece = percer(piece, extrusion(bloc, prof + 1.0, ep - prof))
    else:
        piece = fusionner(piece, extrusion(bloc, prof, ep))

piece = poser_au_sol(piece)
''',
    },
    {
        "id": "rangement_jeu",
        "fr": "Rangement de jeu", "en": "Board game insert",
        "domaine": "maison", "texte": "aucun",
        "synonymes": "rangement jeu societe insert boite plateau cartes jetons "
                     "meeples pions des tuiles casier godet organisateur board "
                     "game insert tray token card holder",
        "params": [
            ["longueur", "Longueur", "Length", 40, 250, 140, 5],
            ["largeur", "Largeur", "Width", 40, 250, 90, 5],
            ["hauteur", "Hauteur", "Height", 10, 90, 30, 1],
            ["paroi", "Épaisseur des parois", "Wall thickness", 1.2, 5, 1.6, 0.2],
            ["carte_largeur", "Largeur d'une carte", "Card width", 30, 120, 63.5, 0.5],
            ["carte_hauteur", "Hauteur d'une carte", "Card height", 40, 160, 88, 0.5],
            ["cases_x", "Cases en longueur", "Cells across", 1, 10, 4, 1],
            ["cases_y", "Cases en largeur", "Cells deep", 1, 8, 3, 1],
        ],
        "flags": [
            ["sous_pochette", "Cartes sous pochette", "Sleeved cards", False],
            ["encoche", "Échancrure pour attraper", "Finger notch", True],
        ],
        "choix": [["contenu", "Contenu", "Contents",
                   [["cartes", "Cartes", "Cards"],
                    ["jetons", "Jetons (godets ronds)", "Tokens (round wells)"],
                    ["meeples", "Meeples et pions (cases)", "Meeples (square cells)"]],
                   "cartes"]],
        # Chaque réglage ne s'affiche que pour le contenu qui le concerne.
        # La condition « menu=valeur » vient d'être ajoutée à l'interface pour
        # cet objet : avant, seules les cases à cocher pouvaient piloter un champ.
        "visible_si": {
            "carte_largeur": "contenu=cartes",
            "carte_hauteur": "contenu=cartes",
            "sous_pochette": "contenu=cartes",
            "encoche": "contenu=cartes",
        },
        "cache_si": {
            "cases_x": "contenu=cartes",
            "cases_y": "contenu=cartes",
        },
        # Idée de Sébastien Dehay (formulaire du site, 2026-09-27) : « pour la
        # bibliothèque de neoGen, étant grand fan de jeu de société, des inserts
        # pour mettre des cartes et jeton ou meeple ».
        #
        # Un seul bac, taillé dans un bloc PLEIN : c'est ce qui laisse des
        # cloisons entre les cases. Creuser la boîte d'abord ne laisserait
        # qu'un bac vide, sans séparation (essayé, et le rendu était vide).
        "code": r'''
p = max(1.2, paroi)
fond = max(1.2, p)
L_ = max(40.0, longueur)
l_ = max(40.0, largeur)
h_ = max(10.0, hauteur)
# ⚠️ Les primitives du KIT sont POSÉES sur z = 0, pas centrées : un outil
# déplacé de h/2 ne mordait que la moitié haute du bloc (piège vécu).
bloc = boite_3d(L_, l_, h_)
creux = max(2.0, h_ - fond)

if contenu == "cartes":
    # Jeu volontaire : une carte qui frotte ne se sort plus à une main.
    jeu = 3.0 if sous_pochette else 1.5
    lc = min(carte_largeur + jeu, L_ - 2 * p)
    hc = min(carte_hauteur + jeu, l_ - 2 * p)
    bloc = percer(bloc, deplacer(boite_3d(lc, hc, creux + 1.0), 0, 0, fond))
    if encoche:
        # Demi lune dans la paroi avant, pour glisser le pouce sous le paquet.
        # Elle ne traverse QUE cette paroi : de part en part, le bac perdrait
        # ses deux faces et tiendrait beaucoup moins bien.
        d = min(lc * 0.66, 38.0)
        prof = p + hc / 2.0 + 1.0
        # ⚠️ Le BAS de la demi lune doit rester au dessus du fond. Placée à
        # mi hauteur, elle descendait sous z = 0 sur un bac courant (rayon 19,
        # centre à 17,2) et PERÇAIT LE FOND : les cartes seraient tombées au
        # travers. On la pose donc 2 mm au dessus du fond ; elle ressort par le
        # haut de la paroi, ce qui est justement la forme qu'on veut.
        z_encoche = fond + 2.0 + d / 2.0
        bloc = percer(bloc, deplacer(tourner(cylindre(d, prof), "x", 90),
                                     0, -l_ / 2.0 + prof, z_encoche))
else:
    ux = L_ - 2 * p
    uy = l_ - 2 * p
    # On RAMÈNE le nombre de cases à ce qui tient vraiment, au lieu de renoncer.
    # Avec l'ancien garde-fou, demander 10 × 8 cases sur un bac de 40 × 40 ne
    # creusait RIEN : on obtenait un bloc plein, sans le moindre message
    # (mesuré : 100 % de matière). Une option qui ne fait rien en silence est
    # un défaut, pas un choix. Six millimètres est le plus petit casier où l'on
    # arrive encore à prendre un jeton avec les doigts.
    mini = 6.0
    nx = max(1, min(int(cases_x), int((ux + p) / (mini + p))))
    ny = max(1, min(int(cases_y), int((uy + p) / (mini + p))))
    cx = (ux - (nx - 1) * p) / nx
    cy = (uy - (ny - 1) * p) / ny
    if cx > 2.0 and cy > 2.0:
        outils = []
        for i in range(nx):
            for j in range(ny):
                x = -ux / 2.0 + cx / 2.0 + i * (cx + p)
                y = -uy / 2.0 + cy / 2.0 + j * (cy + p)
                if contenu == "jetons":
                    outils.append(deplacer(cylindre(min(cx, cy), creux + 1.0),
                                           x, y, fond))
                else:
                    outils.append(deplacer(boite_3d(cx, cy, creux + 1.0), x, y, fond))
        bloc = percer(bloc, fusionner(*outils))

piece = poser_au_sol(bloc)
''',
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
    from core.neogen.objets_module import _defauts, verifier_variantes

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
                err = verifier_variantes(obj, ns)
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
