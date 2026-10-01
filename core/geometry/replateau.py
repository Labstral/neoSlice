# -*- coding: utf-8 -*-
"""Réorganiser les pièces d'un projet sur le moins de plateaux possible.

Moteur PUR (aucun Qt, aucun trimesh) : à partir de l'empreinte au sol de
chaque pièce et des dimensions du plateau de l'imprimante choisie, décide sur
quel plateau chaque pièce va et où elle se pose dessus.

Demandé par eleovna BERGES (Elegoo Neptune 4 Max, 2026-10-01) : « il serait
judicieux que le logiciel tienne compte du plateau dans la répartition des
éléments par plateau sur un projet volumineux ». À l'import, neoSlice
respectait les plateaux déclarés dans le fichier, même quand ils venaient
d'une machine deux fois plus petite que la sienne.

Le rangement est un PAVAGE PAR RANGÉES : les pièces sont posées de gauche à
droite sur une rangée dont la hauteur est celle de la plus haute pièce qu'elle
contient, puis on descend d'une rangée, puis on ouvre un plateau. Les pièces
sont triées de la plus profonde à la moins profonde, ce qui évite les rangées
à moitié vides. C'est la méthode classique du rangement en rayonnages, elle
donne un résultat proche de l'optimum sans être imprévisible.

Choix assumés :
  * AUCUNE rotation. Faire pivoter une pièce gagnerait quelques pourcents mais
    l'utilisateur retrouverait ses pièces tournées sans l'avoir demandé, et
    une pièce orientée exprès (surplombs, résistance) serait abîmée.
  * Les pièces TROP GRANDES pour le plateau ne sont pas écartées en silence :
    elles sont rendues à part pour que l'appelant le dise franchement.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.geometry.serie import ESPACEMENT_MM, MARGE_MM


@dataclass(frozen=True)
class Pose:
    """Où atterrit une pièce : son plateau et sa translation en XY (mm).

    `dx`/`dy` sont à AJOUTER à la position actuelle de la pièce. Le centre du
    groupe de chaque plateau est ramené sur (0, 0) : l'écrivain 3MF recentre
    ensuite chaque groupe sur le plateau physique, en préservant les positions
    relatives, exactement comme pour une série.
    """
    id: str
    plateau: int
    dx: float
    dy: float


@dataclass(frozen=True)
class Plan:
    poses: list[Pose]
    trop_grandes: list[str]          # ids des pièces plus grandes que le plateau
    plateaux: int                    # nombre de plateaux utilisés

    @property
    def utile(self) -> bool:
        return bool(self.poses)


def repartir(pieces: list[tuple[str, float, float, float, float]],
             bed_xy: tuple[float, float],
             marge: float = MARGE_MM,
             espacement: float = ESPACEMENT_MM) -> Plan:
    """Range `pieces` sur des plateaux de `bed_xy` mm.

    `pieces` : liste de (id, xmin, ymin, xmax, ymax), l'empreinte au sol
    ACTUELLE de chaque pièce, dans le repère du projet. On en déduit sa taille
    et de combien la déplacer.

    Les pièces plus grandes que le plateau utile sont listées dans
    `trop_grandes` et ne reçoivent aucune pose : à l'appelant de le dire.
    """
    utile_x = float(bed_xy[0]) - 2 * marge
    utile_y = float(bed_xy[1]) - 2 * marge
    if utile_x <= 0 or utile_y <= 0:
        return Plan(poses=[], trop_grandes=[p[0] for p in pieces], plateaux=0)

    trop_grandes, a_ranger = [], []
    for pid, x0, y0, x1, y1 in pieces:
        w, h = float(x1 - x0), float(y1 - y0)
        if w > utile_x or h > utile_y:
            trop_grandes.append(pid)
        else:
            a_ranger.append((pid, x0, y0, w, h))

    # La plus PROFONDE d'abord : une rangée coûte la hauteur de sa plus haute
    # pièce, donc mélanger les hauteurs gaspille. À profondeur égale, la plus
    # large d'abord. L'id départage pour que deux exécutions donnent le MÊME
    # résultat (sinon l'aperçu changerait d'un clic à l'autre).
    a_ranger.sort(key=lambda t: (-t[4], -t[3], t[0]))

    brutes: list[tuple[str, int, float, float, float, float]] = []
    plateau = 0
    rangee_y = 0.0        # bas de la rangée courante
    rangee_h = 0.0        # hauteur de la rangée courante
    curseur_x = 0.0       # bord gauche libre sur la rangée courante

    for pid, x0, y0, w, h in a_ranger:
        if curseur_x > 0 and curseur_x + w > utile_x + 1e-9:
            # Rangée pleine → on descend.
            rangee_y += rangee_h + espacement
            curseur_x, rangee_h = 0.0, 0.0
        if rangee_y + h > utile_y + 1e-9:
            # Plateau plein → on en ouvre un.
            plateau += 1
            rangee_y, rangee_h, curseur_x = 0.0, 0.0, 0.0
        brutes.append((pid, plateau, curseur_x, rangee_y, w, h))
        curseur_x += w + espacement
        rangee_h = max(rangee_h, h)

    # Chaque plateau est ramené autour de (0, 0) : l'écrivain 3MF centre le
    # groupe sur le plateau physique et garde les positions relatives.
    par_plateau: dict[int, list] = {}
    for item in brutes:
        par_plateau.setdefault(item[1], []).append(item)

    origines = {p[0]: (p[1], p[2]) for p in
                [(pid, x0, y0) for pid, x0, y0, _w, _h in a_ranger]}

    poses: list[Pose] = []
    for p in sorted(par_plateau):
        items = par_plateau[p]
        gx = (min(i[2] for i in items) + max(i[2] + i[4] for i in items)) / 2
        gy = (min(i[3] for i in items) + max(i[3] + i[5] for i in items)) / 2
        for pid, _pl, px, py, _w, _h in items:
            x0, y0 = origines[pid]
            poses.append(Pose(id=pid, plateau=p,
                              dx=(px - gx) - x0, dy=(py - gy) - y0))

    poses.sort(key=lambda q: (q.plateau, q.id))
    return Plan(poses=poses, trop_grandes=trop_grandes,
                plateaux=(max(par_plateau) + 1 if par_plateau else 0))


def gain(avant: int, plan: Plan) -> int:
    """Plateaux économisés, 0 si la réorganisation n'apporte rien."""
    return max(0, int(avant) - plan.plateaux) if plan.utile else 0
