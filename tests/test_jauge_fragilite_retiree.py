# -*- coding: utf-8 -*-
"""La jauge FRAGILITÉ a quitté la colonne d'analyse.

Emmanuel, 2026-09-29 : « je veux qu'on retire complètement la jauge de
fragilité en haut entre stabilité et volume support. Elle ne sert plus à rien.
Je veux dorénavant qu'on puisse afficher la fragilité avec le thermomap sur
chaque pièce y compris quand on clique sur une pièce pour l'isoler. »

Un chiffre unique pour toute une pièce ne disait pas grand-chose, et sur un
plateau multi-objets la jauge était de toute façon grisée. La thermomap montre
maintenant l'endroit exact.

Le widget SURVIT, masqué et posé dans la mise en page. Deux raisons, toutes
deux testées ici : une dizaine d'appels le manipulent encore ailleurs, et un
widget sans parent serait une fenêtre de premier niveau, prête à surgir toute
seule si quelqu'un l'affichait par mégarde.
"""
import pytest


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def panneau(app):
    from ui.components.analysis_panel import AnalysisPanel
    p = AnalysisPanel()
    p.resize(400, 900)
    p.show()
    app.processEvents()
    yield p
    p.close()


# ── Ce qui reste à l'écran ─────────────────────────────────────────────────
def test_la_jauge_fragilite_n_est_plus_visible(panneau):
    assert not panneau._g_fragility.isVisible()


def test_les_trois_autres_jauges_restent(panneau):
    for g in (panneau._g_overhangs, panneau._g_stability, panneau._g_support):
        assert g.isVisible()


def test_elle_ne_reserve_aucune_place(panneau, app):
    """Masquer sans retirer laisserait un trou entre Stabilité et Volume
    support. Qt ignore un widget caché, on le vérifie en le rallumant."""
    boite = panneau._gauges_box
    cachee = boite.sizeHint().height()
    panneau._g_fragility.show()
    app.processEvents()
    visible = boite.sizeHint().height()
    panneau._g_fragility.hide()
    app.processEvents()
    assert visible > cachee, "témoin : la jauge occupe bien de la place quand on l'affiche"
    assert boite.sizeHint().height() == cachee, "elle ne doit rien réserver une fois cachée"


def test_elle_a_un_parent_et_n_est_pas_une_fenetre_volante(panneau):
    """Sans parent, ce serait une fenêtre de premier niveau."""
    assert panneau._g_fragility.parent() is not None
    assert not panneau._g_fragility.isWindow()


# ── Ce qui continue de fonctionner ─────────────────────────────────────────
def test_les_appels_qui_la_manipulent_ne_plantent_pas(panneau):
    """Le viewer et la fenêtre principale l'appellent encore. Les supprimer
    partout casserait plus que ça ne nettoierait."""
    panneau.set_fragility_disabled()
    panneau.set_fragility_independent(0.5)
    panneau.reset()
    assert not panneau._g_fragility.isVisible()


def test_un_rapport_fragile_ne_la_fait_pas_reapparaitre(panneau):
    from core.geometry.analysis_report import AnalysisReport
    r = AnalysisReport()
    r.fragility_severity = 0.9
    r.has_fragile_zones = True
    panneau.update_from_report(r)
    assert not panneau._g_fragility.isVisible()


def test_le_changement_de_theme_ne_la_ramene_pas(panneau, app):
    rafraichir = getattr(panneau, "refresh_theme", None)
    if rafraichir is None:
        pytest.skip("pas de rafraîchissement de thème sur ce panneau")
    rafraichir()
    app.processEvents()
    assert not panneau._g_fragility.isVisible()


# ── La thermomap prend le relais, sur TOUTE pièce ─────────────────────────
def test_le_calcul_est_annonce_pour_toute_piece():
    """Avant, l'indicateur « Fragilité (calcul…) » n'était montré que pour les
    scènes à plusieurs corps. Depuis qu'une pièce seule a sa carte, et que le
    calcul peut durer plusieurs secondes sur un maillage dense, il faut le dire
    à l'utilisateur, sinon le viewer reste muet."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "main_window.py").read_text(encoding="utf-8")
    bloc = src[src.index("def _demarrer_thermomap_fragilite"):]
    bloc = bloc[:bloc.index("def _auto_renforcer_pieces_fragiles")]
    assert "_frag_upfront = True" in bloc
    assert "montrer_case_fragilite_calcul()" in bloc
    assert "_is_multipart or (" not in bloc, "l'ancienne condition doit avoir disparu"


# ── La case « Fragilité » doit être là DANS TOUS LES CAS ──────────────────
"""Emmanuel, 2026-09-29 : « il faut que la case fragilité en bas à droite qui
permet d'afficher ce thermomap soit toujours visible, qu'on voie plusieurs
objets, un seul, ou qu'on en isole un ».

Elle disparaissait dans plusieurs situations parfaitement ordinaires, et le
problème est devenu criant depuis le retrait de la jauge : la pièce se
retrouvait alors sans AUCUNE information de fragilité. Constaté par Emmanuel
sur une Main Suspendue Vortex de 514 000 faces, refusée par un plafond de
coût fixé à 250 000.
"""


def test_le_plafond_de_cout_ne_prive_plus_les_gros_fichiers():
    """514 000 faces passaient sous la barre. Le calcul tourne en tâche de
    fond avec son indicateur : environ 6 s pour 490 000 faces, mesuré."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "main_window.py").read_text(encoding="utf-8")
    bloc = src[src.index("def _build_bodysplit_fragility_severity"):]
    bloc = bloc[:bloc.index("def _build_whole_fragility_severity")]
    assert "250_000" not in bloc, "l'ancien plafond doit avoir sauté"
    assert "1_500_000" in bloc


def test_il_existe_un_dernier_recours_sans_decoupage():
    """Chaque constructeur spécialisé peut renoncer. Sans repli, la case
    n'apparaissait pas du tout."""
    from ui.main_window import MainWindow
    assert hasattr(MainWindow, "_build_whole_fragility_severity")


def test_aucun_cas_ne_sort_sans_carte():
    """Les quatre branches du calcul doivent toutes finir sur une carte."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "main_window.py").read_text(encoding="utf-8")
    bloc = src[src.index("def _calcul_thermomap"):]
    bloc = bloc[:bloc.index("def _thermomap_prete")]
    assert "_build_whole_fragility_severity()" in bloc, "le repli doit être câblé"
    assert bloc.count("return") >= 4


def test_l_assemblage_couleur_n_est_plus_exclu():
    """Il sortait par un `return` anticipé, donc jamais de case."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "main_window.py").read_text(encoding="utf-8")
    bloc = src[src.index("def _demarrer_thermomap_fragilite"):]
    bloc = bloc[:bloc.index("def _calcul_thermomap")]
    assert "if _is_color_asm:\n            return" not in bloc
