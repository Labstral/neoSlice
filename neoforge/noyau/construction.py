# -*- coding: utf-8 -*-
"""Rejoue la pile d'étapes et produit la pièce, étape par étape.

Chaque étape donne un résultat (le solide APRÈS elle) ou une erreur
compréhensible. Une étape en erreur ne casse rien : la pièce garde le résultat
de l'étape précédente, et l'interface colore l'étape en rouge avec le message.

Cache : on ne recalcule qu'à partir de la première étape modifiée (le résultat
d'une étape ne dépend que d'elle et de celles au-dessus).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from neoforge.noyau import occ as O
from neoforge.noyau import aretes as A
from neoforge.noyau.primitives import solide
from neoforge.projet.modele import Arrondi, Coupe, Forme, groupe_de

# Codes d'erreur (traduits par l'interface)
ERR_VIDE = "vide"                    # le résultat ne contient plus de matière
ERR_GEOMETRIE = "geometrie"          # le noyau n'a pas su calculer
ERR_RIEN = "rien_a_arrondir"         # arrondi avant toute forme
ERR_AUCUNE = "aucune_arete"          # la règle ne désigne aucune arête
ERR_INTROUVABLES = "introuvables"    # arêtes cliquées disparues
ERR_TROP_GRAND = "trop_grand"        # congé / chanfrein impossible à cette taille


ECART_COUPE = 2.0      # mm : l'espace qui SÉPARE les deux morceaux d'une découpe


def _demi_espace(forme, axe: int, position: float, au_dessus: bool):
    """Une boîte franchement plus grande que la pièce, d'un seul côté du plan :
    c'est l'outil qui tranche."""
    (x0, y0, z0), (x1, y1, z1) = O.boite(forme)
    marge = max(x1 - x0, y1 - y0, z1 - z0) + 10.0
    bas = [x0 - marge, y0 - marge, z0 - marge]
    haut = [x1 + marge, y1 + marge, z1 + marge]
    if au_dessus:
        bas[axe] = position
    else:
        haut[axe] = position
    return O.BRepPrimAPI_MakeBox(O.gp_Pnt(*bas), haut[0] - bas[0],
                                 haut[1] - bas[1], haut[2] - bas[2]).Shape()


def _couper(forme, etape: Coupe):
    """Tranche par un plan. « les_deux » renvoie les deux morceaux réunis en un
    seul objet à deux corps, que la suite de la chaîne sait afficher, mesurer et
    exporter (la pièce est simplement « en 2 morceaux séparés »)."""
    dessous = _booleen("creux", forme,
                       _demi_espace(forme, etape.axe, etape.position, True))
    if etape.garder == "dessous":
        return dessous
    dessus = _booleen("creux", forme,
                      _demi_espace(forme, etape.axe, etape.position, False))
    if etape.garder == "dessus":
        return dessus
    # Les deux morceaux sont ÉCARTÉS : au contact exact ils ne formaient pas
    # deux parties distinctes à l'usage (retour d'Emmanuel), et il fallait les
    # séparer à la main avant d'imprimer.
    ecart = [0.0, 0.0, 0.0]
    ecart[etape.axe] = ECART_COUPE
    # Plus le déplacement donné à la partie HAUTE : elle est listée comme une
    # pièce à part et se tire toute seule (choix d'Emmanuel).
    for k in range(3):
        ecart[k] += float(getattr(etape, "decalage", (0.0, 0.0, 0.0))[k])
    glissement = O.gp_Trsf()
    glissement.SetTranslation(O.gp_Vec(*ecart))
    dessus = O.BRepBuilderAPI_Transform(dessus, glissement, True).Shape()
    batisseur = O.BRep_Builder()
    ensemble = O.TopoDS_Compound()
    batisseur.MakeCompound(ensemble)
    batisseur.Add(ensemble, dessous)
    batisseur.Add(ensemble, dessus)
    return ensemble


@dataclass
class Resultat:
    forme: object = None             # solide après l'étape (ou celui d'avant si erreur)
    erreur: str | None = None
    detail: dict = field(default_factory=dict)
    aretes: list = field(default_factory=list)    # arêtes traitées (arrondi)


def _booleen(op: str, a, b):
    algo = {"matiere": O.BRepAlgoAPI_Fuse, "creux": O.BRepAlgoAPI_Cut,
            "intersection": O.BRepAlgoAPI_Common}[op](a, b)
    if not algo.IsDone():
        raise RuntimeError("booléen")
    return O.unifier(algo.Shape())


def _a_de_la_matiere(forme) -> bool:
    if forme is None or forme.IsNull():
        return False
    ex = O.TopExp_Explorer(forme, O.TopAbs_SOLID)
    return ex.More() and O.volume(forme) > 1e-6


def _arrondir(genre: str, taille: float, forme, aretes: list):
    algo = (O.BRepFilletAPI_MakeFillet(forme) if genre == "conge"
            else O.BRepFilletAPI_MakeChamfer(forme))
    for e in aretes:
        algo.Add(float(taille), e)
    algo.Build()
    if not algo.IsDone():
        return None
    r = algo.Shape()
    return r if O.valide(r) and _a_de_la_matiere(r) else None


def taille_max(genre: str, forme, aretes: list, demandee: float) -> float:
    """Plus grande taille qui passe (recherche par dichotomie), 0 si aucune."""
    lo, hi = 0.0, float(demandee)
    for _ in range(9):
        mid = (lo + hi) / 2
        if mid < 0.05:
            break
        if _arrondir(genre, mid, forme, aretes) is not None:
            lo = mid
        else:
            hi = mid
    # Arrondi VERS LE BAS : proposer « 10 » quand 10 échoue serait un mensonge.
    return math.floor(lo * 10) / 10 if lo >= 0.1 else 0.0


class Constructeur:
    def __init__(self):
        self._cles: list[str] = []
        self._resultats: list[Resultat] = []

    def construire(self, projet, taille_max_si_erreur: bool = True) -> list[Resultat]:
        # L'identifiant, le lien parent et le verrou ne changent RIEN à la
        # géométrie : les écarter du cache évite de tout recalculer quand on
        # relie deux pièces ou qu'on en verrouille une.
        cles = [json.dumps({c: v for c, v in e.dico().items()
                            if c not in ("id", "parent", "verrou")}, sort_keys=True)
                for e in projet.etapes]
        commun = 0
        while (commun < len(cles) and commun < len(self._cles)
               and cles[commun] == self._cles[commun]):
            commun += 1
        resultats = self._resultats[:commun]
        courant = resultats[-1].forme if resultats else None
        premiere_forme = not any(isinstance(e, Forme) and e.actif
                                 for e in projet.etapes[:commun])
        for etape in projet.etapes[commun:]:
            # Un arrondi peut VISER un objet : il ne touchera que lui et sa
            # descendance, jamais les objets ajoutés ensuite.
            cibles = (groupe_de(projet.etapes, etape.cible)
                      if isinstance(etape, Arrondi) and etape.cible else None)
            r = self._etape(etape, courant, premiere_forme, taille_max_si_erreur,
                            cibles)
            if isinstance(etape, Forme) and etape.actif and r.erreur is None:
                premiere_forme = False
            resultats.append(r)
            courant = r.forme
        self._cles, self._resultats = cles, resultats
        return list(resultats)

    def _etape(self, etape, courant, premiere_forme: bool, avec_max: bool,
               cibles=None) -> Resultat:
        if not etape.actif:
            return Resultat(courant)
        if isinstance(etape, Forme):
            try:
                s = solide(etape)
                if premiere_forme or courant is None:
                    # La première forme est TOUJOURS de la matière (comme la console).
                    return Resultat(O.unifier(s))
                r = _booleen(etape.op, courant, s)
            except Exception:
                return Resultat(courant, ERR_GEOMETRIE)
            if not _a_de_la_matiere(r):
                return Resultat(courant, ERR_VIDE)
            return Resultat(r)

        if isinstance(etape, Coupe):
            if courant is None:
                return Resultat(None, ERR_RIEN)
            try:
                r = _couper(courant, etape)
            except Exception:
                return Resultat(courant, ERR_GEOMETRIE)
            if r is None or not _a_de_la_matiere(r):
                return Resultat(courant, ERR_VIDE)   # le plan est hors de la pièce
            return Resultat(r)

        assert isinstance(etape, Arrondi)
        if courant is None:
            return Resultat(None, ERR_RIEN)
        boite = O.boite(courant)
        candidates = A.aretes_arrondissables(courant)
        if cibles:
            candidates = A.restreindre(candidates, cibles)
        manquantes = 0
        if etape.regle == "liste":
            if not etape.aretes:
                # Aucune arête ENCORE choisie : ce n'est pas une erreur, c'est
                # une étape qui attend. Sans cela, cliquer « Arrondir des
                # arêtes » affichait aussitôt une ligne rouge, avant même
                # d'avoir pu désigner quoi que ce soit (retour d'Emmanuel).
                return Resultat(courant)
            choisies, manquantes = A.retrouver(etape.aretes, candidates, boite)
            if not choisies:
                return Resultat(courant, ERR_INTROUVABLES, {"manquantes": manquantes})
        else:
            choisies = A.selon_regle(etape.regle, candidates, boite)
            if not choisies:
                return Resultat(courant, ERR_AUCUNE)
        try:
            r = _arrondir(etape.genre_arrondi, etape.taille, courant, choisies)
        except Exception:
            r = None
        if r is None:
            detail = {}
            if avec_max:
                try:
                    detail["max"] = taille_max(etape.genre_arrondi, courant, choisies,
                                               etape.taille)
                except Exception:
                    pass
            return Resultat(courant, ERR_TROP_GRAND, detail, choisies)
        return Resultat(r, None, {"manquantes": manquantes} if manquantes else {},
                        choisies)
