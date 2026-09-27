# -*- coding: utf-8 -*-
"""La première forme de la pile peut enfin creuser.

« On ne peut pas creuser et garder l'intersection avec l'anneau. Il faut
changer cela pour que ce soit possible comme tous les autres objets »
(Emmanuel, 2026-09-26).

L'anneau n'y était pour rien : il se comportait exactement comme un cube. Le
vrai défaut est ailleurs. La PREMIÈRE forme de la pile est toujours de la
matière, c'est la règle du moteur, et ses boutons Creuser et Garder
l'intersection restaient donc grisés POUR TOUJOURS, même après avoir ajouté
une deuxième pièce. Quand on pose sa forme creuse en premier, ce qui arrive
tout le temps, on ne pouvait plus jamais s'en servir pour creuser.

Désormais, cliquer Creuser sur la première forme la DESCEND juste sous la
forme suivante : elle a enfin quelque chose à entamer. Le bouton ne reste
grisé que lorsqu'il n'y a réellement rien d'autre dans la pièce.
"""
import pytest

from neoforge.projet.modele import Arrondi, Forme, Projet


def _fenetre(etapes, selection=0):
    """La fenêtre SANS interface : on n'appelle que les trois méthodes en
    cause, avec de quoi les faire tourner."""
    from neoforge.ui.fenetre import FenetreNeoForge
    f = FenetreNeoForge.__new__(FenetreNeoForge)
    f._projet = Projet(list(etapes))
    f._selection = selection
    f._memoriser = lambda: None
    f._statut = lambda *_a, **_k: None
    return f


def _cube(x=0.0):
    return Forme("cube", "matiere", [x, 0, 10], [20.0, 20.0, 20.0])


def _anneau(x=0.0):
    f = Forme("anneau", "matiere", [x, 0, 2], [40.0, 40.0, 4.0])
    f.bord = 4.0
    return f


# ── Ce que le bouton propose ───────────────────────────────────────────────
def test_une_forme_toute_seule_ne_peut_rien_creuser():
    """Là, le refus est juste : il n'y a rien à entamer."""
    seule = _anneau()
    f = _fenetre([seule])
    assert f._est_premiere(seule)
    assert not f._peut_creuser(seule)


def test_la_premiere_forme_peut_creuser_des_qu_une_autre_existe():
    """LE défaut : elle restait grisée même avec une deuxième pièce."""
    anneau, cube = _anneau(), _cube(60.0)
    f = _fenetre([anneau, cube])
    assert f._est_premiere(anneau)        # elle est bien la première
    assert f._peut_creuser(anneau)        # et pourtant elle peut creuser


def test_une_forme_qui_n_est_pas_la_premiere_a_toujours_pu():
    anneau, cube = _anneau(), _cube(60.0)
    f = _fenetre([cube, anneau])
    assert f._peut_creuser(anneau)


def test_une_deuxieme_forme_masquee_ne_compte_pas():
    """Masquée, elle n'est pas dans la pièce : il n'y a toujours rien à
    creuser."""
    anneau, cube = _anneau(), _cube(60.0)
    cube.actif = False
    f = _fenetre([anneau, cube])
    assert not f._peut_creuser(anneau)


def test_un_arrondi_ne_compte_pas_comme_matiere():
    anneau = _anneau()
    f = _fenetre([anneau, Arrondi("conge", 2.0, "toutes")])
    assert not f._peut_creuser(anneau)


# ── Ce que le clic fait ────────────────────────────────────────────────────
def test_le_clic_descend_la_forme_sous_la_suivante():
    anneau, cube = _anneau(), _cube(60.0)
    f = _fenetre([anneau, cube])
    assert f._rendre_creusable(anneau) is True
    assert [e.forme for e in f._projet.etapes] == ["cube", "anneau"]
    assert f._selection == 1               # la sélection suit la forme


def test_la_forme_se_pose_JUSTE_APRES_la_premiere_matiere():
    """Et non tout en bas : elle doit creuser la pièce qui la précède, sans
    passer après des formes ajoutées plus tard."""
    anneau = _anneau()
    f = _fenetre([anneau, _cube(60.0), _cube(120.0)])
    assert f._rendre_creusable(anneau) is True
    assert [e.forme for e in f._projet.etapes] == ["cube", "anneau", "cube"]


def test_rien_a_descendre_quand_la_forme_est_seule():
    seule = _anneau()
    f = _fenetre([seule])
    assert f._rendre_creusable(seule) is False
    assert [e.forme for e in f._projet.etapes] == ["anneau"]


def test_toutes_les_formes_se_comportent_pareil():
    """« comme tous les autres objets » : l'anneau n'avait rien de spécial, et
    la correction ne doit privilégier aucune forme."""
    for nom in ("cube", "cylindre", "anneau", "cadre", "engrenage", "taraudage",
                "sphere", "prisme"):
        premiere = Forme(nom, "matiere", [0, 0, 10], [20.0, 20.0, 20.0])
        f = _fenetre([premiere, _cube(60.0)])
        assert f._peut_creuser(premiere), nom
        assert f._rendre_creusable(premiere) is True, nom
        assert f._projet.etapes[1] is premiere, nom
