# -*- coding: utf-8 -*-
"""Arêtes d'un solide : lesquelles on peut arrondir, comment on les choisit,
et comment on les RETROUVE quand la pièce change.

Le piège classique de la CAO (« nommage topologique ») : si on change la taille
du cube tout en haut de la pile, les arêtes du résultat sont renumérotées, et un
congé posé « sur l'arête 12 » partirait ailleurs. neoForge ne garde donc jamais
un numéro d'arête. Il garde :
  soit une RÈGLE recalculée à chaque fois (toutes, celles du haut, du bas,
  les verticales) : robuste par construction ;
  soit, pour des arêtes cliquées, une SIGNATURE géométrique (milieu absolu et
  relatif à la boîte de la pièce, direction, type, rayon) qu'on rapproche des
  arêtes du nouveau résultat. Une signature sans correspondant n'est jamais
  appliquée au hasard : l'étape le signale.
"""
from __future__ import annotations

import numpy as np

from neoforge.noyau import occ as O
from neoforge.noyau.maillage import polyligne

SEUIL_ACCORD = 0.12     # au-delà, une signature n'a pas de correspondant


def _pt(p) -> np.ndarray:
    return np.array([p.X(), p.Y(), p.Z()])


def toutes_les_aretes(forme) -> list:
    """TOUTES les arêtes de la pièce, y compris celles qu'on ne peut pas
    arrondir. La règle mesure sur n'importe quel bord, même le cercle de
    couture d'un cylindre ou le bord d'un congé déjà posé."""
    out = []
    for e, _faces in O.aretes_et_faces(forme):
        if not O.degeneree(e):
            out.append(e)
    return out


def aretes_arrondissables(forme) -> list:
    """Arêtes UNIQUES où un congé a un sens : ni dégénérées (pôles de sphère),
    ni coutures (cylindre), ni déjà lisses (bord d'un congé existant)."""
    O.encoder_regularite(forme)
    out = []
    for e, faces in O.aretes_et_faces(forme):
        if O.degeneree(e):
            continue
        if len(faces) != 2:            # couture ou bord libre
            continue
        try:
            if O.continuite(e, faces[0], faces[1]) != O.GeomAbs_C0:
                continue               # arête lisse : rien à arrondir
        except Exception:
            pass
        out.append(e)
    return out


def signature(e, boite) -> dict:
    c = O.BRepAdaptor_Curve(e)
    u0, u1 = c.FirstParameter(), c.LastParameter()
    um = (u0 + u1) / 2
    milieu = _pt(c.Value(um))
    genre = "ligne" if c.GetType() == O.GeomAbs_Line else (
        "cercle" if c.GetType() == O.GeomAbs_Circle else "autre")
    rayon = 0.0
    if genre == "cercle":
        cercle = c.Circle()
        a = cercle.Axis().Direction()
        direction = np.array([a.X(), a.Y(), a.Z()])
        rayon = float(cercle.Radius())
        milieu = _pt(cercle.Location())      # le CENTRE : stable si le diamètre change
    else:
        du = (u1 - u0) * 0.05
        direction = _pt(c.Value(um + du)) - _pt(c.Value(um - du))
    n = np.linalg.norm(direction)
    direction = direction / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])
    lo, hi = np.array(boite[0]), np.array(boite[1])
    relatif = (milieu - lo) / np.maximum(hi - lo, 1.0)
    return {"milieu": [round(float(v), 4) for v in milieu],
            "relatif": [round(float(v), 4) for v in relatif],
            "dir": [round(float(v), 4) for v in direction],
            "genre": genre, "rayon": round(rayon, 4),
            "long": round(O.longueur(e), 4)}


def _ecart(a: dict, b: dict, diag: float, large: bool = False) -> float:
    """Écart entre deux signatures (0 = identiques).
    Serré : le MEILLEUR des deux repères (absolu ou relatif à la boîte), pour
    suivre une pièce redimensionnée ou déplacée en bloc.
    Large : leur MOYENNE, plus discriminante quand une arête a bougé seule (le
    bord haut et le bord bas d'un trou déplacé sont proches en absolu mais
    opposés en relatif)."""
    d_abs = np.linalg.norm(np.subtract(a["milieu"], b["milieu"])) / max(diag, 1.0)
    d_rel = np.linalg.norm(np.subtract(a["relatif"], b["relatif"]))
    s = (d_abs + d_rel) / 2 if large else min(d_abs, d_rel)
    s += 0.5 * (1.0 - abs(float(np.dot(a["dir"], b["dir"]))))
    if a["genre"] != b["genre"]:
        s += 1.0
    elif a["genre"] == "cercle":
        s += 0.5 * abs(a["rayon"] - b["rayon"]) / max(a["rayon"], b["rayon"], 1.0)
    return s


