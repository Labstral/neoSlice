# -*- coding: utf-8 -*-
"""Les gestes de la console, portés tels quels (sans noyau, sur les boîtes
englobantes des formes) :

  collage       une pièce de matière qui avance s'arrête à fleur des autres
                pièces de matière et du plateau ; un creux traverse tout ;
  poser         fait tomber la pièce sur ce qu'il y a dessous, sinon le plateau ;
  centrer       centre la pièce sur celle du dessous (ou sur le plateau) ;
  à côté        une nouvelle pièce se pose à droite de la sélection.
"""
from __future__ import annotations

import math

from neoforge.projet.modele import Forme, Projet  # noqa: F401  (Projet : annotations)


def coins(f: Forme) -> list[tuple[float, float, float]]:
    """Les huit sommets de la boîte englobante, après rotation (X, Y puis Z)."""
    ex, ey, ez = f.demi_etendue()
    cr = [math.radians(a) for a in f.rot]
    cx, sx = math.cos(cr[0]), math.sin(cr[0])
    cy, sy = math.cos(cr[1]), math.sin(cr[1])
    cz, sz = math.cos(cr[2]), math.sin(cr[2])
    out = []
    for i in range(8):
        x = ex if i & 1 else -ex
        y = ey if i & 2 else -ey
        z = ez if i & 4 else -ez
        y, z = y * cx - z * sx, y * sx + z * cx
        x, z = x * cy + z * sy, -x * sy + z * cy
        x, y = x * cz - y * sz, x * sz + y * cz
        out.append((x + f.pos[0], y + f.pos[1], z + f.pos[2]))
    return out


def direction_axe(f: Forme, axe: int) -> tuple[float, float, float]:
    """Direction, dans le monde, de l'axe local `axe` de la forme (elle suit sa
    rotation X puis Y puis Z)."""
    cr = [math.radians(a) for a in f.rot]
    cx, sx = math.cos(cr[0]), math.sin(cr[0])
    cy, sy = math.cos(cr[1]), math.sin(cr[1])
    cz, sz = math.cos(cr[2]), math.sin(cr[2])
    x, y, z = (1.0 if axe == 0 else 0.0, 1.0 if axe == 1 else 0.0, 1.0 if axe == 2 else 0.0)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return (x, y, z)


MINI_DIM = 0.5


def redimensionner(f: Forme, axe: int, delta: float, sens: int = 1) -> float:
    """Tire un côté de la forme de `delta` mm (mesuré sur la face tirée).

    Un côté droit garde sa face OPPOSÉE immobile : seule la face tirée bouge,
    comme quand on étire une boîte. Un DIAMÈTRE grandit des deux côtés à la
    fois, le centre ne bouge pas. Renvoie la variation réellement appliquée
    (bornée par la taille minimale)."""
    from neoforge.projet.mesures import est_diametre
    diametre = est_diametre(f, axe)
    ancienne = float(f.dim[axe])
    variation = 2 * delta if diametre else delta
    nouvelle = max(MINI_DIM, ancienne + variation)
    applique = nouvelle - ancienne
    f.dim[axe] = nouvelle
    if not diametre:
        d = direction_axe(f, axe)
        for k in range(3):
            f.pos[k] += d[k] * sens * applique / 2.0
    if f.forme == "sphere":
        f.dim[1] = f.dim[2] = f.dim[0]
    elif getattr(f, "lien_xy", False) and axe in (0, 1):
        # Cadenas fermé : largeur et profondeur restent égales, la pièce garde
        # sa rondeur (demande d'Emmanuel, « comme sur la plupart des logiciels »).
        f.dim[1 - axe] = f.dim[axe]
    # ⚠️ Le cylindre recopiait ici dim[0] dans dim[1], parce que son second
    # diamètre ne se réglait pas et que la boîte englobante serait restée
    # périmée. Depuis la 2.1 il a DEUX diamètres réglables : recopier
    # annulerait l'ovale dès qu'on tire une poignée.
    return applique


