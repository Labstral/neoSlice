# -*- coding: utf-8 -*-
"""Les poignées de manipulation dans la vue 3D, façon Blender.

Trois modes, un seul à la fois :
  taille     les cotes vertes, une poignée à chaque bout ;
  deplacer   une flèche par axe (X rouge, Y vert, Z bleu) ;
  tourner    un cercle par axe, dans son plan.

Tout est construit dans le repère PROPRE de la forme (centre à l'origine, sans
rotation) puis placé par une transformation. Pendant un geste, on ne
reconstruit donc rien : on change la transformation, ce que la carte graphique
fait instantanément. C'est ce qui manquait pour que ça soit fluide."""
from __future__ import annotations

import numpy as np
import pyvista as pv
from vtkmodules.vtkCommonTransforms import vtkTransform

COULEUR_AXE = {0: "#E0564F", 1: "#5BC85B", 2: "#5AA2E0"}     # X, Y, Z
VERT_COTE = "#4ADE80"
TAILLE_POIGNEE = 9           # pixels
EPAISSEUR = 5                # pixels, flèches et cercles
MODES = ("taille", "deplacer", "tourner")


def rayon_cercle(demi, axe: int) -> float:
    """Rayon du cercle de rotation de l'axe donné, dans SON plan.

    Le cercle de l'axe i vit dans le plan des deux autres axes : son rayon utile
    est la demi diagonale de ce plan, plus une petite marge pour qu'il passe
    juste au dehors des coins et reste attrapable à la souris.

    Les trois cercles partaient auparavant de la PLUS GRANDE dimension de la
    pièce (× 0,8 puis + 6 mm), donc tous les trois de la même taille et bien
    plus larges que l'objet : « les cercles de rotation sont très grands par
    rapport à la pièce » (Emmanuel, 2026-09-24).
    """
    demi = [max(0.1, float(v)) for v in demi]
    u, v = ((axe + 1) % 3), ((axe + 2) % 3)
    rayon = float(np.hypot(demi[u], demi[v]))
    return max(6.0, rayon + max(2.0, rayon * 0.04))


def _axe(i: int) -> np.ndarray:
    v = np.zeros(3)
    v[i] = 1.0
    return v


def transformation(pos, rot, echelle=(1.0, 1.0, 1.0)) -> vtkTransform:
    """Place le repère de la forme dans le monde : mise à l'échelle, puis
    rotation X, Y, Z (comme le modèle), puis position."""
    t = vtkTransform()
    t.PostMultiply()
    t.Scale(float(echelle[0]), float(echelle[1]), float(echelle[2]))
    t.RotateX(float(rot[0]))
    t.RotateY(float(rot[1]))
    t.RotateZ(float(rot[2]))
    t.Translate(float(pos[0]), float(pos[1]), float(pos[2]))
    return t


