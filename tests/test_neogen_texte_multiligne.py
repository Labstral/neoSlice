# -*- coding: utf-8 -*-
"""La touche Entrée va à la ligne dans le texte d'un objet neoGen.

« Il serait bien également de pouvoir écrire sur plusieurs lignes. Faire en
sorte que la touche Entrée fonctionne pour aller à la ligne. » Puis, après un
premier correctif côté recette seulement : « je ne peux toujours pas aller à
la ligne dans le texte de la pancarte de porte » (Emmanuel, 2026-09-26).

Il fallait deux choses, et la première ne suffisait pas :
  1. le champ de saisie était un QLineEdit, qui ne peut PHYSIQUEMENT pas
     contenir un saut de ligne. Il est devenu un champ de trois lignes ;
  2. le moteur de texte ne coupait que sur la barre verticale. Un texte tapé
     avec Entrée arrivait donc comme une seule ligne contenant un caractère
     invisible.

La barre verticale continue de marcher : les deux donnent le MÊME dessin.
"""
import pytest

SAUT = chr(10)
RETOUR = chr(13)


# ── Le moteur de texte, partagé par tous les objets ────────────────────────
def _bornes(texte):
    from core.neogen.goodies import texte_multilignes
    return [round(v, 3) for v in texte_multilignes(texte, 10.0).bounds]


def test_entree_et_barre_donnent_le_meme_dessin():
    assert _bornes("NE PAS" + SAUT + "DERANGER") == _bornes("NE PAS|DERANGER")


def test_les_fins_de_ligne_windows_aussi():
    assert _bornes("A" + RETOUR + SAUT + "B") == _bornes("A|B")


def test_trois_lignes_sont_plus_hautes_que_deux():
    deux = _bornes("A" + SAUT + "B")
    trois = _bornes("A" + SAUT + "B" + SAUT + "C")
    assert trois[3] - trois[1] > deux[3] - deux[1]


def test_on_peut_melanger_les_deux_separateurs():
    assert _bornes("A" + SAUT + "B | C") == _bornes("A|B|C")


def test_un_texte_sans_rien_dedans_leve_toujours():
    """Le garde-fou des recettes s'appuie dessus : une pancarte sans texte ne
    doit pas appeler le moteur."""
    from core.neogen.goodies import texte_multilignes
    for vide in ("", "   ", "|", SAUT, " | " + SAUT):
        with pytest.raises(ValueError):
            texte_multilignes(vide, 10.0)


# ── Le champ de saisie ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_le_champ_retient_un_saut_de_ligne(app):
    from ui.components.neogen_dialog import _ChampTexte
    c = _ChampTexte()
    c.setText("NE PAS" + SAUT + "DERANGER")
    assert c.text() == "NE PAS" + SAUT + "DERANGER"
    assert c.text().count(SAUT) == 1


def test_la_touche_entree_ajoute_bien_une_ligne(app):
    """Le geste exact d'Emmanuel : taper, appuyer sur Entrée, retaper."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from ui.components.neogen_dialog import _ChampTexte
    c = _ChampTexte()
    c.show()
    QTest.keyClicks(c, "NE PAS")
    QTest.keyClick(c, Qt.Key_Return)
    QTest.keyClicks(c, "DERANGER")
    assert c.text() == "NE PAS" + SAUT + "DERANGER"


def test_le_champ_se_comporte_comme_un_champ_ordinaire(app):
    """Le reste du formulaire le lit avec text() et l'écrit avec setText() :
    il ne doit rien avoir à savoir de son type."""
    from ui.components.neogen_dialog import _ChampTexte
    c = _ChampTexte()
    assert callable(c.text) and callable(c.setText)
    assert callable(c.setPlaceholderText)


# ── Le formulaire réel ─────────────────────────────────────────────────────
def _panneau(app):
    from core.neogen import catalogue as C
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    return NeoGenPanel(), C


@pytest.mark.parametrize("objet", ["pancarte_porte", "porte_cle"])
def test_le_formulaire_pose_un_champ_multi_lignes(app, objet):
    from ui.components.neogen_dialog import _ChampTexte
    panneau, C = _panneau(app)
    entree = C.PAR_ID.get(objet)
    if entree is None:
        pytest.skip(f"{objet} absent du catalogue")
    form = panneau._construire_formulaire(entree)
    champs = form.findChildren(_ChampTexte)
    assert len(champs) == 1, objet
    assert champs[0].styleSheet(), "le champ doit suivre le thème"


def test_un_champ_de_LIEN_reste_sur_une_seule_ligne(app):
    """Une adresse web n'a pas de lignes : le QR code garde un champ simple."""
    from PySide6.QtWidgets import QLineEdit
    from ui.components.neogen_dialog import _ChampTexte
    panneau, C = _panneau(app)
    lien = next((e for e in C.PAR_ID.values() if e.get("texte") == "lien"), None)
    if lien is None:
        pytest.skip("aucun objet à lien dans le catalogue")
    form = panneau._construire_formulaire(lien)
    assert not form.findChildren(_ChampTexte)
    assert form.findChildren(QLineEdit)


# ── Bout en bout, sur la pancarte ──────────────────────────────────────────
def test_la_pancarte_se_construit_avec_un_texte_tape_a_la_main(app):
    """Exactement ce qui sortira du champ : un texte avec un vrai saut."""
    from core.neogen import catalogue as C
    from core.neogen import libre as L
    C.recharger_objets_module()
    if "pancarte_porte" not in C.PAR_ID:
        pytest.skip("pancarte absente du catalogue")
    piece = C.construire("pancarte_porte", {"texte": "NE PAS" + SAUT + "DERANGER"})
    assert L.verifier(piece) is None
    une_ligne = C.construire("pancarte_porte", {"texte": "NE PAS DERANGER"})
    assert abs(piece.volume - une_ligne.volume) > 1.0    # deux lignes, pas une
