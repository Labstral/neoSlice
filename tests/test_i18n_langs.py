# -*- coding: utf-8 -*-
"""Langues ES/DE/IT — complétude, placeholders et moteur de repli.

Chaque langue de core/i18n_langs/ doit couvrir TOUTES les clés de _FR avec les
mêmes placeholders {xxx}. Le moteur retombe sur l'anglais puis le français si
une clé manque (garantie de non-régression à l'ajout de clés futures)."""
import importlib
import re

import pytest

import core.i18n as i18n

LANGS = ("es", "de", "it")


@pytest.fixture(autouse=True)
def _restaure_langue():
    code = i18n.lang()
    yield
    i18n.set_lang(code)


@pytest.mark.parametrize("code", LANGS)
def test_completude(code):
    m = importlib.import_module(f"core.i18n_langs.{code}")
    manquantes = [k for k in i18n._FR if k not in m.TR]
    assert not manquantes, (f"{code}: {len(manquantes)} clés manquantes, "
                            f"ex. {manquantes[:8]}")
    orphelines = [k for k in m.TR if k not in i18n._FR]
    assert not orphelines, (f"{code}: {len(orphelines)} clés inconnues de _FR, "
                            f"ex. {orphelines[:8]}")


@pytest.mark.parametrize("code", LANGS)
def test_placeholders(code):
    m = importlib.import_module(f"core.i18n_langs.{code}")
    bad = []
    for k, v in i18n._FR.items():
        if k not in m.TR:
            continue
        pf = set(re.findall(r"\{(\w+)\}", v))
        pl = set(re.findall(r"\{(\w+)\}", m.TR[k]))
        if pf != pl:
            bad.append((k, pf, pl))
    assert not bad, f"{code}: placeholders divergents, ex. {bad[:5]}"


@pytest.mark.parametrize("code", LANGS)
def test_set_lang(code):
    i18n.set_lang(code)
    assert i18n.lang() == code
    # une clé courante est bien servie dans la langue (ou repli EN, jamais la clé)
    assert i18n._("settings.language") != "settings.language"


def test_langue_inconnue_retombe_sur_fr():
    i18n.set_lang("xx")
    assert i18n.lang() == "fr"


def test_repli_en_puis_fr():
    """Clé absente de la langue active → valeur EN ; absente partout → la clé."""
    i18n.set_lang("es")
    try:
        i18n._EN["_test_repli"] = "fallback-en"
        assert i18n._("_test_repli") == "fallback-en"
        assert i18n._("_cle_inexistante_xyz") == "_cle_inexistante_xyz"
    finally:
        i18n._EN.pop("_test_repli", None)
