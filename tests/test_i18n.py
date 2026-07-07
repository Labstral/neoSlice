"""i18n : symétrie stricte FR/EN (règle projet : toute clé existe dans les deux
langues) et formatage des clés paramétrées."""
import core.i18n as i18n


def test_symetrie_fr_en():
    fr, en = set(i18n._FR), set(i18n._EN)
    assert fr - en == set(), f"clés FR sans EN : {sorted(fr - en)[:10]}"
    assert en - fr == set(), f"clés EN sans FR : {sorted(en - fr)[:10]}"


def test_formatage_parametres_oen():
    i18n.set_lang("fr")
    try:
        assert "0.1.7" in i18n._("oen.kb_needs_app", min="0.1.7")
        assert "2026-08-15" in i18n._("oen.kb_available", version="2026-08-15")
        assert "42" in i18n._("oen.kb_download_size", mo="42")
        i18n.set_lang("en")
        assert "0.1.7" in i18n._("oen.kb_needs_app", min="0.1.7")
    finally:
        i18n.set_lang("fr")


def test_cle_inconnue_rendue_telle_quelle():
    assert i18n._("cle.qui.nexiste.pas") == "cle.qui.nexiste.pas"
