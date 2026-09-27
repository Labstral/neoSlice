# -*- coding: utf-8 -*-
"""Modèle d'un projet neoForge : une PILE d'étapes rejouée de haut en bas.

Deux sortes d'étapes :
  Forme    une forme simple (cube, sphère, cylindre, cône) ajoutée en matière,
           creusée, ou intersectée avec ce qui précède ;
  Arrondi  un congé (arrondi) ou un chanfrein (biseau) sur des arêtes du
           résultat courant.

Rien n'est jamais détruit : la pièce est toujours RECALCULÉE depuis la pile, une
étape peut être masquée (actif = False) sans être supprimée, et l'historique
garde chaque état (voir historique.py).

Compatibilité console : les formes gardent exactement la sémantique de
neoForge 1.1 (Anbernic) : dimensions centrées sur la position, rotation en
degrés autour de X puis Y puis Z, et le fichier écrit garde la clé
« primitives » que la console sait relire (les arrondis y sont ignorés).
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field

VERSION_FICHIER = "2.1"
# 2.1 : le cylindre a deux diamètres (dim[0] et dim[1]) et peut donc être OVALE.
# Avant, dim[1] ne servait à rien pour lui et gardait la valeur de sa création,
# 20 mm : un fichier plus ancien deviendrait une ellipse au chargement. On le
# remet donc rond (voir _rendre_les_cylindres_ronds).

FORMES = ("cube", "sphere", "cylindre", "cone",      # index = code console
          "tore", "coin", "prisme",                  # ajoutées le 2026-09-13
          "cadre", "anneau", "taraudage",            # ajoutées le 2026-09-26
          "engrenage")
# La console 1.1 ne connaît que les quatre premières : dans la liste de
# compatibilité qu'on écrit pour elle, les nouvelles sont approchées par la plus
# proche. Le vrai fichier, lui, garde la forme exacte dans « etapes ».
CONSOLE = {"tore": "cylindre", "coin": "cube", "prisme": "cylindre",
           "cadre": "cube", "anneau": "cylindre", "taraudage": "cylindre",
           "engrenage": "cylindre"}
OPS = ("matiere", "creux", "intersection")           # index = code console
GENRES_ARRONDI = ("conge", "chanfrein")
REGLES = ("toutes", "haut", "bas", "verticales", "liste")
GARDER = ("dessous", "dessus", "les_deux")           # découpe par un plan

LIMITE_ETAPES = 60


def _avant(version: str, seuil: str) -> bool:
    """Compare deux numéros de version « majeur.mineur », tolérant au n'importe
    quoi (un fichier abîmé est traité comme le plus ancien)."""
    def parts(v):
        out = []
        for morceau in str(v).split("."):
            try:
                out.append(int(morceau))
            except ValueError:
                out.append(0)
        return tuple(out)
    try:
        return parts(version) < parts(seuil)
    except Exception:
        return True


def _rendre_les_cylindres_ronds(etapes) -> None:
    """Fichier d'avant la 2.1 : le second diamètre d'un cylindre n'existait pas,
    dim[1] traînait la valeur de sa création (20 mm). Sans cette remise à plat,
    un cylindre de Ø60 enregistré hier rouvrirait en ovale 60 × 20."""
    for e in etapes:
        if isinstance(e, Forme) and e.forme == "cylindre":
            e.dim[1] = e.dim[0]
            e.lien_xy = True          # il était rond, il le reste tant qu'on veut


def identifiant() -> str:
    """Étiquette stable d'une forme. Les liens parent/enfant s'appuient dessus
    et NON sur la place dans la pile : sinon déplacer, dupliquer ou supprimer
    une étape redirigerait les liens vers la mauvaise pièce."""
    return uuid.uuid4().hex[:8]


def _vec3(v, defaut) -> list[float]:
    try:
        out = [float(x) for x in list(v)[:3]]
        return out if len(out) == 3 else list(defaut)
    except Exception:
        return list(defaut)


@dataclass
class Forme:
    forme: str = "cube"
    op: str = "matiere"
    pos: list[float] = field(default_factory=lambda: [0.0, 0.0, 10.0])
    dim: list[float] = field(default_factory=lambda: [20.0, 20.0, 20.0])
    rot: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    actif: bool = True
    # Les nouveaux champs viennent APRÈS `actif` : tout le code qui construit
    # une forme par position continue de marcher.
    ident: str = field(default_factory=identifiant)
    parent: str = ""              # identifiant de la pièce dont celle ci dépend
    # Verrouillée : la pièce ne bouge plus toute seule, un geste sur elle
    # déplace ou tourne TOUT l'ensemble à partir de son parent.
    verrou: bool = False
    # Nombre de côtés d'un prisme ou d'un cadre, et nombre de DENTS d'un
    # engrenage : la borne haute est celle de l'engrenage, l'interface limite
    # chaque forme à ce qui a du sens pour elle.
    cotes: int = 6
    # Épaisseur du contour d'un cadre ou d'un anneau : ces formes sont VIDES au
    # milieu, seul leur bord est de la matière (demande d'Emmanuel, 2026-09-26).
    bord: float = 4.0
    # Pas d'un trou taraudé, en millimètres par tour (M3 = 0,5 ; M6 = 1).
    pas: float = 1.0
    # Sous type d'une forme qui en a plusieurs : profil des dents d'un
    # engrenage (« droit », « arrondi », « pointu »).
    variante: str = ""
    # Cadenas des deux premiers axes : la largeur et la profondeur bougent
    # ENSEMBLE, ce qui garde un cylindre rond et une roue ronde. Faux par
    # défaut, sinon un pavé déjà enregistré se retrouverait bridé au
    # chargement.
    lien_xy: bool = False
    genre = "forme"

    def dico(self) -> dict:
        return {"type": "forme", "forme": self.forme, "op": self.op,
                "pos": list(self.pos), "dim": list(self.dim),
                "rot": list(self.rot), "actif": self.actif,
                "id": self.ident, "parent": self.parent, "verrou": self.verrou,
                "cotes": self.cotes, "bord": self.bord, "pas": self.pas,
                "variante": self.variante, "lien_xy": self.lien_xy}

    @staticmethod
    def depuis_dico(d: dict) -> "Forme":
        forme = d.get("forme", "cube")
        if isinstance(forme, int):                       # format console
            forme = FORMES[forme] if 0 <= forme < len(FORMES) else "cube"
        op = d.get("op", "matiere")
        if isinstance(op, int):
            op = OPS[op] if 0 <= op < len(OPS) else "matiere"
        if forme not in FORMES:
            forme = "cube"
        if op not in OPS:
            op = "matiere"
        return Forme(forme, op,
                     _vec3(d.get("pos"), [0.0, 0.0, 10.0]),
                     _vec3(d.get("dim"), [20.0, 20.0, 20.0]),
                     _vec3(d.get("rot"), [0.0, 0.0, 0.0]),
                     bool(d.get("actif", True)),
                     str(d.get("id") or "") or identifiant(),
                     str(d.get("parent") or ""),
                     bool(d.get("verrou", False)),
                     max(3, min(120, int(d.get("cotes", 6) or 6))),
                     max(0.2, float(d.get("bord", 4.0) or 4.0)),
                     max(0.15, float(d.get("pas", 1.0) or 1.0)),
                     str(d.get("variante", "") or ""),
                     bool(d.get("lien_xy", False)))

    def dico_console(self) -> dict:
        return {"forme": FORMES.index(CONSOLE.get(self.forme, self.forme)),
                "op": OPS.index(self.op), "pos": list(self.pos),
                "dim": list(self.dim), "rot": list(self.rot)}

    # ── Géométrie simple (sans noyau) : boîte englobante, comme la console ──
    def demi_etendue(self) -> list[float]:
        d = self.dim
        if self.forme == "cube":
            return [d[0] / 2.0, d[1] / 2.0, d[2] / 2.0]
        if self.forme == "sphere":
            return [d[0] / 2.0] * 3
        if self.forme == "cylindre":
            # Deux diamètres depuis la 2.1 : le cylindre peut être ovale.
            return [d[0] / 2.0, d[1] / 2.0, d[2] / 2.0]
        if self.forme == "tore":
            # d[0] = diamètre du cercle porteur, d[1] = diamètre du tube
            return [(d[0] + d[1]) / 2.0, (d[0] + d[1]) / 2.0, d[1] / 2.0]
        if self.forme == "coin":
            return [d[0] / 2.0, d[1] / 2.0, d[2] / 2.0]
        if self.forme == "prisme":
            return [d[0] / 2.0, d[0] / 2.0, d[2] / 2.0]
        if self.forme in ("cadre", "anneau"):
            return [d[0] / 2.0, d[1] / 2.0, d[2] / 2.0]
        if self.forme == "taraudage":
            return [d[0] / 2.0, d[0] / 2.0, d[2] / 2.0]
        if self.forme == "engrenage":
            return [d[0] / 2.0, d[1] / 2.0, d[2] / 2.0]
        r = max(d[0], d[1]) / 2.0
        return [r, r, d[2] / 2.0]


@dataclass
class Arrondi:
    genre_arrondi: str = "conge"            # « conge » ou « chanfrein »
    taille: float = 1.0                     # rayon ou distance, en mm
    regle: str = "toutes"                   # voir REGLES
    aretes: list[dict] = field(default_factory=list)   # signatures (règle « liste »)
    actif: bool = True
    # Identifiant de la forme VISÉE : l'arrondi ne touche que cette forme et sa
    # descendance. Vide = toute la pièce. Sans cela, « toutes les arêtes »
    # arrondissait aussi les objets ajoutés ensuite (retour d'Emmanuel).
    cible: str = ""
    genre = "arrondi"

    def dico(self) -> dict:
        return {"type": "arrondi", "genre": self.genre_arrondi,
                "taille": self.taille, "regle": self.regle,
                "aretes": copy.deepcopy(self.aretes), "actif": self.actif,
                "cible": self.cible}

    @staticmethod
    def depuis_dico(d: dict) -> "Arrondi":
        g = d.get("genre", "conge")
        r = d.get("regle", "toutes")
        try:
            taille = max(0.05, float(d.get("taille", 1.0)))
        except Exception:
            taille = 1.0
        aretes = d.get("aretes") or []
        return Arrondi(g if g in GENRES_ARRONDI else "conge", taille,
                       r if r in REGLES else "toutes",
                       [a for a in aretes if isinstance(a, dict)],
                       bool(d.get("actif", True)),
                       str(d.get("cible") or ""))


@dataclass
class Coupe:
    """Tranche la pièce par un plan perpendiculaire à un axe.

    On garde le morceau du dessous, celui du dessus, ou LES DEUX, qui deviennent
    alors deux objets séparés (demande d'Emmanuel, pratique pour couper une
    pièce trop haute en deux moitiés imprimables)."""
    axe: int = 2                     # 0 = X, 1 = Y, 2 = Z
    position: float = 0.0            # en mm, le long de cet axe
    garder: str = "dessous"          # voir GARDER
    actif: bool = True
    # Déplacement propre à la partie HAUTE, en plus de l'écart automatique :
    # « garder les deux » donne deux pièces dans la liste, et celle du haut se
    # tire à part pour l'écarter de l'autre (choix d'Emmanuel). Ajouté APRÈS
    # `actif` pour que toutes les constructions positionnelles tiennent.
    decalage: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    genre = "coupe"

    def dico(self) -> dict:
        return {"type": "coupe", "axe": self.axe, "position": self.position,
                "garder": self.garder, "actif": self.actif,
                "decalage": [float(v) for v in self.decalage]}

    @staticmethod
    def depuis_dico(d: dict) -> "Coupe":
        g = str(d.get("garder", "dessous"))
        try:
            axe = max(0, min(2, int(d.get("axe", 2))))
        except Exception:
            axe = 2
        try:
            position = float(d.get("position", 0.0))
        except Exception:
            position = 0.0
        decalage = [0.0, 0.0, 0.0]
        brut = d.get("decalage")
        if isinstance(brut, (list, tuple)) and len(brut) == 3:
            try:
                decalage = [float(v) for v in brut]
            except Exception:
                decalage = [0.0, 0.0, 0.0]
        return Coupe(axe, position, g if g in GARDER else "dessous",
                     bool(d.get("actif", True)), decalage)


def groupe_de(etapes: list, ident: str) -> list:
    """La forme portant cet identifiant ET toute sa descendance.

    Sert à limiter un arrondi à l'objet choisi : quand on arrondit un objet, ses
    enfants suivent, mais rien d'autre."""
    if not ident:
        return []
    racine = next((e for e in etapes
                   if isinstance(e, Forme) and e.ident == ident), None)
    if racine is None:
        return []
    out, a_voir, vus = [racine], [ident], {ident}
    while a_voir:
        courant = a_voir.pop()
        for e in etapes:
            if isinstance(e, Forme) and e.parent == courant and e.ident not in vus:
                vus.add(e.ident)
                out.append(e)
                a_voir.append(e.ident)
    return out


