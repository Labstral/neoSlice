# -*- coding: utf-8 -*-
"""Les mesures s'affichent dans l'unité choisie, le modèle reste en millimètres.

Demande d'Emmanuel : mm par défaut, un réglage pour en changer, et les unités
les plus répandues dans le monde pour que neoForge serve partout."""
import pytest

from neoforge.projet import unites as U


def test_le_millimetre_est_l_unite_par_defaut():
    """C'est la demande explicite : « que par défaut les mesures apparaissent en
    mm et non en cm »."""
    assert U.DEFAUT == "mm"
    assert U.facteur("mm") == 1.0
    assert U.symbole("mm") == "mm" and U.symbole_volume("mm") == "mm³"


def test_le_pouce_est_propose_pour_les_pays_qui_l_emploient():
    assert "in" in U.UNITES
    assert U.facteur("in") == 25.4


@pytest.mark.parametrize("unite", ["mm", "cm", "in"])
def test_aller_et_revenir_ne_perd_rien(unite):
    """Le modèle reste en millimètres : la conversion doit être réversible, sans
    quoi une cote saisie se déplacerait à chaque affichage."""
    for mm in (0.1, 1.0, 12.5, 30.0, 256.0, 999.9):
        assert U.depuis(U.vers(mm, unite), unite) == pytest.approx(mm, rel=1e-12)


def test_les_conversions_tombent_juste():
    assert U.vers(25.4, "in") == pytest.approx(1.0)
    assert U.vers(30.0, "cm") == pytest.approx(3.0)
    assert U.depuis(2.0, "cm") == pytest.approx(20.0)
    assert U.depuis(1.0, "in") == pytest.approx(25.4)


def test_une_unite_inconnue_retombe_sur_le_millimetre():
    """Un fichier de réglages abîmé ou plus ancien ne doit pas empêcher la
    fenêtre de s'ouvrir."""
    for mauvaise in ("", "pouce", "yard", None, "MM"):
        assert U.connue(mauvaise) == "mm"
        assert U.facteur(mauvaise) == 1.0
        assert U.symbole(mauvaise) == "mm"


def test_assez_de_decimales_pour_viser_le_millimetre():
    """Au pouce, un dixième de millimètre vaut 0,004 pouce : sans trois
    décimales, on ne pourrait plus régler finement une pièce."""
    assert U.decimales("mm") == 1
    assert U.decimales("cm") == 2
    assert U.decimales("in") == 3
    assert U.vers(0.1, "in") == pytest.approx(0.00394, abs=1e-5)


def test_le_texte_affiche_le_bon_nombre_de_decimales():
    assert U.texte(30.0, "mm") == "30.0"
    assert U.texte(30.0, "cm") == "3.00"
    assert U.texte(25.4, "in") == "1.000"
    assert U.avec_symbole(30.0, "cm") == "3.00 cm"


def test_les_cotes_dessinees_restent_courtes():
    """Dans la vue, la place manque : on grave « 30 » et non « 30,0 »."""
    assert U.court(30.0, "mm") == "30"
    assert U.court(12.5, "mm") == "12.5"
    assert U.court(30.0, "cm") == "3"
    assert U.court(25.4, "in") == "1"


def test_le_volume_suit_l_unite():
    """Un cube de 30 mm de côté : 27 000 mm³, soit 27 cm³, soit 1,65 pouce cube.
    C'est ce « cm » du volume qu'Emmanuel voyait alors qu'il voulait des mm."""
    assert U.volume(27000.0, "mm") == "27000"
    assert U.volume(27000.0, "cm") == "27.00"
    assert U.volume(27000.0, "in") == "1.65"        # 27000 / 25,4³


def test_le_volume_en_millimetres_cubes_n_a_pas_de_decimale():
    """Les nombres y sont gros : une décimale n'apprendrait rien."""
    assert "." not in U.volume(123456.789, "mm")


def test_le_pas_des_compteurs_reste_maniable():
    """Un pas d'un millimètre reste un pas d'environ un millimètre dans les
    autres unités : sinon un clic sur la flèche ferait bondir la pièce."""
    for unite in ("mm", "cm", "in"):
        assert 0.8 <= U.pas(unite) * U.facteur(unite) <= 1.5
