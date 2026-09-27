# -*- coding: utf-8 -*-
"""Une coupe « garder les deux » donne DEUX pièces dans la liste de gauche.

Choix d'Emmanuel, question posée : « je suis censé retrouver deux pièces dans les
formes à gauche », et il a retenu deux lignes déplaçables séparément. Les deux
lignes pointent vers la MÊME étape, ce qui enfreint l'invariant habituel (une
ligne pour une étape) : c'est `Pile.partie()` qui dit laquelle des deux on tient.

Ce test construit un vrai widget, comme celui du panneau : c'est le seul moyen de
voir ce genre de défaut, aucun autre test ne bâtit d'interface."""
import pytest

from neoforge.projet.modele import Arrondi, Coupe, Forme


@pytest.fixture(scope="module")
def application():
    import os

    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    deja = QtWidgets.QApplication.instance()
    if deja is not None:
        yield deja
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        a = QtWidgets.QApplication([])
    except Exception as exc:
        pytest.skip(f"QApplication indisponible : {exc}")
    yield a


@pytest.fixture
def pile(application):
    from neoforge.ui.pile import Pile
    p = Pile()
    p.show()
    yield p
    p.hide()
    p.deleteLater()


def _cube():
    return Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])


class _Resultat:
    erreur = None
    detail: dict = {}


def _remplir(pile, etapes, selection=-1):
    pile.remplir(etapes, [_Resultat() for _ in etapes], selection)


def test_garder_les_deux_ajoute_DEUX_lignes(pile):
    _remplir(pile, [_cube(), Coupe(2, 10.0, "les_deux")])
    assert pile._liste.count() == 3          # la forme, puis ses deux morceaux
    assert pile._arrondis.count() == 1       # la découpe garde sa propre ligne


@pytest.mark.parametrize("garder", ["dessous", "dessus"])
def test_garder_un_seul_morceau_n_ajoute_rien(pile, garder):
    _remplir(pile, [_cube(), Coupe(2, 10.0, garder)])
    assert pile._liste.count() == 1


def test_une_coupe_masquee_n_ajoute_pas_de_morceau(pile):
    coupe = Coupe(2, 10.0, "les_deux")
    coupe.actif = False
    _remplir(pile, [_cube(), coupe])
    assert pile._liste.count() == 1


def test_les_deux_lignes_visent_la_MEME_etape(pile):
    _remplir(pile, [_cube(), Coupe(2, 10.0, "les_deux")])
    assert pile._index_formes == [0, 1, 1]
    assert pile._parties == ["", "bas", "haut"]


def test_la_pile_dit_QUEL_morceau_est_choisi(pile):
    _remplir(pile, [_cube(), Coupe(2, 10.0, "les_deux")])
    vus = []
    pile.selection_changee.connect(lambda i: vus.append((i, pile.partie())))
    for ligne, attendu in ((0, ""), (1, "bas"), (2, "haut")):
        pile._liste.setCurrentRow(ligne)
        assert pile.partie() == attendu
    assert vus[-1][0] == 1                   # l'étape reste celle de la coupe


def test_apres_un_recalcul_la_selection_reste_sur_le_BON_morceau(pile):
    """Les deux morceaux visent la même étape. Sans précaution, un recalcul
    replaçait la sélection sur le PREMIER des deux : l'application croyait tenir
    le bas alors qu'on tenait le haut, et c'est la mauvaise pièce qui bougeait
    (mesuré au pilote, dans la vraie fenêtre)."""
    etapes = [_cube(), Coupe(2, 10.0, "les_deux")]
    _remplir(pile, etapes)
    pile._liste.setCurrentRow(2)
    assert pile.partie() == "haut"

    _remplir(pile, etapes, selection=1)       # le recalcul refait toute la liste
    assert pile._liste.currentRow() == 2
    assert pile.partie() == "haut"


def test_sans_morceau_tenu_on_retombe_sur_la_premiere_ligne(pile):
    etapes = [_cube(), Coupe(2, 10.0, "les_deux")]
    _remplir(pile, etapes, selection=1)
    assert pile._liste.currentRow() == 1      # la partie du bas, faute de mieux


def test_deselectionner_oublie_le_morceau(pile):
    _remplir(pile, [_cube(), Coupe(2, 10.0, "les_deux")])
    pile._liste.setCurrentRow(2)
    assert pile.partie() == "haut"
    pile.deselectionner()
    assert pile.partie() == ""


def test_un_morceau_ne_porte_ni_oeil_ni_cadenas(pile):
    """Masquer un demi morceau n'a pas de sens : il n'existe que par sa coupe."""
    from neoforge.ui.pile import ROLE_FORME, ROLE_PARTIE

    _remplir(pile, [_cube(), Coupe(2, 10.0, "les_deux")])
    forme = pile._liste.item(0)
    morceau = pile._liste.item(2)
    assert forme.data(ROLE_FORME) and not forme.data(ROLE_PARTIE)
    assert morceau.data(ROLE_PARTIE) == "haut"
    assert not morceau.data(ROLE_FORME)


def test_les_arrondis_restent_dans_leur_section(pile):
    _remplir(pile, [_cube(), Arrondi("conge", 2.0, "toutes"),
                    Coupe(2, 10.0, "les_deux")])
    assert pile._liste.count() == 3          # la forme et les deux morceaux
    assert pile._arrondis.count() == 2       # l'arrondi et la découpe
