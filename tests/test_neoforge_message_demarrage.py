# -*- coding: utf-8 -*-
"""Le message d'échec au lancement de neoForge doit dire QUOI FAIRE.

Emmanuel, 2026-09-28, après avoir vécu le cas : « dans le message quand on ouvre
neoForge il est dit qu'il n'a pas pu démarrer mais il faudrait préciser qu'on
doive le mettre à jour dans paramètres, gérer modules, mettre à jour neoForge ».

L'ancien texte disait « Réinstallez le module depuis Gérer les modules ». C'est
la mauvaise manœuvre : réinstaller retélécharge le noyau de 175 Mo, alors que la
mise à jour pèse quelques centaines de kilo-octets et règle le cas.

Ces tests vérifient deux choses qu'une relecture humaine rate facilement :
  1. le message nomme les boutons EXACTEMENT comme l'interface les écrit, sinon
     l'utilisateur les cherche en vain ;
  2. les cinq langues ont été traitées, pas seulement le français.
"""
import pytest

LANGUES = ("fr", "en", "es", "de", "it")


@pytest.fixture(autouse=True)
def _langue_rendue():
    """Chaque test remet la langue d'origine, sinon il pollue les suivants."""
    from core import i18n
    avant = i18n.lang()
    yield
    i18n.set_lang(avant)


def _msg(langue):
    from core import i18n
    i18n.set_lang(langue)
    return i18n._("neoforge.lance_abime")


# ── Le message dit la bonne manœuvre ───────────────────────────────────────
def test_le_message_francais_indique_la_mise_a_jour():
    m = _msg("fr")
    assert "Mettre à jour" in m, "c'est la manœuvre qui règle le cas"
    assert "Gérer les modules" in m, "il faut dire où"
    assert "réglages" in m.lower(), "il faut dire par où commencer"


def test_le_message_nomme_les_boutons_comme_l_interface_les_ecrit():
    """Piège classique : écrire « gestion des modules » alors que le bouton dit
    « Gérer les modules… ». L'utilisateur cherche un libellé qui n'existe pas."""
    from core import i18n
    i18n.set_lang("fr")
    bouton_modules = i18n._("modules.manage_btn").rstrip("… .")
    bouton_maj = i18n._("neoforge.update")
    m = i18n._("neoforge.lance_abime")
    assert bouton_modules in m, f"le message doit citer {bouton_modules!r}"
    assert bouton_maj in m, f"le message doit citer {bouton_maj!r}"


def test_la_reinstallation_reste_citee_mais_en_second():
    """Elle règle les paquets vraiment abîmés, elle ne doit pas disparaître,
    mais elle ne doit plus être le premier conseil."""
    m = _msg("fr")
    assert "réinstall" in m.lower()
    assert m.lower().index("mettre à jour") < m.lower().index("réinstall")


# ── Les cinq langues ───────────────────────────────────────────────────────
@pytest.mark.parametrize("langue", LANGUES)
def test_le_message_existe_dans_toutes_les_langues(langue):
    m = _msg(langue)
    assert m != "neoforge.lance_abime", f"{langue} : clé non traduite"
    assert "neoForge" in m


@pytest.mark.parametrize("langue", LANGUES)
def test_toutes_les_langues_ont_ete_mises_a_jour(langue):
    """Sans ce test, quatre langues garderaient l'ancien conseil pendant des
    mois sans que personne ne s'en aperçoive."""
    m = _msg(langue)
    assert len(m) > 90, f"{langue} : message trop court, l'ancien texte ?"
    attendu = {"fr": "Mettre à jour", "en": "Update", "es": "Actualizar",
               "de": "Aktualisieren", "it": "Aggiorna"}[langue]
    assert attendu in m, f"{langue} : le mot {attendu!r} manque"


@pytest.mark.parametrize("langue", LANGUES)
def test_le_message_reste_lisible_dans_une_fenetre(langue):
    """Une boîte de dialogue Qt ne met pas à la ligne toute seule au delà d'une
    certaine longueur : on garde un texte court."""
    assert len(_msg(langue)) < 260, f"{langue} : message trop long"


# ── La clé est bien celle que le lanceur utilise ───────────────────────────
def test_le_lanceur_utilise_bien_cette_cle():
    """Si quelqu'un renomme la clé un jour, ces tests deviendraient muets."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "core" / "neoforge" / "lanceur.py").read_text(encoding="utf-8")
    assert "neoforge.lance_abime" in src
    assert "neoforge.lance_python" in src, "le cas Python garde son propre message"


def test_les_autres_messages_de_lancement_restent_distincts():
    """« pas installé », « mauvais Python » et « abîmé » doivent rester trois
    messages différents : c'est tout l'intérêt d'avoir trois clés."""
    from core import i18n
    i18n.set_lang("fr")
    textes = {i18n._(c) for c in ("neoforge.lance_absent", "neoforge.lance_python",
                                  "neoforge.lance_abime")}
    assert len(textes) == 3
