"""Non-régression du nettoyage de texte d'Oen (ui/components/glass_panel).

Oen est HORS-LIGNE : il ne doit JAMAIS afficher d'URL ni de chemin de doc inventé.
Un modèle local fabrique des liens (http, www, mais AUSSI des chemins relatifs type
/fr/a1-mini/maintenance/...). _plain_text doit tous les retirer en gardant le libellé.
"""
from ui.components.glass_panel import _plain_text


def test_strip_relative_markdown_link():
    out = _plain_text("Guide : [Nettoyage buse](/fr/a1-mini/maintenance/clean-hotend).")
    assert "/fr/" not in out and "](" not in out
    assert "Nettoyage buse" in out


def test_strip_http_and_www():
    out = _plain_text("Voir [le site](https://bambulab.com) ou www.exemple.com ici.")
    assert "http" not in out and "www." not in out
    assert "le site" in out


def test_strip_bare_relative_path_in_parens():
    out = _plain_text("Documentation : (/fr/a1-mini/maintenance/period-maintenance).")
    assert "/fr/" not in out


def test_keeps_plain_text_intact():
    out = _plain_text("Baisse la température de 5 °C et sèche le filament.")
    assert out == "Baisse la température de 5 °C et sèche le filament."
