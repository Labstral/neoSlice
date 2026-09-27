# -*- coding: utf-8 -*-
"""Deux retours d'Emmanuel sur la vue 3D de neoForge (2026-09-24).

1. « La perspective a changé subitement, comme si tout était très étiré. Dès que
   j'ai ajouté un autre élément ça a fait ce bug d'un seul coup. »
   Cause MESURÉE : pour reculer la caméra, le code appelait `camera.zoom(1/f)`.
   En perspective, `vtkCamera.Zoom` ne recule RIEN, il divise l'angle de vue.
   Relevé au pilote : 30° puis 60°, 120°, et le plafond de VTK à 179°, la
   distance caméra restant à 700,5 mm du début à la fin. À 179° l'image est un
   fisheye. Et comme rien ne remettait l'angle en place, l'effet s'accumulait.

2. « Les cercles de rotation sont très grands par rapport à la pièce. »
   Les trois cercles étaient dimensionnés sur la PLUS GRANDE dimension de la
   pièce, donc identiques entre eux et bien plus larges que l'objet.
"""
import numpy as np
import pytest

from neoforge.ui.gizmo import rayon_cercle
from neoforge.ui.viewer import position_reculee


# ── 1. Reculer la caméra, pour de bon ───────────────────────────────────────
def test_reculer_eloigne_vraiment_la_camera():
    pos = position_reculee((0.0, 0.0, 100.0), (0.0, 0.0, 0.0), 2.0)
    assert np.allclose(pos, (0.0, 0.0, 200.0))


def test_reculer_garde_la_direction_de_visee():
    """La vue ne doit pas pivoter : seule la distance change."""
    foyer = (10.0, -5.0, 3.0)
    depart = (110.0, 45.0, 83.0)
    for facteur in (1.5, 2.0, 4.0):
        arrivee = position_reculee(depart, foyer, facteur)
        a = np.array(depart, float) - np.array(foyer, float)
        b = np.array(arrivee, float) - np.array(foyer, float)
        assert np.allclose(b, a * facteur)
        cos = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        assert cos == pytest.approx(1.0, abs=1e-9)


def test_reculer_ne_divise_pas_par_zero():
    """Caméra confondue avec son point de visée : on ne bouge pas, on ne casse
    rien (ça arrive sur une scène vide)."""
    assert np.allclose(position_reculee((4.0, 4.0, 4.0), (4.0, 4.0, 4.0), 3.0),
                       (4.0, 4.0, 4.0))


def test_plus_aucun_zoom_de_camera_dans_neoforge():
    """Garde-fou : `camera.zoom()` est le piège qui a causé le défaut. Personne
    ne doit le réintroduire dans neoForge sans savoir ce qu'il fait."""
    import ast
    from pathlib import Path
    racine = Path(__file__).resolve().parents[1] / "neoforge"
    fautifs = []
    for f in racine.rglob("*.py"):
        arbre = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        for n in ast.walk(arbre):
            # On cherche un APPEL, pas une mention : les explications qui
            # nomment le piège dans un commentaire sont les bienvenues.
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "zoom"):
                fautifs.append(f"{f.name}:{n.lineno}")
    assert not fautifs, ("camera.zoom() élargit l'angle de vue au lieu de "
                         "reculer : " + ", ".join(fautifs))


# ── 2. Des cercles de rotation à la taille de la pièce ──────────────────────
@pytest.mark.parametrize("demi", [[45.0, 40.0, 4.0], [10.0, 10.0, 10.0],
                                  [60.0, 5.0, 5.0], [15.0, 25.0, 3.0]])
def test_cercle_epouse_son_plan(demi):
    """Chaque cercle enferme la silhouette vue depuis SON axe, sans excès : il
    passe au dehors des coins, mais de peu."""
    for axe in range(3):
        u, v = (axe + 1) % 3, (axe + 2) % 3
        coin = float(np.hypot(demi[u], demi[v]))
        r = rayon_cercle(demi, axe)
        assert r >= coin, (demi, axe)                 # visible, jamais noyé dedans
        assert r <= coin * 1.05 + 2.01, (demi, axe)   # et pas plus large que ça


def test_cercles_plus_petits_qu_avant():
    """Sur la plaque qu'Emmanuel manipulait, les trois cercles faisaient 78 mm
    de rayon. Ils descendent à 63, 47 et 42, chacun ajusté à son plan."""
    demi = [45.0, 40.0, 4.0]
    ancien = max(demi) * 2 * 0.8 + 6.0
    assert ancien == pytest.approx(78.0)
    rayons = [rayon_cercle(demi, a) for a in range(3)]
    assert rayons[0] == pytest.approx(42.2, abs=0.2)
    assert rayons[1] == pytest.approx(47.2, abs=0.2)
    assert rayons[2] == pytest.approx(62.6, abs=0.2)
    assert max(rayons) < ancien * 0.85


def test_cercles_pas_tous_identiques_sur_une_piece_plate():
    """Une pièce plate ne doit plus recevoir trois anneaux de même taille :
    c'est justement ce qui les faisait paraître énormes."""
    rayons = [rayon_cercle([45.0, 40.0, 4.0], a) for a in range(3)]
    assert max(rayons) - min(rayons) > 15.0


def test_cercle_reste_attrapable_sur_une_piece_minuscule():
    """Une pièce de 1 mm ne doit pas donner un anneau invisible."""
    assert rayon_cercle([0.5, 0.5, 0.5], 0) >= 6.0
    assert rayon_cercle([0.0, 0.0, 0.0], 2) >= 6.0
