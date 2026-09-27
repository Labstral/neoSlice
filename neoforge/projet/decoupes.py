# -*- coding: utf-8 -*-
"""Ce qu'une découpe retire, vu depuis une étape.

Le noyau applique les coupes à la pièce ENTIÈRE, dans l'ordre des étapes. Mais
l'aperçu de manipulation, les poignées et le clic travaillent forme par forme,
sur la PRIMITIVE : ne sachant rien des coupes qui suivent, ils montraient encore
la moitié retirée, invisible dans la pièce mais bien peinte en surbrillance, et
le clic tombait dessus (retour d'Emmanuel : « quand on clique sur la moitié, on
voit encore toute l'autre moitié en invisible qui apparaît et qui crée une box
de collision très pénible »).

Ce module dit, pour une étape donnée, quels demi-espaces la rognent, et où ils
passent dans son repère propre. Géométrie pure : aucun noyau, aucun Qt."""
from __future__ import annotations

from neoforge.projet.modele import Coupe, Forme


def coupes_apres(projet, index: int) -> list[Coupe]:
    """Les découpes actives qui s'appliquent APRÈS l'étape `index`, donc les
    seules qui rognent la forme de cette étape : celles d'avant ont été faites
    quand cette forme n'existait pas encore."""
    etapes = getattr(projet, "etapes", projet)
    return [e for k, e in enumerate(etapes)
            if k > index and isinstance(e, Coupe) and getattr(e, "actif", True)]


def plans_locaux(f: Forme, coupes) -> list[tuple[list[float], list[float]]]:
    """(normale, point du plan) dans le repère PROPRE de la forme, une entrée par
    coupe qui rogne vraiment (« garder les deux » ne retire rien).

    La normale pointe vers la matière CONSERVÉE : c'est la convention de
    `clip_closed_surface`, mesurée au pilote. Passage du repère propre au monde :
    `monde[axe] = Σ_k local[k]·base[k][axe] + centre[axe]`, donc l'axe du monde
    se lit dans le repère propre comme le vecteur `u[k] = base[k][axe]`. La base
    étant orthonormée, `u` est unitaire et `u·seuil` est un point du plan."""
    from neoforge.projet.ergonomie import direction_axe

    base = [direction_axe(f, k) for k in range(3)]        # lignes = axes propres
    out = []
    for c in coupes:
        if c.garder == "les_deux":
            continue
        axe = int(c.axe)
        u = [float(base[k][axe]) for k in range(3)]
        seuil = float(c.position) - float(f.pos[axe])
        signe = 1.0 if c.garder == "dessus" else -1.0
        out.append(([signe * v for v in u], [v * seuil for v in u]))
    return out


def quadrilatere(axe: int, position: float, boite, marge: float = 6.0):
    """Le carré à dessiner pour MONTRER le plan de coupe : (centre, direction,
    côté 1, côté 2), déduits de la boîte de la pièce.

    Un plan est mathématiquement infini ; à l'écran il doit rester lisible, donc
    on le borne à la pièce, en débordant d'une petite marge pour qu'on voie bien
    qu'il la traverse de part en part (demande d'Emmanuel : « j'aimerais qu'on
    puisse voir le plan de coupe »)."""
    axe = int(axe)
    bas, haut = boite
    centre = [(float(bas[k]) + float(haut[k])) / 2.0 for k in range(3)]
    centre[axe] = float(position)
    autres = [k for k in range(3) if k != axe]
    cotes = [max(4.0, float(haut[k]) - float(bas[k]) + 2.0 * float(marge))
             for k in autres]
    direction = [1.0 if k == axe else 0.0 for k in range(3)]
    return centre, direction, cotes[0], cotes[1]


def retiree_par(point, coupe: Coupe, tolerance: float = 0.0) -> bool:
    """Vrai si ce point du monde tombe dans la moitié RETIRÉE par la coupe."""
    if coupe.garder == "les_deux":
        return False
    v, p = float(point[int(coupe.axe)]), float(coupe.position)
    return v > p + tolerance if coupe.garder == "dessous" else v < p - tolerance


def sur_le_plan(point, coupe: Coupe, tolerance: float) -> bool:
    """Vrai si le point tombe sur la face NUE ouverte par la coupe. Cette face
    n'appartient à aucune surface de la primitive : sans ce test, cliquer le
    dessus tout plat d'une pièce coupée ne sélectionnait rien, car la face la
    plus proche de la primitive pouvait se trouver à quinze millimètres."""
    if coupe.garder == "les_deux":
        return False
    return abs(float(point[int(coupe.axe)]) - float(coupe.position)) <= tolerance


def sans_ecart(point, coupes) -> list[float]:
    """Ramène un point cliqué sur la pièce là où se trouve la PRIMITIVE.

    « Garder les deux » écarte le morceau du haut de `ECART_COUPE` : un clic
    dessus tombait donc à deux millimètres de la forme d'origine, pour une
    tolérance de sélection d'un millimètre, et cette moitié n'était
    sélectionnable par aucun clic."""
    from neoforge.noyau.construction import ECART_COUPE

    p = [float(v) for v in point]
    for c in coupes:
        if c.garder != "les_deux":
            continue
        axe = int(c.axe)
        if p[axe] > float(c.position) + ECART_COUPE / 2.0:
            p[axe] -= ECART_COUPE
    return p
