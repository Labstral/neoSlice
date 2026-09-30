# -*- coding: utf-8 -*-
"""Sauvegarde automatique : la liste déroulante et la case à cocher.

Emmanuel, 2026-09-30 : « dans l'espace pro en thème sombre il y a un problème
avec l'affichage du menu déroulant dans fréquence, le texte n'est pas adapté à
la couleur sombre », puis « la case activer la sauvegarde automatique doit se
cocher en bleu et pas en vert en thème sombre ».

Deux oublis dans la même fenêtre :

  1. la LISTE DÉROULÉE est une fenêtre à part. Sans règle pour elle, Qt lui
     laisse ses couleurs par défaut : texte gris sombre sur fond sombre. Toutes
     les autres listes de l'Espace Pro la stylent, celle ci était la seule à ne
     pas le faire ;
  2. la case était cochée en vert alors que toutes les autres cases de
     l'application utilisent l'accent.
"""
import re

import pytest


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _luminance(hexa):
    h = hexa.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contraste(a, b):
    x, y = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


@pytest.fixture
def fenetre(app, request):
    """La fenêtre dans le thème demandé, puis on remet le thème d'origine."""
    from ui.styles.theme import MANAGER as T
    from ui.components.auto_backup_dialog import AutoBackupDialog
    depart = T.name()
    T.switch(request.param)
    app.processEvents()
    d = AutoBackupDialog()
    app.processEvents()
    yield d, T.palette(), request.param
    d.close()
    app.processEvents()
    T.switch(depart)


THEMES = ["dark", "light"]


# ── La liste déroulée ─────────────────────────────────────────────────────
@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_la_liste_deroulee_est_stylee(fenetre):
    """Sans cette règle, Qt garde ses couleurs par défaut et le texte devient
    illisible sur fond sombre."""
    d, _pal, theme = fenetre
    assert "QComboBox QAbstractItemView" in d._freq_combo.styleSheet(), theme


@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_le_texte_de_la_liste_est_lisible(fenetre):
    d, pal, theme = fenetre
    c = _contraste(pal["TEXT_PRIMARY"], pal["BG_ELEVATED"])
    assert c > 4.5, f"{theme} : contraste {c:.1f} pour 1"


@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_la_ligne_survolee_est_lisible(fenetre):
    """Le piège discret : du blanc sur l'accent brut tombe à 3,2 pour 1 en
    thème sombre. On assombrit l'accent de 20 %, la ligne reste bleue et
    remonte à 4,8."""
    d, _pal, theme = fenetre
    css = d._freq_combo.styleSheet()
    m = re.search(r"selection-background-color: (#[0-9a-fA-F]{6})", css)
    assert m, f"{theme} : pas de couleur de survol"
    c = _contraste("#ffffff", m.group(1))
    assert c > 4.5, f"{theme} : contraste {c:.1f} pour 1 sur la ligne survolée"


@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_la_fleche_est_redessinee(fenetre):
    """Styler un QComboBox lui fait perdre sa flèche native."""
    d, _pal, theme = fenetre
    assert "down-arrow" in d._freq_combo.styleSheet(), theme


# ── La case à cocher ──────────────────────────────────────────────────────
@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_la_case_se_coche_a_la_couleur_d_accent(fenetre):
    """Elle était la seule de l'application à se cocher en vert."""
    d, pal, theme = fenetre
    m = re.search(r"indicator:checked \{[^}]*background: (#[0-9a-fA-F]{6})",
                  d._enable_cb.styleSheet())
    assert m, f"{theme} : couleur de coche introuvable"
    assert m.group(1).lower() == pal["ACCENT"].lower(), (
        f"{theme} : cochée en {m.group(1)}, attendu l'accent {pal['ACCENT']}")


@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_la_case_n_est_plus_verte_en_sombre(fenetre):
    d, pal, theme = fenetre
    if theme != "dark":
        pytest.skip("le vert est l'accent du thème clair, c'est voulu")
    assert pal["ACCENT"].lower() != pal["TELE_GREEN"].lower()
    assert pal["TELE_GREEN"].lower() not in d._enable_cb.styleSheet().lower()


# ── Le champ dossier suit le même style ───────────────────────────────────
@pytest.mark.parametrize("fenetre", THEMES, indirect=True)
def test_le_champ_dossier_reste_lisible(fenetre):
    d, pal, theme = fenetre
    assert pal["TEXT_PRIMARY"] in d._folder_edit.styleSheet(), theme
    assert _contraste(pal["TEXT_PRIMARY"], pal["BG_INPUT"]) > 4.5, theme
