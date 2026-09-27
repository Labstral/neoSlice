# -*- coding: utf-8 -*-
"""Où se pose une nouvelle étape, et ce qu'elle voit.

Trois retours d'Emmanuel, une seule et même cause : une étape neuve s'insérait
juste après la sélection, donc AVANT ce qui la concerne.

1. « Quand je découpe un objet, le plan de coupe reste dans la scène ; quand je
   place un nouvel objet à côté, il se retrouve lui aussi coupé. »
2. « Quand je clique sur arrondir les arêtes sur un objet que j'ai coupé, la
   pièce revient à son état d'origine et on la voit entière. »
3. « Quand je clique sur l'objet parent pour arrondir les arêtes créées par les
   objets qui ont creusé les trous, tous les trous disparaissent. »"""
import pytest

from neoforge.noyau import occ as O
from neoforge.noyau.construction import Constructeur
from neoforge.projet import ergonomie as E
from neoforge.projet.modele import Arrondi, Coupe, Forme, Projet


def _socle():
    return Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])


def _trou(pos=(0, 0, 15)):
    return Forme("cylindre", "creux", list(pos), [10, 10, 60])


# ── Une scène neuve est vide ──────────────────────────────────────────────
def test_une_scene_neuve_est_vide():
    """« Quand on lance le logiciel ou qu'on fait nouveau, je ne veux voir
    aucune pièce dans la scène. »"""
    assert Projet.nouveau().etapes == []


def test_un_fichier_sans_forme_reste_vide():
    """On n'ajoute plus une pièce d'office : le vide est un état normal."""
    assert Projet.depuis_dico({"etapes": []}).etapes == []
    assert Projet.depuis_dico({"primitives": []}).etapes == []


def test_un_projet_vide_se_construit_sans_broncher():
    assert Constructeur().construire(Projet([])) == []


# ── Rien ne s'insère avant une découpe ────────────────────────────────────
@pytest.mark.parametrize("selection", [-1, 0, 1, 2])
def test_rien_ne_s_insere_avant_une_coupe(selection):
    etapes = [_socle(), Coupe(2, 10.0, "dessous"), _socle()]
    assert E.position_insertion(etapes, selection) >= 2


def test_sans_coupe_la_regle_ne_change_pas():
    """La règle d'avant reste vraie quand il n'y a aucune découpe."""
    etapes = [_socle(), _socle(), _socle()]
    assert E.position_insertion(etapes, 0) == 1
    assert E.position_insertion(etapes, -1) == 3


def test_une_forme_ajoutee_apres_une_coupe_n_est_PAS_coupee():
    """Le plan ne doit plus trancher ce qui arrive après lui."""
    etapes = [_socle(), Coupe(2, 10.0, "dessous")]
    ou = E.position_insertion(etapes, 0)
    etapes.insert(ou, Forme("cube", "matiere", [60, 0, 15], [30, 30, 30]))
    r = Constructeur().construire(Projet(etapes))[-1]
    assert r.erreur is None
    # Le socle coupé (30 × 30 × 10) plus le cube neuf, entier.
    assert O.volume(r.forme) == pytest.approx(30 * 30 * 10 + 27000, rel=1e-6)


# ── Un arrondi voit la pièce ASSEMBLÉE ────────────────────────────────────
def _base_de_l_arrondi(etapes) -> object:
    """Ce que le mode « choix des arêtes » affiche : l'état AVANT l'arrondi."""
    resultats = Constructeur().construire(Projet(etapes))
    i = next(k for k, e in enumerate(etapes) if isinstance(e, Arrondi))
    return resultats[i - 1].forme


def test_un_arrondi_en_fin_de_pile_voit_les_TROUS():
    """Posé après le parent mais avant ses enfants, il montrait la pièce pleine
    et n'offrait aucune arête de trou (retour d'Emmanuel)."""
    perce = [_socle(), _trou()]
    plein = O.volume(Constructeur().construire(Projet([_socle()]))[-1].forme)

    en_fin = _base_de_l_arrondi(perce + [Arrondi("conge", 2.0, "liste")])
    assert O.volume(en_fin) < plein                 # le trou est bien là

    # L'ancien placement, pour montrer ce qui n'allait pas.
    au_milieu = _base_de_l_arrondi([_socle(), Arrondi("conge", 2.0, "liste"),
                                    _trou()])
    assert O.volume(au_milieu) == pytest.approx(plein)


def test_les_aretes_du_trou_sont_proposees():
    """C'est tout l'objet de la demande : pouvoir arrondir le bord d'un trou."""
    from neoforge.noyau import aretes as A

    base = _base_de_l_arrondi([_socle(), _trou(), Arrondi("conge", 2.0, "liste")])
    candidates = A.aretes_arrondissables(base)
    # Les bords du trou sont des cercles : leur boîte fait le diamètre du
    # cylindre, jamais les 30 mm du socle.
    cercles = 0
    for e in candidates:
        (x0, y0, _z0), (x1, y1, _z1) = O.boite(e)
        if abs((x1 - x0) - 10.0) < 0.5 and abs((y1 - y0) - 10.0) < 0.5:
            cercles += 1
    assert cercles >= 1


def test_un_arrondi_apres_une_coupe_voit_la_piece_COUPEE():
    """« La pièce revient à son état d'origine et on la voit entière. »"""
    base = _base_de_l_arrondi([_socle(), Coupe(2, 10.0, "dessous"),
                               Arrondi("conge", 2.0, "liste")])
    assert O.volume(base) == pytest.approx(30 * 30 * 10, rel=1e-6)
