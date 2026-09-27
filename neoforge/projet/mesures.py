# -*- coding: utf-8 -*-
"""Les cotes d'une forme : ce qu'on affiche sur la pièce dans le viewer.

Une poignée par axe réglable, mais UN SEUL chiffre quand deux côtés mesurent la
même chose (un cube de 20 n'affiche pas « 20 » trois fois). Un diamètre et une
hauteur de même valeur restent deux cotes différentes : ce ne sont pas les
mêmes mesures."""
from __future__ import annotations

from dataclasses import dataclass

from neoforge.projet.modele import Forme

MINI_COTE = 0.05        # en dessous, l'axe n'est pas réglable (pointe de cône)


@dataclass
class Cote:
    axe: int                 # 0, 1, 2 = axe local X, Y, Z de la forme
    valeur: float            # en mm
    diametre: bool           # un diamètre grandit des DEUX côtés
    libelle: str | None      # None = même mesure qu'une cote déjà écrite


def _axes_reglables(f: Forme) -> list[tuple[int, float, bool]]:
    d = f.dim
    if f.forme == "cube":
        return [(0, d[0], False), (1, d[1], False), (2, d[2], False)]
    if f.forme == "sphere":
        return [(0, d[0], True)]
    if f.forme == "cylindre":
        # Trois cotes tirables : les DEUX diamètres (le cylindre peut être
        # ovale depuis la 2.1) et la hauteur.
        return [(0, d[0], True), (1, d[1], True), (2, d[2], False)]
    if f.forme == "tore":
        return [(0, d[0], True), (1, d[1], True)]   # cercle porteur, puis tube
    if f.forme == "coin":
        return [(0, d[0], False), (1, d[1], False), (2, d[2], False)]
    if f.forme == "prisme":
        return [(0, d[0], True), (2, d[2], False)]
    if f.forme == "cadre":
        return [(0, d[0], False), (1, d[1], False), (2, d[2], False)]
    if f.forme == "anneau":
        return [(0, d[0], True), (1, d[1], True), (2, d[2], False)]
    if f.forme == "engrenage":
        return [(0, d[0], False), (1, d[1], False), (2, d[2], False)]
    if f.forme == "taraudage":
        # Le diamètre est celui de la visserie : on ne le tire pas à la souris,
        # sinon le trou ne reçoit plus aucune vis normalisée. Seule la
        # PROFONDEUR se règle dans la vue.
        return [(2, d[2], False)]
    return [(0, d[0], True), (1, d[1], True), (2, d[2], False)]     # cône


def echelle_apercu(f: Forme, dim_base) -> tuple[float, float, float] | None:
    """Mise à l'échelle à appliquer à l'aperçu déjà construit, ou None s'il faut
    le reconstruire.

    Les dimensions d'une forme ne sont PAS des longueurs selon ses trois axes :
    pour un cylindre, dim[0] est un diamètre qui vaut pour X et pour Y ; pour un
    cône, dim[1] est le diamètre du HAUT. Mettre à l'échelle les axes avec les
    dimensions brutes déformait le cylindre en ovale et écrasait complètement un
    cône pointu, dont le diamètre du haut vaut zéro (retour d'Emmanuel)."""
    brut = [float(v) for v in dim_base]
    # Diviser par zéro n'a pas de sens, mais COMPARER à zéro si : le diamètre du
    # haut d'un cône pointu vaut 0, et le confondre avec 1 faisait croire à un
    # changement de forme à chaque pas.
    b = [v if abs(v) > 1e-9 else 1.0 for v in brut]
    d = [float(v) for v in f.dim]
    if f.forme == "cube":
        return (d[0] / b[0], d[1] / b[1], d[2] / b[2])
    if f.forme == "sphere":
        k = d[0] / b[0]
        return (k, k, k)
    if f.forme == "prisme":
        k = d[0] / b[0]
        return (k, k, d[2] / b[2])
    if f.forme == "cylindre":
        # Ovale : chaque diamètre porte son propre axe, l'aperçu se met donc à
        # l'échelle axe par axe comme pour un pavé.
        return (d[0] / b[0], d[1] / b[1], d[2] / b[2])
    if f.forme == "coin":
        return (d[0] / b[0], d[1] / b[1], d[2] / b[2])
    if f.forme in ("cadre", "anneau"):
        # Mettre le contour à l'échelle épaissirait aussi son bord, qui doit
        # justement rester à la cote demandée : on refait l'aperçu.
        return None
    if f.forme == "engrenage":
        # Les dents suivent la boîte : la mise à l'échelle est fidèle.
        return (d[0] / b[0], d[1] / b[1], d[2] / b[2])
    if f.forme == "taraudage":
        # Un filetage coûte une à six secondes à construire : hors de question
        # de le refaire à chaque pixel pendant qu'on tire la profondeur.
        # L'aperçu s'étire donc en hauteur, et le vrai pas revient au
        # relâchement. Le diamètre, lui, ne bouge jamais.
        return (1.0, 1.0, d[2] / b[2])
    if f.forme == "tore":
        # Le cercle porteur et le tube sont indépendants : aucune mise à
        # l'échelle ne les représente, on refait l'aperçu.
        return None if (abs(d[0] - brut[0]) > 1e-9 or abs(d[1] - brut[1]) > 1e-9) \
            else (1.0, 1.0, 1.0)
    # Cône : les deux diamètres sont indépendants, aucune mise à l'échelle ne
    # peut les représenter. Seule une hauteur qui change se rattrape.
    if abs(d[0] - brut[0]) < 1e-9 and abs(d[1] - brut[1]) < 1e-9:
        return (1.0, 1.0, d[2] / b[2])
    return None


