# -*- coding: utf-8 -*-
"""Deux défauts vus par Emmanuel en testant la 2.3.1, le 2026-10-01.

1. « une fois qu'on a validé l'imprimante on ne peut plus recliquer sur le
   bouton valider donc le slicer ne change plus », puis « il faut faire de même
   avec le filament ».

   Les étapes ① et ② restaient cochées ✓ avec leur bouton grisé. On pouvait
   donc changer de machine après coup sans pouvoir revalider : la sortie restait
   celle de l'ancienne, et le badge de compatibilité parlait d'un filament
   qui n'était plus sélectionné. Le défaut existait avant, mais montrer tout le
   catalogue le rend dangereux : on choisit une Elegoo Centauri et on exporte
   pour Bambu Studio sans rien voir.

   Deux réponses, volontairement complémentaires : l'étape redevient « à
   valider » dès que le choix change, ET la sortie se corrige TOUT DE SUITE
   quand elle est incapable de produire la machine, sans attendre un clic que
   l'utilisateur ne fera peut-être pas.

2. « quand je modifie la valeur série rien ne bouge sur le plateau, il faudrait
   mettre un petit OK à côté pour valider et voir toutes les pièces clonées ».

   On réglait ×16 à l'aveugle et on découvrait la disposition en ouvrant le
   slicer. Le bouton pose les exemplaires sur leurs plateaux dans le viewer.

⚠ L'aperçu ne touche PAS `self._mesh` : l'export recalcule la série de son
côté, et dupliquer deux fois donnerait ×256 au lieu de ×16.
"""
import os

import pytest
import trimesh

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.geometry.threemf_data import ThreeMFData              # noqa: E402