class Gizmo:
    """Construit, place et désigne les poignées. Ne connaît ni la souris ni le
    projet : le viewer s'en charge."""

    def __init__(self, plotter, calque=None):
        self._plotter = plotter
        self._calque = calque        # calque de dessus : jamais masqué par la matière
        self._acteurs: list = []
        self._cibles: list[tuple] = []        # (acteur, mode, axe, point local)
        self._traits: list[tuple] = []        # (mode, axe, polyligne locale)
        self._etiquettes: list = []
        self.mode = "taille"

    # ── Construction ───────────────────────────────────────────────────────
    def montrer(self, forme, cotes_locales: list[dict], centre=None, demi=None):
        """(Re)construit les poignées pour la forme sélectionnée.

        `centre` et `demi` décrivent la matière qui RESTE après les découpes.
        Sans eux, les poignées se posaient autour de la forme d'origine : sur un
        socle coupé à 10 mm, le point d'origine restait à 15 mm de haut, soit
        10 mm au dessus de la matière (mesuré au pilote, retour d'Emmanuel).
        Les cotes, elles, arrivent DÉJÀ recentrées par `mesures`."""
        self.cacher()
        if forme is None:
            return
        demi = forme.demi_etendue() if demi is None else [float(v) for v in demi]
        taille = max(4.0, max(demi) * 2)
        base = None if centre is None else np.array(centre, float)
        if self.mode == "taille":
            self._cotes(cotes_locales)
        elif self.mode == "deplacer":
            self._fleches(taille, base)
        else:
            self._cercles(demi, base)

    def _ajouter(self, maillage, couleur, mode, axe, point=None, **kw):
        # reset_camera=False : sans ça, PyVista recadre la vue à chaque ajout et
        # la scène « saute » quand on change de mode (retour d'Emmanuel).
        acteur = self._plotter.add_mesh(maillage, color=couleur, reset_camera=False,
                                        render=False, **kw)
        self._adopter(acteur)
        self._acteurs.append(acteur)
        self._cibles.append((acteur, mode, axe, None if point is None
                             else np.array(point, float)))
        return acteur

    def _cotes(self, cotes_locales: list[dict]):
        points, cibles = [], []
        for c in cotes_locales:
            p0, p1 = np.array(c["p0"], float), np.array(c["p1"], float)
            self._ajouter(pv.MultipleLines(np.vstack([p0, p1])), VERT_COTE,
                          "taille", int(c["axe"]), None, line_width=3,
                          pickable=False)
            for point, sens in ((p1, 1), (p0, -1)):
                points.append(point)
                cibles.append((int(c["axe"]), sens, point))
            if c.get("libelle"):
                # milieu du trait + sa direction : le décalage du chiffre se
                # calcule à l'écran (voir Viewer), pas ici.
                self._etiquettes.append((np.array(c["milieu"], float),
                                         np.array(c["direction"], float),
                                         c["libelle"]))
        if points:
            acteur = self._plotter.add_points(
                np.array(points, float), color=VERT_COTE, point_size=TAILLE_POIGNEE,
                render_points_as_spheres=True, pickable=False, reset_camera=False,
                render=False)
            self._adopter(acteur)
            self._acteurs.append(acteur)
            for axe, sens, point in cibles:
                self._cibles.append((acteur, "taille", (axe, sens), point))

    def _fleches(self, taille: float, centre=None):
        """Une flèche par axe. TOUTE la tige est attrapable, pas seulement la
        pointe : en ne visant que la pointe, un clic un peu à côté partait à la
        caméra et il fallait s'y reprendre (retour d'Emmanuel)."""
        base = np.zeros(3) if centre is None else np.array(centre, float)
        longueur = taille * 0.6 + 6.0
        # Pointes DISCRÈTES et BORNÉES : proportionnelles à la pièce, elles
        # devenaient énormes et on ne voyait plus qu'elles (retour d'Emmanuel).
        hauteur = min(7.0, max(2.2, taille * 0.055))
        rayon = min(2.2, max(0.6, taille * 0.02))
        for i in range(3):
            d = _axe(i)
            tige = pv.MultipleLines(np.vstack([base, base + d * longueur]))
            acteur = self._ajouter(tige, COULEUR_AXE[i], "deplacer", i, None,
                                   line_width=EPAISSEUR, render_lines_as_tubes=True,
                                   pickable=False)
            sommet = base + d * (longueur + hauteur / 2.0)
            pointe = pv.Cone(center=sommet, direction=d, height=hauteur,
                             radius=rayon, resolution=24)
            self._ajouter(pointe, COULEUR_AXE[i], "deplacer", i, sommet,
                          pickable=False)
            # Toute la tige est visée, pas seulement des points : on mesure la
            # distance au TRAIT (voir Viewer._cible_sous_la_souris).
            self._traits.append(("deplacer", i,
                                 np.vstack([base + d * (longueur * 0.2),
                                            base + d * (longueur + taille * 0.1)])))
            del acteur

    def _cercles(self, demi, centre=None):
        """Un cercle par axe, dans son plan. Chaque cercle sème aussi des points
        de visée : sans eux, le clic ne pouvait atteindre aucun cercle et la
        rotation ne faisait rien (retour d'Emmanuel).

        Chaque cercle est dimensionné sur SON plan, au plus juste : il épouse le
        contour de la pièce vu depuis son axe, plus une petite marge pour rester
        attrapable. Tous les trois partaient de la PLUS GRANDE dimension de la
        pièce, multipliée par 0,8 puis augmentée de 6 mm, ce qui donnait des
        anneaux bien plus larges que l'objet (retour d'Emmanuel : « les cercles
        de rotation sont très grands par rapport à la pièce »). Sur une plaque
        de 90 × 80 × 8, les trois faisaient 78 mm de rayon ; ils font désormais
        62, 47 et 42, chacun collé à la silhouette qu'il fait tourner.
        """
        base = np.zeros(3) if centre is None else np.array(centre, float)
        angles = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        for i in range(3):
            rayon = rayon_cercle(demi, i)
            u, v = ((i + 1) % 3), ((i + 2) % 3)
            cercle = pv.Circle(radius=rayon, resolution=96)
            if i == 0:                       # le cercle est dans le plan XY
                cercle = cercle.rotate_y(90, inplace=False)
            elif i == 1:
                cercle = cercle.rotate_x(90, inplace=False)
            contour = cercle.extract_feature_edges(boundary_edges=True,
                                                   feature_edges=False,
                                                   manifold_edges=False,
                                                   non_manifold_edges=False)
            if float(np.linalg.norm(base)) > 1e-9:
                contour = contour.translate(base, inplace=False)
            self._ajouter(contour, COULEUR_AXE[i], "tourner", i, None,
                          line_width=EPAISSEUR, render_lines_as_tubes=True,
                          pickable=False)
            anneau = np.zeros((len(angles) + 1, 3))
            anneau[:-1, u] = rayon * np.cos(angles)
            anneau[:-1, v] = rayon * np.sin(angles)
            anneau[-1] = anneau[0]                     # on referme le cercle
            self._traits.append(("tourner", i, anneau + base))

    def _adopter(self, acteur):
        """Range l'acteur dans le calque de dessus : les cotes, leurs poignées et
        leurs chiffres restent visibles même quand une pièce passe devant
        (demande d'Emmanuel : un trait de mesure ne doit jamais être coupé)."""
        if acteur is None or self._calque is None:
            return acteur
        try:
            self._plotter.renderer.remove_actor(acteur, reset_camera=False,
                                                render=False)
            self._calque.AddActor(acteur)
        except Exception:
            pass
        return acteur

    def cacher(self):
        for a in self._acteurs:
            if self._calque is not None:
                try:
                    self._calque.RemoveActor(a)
                except Exception:
                    pass
            try:
                # render=False : sinon chaque poignée retirée déclenche une
                # image de la scène à moitié refaite (l'objet paraît sauter).
                self._plotter.remove_actor(a, render=False)
            except Exception:
                pass
        self._acteurs.clear()
        self._cibles.clear()
        self._traits.clear()
        self._etiquettes.clear()

    # ── Placement (instantané) ─────────────────────────────────────────────
    def placer(self, pos, rot, echelle=(1.0, 1.0, 1.0)):
        t = transformation(pos, rot, echelle)
        for a in self._acteurs:
            a.SetUserTransform(t)

    def points_monde(self, pos, rot, echelle=(1.0, 1.0, 1.0)) -> list[tuple]:
        """[(mode, axe, point dans le monde)] pour viser à la souris."""
        t = transformation(pos, rot, echelle)
        out = []
        for _acteur, mode, axe, point in self._cibles:
            if point is None:
                continue
            out.append((mode, axe, np.array(t.TransformPoint(*point), float)))
        return out

    def traits_monde(self, pos, rot, echelle=(1.0, 1.0, 1.0)) -> list[tuple]:
        """[(mode, axe, polyligne dans le monde)] : flèches et cercles, visés au
        trait et non par points isolés."""
        t = transformation(pos, rot, echelle)
        out = []
        for mode, axe, points in self._traits:
            monde = np.array([t.TransformPoint(*p) for p in points], float)
            out.append((mode, axe, monde))
        return out

    def etiquettes_monde(self, pos, rot, echelle=(1.0, 1.0, 1.0)) -> list[tuple]:
        """[(milieu du trait, direction du trait, texte)] dans le monde."""
        t = transformation(pos, rot, echelle)
        out = []
        for point, direction, texte in self._etiquettes:
            d = np.array(t.TransformVector(*direction), float)
            n = float(np.linalg.norm(d))
            out.append((np.array(t.TransformPoint(*point), float),
                        d / n if n > 1e-9 else np.array([0.0, 0.0, 1.0]), texte))
        return out
