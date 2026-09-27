# -*- coding: utf-8 -*-
"""Changer d'unité ne doit JAMAIS toucher à la pièce.

Ce test existe parce que le bug est arrivé. Les compteurs affichent encore
l'ancienne unité quand on change leurs décimales : 1,181 pouce se réarrondissait
à 1,2, `setDecimals` émettait `valueChanged`, la saisie se croyait modifiée et
réécrivait 1,2 MILLIMÈTRE dans le modèle. Une pièce de 30 mm tombait ainsi à
1,2 mm pour avoir simplement changé d'unité.

Les 640 autres tests n'ont rien vu : aucun ne construisait de widget. C'est
exactement le trou par lequel ce bug est passé, d'où ce test qui bâtit le panneau
pour de vrai."""
import pytest

from neoforge.projet import unites as U
from neoforge.projet.modele import Coupe, Forme


@pytest.fixture(scope="module")
def application():
    """Une QApplication, réutilisée si elle existe déjà (Qt n'en accepte qu'une).

    Plateforme HORS ÉCRAN quand c'est nous qui la créons : le panneau doit être
    affiché (voir `panneau`) et aucune fenêtre ne doit surgir pendant la suite."""
    import os

    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    deja = QtWidgets.QApplication.instance()
    if deja is not None:
        yield deja
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        a = QtWidgets.QApplication([])
    except Exception as exc:                       # pas d'affichage disponible
        pytest.skip(f"QApplication indisponible : {exc}")
    yield a


@pytest.fixture
def panneau(application):
    """Le panneau de droite, seul. L'unité courante est remise après le test.

    ⚠️ Il est AFFICHÉ : `_valeurs_changees` n'écrit une dimension que si son
    compteur est visible (les axes inutilisés sont masqués selon la forme). Sur un
    panneau jamais affiché, toute saisie de dimension est ignorée et le test
    passerait à côté de ce qu'il prétend vérifier."""
    from neoforge.ui.panneaux import Proprietes
    avant = U.courante()
    p = Proprietes()
    p.show()
    yield p
    U.definir(avant)
    p.hide()
    p.deleteLater()


def _cube():
    return Forme("cube", "matiere", [0.0, 0.0, 15.0], [30.0, 30.0, 30.0],
                 [0.0, 0.0, 0.0])


@pytest.mark.parametrize("chemin", [
    ("cm",), ("in",), ("cm", "in", "mm"), ("in", "mm", "in", "cm", "mm"),
])
def test_changer_d_unite_ne_touche_PAS_a_la_piece(panneau, chemin):
    """Le cœur de l'affaire : seul l'affichage change, jamais le modèle."""
    cube = _cube()
    panneau.set_etape(cube)
    depart = list(cube.dim), list(cube.pos)
    for unite in chemin:
        U.definir(unite)
        panneau.definir_unite(unite)
        assert (list(cube.dim), list(cube.pos)) == depart, \
            f"la pièce a bougé en passant en {unite}"


def test_les_valeurs_s_affichent_dans_l_unite_choisie(panneau):
    cube = _cube()
    panneau.set_etape(cube)
    assert panneau._dim[0].value() == pytest.approx(30.0)

    U.definir("cm")
    panneau.definir_unite("cm")
    assert panneau._dim[0].value() == pytest.approx(3.0)
    assert panneau._dim[0].decimals() == 2

    U.definir("in")
    panneau.definir_unite("in")
    assert panneau._dim[0].value() == pytest.approx(1.181, abs=5e-4)
    assert panneau._dim[0].decimals() == 3


def test_une_cote_saisie_en_pouces_est_rangee_en_millimetres(panneau):
    cube = _cube()
    panneau.set_etape(cube)
    U.definir("in")
    panneau.definir_unite("in")
    panneau._dim[0].setValue(2.0)
    panneau._valeurs_changees()
    assert cube.dim[0] == pytest.approx(50.8)


def test_la_position_d_une_coupe_suit_l_unite(panneau):
    coupe = Coupe(2, 25.4, "dessous")
    panneau.set_etape(coupe)
    assert panneau._pos_coupe.value() == pytest.approx(25.4)
    U.definir("in")
    panneau.definir_unite("in")
    assert panneau._pos_coupe.value() == pytest.approx(1.0, abs=5e-4)
    assert coupe.position == pytest.approx(25.4)        # le modèle n'a pas bougé
    panneau._pos_coupe.setValue(0.5)
    panneau._valeurs_changees()
    assert coupe.position == pytest.approx(12.7)


def test_le_rayon_d_un_arrondi_est_une_longueur_lui_aussi(panneau):
    from neoforge.projet.modele import Arrondi
    arrondi = Arrondi("conge", 25.4, "toutes")
    panneau.set_etape(arrondi)
    U.definir("in")
    panneau.definir_unite("in")
    assert panneau._taille.value() == pytest.approx(1.0, abs=5e-4)
    assert arrondi.taille == pytest.approx(25.4)


def test_la_rotation_reste_en_degres(panneau):
    """Un angle n'est pas une longueur : il ne doit surtout pas être converti."""
    cube = _cube()
    cube.rot = [45.0, 0.0, 0.0]
    panneau.set_etape(cube)
    for unite in ("cm", "in", "mm"):
        U.definir(unite)
        panneau.definir_unite(unite)
        assert panneau._rot[0].value() == pytest.approx(45.0)
        assert cube.rot[0] == pytest.approx(45.0)


def test_les_bornes_restent_atteignables_dans_chaque_unite(panneau):
    """Une pièce peut toujours faire 1000 mm : soit 39,370 pouces, et non 1000
    pouces. Les bornes sont gardées en millimètres puis reconverties."""
    panneau.set_etape(_cube())
    U.definir("in")
    panneau.definir_unite("in")
    assert panneau._dim[0].maximum() == pytest.approx(1000.0 / 25.4, abs=1e-3)
    U.definir("mm")
    panneau.definir_unite("mm")
    assert panneau._dim[0].maximum() == pytest.approx(1000.0)