NEPTUNE = "Elegoo Neptune 4 Max"
CENTAURI = "Elegoo Centauri Carbon 2"


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def selecteur(app, monkeypatch):
    import core.prefs as _p
    import ui.components.filament_printer_selector as F
    store = {"slicer_output": "bambu"}
    monkeypatch.setattr(_p.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(_p.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(F, "PREFS", _p.PREFS)
    sel = F.FilamentPrinterSelector()
    sel.setFixedWidth(360)
    sel.show()
    app.processEvents()
    yield sel, store
    sel.deleteLater()


def _autre_filament(sel):
    """Index d'un filament sélectionnable différent de l'actuel."""
    combo = sel._filament_combo
    i = (combo.currentIndex() + 1) % combo.count()
    for _ in range(combo.count()):
        if combo.model().item(i).isEnabled():
            return i
        i = (i + 1) % combo.count()
    pytest.skip("un seul filament sélectionnable")


# ── ① Revalider l'imprimante ──────────────────────────────────────────────
def test_changer_d_imprimante_redemande_une_validation(selecteur, app):
    sel, _store = selecteur
    sel._printer_combo.set_current_key(NEPTUNE, emit=True)
    sel._on_confirm_printer()
    assert not sel._btn_confirm_printer.isEnabled(), "l'étape doit d'abord être cochée"

    sel._printer_combo.set_current_key("X1 Carbon", emit=True)
    app.processEvents()
    assert sel._btn_confirm_printer.isEnabled(), "bouton Valider toujours grisé"
    assert sel._btn_confirm_printer.text() != "✓"
    assert sel._printer_done is False


def test_revalider_la_meme_imprimante_ne_fait_rien(selecteur, app):
    """Rouvrir le menu et reprendre la MÊME machine ne doit pas tout défaire."""
    sel, _store = selecteur
    sel._printer_combo.set_current_key(NEPTUNE, emit=True)
    sel._on_confirm_printer()
    sel._printer_combo.set_current_key(NEPTUNE, emit=True)
    app.processEvents()
    assert sel._printer_done is True
    assert not sel._btn_confirm_printer.isEnabled()


# ── ② Revalider le filament ───────────────────────────────────────────────
def test_changer_de_filament_redemande_une_validation(selecteur, app):
    sel, _store = selecteur
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    assert not sel._btn_confirm_filament.isEnabled()

    sel._filament_combo.setCurrentIndex(_autre_filament(sel))
    app.processEvents()
    assert sel._btn_confirm_filament.isEnabled(), "bouton Valider toujours grisé"
    assert sel._btn_confirm_filament.text() != "✓"
    assert sel._filament_done is False


def test_le_badge_de_compatibilite_ne_survit_pas_au_changement(selecteur, app):
    """Il affirmait « Compatible avec X » pour un couple qui n'existait plus."""
    sel, _store = selecteur
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    sel._filament_combo.setCurrentIndex(_autre_filament(sel))
    app.processEvents()
    assert sel._compat_badge.text() == ""


def test_le_bouton_revenu_a_valider_reprend_le_style_du_theme(selecteur, app):
    """Il gardait l'habillage vert du ✓ en affichant « Valider »."""
    sel, _store = selecteur
    sel._printer_combo.set_current_key(NEPTUNE, emit=True)
    sel._on_confirm_printer()
    coche = sel._btn_confirm_printer.styleSheet()
    sel._printer_combo.set_current_key("X1 Carbon", emit=True)
    app.processEvents()
    assert sel._btn_confirm_printer.styleSheet() != coche


# ── La sortie se corrige sans attendre la validation ──────────────────────
def test_choisir_une_machine_hors_portee_corrige_la_sortie_aussitot(selecteur, app):
    """Sans ça, on choisit une Centauri, on oublie de revalider, et le fichier
    part pour Bambu Studio qui ne connaît pas la machine."""
    sel, store = selecteur
    assert store["slicer_output"] == "bambu"
    sel._printer_combo.set_current_key(CENTAURI, emit=True)
    app.processEvents()
    assert store["slicer_output"] == "elegoo"
    assert sel.current_printer() == CENTAURI


def test_une_machine_deja_geree_ne_deplace_pas_la_sortie(selecteur, app):
    sel, store = selecteur
    sel._printer_combo.set_current_key(NEPTUNE, emit=True)
    app.processEvents()
    assert store["slicer_output"] == "bambu"


def test_la_correction_ne_se_mord_pas_la_queue(selecteur, app):
    """La bascule recharge le catalogue, ce qui peut relancer le même code.
    Sans verrou, on boucle. Dix changements d'affilée doivent passer."""
    sel, store = selecteur
    for _ in range(5):
        sel._printer_combo.set_current_key(CENTAURI, emit=True)
        app.processEvents()
        sel._printer_combo.set_current_key("X1 Carbon", emit=True)
        app.processEvents()
    assert sel.current_printer() == "X1 Carbon"
    assert sel._bascule_en_cours is False


# ── L'aperçu de la série ──────────────────────────────────────────────────
class _Viewer:
    def __init__(self):
        self.recu = None

    def load_mesh(self, m):
        self.recu = m


class _Barre:
    def __init__(self, n=1):
        self.n = n
        self.messages = []

    def serie_count(self):
        return self.n

    def set_message(self, texte, couleur=None):
        self.messages.append(texte)


def _fenetre_serie(n, imprimante=NEPTUNE, mesh=None, td=None):
    from ui.main_window import MainWindow

    class _Faux:
        _apercu_serie = MainWindow._apercu_serie

    f = _Faux()
    f._mesh = mesh if mesh is not None else trimesh.creation.box((60, 60, 20))
    f._threemf_data = td
    f._stl_path = None
    f._current_printer = imprimante
    f._viewer = _Viewer()
    f._statusbar = _Barre(n)
    return f


def test_l_apercu_pose_les_exemplaires_sur_leurs_plateaux():
    f = _fenetre_serie(16)
    f._apercu_serie()
    recu = f._viewer.recu
    assert isinstance(recu, ThreeMFData)
    assert len(recu.objects) == 16
    assert len({o.plate_index for o in recu.objects}) == 1   # 420 mm : tout tient
    assert recu.reagence is True, "le viewer ne doit pas recompacter l'aperçu"
    assert any("16" in m for m in f._statusbar.messages)


def test_l_apercu_suit_l_imprimante():
    """Même série, machine plus petite : les exemplaires débordent sur un
    deuxième plateau, et ça doit se VOIR avant d'exporter."""
    grand = _fenetre_serie(16, NEPTUNE)
    grand._apercu_serie()
    petit = _fenetre_serie(16, "X1 Carbon")
    petit._apercu_serie()
    assert len({o.plate_index for o in grand._viewer.recu.objects}) == 1
    assert len({o.plate_index for o in petit._viewer.recu.objects}) == 2


def test_revenir_a_un_exemplaire_remet_la_piece_seule():
    f = _fenetre_serie(1)
    f._apercu_serie()
    assert isinstance(f._viewer.recu, trimesh.Trimesh)


def test_l_apercu_ne_duplique_pas_la_piece_de_travail():
    """Piège : si l'aperçu remplaçait `self._mesh`, l'export rejouerait la
    série par dessus et livrerait ×256 au lieu de ×16."""
    f = _fenetre_serie(16)
    avant = f._mesh
    f._apercu_serie()
    assert f._mesh is avant
    assert len(f._mesh.faces) == len(avant.faces)


def test_une_piece_plus_grande_que_le_plateau_le_dit():
    f = _fenetre_serie(9, "X1 Carbon", mesh=trimesh.creation.box((300, 300, 20)))
    f._apercu_serie()
    assert f._viewer.recu is None
    assert f._statusbar.messages, "l'utilisateur doit être prévenu"


def test_un_3mf_mono_objet_se_comporte_comme_une_piece_seule():
    """RÈGLE ÉLARGIE le 2026-10-01. L'aperçu refusait TOUT projet 3MF. Il ne
    refuse plus que ceux qu'on ne peut pas reconstruire sans les abîmer,
    modificateurs et multi-couleurs, testés dans test_serie_multi_objets.py.
    Un 3MF d'un seul objet suit donc la voie normale."""
    faux_td = ThreeMFData(combined_mesh=trimesh.creation.box((10, 10, 10)),
                          objects=[], source_path=None)
    f = _fenetre_serie(8, td=faux_td)
    f._active_object_id = None
    f._serie_objet, f._serie_globale = {}, 1
    f._apercu_serie()
    assert isinstance(f._viewer.recu, ThreeMFData)
    assert len(f._viewer.recu.objects) == 8


# ── Le bouton OK dans la barre ────────────────────────────────────────────
@pytest.fixture
def barre(app):
    from ui.main_window import _StatusBar
    b = _StatusBar()
    b.resize(1200, 40)
    b.show()
    app.processEvents()
    yield b
    b.deleteLater()


def test_le_bouton_ok_accompagne_le_compteur(barre, app):
    barre.set_export_enabled(True)
    app.processEvents()
    assert barre._serie_ok_btn.isVisible()
    barre.set_export_enabled(False)
    app.processEvents()
    assert not barre._serie_ok_btn.isVisible()


def test_le_clic_sur_ok_remonte_a_la_fenetre(barre, app):
    barre.set_export_enabled(True)
    app.processEvents()
    recus = []
    barre.serie_apercu_clicked.connect(lambda: recus.append(1))
    barre._serie_ok_btn.click()
    assert recus == [1]


def test_le_bouton_ok_suit_le_theme(barre):
    import re
    from ui.main_window import _THEME
    depart = _THEME.name()
    try:
        couleurs = {}
        for nom in ("dark", "light"):
            _THEME.switch(nom)
            barre.refresh_theme()
            couleurs[nom] = set(re.findall(r"#[0-9A-Fa-f]{6}",
                                           barre._serie_ok_btn.styleSheet()))
        assert couleurs["dark"] != couleurs["light"], "palette figée"
    finally:
        _THEME.switch(depart)


def test_on_peut_toujours_revenir_a_sa_bambu(selecteur, app):
    """Le piège de la bascule : essayer une Elegoo met la sortie sur
    ElegooSlicer, qui ne proposait aucune Bambu Lab. L'utilisateur se
    retrouvait enfermé, sans moyen évident de revenir à sa propre machine."""
    sel, store = selecteur
    sel._printer_combo.set_current_key(CENTAURI, emit=True)
    app.processEvents()
    assert store["slicer_output"] == "elegoo"
    assert "X1 Carbon" in sel._printer_combo._key_label, "Bambu Lab introuvable"

    sel._printer_combo.set_current_key("X1 Carbon", emit=True)
    app.processEvents()
    assert sel.current_printer() == "X1 Carbon"
    assert store["slicer_output"] == "bambu", "une Bambu Lab a besoin de Bambu Studio"


def test_une_bambu_sous_orcaslicer_ne_bascule_pas(selecteur, app):
    """OrcaSlicer est générique et connaît les Bambu Lab : choix légitime."""
    sel, store = selecteur
    store["slicer_output"] = "orca"
    sel.refresh_printers()
    sel._printer_combo.set_current_key("X1 Carbon", emit=True)
    app.processEvents()
    assert store["slicer_output"] == "orca"


# ── L'import reste fermé tant que tout n'est pas validé ───────────────────
"""Emmanuel, 2026-10-01 : « on peut importer un objet sans avoir à revalider
l'imprimante et le filament, c'est pas bon. Il faut obligatoirement valider
les deux avant de pouvoir importer un objet. »

La zone d'import s'ouvrait à la validation du filament et ne se refermait
JAMAIS. On pouvait donc valider, changer d'imprimante, et importer quand même :
la configuration partait sur une machine jamais confirmée.

⚠ Un seul endroit décide, sinon les cas se contredisent : revalider la seule
imprimante après l'avoir changée rend l'étape ① complète, et l'import doit
rouvrir sans qu'on ait à retoucher au filament.
"""


class _Etape:
    def __init__(self):
        self.etat = None

    def set_done(self):
        self.etat = "done"

    def set_active(self):
        self.etat = "active"


class _Intent:
    def __init__(self):
        self.prerequis = None

    def set_prerequis(self, v):
        self.prerequis = v


@pytest.fixture
def fenetre_verrou(selecteur, app):
    """Les VRAIES méthodes de la fenêtre, câblées aux signaux du sélecteur."""
    from ui.components.drop_zone import DropZone
    from ui.main_window import MainWindow
    sel, _store = selecteur

    class _Faux:
        _maj_verrou_import = MainWindow._maj_verrou_import
        _maj_prerequis_generation = MainWindow._maj_prerequis_generation

    f = _Faux()
    f._filament_selector = sel
    f._drop_zone = DropZone()
    f._step_config, f._step_stl = _Etape(), _Etape()
    f._intent_selector = _Intent()
    sel.printer_confirmed.connect(f._maj_verrou_import)
    sel.filament_confirmed.connect(f._maj_verrou_import)
    sel.validation_perdue.connect(f._maj_verrou_import)
    f._maj_verrou_import()
    app.processEvents()
    return f, sel


def test_l_import_est_ferme_au_depart(fenetre_verrou):
    f, _sel = fenetre_verrou
    assert f._drop_zone._locked is True


def test_valider_l_imprimante_seule_ne_suffit_pas(fenetre_verrou, app):
    f, sel = fenetre_verrou
    sel._on_confirm_printer()
    app.processEvents()
    assert f._drop_zone._locked is True, "le filament n'est pas validé"


def test_l_import_s_ouvre_quand_les_deux_sont_valides(fenetre_verrou, app):
    f, sel = fenetre_verrou
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    assert f._drop_zone._locked is False
    assert f._intent_selector.prerequis is True
    assert f._step_stl.etat == "active"


def test_changer_d_imprimante_referme_l_import(fenetre_verrou, app):
    f, sel = fenetre_verrou
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._printer_combo.set_current_key("A1 Mini", emit=True)
    app.processEvents()
    assert f._drop_zone._locked is True
    assert f._intent_selector.prerequis is False
    assert f._step_config.etat == "active"


def test_changer_de_filament_referme_l_import(fenetre_verrou, app):
    f, sel = fenetre_verrou
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._filament_combo.setCurrentIndex(_autre_filament(sel))
    app.processEvents()
    assert f._drop_zone._locked is True


def test_revalider_la_seule_etape_touchee_rouvre_l_import(fenetre_verrou, app):
    """Le cas qui se contredisait : on change l'imprimante, on la revalide, et
    l'import doit rouvrir sans qu'on retouche au filament."""
    f, sel = fenetre_verrou
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._printer_combo.set_current_key("A1 Mini", emit=True)
    app.processEvents()
    assert f._drop_zone._locked is True
    sel._on_confirm_printer()
    app.processEvents()
    assert f._drop_zone._locked is False, "l'étape ① est pourtant complète"


# ── Changer d'imprimante avec une pièce déjà chargée ──────────────────────
"""Emmanuel, 2026-10-01 : « quand un objet est déjà importé et qu'on change
l'imprimante, c'est quoi le mieux ? »

Pas de vider la pièce : sa géométrie ne change pas quand on change de machine,
et il faudrait réimporter le même fichier pour rien. Ce qu'il faut jeter, c'est
la CONFIGURATION générée. Elle a été calculée avec les vitesses, accélérations,
débit et températures de l'ancienne machine, alors que l'export lit
l'imprimante COURANTE : le fichier serait étiqueté « Neptune 4 Max » tout en
portant les réglages d'une X1 Carbon, sans que rien ne le signale.

L'analyse reste aussi : surplombs, stabilité et épaisseurs ne dépendent que de
la géométrie, et la refaire coûterait une vingtaine de secondes sur une pièce
lourde.
"""


class _BarreExport:
    def __init__(self):
        self.export = None
        self.messages = []

    def set_export_enabled(self, v):
        self.export = v

    def set_message(self, texte, couleur=None):
        self.messages.append(texte)


def _fenetre_config(selecteur, app, avec_config=True):
    from ui.components.drop_zone import DropZone
    from ui.main_window import MainWindow
    sel, _store = selecteur

    class _Faux:
        _maj_verrou_import = MainWindow._maj_verrou_import
        _maj_prerequis_generation = MainWindow._maj_prerequis_generation
        _on_validation_perdue = MainWindow._on_validation_perdue

    f = _Faux()
    f._filament_selector = sel
    f._drop_zone = DropZone()
    f._step_config, f._step_stl = _Etape(), _Etape()
    f._intent_selector = _Intent()
    f._statusbar = _BarreExport()
    f._mesh = trimesh.creation.box((20, 20, 10))
    f._current_config = object() if avec_config else None
    sel.validation_perdue.connect(f._on_validation_perdue)
    app.processEvents()
    return f, sel


def test_la_piece_reste_quand_on_change_d_imprimante(selecteur, app):
    f, sel = _fenetre_config(selecteur, app)
    avant = f._mesh
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._printer_combo.set_current_key("A1 Mini", emit=True)
    app.processEvents()
    assert f._mesh is avant, "la pièce ne doit surtout pas être vidée"


def test_la_configuration_est_jetee_quand_on_change_d_imprimante(selecteur, app):
    f, sel = _fenetre_config(selecteur, app)
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._printer_combo.set_current_key("A1 Mini", emit=True)
    app.processEvents()
    assert f._current_config is None
    assert f._statusbar.export is False, "on exporterait les réglages de l'ancienne machine"
    assert f._statusbar.messages, "l'utilisateur doit savoir qu'il faut regénérer"


def test_changer_de_filament_jette_aussi_la_configuration(selecteur, app):
    """Températures, ventilation et rétraction en dépendent directement."""
    f, sel = _fenetre_config(selecteur, app)
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._filament_combo.setCurrentIndex(_autre_filament(sel))
    app.processEvents()
    assert f._current_config is None
    assert f._statusbar.export is False


def test_sans_configuration_generee_on_ne_dit_rien(selecteur, app):
    """Changer d'imprimante avant d'avoir généré quoi que ce soit ne doit pas
    afficher un avertissement sorti de nulle part."""
    f, sel = _fenetre_config(selecteur, app, avec_config=False)
    sel._on_confirm_printer()
    sel._on_confirm_filament()
    app.processEvents()
    sel._printer_combo.set_current_key("A1 Mini", emit=True)
    app.processEvents()
    assert f._statusbar.messages == []
    assert f._statusbar.export is None