def nettoyer_liens(etapes: list) -> list:
    """Remet les liens parent/enfant d'aplomb après une lecture de fichier :
    identifiants uniques, parent qui existe vraiment, et AUCUNE boucle (une
    pièce ne peut pas descendre d'elle même, sinon un déplacement tournerait
    sans fin)."""
    vus: set[str] = set()
    formes = [e for e in etapes if isinstance(e, Forme)]
    for f in formes:
        if not f.ident or f.ident in vus:
            f.ident = identifiant()
        vus.add(f.ident)
    par_id = {f.ident: f for f in formes}
    for f in formes:
        if not f.ident or not f.parent:
            continue
        if f.parent not in par_id:
            f.parent = ""
            continue
        chaine, courant = {f.ident}, par_id.get(f.parent)
        while courant is not None:
            if courant.ident in chaine:
                f.parent = ""                  # boucle : on coupe le lien
                break
            chaine.add(courant.ident)
            courant = par_id.get(courant.parent) if courant.parent else None
    return etapes


def etape_depuis_dico(d: dict):
    if d.get("type") == "arrondi":
        return Arrondi.depuis_dico(d)
    if d.get("type") == "coupe":
        return Coupe.depuis_dico(d)
    return Forme.depuis_dico(d)


@dataclass
class Projet:
    etapes: list = field(default_factory=list)
    nom: str = ""

    @staticmethod
    def nouveau() -> "Projet":
        """Une scène VIDE.

        La console posait un cube de départ ; Emmanuel n'en veut pas : « quand on
        lance le logiciel ou qu'on fait nouveau, je ne veux voir aucune pièce
        dans la scène »."""
        return Projet([])

    def formes(self) -> list[Forme]:
        return [e for e in self.etapes if isinstance(e, Forme)]

    def copie(self) -> "Projet":
        return Projet.depuis_dico(self.dico())

    def dico(self) -> dict:
        return {"neoforge": VERSION_FICHIER, "nom": self.nom,
                "etapes": [e.dico() for e in self.etapes],
                # lisible par la console 1.1 (qui ignore les arrondis)
                "primitives": [f.dico_console() for f in self.formes()]}

    @staticmethod
    def depuis_dico(d: dict) -> "Projet":
        if isinstance(d.get("etapes"), list):
            etapes = [etape_depuis_dico(x) for x in d["etapes"] if isinstance(x, dict)]
        else:                                           # projet de la console
            etapes = [Forme.depuis_dico(x) for x in d.get("primitives", [])
                      if isinstance(x, dict)]
        if _avant(str(d.get("neoforge", "1.0")), "2.1"):
            _rendre_les_cylindres_ronds(etapes)
        # Un fichier sans aucune forme donne une scène VIDE : on n'y ajoute plus
        # une pièce d'office, puisqu'une scène vide est désormais un état normal.
        return Projet(nettoyer_liens(etapes[:LIMITE_ETAPES]),
                      str(d.get("nom", "") or ""))
