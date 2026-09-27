# -*- coding: utf-8 -*-
"""Garde-fou thème clair / thème sombre pour neoForge.

« Veille bien à ce que tout ce qu'on a fait comme modification ces derniers
jours soit bien compatible entre thème clair et sombre. Hyper important. »
(Emmanuel, 2026-09-26.)

LE piège du projet : un widget créé puis oublié dans `refresh_theme` garde la
couleur qu'il avait à sa naissance. En thème sombre TEXT_LABEL vaut #2A5F8A,
en clair #777777 : un titre de section né en sombre restait donc bleu sur fond
clair. Le bouton Mesurer, lui, n'était dans aucune liste de style, d'où une
graisse qui ne ressemblait à rien et aucune surbrillance à l'enclenchement.

On ne vérifie pas le code, on vérifie le RÉSULTAT : on construit chaque
panneau en sombre, on bascule en clair, et on cherche ce qui porte encore une
couleur du thème d'avant. C'est l'audit décrit dans les notes du projet, fait
par la machine plutôt qu'à l'œil.
"""
import pytest

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def theme(monkeypatch):
    """Bascule de thème SANS toucher aux préférences de l'utilisateur :
    `switch()` écrit normalement dans ~/.neoslice/prefs.json."""
    from ui.styles.theme import MANAGER
    monkeypatch.setattr(MANAGER, "_save", lambda *_a, **_k: None)
    depart = MANAGER.name()
    yield MANAGER
    if MANAGER.name() != depart:
        MANAGER.switch(depart)


def _couleurs_visibles(widget):
    """Toutes les couleurs écrites dans les feuilles de style de l'arbre."""
    import re
    from PySide6.QtWidgets import QWidget
    trouvees = set()
    for enfant in [widget] + widget.findChildren(QWidget):
        trouvees.update(c.lower() for c in re.findall(r"#[0-9A-Fa-f]{6}",
                                                      enfant.styleSheet()))
    return trouvees


def _panneaux():
    from neoforge.ui.panneaux import Proprietes
    from neoforge.ui.pile import Pile
    from neoforge.ui.accueil import Accueil
    return [("Proprietes", Proprietes), ("Pile", Pile), ("Accueil", Accueil)]


@pytest.mark.parametrize("nom,classe", _panneaux(), ids=[n for n, _ in _panneaux()])
def test_rien_ne_garde_les_couleurs_du_theme_precedent(app, theme, nom, classe):
    from ui.styles.theme import _DARK, _LIGHT

    theme.switch("dark")
    panneau = classe()                      # né en SOMBRE
    panneau.refresh_theme()
    theme.switch("light")
    panneau.refresh_theme()                 # basculé en CLAIR

    visibles = _couleurs_visibles(panneau)
    # Les teintes propres au thème sombre, absentes du thème clair.
    du_sombre = {v.lower() for k, v in _DARK.items()
                 if isinstance(v, str) and v.startswith("#")
                 and str(_LIGHT.get(k, "")).lower() != v.lower()}
    residus = sorted(visibles & du_sombre)
    assert not residus, f"{nom} garde des couleurs du thème sombre : {residus}"


@pytest.mark.parametrize("nom,classe", _panneaux(), ids=[n for n, _ in _panneaux()])
def test_et_dans_l_autre_sens(app, theme, nom, classe):
    """Le sens clair vers sombre compte autant : c'est celui que la plupart
    des gens font, puisque neoSlice s'installe en sombre."""
    from ui.styles.theme import _DARK, _LIGHT

    theme.switch("light")
    panneau = classe()
    panneau.refresh_theme()
    theme.switch("dark")
    panneau.refresh_theme()

    visibles = _couleurs_visibles(panneau)
    du_clair = {v.lower() for k, v in _LIGHT.items()
                if isinstance(v, str) and v.startswith("#")
                and str(_DARK.get(k, "")).lower() != v.lower()}
    residus = sorted(visibles & du_clair)
    assert not residus, f"{nom} garde des couleurs du thème clair : {residus}"


def test_les_titres_de_section_se_recolorent(app, theme):
    """Le cas qui a servi de révélateur : ils figeaient leur couleur à la
    construction, et personne ne les reprenait."""
    from neoforge.ui import style as S
    from ui.styles.theme import _DARK, _LIGHT

    theme.switch("dark")
    titre = S.titre_section("FORMES")
    assert _DARK["TEXT_LABEL"].lower() in titre.styleSheet().lower()

    from PySide6.QtWidgets import QWidget, QVBoxLayout
    boite = QWidget()
    QVBoxLayout(boite).addWidget(titre)
    theme.switch("light")
    S.rhabiller(boite)
    feuille = titre.styleSheet().lower()
    assert _LIGHT["TEXT_LABEL"].lower() in feuille
    assert _DARK["TEXT_LABEL"].lower() not in feuille


def test_le_bouton_mesurer_est_habille_comme_les_autres():
    """Le défaut précis signalé : il n'était dans aucune liste de style, donc
    il gardait la palette par défaut de Qt."""
    from pathlib import Path
    viewer = (Path(__file__).resolve().parents[1] / "neoforge" / "ui" / "viewer.py")
    texte = viewer.read_text(encoding="utf-8")
    corps = texte[texte.index("def refresh_theme"):][:2500]
    assert "_btn_regle" in corps and "_boutons_mode" in corps
