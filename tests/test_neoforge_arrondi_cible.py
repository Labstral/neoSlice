# -*- coding: utf-8 -*-
"""Un arrondi VISE un objet : il ne touche que lui et sa descendance.

Retour d'Emmanuel (2026-09-13) : « quand je fais apparaître une nouvelle forme,
ses arêtes sont arrondies parce que dans la pièce précédente j'ai mis arrondir
toutes les arêtes ». Désormais « toutes les arêtes » veut dire toutes celles de
l'objet choisi, et rien d'autre."""
import pytest

from neoforge.noyau import occ as O
from neoforge.noyau.construction import Constructeur
from neoforge.projet.modele import Arrondi, Forme, Projet, groupe_de


def _pieces():
    """Un socle plat et un plot posé dessus, deux objets bien distincts."""
    return (Forme("cube", "matiere", [0, 0, 5], [40, 40, 10]),
            Forme("cube", "matiere", [0, 0, 16], [12, 12, 12]))


def _volume(etapes) -> float:
    resultats = Constructeur().construire(Projet(list(etapes)))
    assert resultats[-1].erreur is None, resultats[-1].erreur
    return O.volume(resultats[-1].forme)


def test_un_arrondi_vise_enleve_moins_que_s_il_prenait_tout():
    socle, plot = _pieces()
    vise = _volume([socle, plot, Arrondi("conge", 1.0, "toutes", cible=plot.ident)])
    socle2, plot2 = _pieces()
    tout = _volume([socle2, plot2, Arrondi("conge", 1.0, "toutes")])
    brut = _volume(_pieces())
    # Arrondir TOUT ronge aussi les arêtes du socle : il reste moins de matière
    # que si l'on ne vise que le plot, lui même moins que la pièce brute.
    assert tout < vise < brut


def test_une_forme_ajoutee_apres_n_est_pas_arrondie():
    """Le cas exact d'Emmanuel : la nouvelle forme doit rester vive."""
    socle, plot = _pieces()
    arrondi = Arrondi("conge", 1.0, "toutes", cible=plot.ident)
    avant = _volume([socle, plot, arrondi])
    nouvelle = Forme("cube", "matiere", [26, 0, 4], [8, 8, 8])
    apres = _volume([socle, plot, nouvelle, arrondi])
    seule = _volume([Forme("cube", "matiere", [26, 0, 4], [8, 8, 8])])
    # La nouvelle forme s'ajoute ENTIÈRE : rien ne lui a été rogné.
    assert apres == pytest.approx(avant + seule, rel=1e-6)


def test_la_cible_emmene_ses_enfants():
    socle, plot = _pieces()
    plot.parent = socle.ident
    assert [f.ident for f in groupe_de([socle, plot], socle.ident)] \
        == [socle.ident, plot.ident]
    assert groupe_de([socle, plot], plot.ident) == [plot]
    assert groupe_de([socle, plot], "") == []          # aucune cible : toute la pièce


def test_la_cible_survit_a_l_enregistrement():
    socle, plot = _pieces()
    p = Projet([socle, plot, Arrondi("conge", 1.0, "toutes", cible=plot.ident)])
    relu = Projet.depuis_dico(p.dico())
    assert relu.etapes[2].cible == relu.etapes[1].ident


def test_une_cible_disparue_ne_casse_rien():
    """L'objet visé a été supprimé : l'arrondi ne doit ni planter ni bloquer."""
    socle, plot = _pieces()
    resultats = Constructeur().construire(
        Projet([socle, Arrondi("conge", 1.0, "toutes", cible=plot.ident)]))
    assert resultats[-1].forme is not None