def matrice_rotation(rot) -> list[list[float]]:
    """Matrice de la rotation d'une forme : X, puis Y, puis Z (M = Rz·Ry·Rx)."""
    a, b, c = (math.radians(float(v)) for v in rot)
    ca, sa, cb, sb, cc, sc = (math.cos(a), math.sin(a), math.cos(b),
                              math.sin(b), math.cos(c), math.sin(c))
    return [[cb * cc, sa * sb * cc - ca * sc, ca * sb * cc + sa * sc],
            [cb * sc, sa * sb * sc + ca * cc, ca * sb * sc - sa * cc],
            [-sb, sa * cb, ca * cb]]


def matrice_autour(axe_monde, degres: float) -> list[list[float]]:
    """Rotation d'un angle autour d'une direction quelconque (Rodrigues)."""
    x, y, z = axe_monde
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    a = math.radians(float(degres))
    c, s, u = math.cos(a), math.sin(a), 1 - math.cos(a)
    return [[c + x * x * u, x * y * u - z * s, x * z * u + y * s],
            [y * x * u + z * s, c + y * y * u, y * z * u - x * s],
            [z * x * u - y * s, z * y * u + x * s, c + z * z * u]]


def _produit(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def angles_depuis_matrice(M) -> list[float]:
    """Angles X, Y, Z (degrés) d'une matrice, dans la convention des formes."""
    if abs(M[2][0]) > 0.999999:                     # axes alignés : on fixe X
        b = math.copysign(math.pi / 2, -M[2][0])
        return [0.0, math.degrees(b), math.degrees(math.atan2(-M[0][1], M[1][1]))]
    b = math.asin(max(-1.0, min(1.0, -M[2][0])))
    a = math.atan2(M[2][1], M[2][2])
    c = math.atan2(M[1][0], M[0][0])
    return [round(math.degrees(v) % 360.0, 3) for v in (a, b, c)]


def se_touchent(a: Forme, b: Forme, tol: float = 0.05) -> bool:
    """Deux formes se touchent-elles (contact ou recouvrement) ?"""
    ami, ama = boite(a)
    bmi, bma = boite(b)
    return all(min(ama[k], bma[k]) - max(ami[k], bmi[k]) >= -tol for k in range(3))


def enfants(projet: Projet, i: int) -> list[int]:
    """Index des formes directement rattachées à la forme i."""
    base = projet.etapes[i] if 0 <= i < len(projet.etapes) else None
    if not isinstance(base, Forme) or not base.ident:
        return []
    return [k for k, e in enumerate(projet.etapes)
            if isinstance(e, Forme) and e.parent == base.ident]


def descendants(projet: Projet, i: int) -> list[int]:
    """Toute la descendance de la forme i, enfants des enfants compris."""
    out: list[int] = []
    a_voir = [i]
    while a_voir:
        for k in enfants(projet, a_voir.pop()):
            if k != i and k not in out:
                out.append(k)
                a_voir.append(k)
    return sorted(out)


def groupe(projet: Projet, i: int) -> list[int]:
    """La forme i ET sa descendance : ce qui ne fait qu'un quand on la déplace
    ou qu'on la tourne.

    Choix d'Emmanuel (2026-09-12) : le lien est EXPLICITE, parent et enfants,
    et non un collage automatique dès que deux faces se touchent. Avec un
    collage automatique, on ne pourrait plus ajuster une petite pièce contre
    une grande sans emmener la grande avec elle."""
    return [i] + descendants(projet, i)


def peut_recevoir(projet: Projet, enfant: int, parent: int) -> bool:
    """Peut-on rattacher `enfant` à `parent` ? Pas à soi même, et pas à sa
    propre descendance : cela ferait une boucle sans fin."""
    if enfant == parent:
        return False
    if not (0 <= enfant < len(projet.etapes) and 0 <= parent < len(projet.etapes)):
        return False
    if not (isinstance(projet.etapes[enfant], Forme)
            and isinstance(projet.etapes[parent], Forme)):
        return False
    return parent not in descendants(projet, enfant)


def rattacher(projet: Projet, enfant: int, parent: int | None) -> bool:
    """Rattache une forme à une autre, ou la détache (`parent` à None)."""
    if not (0 <= enfant < len(projet.etapes)):
        return False
    forme = projet.etapes[enfant]
    if not isinstance(forme, Forme):
        return False
    if parent is None:
        forme.parent = ""
        return True
    if not peut_recevoir(projet, enfant, parent):
        return False
    forme.parent = projet.etapes[parent].ident
    return True


def cible_du_geste(projet: Projet, i: int) -> int:
    """Sur QUELLE pièce le geste s'applique vraiment.

    Une pièce VERROUILLÉE et rattachée ne bouge plus toute seule : le geste
    remonte à son parent, et c'est donc tout l'ensemble qui se déplace ou qui
    tourne (demande d'Emmanuel : « si l'enfant est bloqué, même en le tournant
    c'est tout le parent qui se met à bouger »). On remonte tant que la chaîne
    reste verrouillée."""
    place = {e.ident: k for k, e in enumerate(projet.etapes) if isinstance(e, Forme)}
    vus: set[int] = set()
    while 0 <= i < len(projet.etapes) and i not in vus:
        f = projet.etapes[i]
        if not isinstance(f, Forme) or not f.verrou or not f.parent:
            return i
        vus.add(i)
        parent = place.get(f.parent)
        if parent is None:
            return i
        i = parent
    return i


def _ordonner(formes: list) -> list:
    """Profondeur d'abord : les pièces libres dans leur ordre, chacune suivie de
    sa descendance."""
    par_id = {f.ident: f for f in formes}
    enfants_de: dict[str, list] = {}
    racines = []
    for f in formes:
        if f.parent and f.parent in par_id:
            enfants_de.setdefault(f.parent, []).append(f)
        else:
            racines.append(f)
    sortie: list = []

    def poser(f, vus: set):
        if f.ident in vus:
            return
        vus.add(f.ident)
        sortie.append(f)
        for enfant in enfants_de.get(f.ident, []):
            poser(enfant, vus)

    vus: set = set()
    for f in racines:
        poser(f, vus)
    for f in formes:                      # garde fou : personne ne disparaît
        if f.ident not in vus:
            sortie.append(f)
    return sortie


def ranger_hierarchie(projet: Projet) -> None:
    """Range la pile pour que CHAQUE pièce soit suivie de sa descendance.

    À appliquer après tout changement de lien : ne ranger qu'au rattachement
    laissait, quand on détachait un enfant du milieu, une pièce étrangère coincée
    entre le parent et ses autres enfants (retour d'Emmanuel).

    Les arrondis servent de FRONTIÈRES : un arrondi s'applique à tout ce qui le
    précède, déplacer une forme par dessus changerait donc la pièce."""
    sortie: list = []
    segment: list = []
    for e in projet.etapes:
        if isinstance(e, Forme):
            segment.append(e)
        else:
            sortie.extend(_ordonner(segment))
            sortie.append(e)
            segment = []
    sortie.extend(_ordonner(segment))
    projet.etapes[:] = sortie


def profondeur(projet: Projet, i: int) -> int:
    """Nombre de parents au dessus de la forme i, pour l'affichage en retrait."""
    par_id = {e.ident: e for e in projet.etapes if isinstance(e, Forme)}
    e = projet.etapes[i] if 0 <= i < len(projet.etapes) else None
    n, vus = 0, set()
    while isinstance(e, Forme) and e.parent and e.parent in par_id:
        if e.parent in vus:
            break
        vus.add(e.parent)
        e = par_id[e.parent]
        n += 1
    return n


def _translater(projet: Projet, indices, vecteur) -> None:
    for k in indices:
        f = projet.etapes[k]
        for axe in range(3):
            f.pos[axe] += vecteur[axe]


def tourner_groupe(projet: Projet, i: int, axe_monde, degres: float) -> list[int]:
    """Fait tourner la forme i ET tout ce qui lui est collé, autour du centre de
    la forme i. Un trou percé dans une pièce tourne donc avec elle (demande
    d'Emmanuel). Renvoie les index déplacés."""
    base = projet.etapes[i]
    if not isinstance(base, Forme) or abs(float(degres)) < 1e-9:
        return []
    W = matrice_autour(axe_monde, degres)
    pivot = list(base.pos)
    touches = groupe(projet, i)
    for k in touches:
        f = projet.etapes[k]
        d = [f.pos[axe] - pivot[axe] for axe in range(3)]
        f.pos[:] = [pivot[axe] + sum(W[axe][c] * d[c] for c in range(3))
                    for axe in range(3)]
        f.rot[:] = angles_depuis_matrice(_produit(W, matrice_rotation(f.rot)))
    return touches


def boite(f: Forme) -> tuple[list[float], list[float]]:
    c = coins(f)
    return ([min(p[i] for p in c) for i in range(3)],
            [max(p[i] for p in c) for i in range(3)])


def _est_matiere(projet: Projet, i: int) -> bool:
    """La première forme active est toujours de la matière (comme la console)."""
    f = projet.etapes[i]
    if not isinstance(f, Forme) or not f.actif:
        return False
    premiere = next((k for k, e in enumerate(projet.etapes)
                     if isinstance(e, Forme) and e.actif), None)
    return i == premiere or f.op == "matiere"


def limiter(projet: Projet, i: int, axe: int, delta: float,
            collage: bool = True, force: bool = False, ignorer=None) -> float:
    """Déplacement réellement possible de la forme i le long d'un axe, arrêté à
    fleur des autres pièces de matière et du plateau (z ≥ 0)."""
    if delta == 0.0 or (not force and not collage):
        return delta
    if not _est_matiere(projet, i):
        return delta                           # un creux traverse tout, c'est son rôle
    mini, maxi = boite(projet.etapes[i])
    d = delta
    for k, autre in enumerate(projet.etapes):
        # `ignorer` : les pièces qui VOYAGENT avec celle ci ne doivent pas lui
        # barrer la route, sinon un enfant posé contre son parent bloquerait
        # tout mouvement dès le premier millimètre.
        if k == i or (ignorer and k in ignorer) or not _est_matiere(projet, k):
            continue
        ami, ama = boite(autre)
        if any(min(maxi[a], ama[a]) - max(mini[a], ami[a]) <= 0.01
               for a in range(3) if a != axe):
            continue                           # pas en face sur cet axe
        if d > 0 and maxi[axe] <= ami[axe] + 0.001:
            d = min(d, ami[axe] - maxi[axe])
        elif d < 0 and mini[axe] >= ama[axe] - 0.001:
            d = max(d, ama[axe] - mini[axe])
    if axe == 2 and d < 0 and mini[2] >= -0.001:
        d = max(d, -mini[2])
    return d


def deplacer_selon(projet: Projet, i: int, direction, distance: float,
                   collage: bool = True) -> float:
    """Déplace la forme i le long d'une direction QUELCONQUE : celle de la
    flèche, qui est l'axe propre de la pièce et tourne donc avec elle.

    Ajouter la distance à `pos[axe]` revenait à pousser la pièce le long de
    l'axe du MONDE alors que la flèche pointait ailleurs : dès qu'une pièce
    était orientée, elle partait de travers (retour d'Emmanuel). Le collage est
    conservé : on regarde ce que chaque composante a le droit de parcourir et on
    garde la plus contraignante, pour ne pas dévier de la flèche."""
    n = math.sqrt(sum(c * c for c in direction)) or 1.0
    u = [c / n for c in direction]
    ensemble = groupe(projet, i)          # la pièce ET tout ce qui lui pend
    part = 1.0
    for axe in range(3):
        voulu = u[axe] * distance
        if abs(voulu) < 1e-9:
            continue
        part = min(part, limiter(projet, i, axe, voulu, collage,
                                 ignorer=set(ensemble)) / voulu)
    part = max(0.0, min(1.0, part))
    reel = distance * part
    _translater(projet, ensemble, [c * reel for c in u])
    return reel


def poser(projet: Projet, i: int) -> str:
    """Fait tomber la forme i. Renvoie « plateau », « piece » ou « creux »."""
    f = projet.etapes[i]
    ensemble = groupe(projet, i)
    if not _est_matiere(projet, i):
        _translater(projet, ensemble,           # un creux est ramené au plateau
                    [0.0, 0.0, f.demi_etendue()[2] - f.pos[2]])
        return "creux"
    _translater(projet, ensemble,
                [0.0, 0.0, limiter(projet, i, 2, -10000.0, force=True,
                                   ignorer=set(ensemble))])
    return "plateau" if abs(boite(f)[0][2]) < 0.01 else "piece"


def piece_dessous(projet: Projet, i: int) -> Forme | None:
    """La pièce de matière sur laquelle celle-ci repose, ou celle qu'elle recouvre le plus."""
    mini, maxi = boite(projet.etapes[i])
    poses, recouvre = [], []
    for k, autre in enumerate(projet.etapes):
        if k == i or not _est_matiere(projet, k):
            continue
        ami, ama = boite(autre)
        r = min(min(maxi[0], ama[0]) - max(mini[0], ami[0]),
                min(maxi[1], ama[1]) - max(mini[1], ami[1]))
        if r <= 0.01:
            continue
        if ama[2] <= mini[2] + 1.0:
            poses.append((ama[2], r, autre))
        else:
            recouvre.append((r, autre))
    if poses:
        return max(poses, key=lambda c: (c[0], c[1]))[2]
    if recouvre:
        return max(recouvre, key=lambda c: c[0])[1]
    return None


def centrer(projet: Projet, i: int) -> str:
    """Centre la forme i sur la pièce du dessous (ou sur le plateau)."""
    f = projet.etapes[i]
    cible = piece_dessous(projet, i)
    mini, maxi = boite(f)
    if cible is None:
        vx = vy = 0.0
    else:
        cmi, cma = boite(cible)
        vx, vy = (cmi[0] + cma[0]) / 2, (cmi[1] + cma[1]) / 2
    _translater(projet, groupe(projet, i),
                [vx - (mini[0] + maxi[0]) / 2, vy - (mini[1] + maxi[1]) / 2, 0.0])
    return "plateau" if cible is None else "piece"


def centrer_plateau(projet: Projet, i: int) -> str:
    """Ramène la forme i au MILIEU DU PLATEAU, quoi qu'il y ait dessous.

    « Centrer sur la pièce du dessous » suit l'empilement, ce qui est le plus
    utile la plupart du temps, mais ne permet pas de recadrer une pièce seule
    sur le plateau quand une autre traîne dessous (demande d'Emmanuel)."""
    mini, maxi = boite(projet.etapes[i])
    _translater(projet, groupe(projet, i),
                [-(mini[0] + maxi[0]) / 2.0, -(mini[1] + maxi[1]) / 2.0, 0.0])
    return "plateau"


# Écrous hexagonaux ISO 4032 : entre plats (s) et épaisseur (m), en millimètres.
# Toute la gamme couramment imprimée, de M2 à M12.
ECROUS: dict[str, tuple[float, float]] = {
    "M2": (4.0, 1.6), "M2.5": (5.0, 2.0), "M3": (5.5, 2.4), "M4": (7.0, 3.2),
    "M5": (8.0, 4.7), "M6": (10.0, 5.2), "M8": (13.0, 6.8), "M10": (16.0, 8.4),
    "M12": (18.0, 10.8),
}
JEU_ECROU = 0.2        # mm : sans jeu, l'écrou n'entre pas dans une pièce imprimée


# Diamètre nominal et PAS GROS (le plus courant) de la visserie métrique.
TARAUDAGES: dict[str, tuple[float, float]] = {
    "M2": (2.0, 0.4), "M2.5": (2.5, 0.45), "M3": (3.0, 0.5), "M4": (4.0, 0.7),
    "M5": (5.0, 0.8), "M6": (6.0, 1.0), "M8": (8.0, 1.25), "M10": (10.0, 1.5),
    "M12": (12.0, 1.75),
}
JEU_TARAUDAGE = 0.2    # mm : une vis M6 n'entre pas dans un trou imprimé à 6,00


def trou_taraude(projet: Projet, taille: str, i_base: int | None) -> Forme:
    """Un trou CREUX au pas de vis métrique : « M3 », « M4 »…

    Le diamètre reçoit le jeu d'impression, comme le logement d'écrou : une vis
    M6 ne se visse pas dans un trou sorti à 6,00 mm, la matière s'écrase et la
    vis casse le filet."""
    diametre, pas = TARAUDAGES[taille]
    f = nouvelle_forme(projet, "taraudage", i_base)
    f.op = "creux"
    f.pas = pas
    f.dim[:] = [diametre + JEU_TARAUDAGE, diametre + JEU_TARAUDAGE,
                max(6.0, round(diametre * 2.0))]
    f.pos[2] = f.demi_etendue()[2]
    return f


def logement_ecrou(projet: Projet, taille: str, i_base: int | None) -> Forme:
    """Un six pans CREUX aux cotes normalisées d'un écrou, avec le jeu qu'exige
    l'impression. `taille` vaut « M3 », « M4 »…

    Le prisme est défini par son diamètre circonscrit, alors qu'un écrou se
    mesure entre plats : d'où la division par le cosinus de 30 degrés."""
    entre_plats, epaisseur = ECROUS[taille]
    f = nouvelle_forme(projet, "prisme", i_base)
    f.op = "creux"
    f.cotes = 6
    f.dim[:] = [(entre_plats + JEU_ECROU) / math.cos(math.pi / 6), 0.0,
                epaisseur + JEU_ECROU]
    f.pos[2] = f.demi_etendue()[2]          # posé au plateau, dimensions à jour
    return f


def position_insertion(etapes: list, selection: int) -> int:
    """Où insérer une nouvelle étape : juste après la sélection, ou À LA FIN
    quand rien n'est sélectionné.

    Jamais en tête : la PREMIÈRE forme est toujours traitée comme de la matière
    par le moteur, si bien qu'une forme insérée là ne pouvait plus creuser, ses
    boutons restant grisés (retour d'Emmanuel, cône ajouté après un clic dans
    le vide, qui désélectionne).

    Jamais AVANT une découpe non plus. Une coupe tranche tout ce qui la précède :
    une forme ajoutée là se retrouvait tranchée par un plan invisible qu'on
    croyait appartenir au passé (« il se retrouve lui aussi coupé par ce plan
    invisible »), et un arrondi glissé au même endroit montrait la pièce telle
    qu'elle était AVANT la coupe, donc entière (« la pièce revient à son état
    d'origine »). Deux symptômes, une seule cause."""
    from neoforge.projet.modele import Coupe

    ou = selection + 1 if 0 <= selection < len(etapes) else len(etapes)
    derniere_coupe = max((i for i, e in enumerate(etapes)
                          if isinstance(e, Coupe)), default=-1)
    return max(ou, derniere_coupe + 1)


def nouvelle_forme(projet: Projet, forme: str, i_base: int | None) -> Forme:
    """Une forme de 20 mm posée sur le plateau, à droite de la sélection."""
    # Chaque forme a ses dimensions de départ : un tore créé en 20 × 20 aurait
    # un trou de diamètre nul, donc pas d'anneau du tout.
    # Le cadre et l'anneau naissent PLATS : ce sont des contours, on les pose à
    # plat sur le plateau et on les relève si besoin (demande d'Emmanuel).
    dims = {"cone": [20.0, 0.0, 24.0],
            "tore": [30.0, 8.0, 8.0],        # anneau Ø30, tube Ø8
            "prisme": [20.0, 0.0, 20.0],
            "cadre": [40.0, 40.0, 4.0],
            "anneau": [40.0, 40.0, 4.0],
            "taraudage": [6.2, 6.2, 12.0],
            "engrenage": [40.0, 40.0, 6.0]}.get(forme, [20.0, 20.0, 20.0])
    f = Forme(forme, "matiere", [0.0, 0.0, 10.0], dims)
    if forme == "cadre":
        f.cotes = 4                      # un carré, la forme qu'on attend
    if forme == "engrenage":
        f.cotes = 16                     # une roue courante, ni trop fine ni trop grosse
        f.variante = "droit"
    # Cadenas FERMÉ d'office sur les formes qu'on attend rondes : les étirer
    # sur un seul axe les ovaliserait sans qu'on l'ait demandé. Il s'ouvre d'un
    # clic pour qui veut justement l'ovale.
    if forme in ("cylindre", "anneau", "engrenage"):
        f.lien_xy = True
    if forme in ("cadre", "anneau"):
        f.bord = 4.0
    base = projet.etapes[i_base] if i_base is not None else None
    if isinstance(base, Forme):
        mn, mx = boite(base)
        f.pos[0] = mx[0] + f.demi_etendue()[0] + 6.0
        f.pos[1] = base.pos[1]
    f.pos[2] = f.demi_etendue()[2]
    return f


