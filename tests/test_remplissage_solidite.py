# -*- coding: utf-8 -*-
"""Remplissage des presets de SOLIDITÉ — retour utilisateur : « en mode
remplissage renforcé, 40 %, c'est un peu abusé ».

En FDM, la résistance vient des parois et des couches pleines ; au-delà de
~25 % de remplissage, chaque point supplémentaire coûte du temps et du filament
pour un gain négligeable. Ces tests figent le barème pour qu'un futur réglage ne
refasse pas grimper le remplissage en douce — et vérifient qu'un plancher du
moteur ne vient pas écraser la valeur du profil (c'était le cas : un
`max(infill, 40)` remontait tout à 40 %).
"""
import pytest

from core.parameters.parameter_engine import (
    ParameterEngine, IntentProfile, AnalysisReport)


def _config(**intentions):
    return ParameterEngine().generate(IntentProfile(**intentions), AnalysisReport())


def test_standard_reste_leger():
    cfg = _config()
    assert cfg.infill_density == 15
    assert cfg.wall_loops == 3


def test_renforcee_25_pourcent():
    """« Renforcée » = 4 parois + 25 % (et non 40 %)."""
    cfg = _config(strength=0.75)
    assert cfg.infill_density == 25
    assert cfg.wall_loops == 4
    assert cfg.top_shell_layers >= 6      # la solidité passe par les couches
    assert cfg.infill_pattern == "gyroid"


def test_ultra_solide_45_pourcent():
    """« Ultra Solide » reste au-dessus de Renforcée, sans frôler le plein."""
    cfg = _config(strength=1.0)
    assert cfg.infill_density == 45
    assert cfg.wall_loops == 5
    assert cfg.infill_pattern == "gyroid"


def test_gradation_coherente():
    std = _config().infill_density
    fort = _config(strength=0.75).infill_density
    ultra = _config(strength=1.0).infill_density
    assert std < fort < ultra


def test_aucun_preset_solidite_ne_depasse_45():
    """Garde-fou : aucun niveau de solidité ne doit exploser le remplissage."""
    for s in (0.6, 0.7, 0.75, 0.8, 0.9, 1.0):
        cfg = _config(strength=s)
        assert cfg.infill_density <= 45, f"remplissage trop élevé (strength={s})"


def test_le_plancher_moteur_n_ecrase_plus_le_profil():
    """Le plancher `max(infill, N)` de la mission solidité doit rester ALIGNÉ
    sur le profil « Renforcée » : sinon, baisser le YAML ne changerait rien."""
    cfg = _config(strength=0.75)
    assert cfg.infill_density == 25
    # solidité demandée en INTENTION SECONDAIRE (qualité dominante) : le
    # plancher s'applique aussi, sans remonter à 40 %
    mixte = _config(quality=0.95, strength=0.75)
    assert mixte.infill_density <= 25


def test_exterieur_ne_gonfle_pas_le_remplissage():
    cfg = _config(outdoor_resistance=0.9)
    assert cfg.infill_density == 30
    assert cfg.wall_loops >= 4


@pytest.mark.parametrize("langue", ["fr", "en", "es", "de", "it"])
def test_les_libelles_annoncent_la_vraie_densite(langue):
    """Les descriptions des presets affichent un pourcentage : il doit
    correspondre à ce que le moteur produit VRAIMENT, dans les 5 langues.
    (Vécu : « Ultra Solide — gyroid 80 % » est resté affiché alors que le
    profil avait changé — l'utilisateur lisait une valeur fausse.)"""
    import re
    from core import i18n

    attendu = {"intent.s_strong_desc": _config(strength=0.75).infill_density,
               "intent.s_ultra_desc": _config(strength=1.0).infill_density}
    origine = i18n.lang()
    try:
        i18n.set_lang(langue)
        for cle, densite in attendu.items():
            texte = i18n._(cle)
            nombres = [int(n) for n in re.findall(r"(\d+)\s*%", texte)]
            assert nombres, f"{langue}/{cle} : aucun pourcentage affiché"
            assert nombres[0] == densite, (
                f"{langue}/{cle} annonce {nombres[0]} % au lieu de {densite} %")
    finally:
        i18n.set_lang(origine)