def _compatible(a: dict, b: dict) -> bool:
    return (a["genre"] == b["genre"]
            and abs(float(np.dot(a["dir"], b["dir"]))) >= 0.99)


SEUIL_LARGE = 0.8       # 2e passe : arête déplacée ou redimensionnée
MARGE_LARGE = 0.1       # … acceptée seulement si elle ne se confond avec aucune autre


def retrouver(signatures: list[dict], aretes: list, boite) -> tuple[list, int]:
    """Rapproche chaque signature d'une arête (au plus une chacune).
    1re passe : correspondance serrée (pièce redimensionnée ou déplacée en bloc).
    2e passe, pour ce qui reste : une arête de même genre et même direction,
    plus loin (trou déplacé, diamètre changé), SEULEMENT si elle se détache
    nettement des autres candidates. Sinon : pas de correspondant.
    Renvoie (arêtes retrouvées, nombre de signatures sans correspondant)."""
    if not signatures:
        return [], 0
    sigs = [signature(e, boite) for e in aretes]
    diag = float(np.linalg.norm(np.subtract(boite[1], boite[0])))
    ecarts = [[_ecart(s, t, diag) for t in sigs] for s in signatures]
    paires = sorted((ecarts[i][j], i, j)
                    for i in range(len(signatures)) for j in range(len(sigs)))
    pris_s, pris_a, choix = set(), set(), {}
    for ecart, i, j in paires:
        if ecart > SEUIL_ACCORD:
            break
        if i in pris_s or j in pris_a:
            continue
        pris_s.add(i)
        pris_a.add(j)
        choix[i] = j
    for i, s in enumerate(signatures):
        if i in pris_s:
            continue
        cands = sorted((_ecart(s, t, diag, large=True), j) for j, t in enumerate(sigs)
                       if j not in pris_a and _compatible(s, t))
        if not cands or cands[0][0] > SEUIL_LARGE:
            continue
        if len(cands) > 1 and cands[1][0] - cands[0][0] < MARGE_LARGE:
            continue                   # ambigu : on ne devine pas
        pris_s.add(i)
        pris_a.add(cands[0][1])
        choix[i] = cands[0][1]
    trouvees = [aretes[choix[i]] for i in sorted(choix)]
    return trouvees, len(signatures) - len(pris_s)


def _sur_une_face(point, faces: list, tolerance: float) -> bool:
    sommet = O.BRepBuilderAPI_MakeVertex(O.gp_Pnt(*[float(v) for v in point])).Vertex()
    for f in faces:
        calcul = O.BRepExtrema_DistShapeShape(sommet, f)
        calcul.Perform()
        if calcul.IsDone() and float(calcul.Value()) <= tolerance:
            return True
    return False


def restreindre(candidates: list, formes: list, tolerance: float = 0.35) -> list:
    """Ne garde que les arêtes qui courent sur la SURFACE d'une de ces formes.

    C'est ce qui limite un arrondi à l'objet choisi et à ses enfants : sans
    cela, « toutes les arêtes » arrondissait aussi les objets ajoutés plus tard
    (retour d'Emmanuel). On écarte d'abord grossièrement par la boîte
    englobante, qui ne coûte rien, avant de mesurer la distance exacte."""
    from neoforge.noyau.primitives import solide
    if not formes:
        return list(candidates)
    cibles = []
    for f in formes:
        try:
            s = solide(f)
            (x0, y0, z0), (x1, y1, z1) = O.boite(s)
        except Exception:
            continue
        faces = []
        ex = O.TopExp_Explorer(s, O.TopAbs_FACE)
        while ex.More():
            faces.append(O.face(ex.Current()))
            ex.Next()
        cibles.append((np.array([x0, y0, z0]) - tolerance,
                       np.array([x1, y1, z1]) + tolerance, faces))
    out = []
    for e in candidates:
        points = polyligne(e, 5)
        for mini, maxi, faces in cibles:
            if not np.all((points >= mini) & (points <= maxi)):
                continue                       # même pas dans la boîte
            if all(_sur_une_face(p, faces, tolerance) for p in points[::2]):
                out.append(e)
                break
    return out


def selon_regle(regle: str, aretes: list, boite) -> list:
    """Arêtes désignées par une règle, recalculées sur la pièce ACTUELLE."""
    if regle == "toutes":
        return list(aretes)
    z0, z1 = boite[0][2], boite[1][2]
    eps = max(1e-3, (z1 - z0) * 1e-4)
    out = []
    for e in aretes:
        p = polyligne(e, 12)
        if regle == "haut" and np.all(p[:, 2] >= z1 - eps):
            out.append(e)
        elif regle == "bas" and np.all(p[:, 2] <= z0 + eps):
            out.append(e)
        elif regle == "verticales" and len(p) == 2:
            d = p[1] - p[0]
            n = np.linalg.norm(d)
            if n > 1e-9 and abs(d[2]) / n > 0.999:
                out.append(e)
    return out
