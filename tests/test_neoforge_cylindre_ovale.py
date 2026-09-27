# -*- coding: utf-8 -*-
"""Le cylindre a DEUX diamètres : il peut être ovale.

« Pour le cylindre il serait bien de pouvoir le déformer en ovale si on le
souhaite » (Emmanuel, 2026-09-26). `dim[1]` ne servait à rien pour le cylindre
et gardait la valeur de sa création, 20 mm : il porte désormais le second
diamètre. Un fichier plus ancien deviendrait donc ovale tout seul, d'où la
version de fichier 2.1 et sa remise à plat au chargement.

La forme est une VRAIE ellipse (gp_Elips poussée sur la hauteur), pas un cercle
aplati par une mise à l'échelle : la surface reste exacte, donc les arrondis,
les booléens et l'export aussi.
"""
import pytest

from neoforge.noyau import maillage as M
from neoforge.noyau.construction import Constructeur
from neoforge.projet.mesures import cotes
from neoforge.projet.modele import Arrondi, Forme, Projet, VERSION_FICHIER


def _boite(etapes):
    p = Projet.nouveau()
    p.etapes = list(etapes)
    res = Constructeur().construire(p)
    assert [r.erreur for r in res] == [None] * len(etapes), [r.erreur for r in res]
    V, _F = M.trianguler(res[-1].forme)
    return V.max(0) - V.min(0)


@pytest.mark.parametrize("dx,dy,h", [(40, 20, 30), (20, 40, 30), (60, 12, 8)])
def test_le_cylindre_sort_aux_deux_diametres(dx, dy, h):
    b = _boite([Forme("cylindre", "matiere", [0, 0, h / 2.0],
                      [float(dx), float(dy), float(h)])])
    assert b[0] == pytest.approx(dx, abs=0.05)
    assert b[1] == pytest.approx(dy, abs=0.05)
    assert b[2] == pytest.approx(h, abs=0.05)


def test_diametres_egaux_donnent_toujours_un_rond():
    """Le cas par défaut ne doit pas changer d'un cheveu."""
    b = _boite([Forme("cylindre", "matiere", [0, 0, 15], [30.0, 30.0, 30.0])])
    assert b[0] == pytest.approx(30.0, abs=0.05)
    assert b[1] == pytest.approx(30.0, abs=0.05)


def test_un_ovale_se_perce_et_s_arrondit():
    """Une ellipse est une surface à part : on vérifie que le noyau sait encore
    la creuser et l'arrondir, sinon la forme serait inutilisable."""
    b = _boite([Forme("cylindre", "matiere", [0, 0, 15], [50.0, 25.0, 30.0]),
                Forme("cylindre", "creux", [0, 0, 15], [12.0, 12.0, 60.0]),
                Arrondi("conge", 2.0, "toutes")])
    assert b[0] == pytest.approx(50.0, abs=0.05)
    assert b[1] == pytest.approx(25.0, abs=0.05)


def test_trois_poignees_de_cote_sur_un_ovale():
    """Les deux diamètres se tirent à la souris dans la vue 3D, pas seulement
    dans le panneau."""
    f = Forme("cylindre", "matiere", [0, 0, 15], [40.0, 20.0, 30.0])
    assert [c.axe for c in cotes(f)] == [0, 1, 2]
    assert [c.libelle for c in cotes(f)] == ["Ø40", "Ø20", "30"]
    assert f.demi_etendue() == [20.0, 10.0, 15.0]


# ── Compatibilité des fichiers déjà enregistrés ─────────────────────────────
def _fichier(version, dim):
    return {"neoforge": version, "nom": "essai", "etapes": [
        {"type": "forme", "forme": "cylindre", "op": "matiere",
         "pos": [0, 0, 15], "dim": list(dim), "rot": [0, 0, 0], "actif": True}]}


def test_version_de_fichier_relevee():
    assert VERSION_FICHIER == "2.1"


def test_un_vieux_fichier_reste_rond():
    """LE piège de cette fonctionnalité : un cylindre de Ø60 enregistré avant la
    2.1 porte dim[1] = 20, la valeur de sa création. Sans remise à plat il
    rouvrirait en ovale 60 × 20, et la pièce de l'utilisateur serait abîmée."""
    p = Projet.depuis_dico(_fichier("2.0", [60.0, 20.0, 30.0]))
    assert p.etapes[0].dim == [60.0, 60.0, 30.0]


def test_un_fichier_sans_version_reste_rond():
    p = Projet.depuis_dico({"nom": "vieux", "etapes": _fichier("2.0", [45.0, 20.0, 10.0])["etapes"]})
    assert p.etapes[0].dim == [45.0, 45.0, 10.0]


def test_un_fichier_2_1_garde_son_ovale():
    p = Projet.depuis_dico(_fichier("2.1", [60.0, 25.0, 30.0]))
    assert p.etapes[0].dim == [60.0, 25.0, 30.0]


def test_aller_retour_sur_disque_conserve_l_ovale(tmp_path):
    from neoforge.projet import nfg
    p = Projet.nouveau()
    p.etapes = [Forme("cylindre", "matiere", [0, 0, 15], [60.0, 25.0, 30.0])]
    chemin = nfg.ecrire(p, tmp_path / "ovale.nfg")
    relu = nfg.lire(chemin)
    assert relu.etapes[0].dim == [60.0, 25.0, 30.0]


def test_les_autres_formes_ne_bougent_pas():
    """La remise à plat ne vise QUE les cylindres : un cône a toujours eu deux
    diamètres, un tore aussi."""
    d = {"neoforge": "2.0", "nom": "x", "etapes": [
        {"type": "forme", "forme": "cone", "op": "matiere", "pos": [0, 0, 5],
         "dim": [30.0, 10.0, 20.0], "rot": [0, 0, 0], "actif": True},
        {"type": "forme", "forme": "tore", "op": "matiere", "pos": [0, 0, 5],
         "dim": [30.0, 8.0, 8.0], "rot": [0, 0, 0], "actif": True}]}
    p = Projet.depuis_dico(d)
    assert p.etapes[0].dim == [30.0, 10.0, 20.0]
    assert p.etapes[1].dim == [30.0, 8.0, 8.0]
