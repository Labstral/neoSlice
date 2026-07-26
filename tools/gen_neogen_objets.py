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

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VERSION = "2026-07-26b"
NOTES = "Nouveau : catégorie Calibration & tests (cube XYZ, trous, tolérance, parois, pont, retrait, 1re couche, surplombs, tour de température) + support de carte Raspberry Pi / Arduino."

# Catégories (domaines) NON natives définies par la base — permet d'ajouter une
# NOUVELLE catégorie neoGen SANS rebuild (fusionnées par catalogue.par_domaine).
DOMAINES = {
    "calibration": ("Calibration & tests", "Calibration & tests"),
}

# ── Objets à publier ────────────────────────────────────────────────────────
OBJETS = [
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
x = deplacer(tourner(extrusion(texte_2d("X", h), 4), 'x', 90), 0, -(t/2 - 1.2), t/2 - h/2)
cube = percer(cube, x)
y = deplacer(tourner(extrusion(texte_2d("Y", h), 4), 'y', 90), (t/2 - 1.2), 0, t/2 - h/2)
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
            ["pas", "Pas (incrément)", "Step", 0.5, 2, 1, 0.5],
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
        "id": "test_surplombs", "fr": "Test de surplombs", "en": "Overhang test",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "test surplomb overhang angle porte-a-faux calibration",
        "params": [["taille", "Largeur", "Width", 60, 120, 80, 5]],
        "code": r'''
Lp = taille
base = boite_3d(Lp, 26, 3)
spine = deplacer(boite_3d(8, 26, 66), -(Lp / 2 - 4), 0, 0)
corps = fusionner(base, spine)
angs = [30, 40, 50, 60, 70]
for i in range(5):
    a = angs[i]
    fin = tourner(boite_3d(30, 22, 3.5), 'y', -(90 - a))
    fin = deplacer(fin, -(Lp / 2 - 20), 0, 8 + i * 11)
    corps = fusionner(corps, fin)
piece = poser_au_sol(corps)''',
    },
    {
        "id": "tour_temp", "fr": "Tour de température", "en": "Temperature tower",
        "domaine": "calibration", "texte": "aucun",
        "synonymes": "tour temperature temp tower calibration paliers chauffe buse",
        "params": [
            ["nb", "Nombre de paliers", "Number of steps", 3, 7, 5, 1],
            ["hauteur_palier", "Hauteur d'un palier", "Step height", 8, 20, 14, 1],
        ],
        "code": r'''
n = int(nb)
hp = hauteur_palier
w = 24
corps = None
for i in range(n):
    c = w - i * 1.5
    seg = deplacer(boite_3d(c, c, hp + 0.4), 0, 0, i * hp)
    corps = seg if corps is None else fusionner(corps, seg)
    corps = fusionner(corps, deplacer(boite_3d(9, 5, 3), c / 2 - 1, 0, i * hp + hp - 3))
    corps = percer(corps, deplacer(tourner(cylindre(4, w + 6), 'x', 90), 0, 0, i * hp + hp / 2))
piece = poser_au_sol(corps)''',
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
