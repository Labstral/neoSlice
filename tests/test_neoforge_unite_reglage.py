# -*- coding: utf-8 -*-
"""Le réglage d'unité : retenu d'une fois sur l'autre, sans rien écraser.

Le fichier de préférences est PARTAGÉ avec neoSlice, qui y garde notamment le
thème : écrire l'unité ne doit donc jamais le remplacer en entier."""
import json

import pytest

from neoforge.projet import nfg
from neoforge.projet import unites as U


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    """Un fichier de préférences à nous, et l'unité courante remise après coup."""
    chemin = tmp_path / "prefs.json"
    monkeypatch.setattr(nfg, "PREFS", chemin)
    avant = U.courante()
    yield chemin
    U.definir(avant)


def test_sans_fichier_c_est_le_millimetre(prefs):
    assert not prefs.exists()
    assert nfg.unite() == "mm"


def test_l_unite_survit_a_la_fermeture(prefs):
    nfg.definir_unite("in")
    assert nfg.unite() == "in"
    nfg.definir_unite("cm")
    assert nfg.unite() == "cm"


def test_ecrire_l_unite_ne_touche_pas_au_theme(prefs):
    """Le fichier appartient aussi à neoSlice : on n'écrase que notre clé."""
    prefs.write_text(json.dumps({"theme": "light", "autre": 12}), encoding="utf-8")
    nfg.definir_unite("cm")
    relu = json.loads(prefs.read_text(encoding="utf-8"))
    assert relu["theme"] == "light" and relu["autre"] == 12
    assert relu["neoforge_unite"] == "cm"


def test_un_fichier_abime_n_empeche_pas_l_ouverture(prefs):
    prefs.write_text("{ceci n'est pas du json", encoding="utf-8")
    assert nfg.unite() == "mm"
    nfg.definir_unite("in")            # et il redevient lisible
    assert nfg.unite() == "in"


def test_un_fichier_qui_n_est_pas_un_dictionnaire_ne_casse_rien(prefs):
    prefs.write_text("[1, 2, 3]", encoding="utf-8")
    nfg.definir_unite("cm")
    assert nfg.unite() == "cm"


def test_une_unite_inconnue_dans_le_fichier_retombe_sur_le_millimetre(prefs):
    prefs.write_text(json.dumps({"neoforge_unite": "yard"}), encoding="utf-8")
    assert nfg.unite() == "mm"


def test_l_unite_courante_se_change_et_se_lit(prefs):
    assert U.definir("cm") == "cm"
    assert U.courante() == "cm"
    assert U.definir("n'importe quoi") == "mm"     # repli, jamais d'erreur
    assert U.courante() == "mm"


def test_les_cotes_dessinees_suivent_l_unite_courante(prefs):
    """`cotes()` ne prend pas l'unité en paramètre : elle lit le réglage, ce qui
    évite de le faire traverser une dizaine de signatures jusqu'à la vue 3D."""
    from neoforge.projet.mesures import cotes
    from neoforge.projet.modele import Forme

    cube = Forme("cube", "matiere", [0, 0, 15], [30, 30, 30], [0, 0, 0])
    U.definir("mm")
    assert [c.libelle for c in cotes(cube) if c.libelle] == ["30"]
    U.definir("cm")
    assert [c.libelle for c in cotes(cube) if c.libelle] == ["3"]
    U.definir("in")
    assert [c.libelle for c in cotes(cube) if c.libelle] == ["1.181"]
