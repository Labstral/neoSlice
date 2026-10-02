# -*- coding: utf-8 -*-
"""Le prix Pro doit dire qu'il est HORS TAXES.

Yannick Lebeau Fraisse, 2026-10-02 : « vous devriez indiquer HT en gras à côté
du prix de la version pro car j'ai eu la désagréable surprise de devoir 107 $
donc en plus des frais bancaires ce n'est pas 79,99 € mais 95 € et quelques
toutes taxes plus frais de change. De ce fait je vais attendre avant de prendre
la version pro. »

Son calcul est juste au centime : 79,99 € hors taxes, plus 20 % de TVA, font
95,99 €, et comme Gumroad facture en dollars sa banque ajoute ses frais de
change, ce qui donne bien 107 $.

Ni le logiciel ni le site ne disaient que le prix était hors taxes. Un client
a donc renoncé à acheter, non pas à cause du prix, mais parce qu'il s'est senti
surpris. C'est le genre de défaut qui ne coûte rien à corriger et cher à
laisser.
"""
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.i18n import _, set_lang                                  # noqa: E402

LANGUES = ("fr", "en", "es", "de", "it")
# Comment chaque langue dit « hors taxes ».
HORS_TAXES = {"fr": "HT", "en": "excl. VAT", "es": "sin IVA",
              "de": "zzgl. MwSt.", "it": "IVA esclusa"}


@pytest.fixture(autouse=True)
def _langue_rendue():
    yield
    set_lang("fr")


@pytest.mark.parametrize("lg", LANGUES)
def test_le_prix_annonce_qu_il_est_hors_taxes(lg):
    set_lang(lg)
    texte = _("pro.price_suffix", price="79,99 €")
    assert HORS_TAXES[lg] in texte, f"[{lg}] rien n'indique le hors taxes : {texte}"


@pytest.mark.parametrize("lg", LANGUES)
def test_la_mention_tva_existe_dans_chaque_langue(lg):
    set_lang(lg)
    m = _("pro.price_vat")
    assert m and not m.startswith("pro."), f"[{lg}] clé manquante"
    assert re.search(r"(?i)\b(tva|vat|iva|mwst)", m), f"[{lg}] la TVA n'est pas nommée"


def test_la_mention_parle_aussi_des_frais_de_change():
    """L'autre moitié de sa surprise : Gumroad facture dans sa devise."""
    set_lang("fr")
    assert "change" in _("pro.price_vat").lower()


# ── Dans la fenêtre ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def paywall(app):
    from ui.components.paywall_dialog import PaywallDialog
    d = PaywallDialog()
    d.resize(460, 700)
    d.show()
    app.processEvents()
    yield d
    d.deleteLater()


def test_la_mention_est_visible_sous_le_prix(paywall):
    assert paywall._price_vat_lbl.isVisible()
    assert "HT" in paywall._price_lbl.text()


def test_la_mention_ne_deborde_pas(paywall):
    """Elle est longue : sans retour à la ligne elle élargirait la fenêtre."""
    assert paywall._price_vat_lbl.wordWrap()
    assert paywall._price_vat_lbl.width() <= paywall.width()


def test_la_mention_reste_lisible_dans_les_deux_themes(paywall, app):
    """Mesuré : le gris le plus pâle de la palette ne donne que 2,88 de
    contraste sur le fond sombre. Une mention de prix doit se lire."""
    from ui.styles.theme import MANAGER as _T

    def _lum(h):
        h = h.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    depart = _T.name()
    try:
        for nom in ("dark", "light"):
            _T.switch(nom)
            paywall._apply_theme()
            app.processEvents()
            pal = _T.palette()
            couleurs = re.findall(r"#[0-9A-Fa-f]{6}", paywall._price_vat_lbl.styleSheet())
            assert couleurs, f"[{nom}] aucune couleur posée"
            la, lb = _lum(couleurs[0]), _lum(pal["BG_PANEL"])
            contraste = (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
            assert contraste >= 4.0, f"[{nom}] contraste {contraste:.2f}, illisible"
    finally:
        _T.switch(depart)
