# -*- coding: utf-8 -*-
"""Trou taraudé M2 à M12 : un VRAI pas de vis, pas un trou lisse.

« Ajouter aussi dans les formes un trou avec un pas de vis, de toutes les
tailles M2 jusqu'à M12 » (Emmanuel, 2026-09-26).

L'outil creusé dans la pièce a la forme d'une vis : un noyau cylindrique au
diamètre intérieur, plus un filet hélicoïdal qui monte au diamètre nominal.

⚠️ LE piège, mesuré : si le filet EFFLEURE le noyau au lieu d'y plonger, les
deux surfaces sont tangentes et le booléen part en vrille. Fusion à 7,4 s,
ratée sur plusieurs diamètres (elle ne rendait que le noyau, donc un trou
lisse). Filet plongeant à 55 % du rayon : 0,3 à 2,4 s et un solide valide
partout. Ces tests vérifient qu'on n'y revient pas.
"""
import numpy as np
import pytest
import trimesh

from neoforge.noyau import maillage as M, occ as O
from neoforge.noyau.construction import Constructeur
from neoforge.noyau.primitives import solide
from neoforge.projet import ergonomie as E
from neoforge.projet.mesures import cotes
from neoforge.projet.modele import Forme, Projet

TAILLES = list(E.TARAUDAGES)


def _outil(taille, profondeur=10.0):
    diametre, pas = E.TARAUDAGES[taille]
    f = Forme("taraudage", "creux", [0.0, 0.0, profondeur / 2.0],
              [diametre + E.JEU_TARAUDAGE, diametre + E.JEU_TARAUDAGE, profondeur])
    f.pas = pas
    return f, diametre, pas


@pytest.mark.parametrize("taille", TAILLES)
def test_l_outil_est_un_solide_valide(taille):
    """Un outil invalide rend un perçage faux, parfois de volume NÉGATIF."""
    f, diametre, _pas = _outil(taille)
    s = solide(f)
    assert O.valide(s), taille
    assert O.volume(s) > 0.0, taille
    V, _F = M.trianguler(s)
    etendue = V.max(0) - V.min(0)
    attendu = diametre + E.JEU_TARAUDAGE
    assert etendue[0] == pytest.approx(attendu, abs=0.05), taille
    assert etendue[1] == pytest.approx(attendu, abs=0.05), taille


@pytest.mark.parametrize("taille", ["M2", "M3", "M6", "M12"])
def test_le_trou_est_vraiment_filete(taille):
    """On sonde une ligne verticale entre le fond du filet et son sommet :
    la matière doit alterner deux fois par tour. Un trou lisse ne donnerait
    aucune alternance."""
    profondeur = 10.0
    f, diametre, pas = _outil(taille, profondeur)
    p = Projet.nouveau()
    p.etapes = [Forme("cube", "matiere", [0, 0, profondeur / 2.0],
                      [30.0, 30.0, profondeur]), f]
    res = Constructeur().construire(p)
    assert res[-1].erreur is None, res[-1].erreur
    V, F = M.trianguler(res[-1].forme)
    maillee = trimesh.Trimesh(vertices=V, faces=F)
    rayon = (diametre + E.JEU_TARAUDAGE) / 2.0 - 1.0825 * pas / 4.0
    zs = np.linspace(1.0, profondeur - 1.0, 400)
    dedans = maillee.contains(
        np.column_stack([np.full_like(zs, rayon), np.zeros_like(zs), zs]))
    alternances = int(np.sum(dedans[1:] != dedans[:-1]))
    tours = (profondeur - 2.0) / pas
    assert alternances >= max(2, int(tours * 1.5)), (taille, alternances, tours)


@pytest.mark.parametrize("taille", ["M3", "M6", "M12"])
def test_le_percage_enleve_bien_de_la_matiere(taille):
    profondeur = 10.0
    f, diametre, _pas = _outil(taille, profondeur)
    p = Projet.nouveau()
    plein = Forme("cube", "matiere", [0, 0, profondeur / 2.0],
                  [30.0, 30.0, profondeur])
    p.etapes = [plein]
    avant = O.volume(Constructeur().construire(p)[-1].forme)
    p.etapes = [plein, f]
    res = Constructeur().construire(p)
    apres = O.volume(res[-1].forme)
    creuse = avant - apres
    # entre le trou au diamètre intérieur et le trou au diamètre nominal
    r_mini = (diametre + E.JEU_TARAUDAGE) / 2.0 * 0.8
    r_maxi = (diametre + E.JEU_TARAUDAGE) / 2.0
    assert np.pi * r_mini ** 2 * profondeur * 0.8 < creuse
    assert creuse < np.pi * r_maxi ** 2 * profondeur * 1.1


def test_le_diametre_recoit_le_jeu_d_impression():
    """Une vis M6 ne se visse pas dans un trou sorti à 6,00 : la matière
    s'écrase et le filet casse."""
    p = Projet.nouveau()
    f = E.trou_taraude(p, "M6", None)
    assert f.dim[0] == pytest.approx(6.0 + E.JEU_TARAUDAGE)
    assert f.op == "creux"
    assert f.pas == pytest.approx(1.0)


@pytest.mark.parametrize("taille,pas", [("M2", 0.4), ("M3", 0.5), ("M6", 1.0),
                                        ("M10", 1.5), ("M12", 1.75)])
def test_les_pas_sont_ceux_de_la_visserie(taille, pas):
    assert E.TARAUDAGES[taille][1] == pytest.approx(pas)


def test_les_neuf_tailles_sont_proposees():
    assert TAILLES == ["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12"]


def test_seule_la_profondeur_se_tire_a_la_souris():
    """Le diamètre est celui de la visserie : le tirer rendrait le trou
    inutilisable avec une vis normalisée."""
    f, _d, _p = _outil("M6")
    assert [c.axe for c in cotes(f)] == [2]


def test_l_apercu_ne_se_reconstruit_pas_pendant_le_geste():
    """Un filetage coûte des secondes à construire : pendant qu'on tire la
    profondeur, l'aperçu s'étire, et le vrai pas revient au relâchement."""
    from neoforge.projet.mesures import echelle_apercu
    f, _d, _p = _outil("M6", 10.0)
    f.dim[2] = 20.0
    assert echelle_apercu(f, [6.2, 6.2, 10.0]) == pytest.approx((1.0, 1.0, 2.0))


def test_le_pas_est_enregistre(tmp_path):
    from neoforge.projet import nfg
    p = Projet.nouveau()
    f, _d, _pas = _outil("M8", 12.0)
    p.etapes = [f]
    relu = nfg.lire(nfg.ecrire(p, tmp_path / "vis.nfg"))
    assert relu.etapes[0].pas == pytest.approx(1.25)
    assert relu.etapes[0].forme == "taraudage"


def test_les_libelles_existent_dans_les_cinq_langues():
    from neoforge.ui.textes import LANGUES
    for code, mots in LANGUES.items():
        for cle in ("taraudage", "trou_taraude", "pas_de_vis", "profondeur_trou"):
            assert mots.get(cle), f"{code} : {cle} manquant"
