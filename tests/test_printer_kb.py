"""printer_kb : ciblage des faits imprimante injectés à Oen (pur, sans Ollama)."""
from core.assistant import printer_kb


def test_machine_configuree_prioritaire():
    out = printer_kb.facts_for("comment imprimer de l'ABS ?", "X1 Carbon")
    assert "X1 Carbon" in out
    assert "ENCEINTE FERMEE" in out


def test_machine_citee_dans_la_question():
    out = printer_kb.facts_for("ma K1 Max fait du stringing", "")
    assert "K1 Max" in out
    assert "KLIPPER" in out


def test_alias_le_plus_specifique_gagne():
    # "Ender-3 V3 KE" ne doit PAS matcher la fiche "Ender-3" (stock, bowden)
    out = printer_kb.facts_for("", "Creality Ender-3 V3 KE")
    assert "KE" in out
    assert "BOWDEN" not in out


def test_pas_de_faits_sans_machine():
    assert printer_kb.facts_for("bonjour", "") == ""


def test_deux_machines_max():
    out = printer_kb.facts_for("parle moi de la Neptune 4 Pro", "A1 Mini")
    assert "Neptune 4" in out and "A1 Mini" in out


def test_bambu_genere_depuis_data_printers():
    # Cohérence avec data/printers.py : specs réelles, pas de valeurs inventées
    from data.printers import PRINTERS
    out = printer_kb.facts_for("", "H2D")
    assert str(PRINTERS["H2D"]["buse_max_temp"]) in out