def est_diametre(f: Forme, axe: int) -> bool:
    return any(a == axe and diam for a, _v, diam in _axes_reglables(f))


def geometrie_cotes_locale(f: Forme, marge: float | None = None,
                           demi=None, centre=None) -> list[dict]:
    """Cotes dans le repère PROPRE de la forme (centre à l'origine, sans
    rotation) : c'est ce repère qu'on transforme d'un bloc pendant un geste,
    sans rien recalculer.

    Chaque cote est DÉPORTÉE hors de la pièce, le long d'une arête de sa boîte,
    comme sur un plan coté : sinon les poignées se posent au milieu des faces et
    on ne peut plus attraper la pièce pour la déplacer."""
    import numpy as np

    # `demi` et `centre` permettent de suivre la matière qui RESTE après une
    # découpe. Sans eux, les cotes et leurs poignées se posaient autour de la
    # forme ENTIÈRE, donc en partie dans le vide, et le point d'origine ne
    # bougeait pas d'un millimètre après une coupe (retour d'Emmanuel).
    demi = f.demi_etendue() if demi is None else [float(v) for v in demi]
    origine = np.zeros(3) if centre is None else np.array(centre, float)
    if marge is None:
        marge = max(1.5, 0.12 * max(demi) * 2)
    out = []
    for c in cotes(f):
        direction = np.zeros(3)
        direction[c.axe] = 1.0
        decalage = np.array(origine, float)
        for a in ((c.axe + 1) % 3, (c.axe + 2) % 3):     # on sort par le coin
            decalage[a] = origine[a] + demi[a] + marge * 0.7
        demi_longueur = direction * (c.valeur / 2.0)
        # Le chiffre se pose au milieu de SA cote, écarté STRICTEMENT
        # perpendiculairement au trait : décaler le long de la diagonale du coin
        # le faisait glisser sur la ligne (0 pixel d'écart mesuré), et le mettre
        # au bout des cotes faisait se chevaucher les chiffres entre eux.
        # L'écart se mesure depuis le CENTRE, sinon un centre décalé le fausse.
        ecart = decalage - origine
        perpendiculaire = ecart - direction * float(np.dot(ecart, direction))
        norme = float(np.linalg.norm(perpendiculaire))
        if norme < 1e-9:
            perpendiculaire, norme = np.array([0.0, 0.0, 1.0]), 1.0
        etiquette = decalage + perpendiculaire / norme * (marge * 1.6)
        out.append({"axe": c.axe, "p0": (decalage - demi_longueur).tolist(),
                    "p1": (decalage + demi_longueur).tolist(),
                    "milieu": decalage.tolist(), "etiquette": etiquette.tolist(),
                    "libelle": c.libelle, "direction": direction.tolist()})
    return out


def geometrie_cotes(f: Forme, marge: float | None = None) -> list[dict]:
    """Les mêmes cotes, placées dans le monde (rotation et position de la forme)."""
    import numpy as np

    from neoforge.projet.ergonomie import direction_axe
    base = np.array([direction_axe(f, a) for a in range(3)], float)   # lignes = axes
    centre = np.array(f.pos, float)
    out = []
    for c in geometrie_cotes_locale(f, marge):
        monde = {cle: (np.array(c[cle], float) @ base + centre).tolist()
                 for cle in ("p0", "p1", "milieu", "etiquette")}
        monde["direction"] = (np.array(c["direction"], float) @ base).tolist()
        monde["axe"], monde["libelle"] = c["axe"], c["libelle"]
        out.append(monde)
    return out


def cotes(f: Forme) -> list[Cote]:
    """Cotes à afficher, dans l'ordre des axes."""
    from neoforge.projet import unites as U
    unite = U.courante()
    out: list[Cote] = []
    deja: set[tuple[float, bool]] = set()
    for axe, valeur, diam in _axes_reglables(f):
        if valeur < MINI_COTE:
            continue                       # rien à tirer sur une pointe
        cle = (round(float(valeur), 3), diam)
        premiere = cle not in deja
        deja.add(cle)
        # Le chiffre gravé sur la cote suit l'unité choisie : la place manque
        # dans la vue, d'où la forme courte (« 30 » et non « 30,0 »).
        libelle = ((("Ø" if diam else "") + U.court(valeur, unite))
                   if premiere else None)
        out.append(Cote(axe, float(valeur), diam, libelle))
    return out
