# -*- coding: utf-8 -*-
"""Toutes les imprimantes du catalogue doivent être TROUVABLES dans le menu.

Pascal Guiheux, 2026-10-01 : « j'ai voulu tester neoslice, hélas, mon
imprimante (elegoo centauri carbon 2) n'apparaît pas dans le menu, vous ne
proposez que la série neptune. »

Sa Centauri Carbon 2 est pourtant au catalogue depuis toujours. Le menu
d'imprimantes était filtré par le LOGICIEL DE SORTIE, et la sortie par défaut
est Bambu Studio, qui ne connaît que 78 des 396 machines. Résultat : il ne
voyait que la série Neptune, et des marques entières (Flashforge, Snapmaker,
Artillery, Sovol, Volumic, Ratrig…) n'apparaissaient pas du tout. Un nouvel
utilisateur en concluait, à raison vu son écran, que sa machine n'était pas
gérée.

Le menu montre désormais TOUT le catalogue. Pour que l'export reste juste,
choisir une machine que la sortie ne sait pas produire déplace la sortie vers
un logiciel qui en est capable, et le dit dans la barre d'état.

⚠ La règle « sortie incapable » est DISTINCTE de la règle « logiciel maison
d'une autre marque » (test_slicer_suit_la_marque.py) : celle là ne touche
jamais un logiciel générique, celle ci le déplace quand même, parce que rester
produirait un fichier pour une imprimante que le logiciel ne connaît pas.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.printers import (_by_model, _slicer_supported,          # noqa: E402
                           catalogue_brands, catalogue_brands_tous,
                           models_for_brand, models_for_brand_tous,
                           slicer_pour_modele)

CENTAURI = "Elegoo Centauri Carbon 2"


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def selecteur(app, monkeypatch):
    """Sélecteur neuf, sortie par DÉFAUT (Bambu Studio), préférences en mémoire."""
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


# ── Le problème existait bien ─────────────────────────────────────────────
def test_la_sortie_par_defaut_ne_connait_qu_un_cinquieme_du_catalogue():
    """Documente la cause. Si ce chiffre grimpe un jour, c'est que Bambu Studio
    a élargi ses profils, pas que le bug est revenu."""
    vus = sum(1 for v in _by_model().values()
              if _slicer_supported("bambu", v["slicers"], v["marque"]))
    assert vus < len(_by_model()) / 2


def test_la_centauri_carbon_2_etait_invisible_en_sortie_bambu():
    assert CENTAURI in {mk for _l, mk in models_for_brand_tous("Elegoo")}
    assert CENTAURI not in {mk for _l, mk in models_for_brand("Elegoo", "bambu")}


# ── Le menu montre tout ───────────────────────────────────────────────────
def test_le_menu_propose_la_machine_de_pascal(selecteur):
    sel, _store = selecteur
    assert CENTAURI in sel._printer_combo._key_label


def test_le_menu_propose_toute_la_serie_centauri(selecteur):
    """Son reproche exact : « vous ne proposez que la série neptune »."""
    sel, _store = selecteur
    cles = set(sel._printer_combo._key_label)
    centauri = {mk for _l, mk in models_for_brand_tous("Elegoo")
                if "Centauri" in mk}
    assert centauri and centauri <= cles


@pytest.mark.parametrize("marque", ["Flashforge", "Snapmaker", "Artillery",
                                    "Sovol", "Elegoo", "Creality"])
def test_les_marques_entierement_absentes_sont_revenues(selecteur, marque):
    """Ces marques affichaient ZÉRO modèle en sortie Bambu Studio : elles ne
    figuraient même pas dans la liste des marques."""
    sel, _store = selecteur
    cles = set(sel._printer_combo._key_label)
    attendus = {mk for _l, mk in models_for_brand_tous(marque)}
    assert attendus, f"{marque} a disparu du catalogue"
    assert attendus <= cles, f"{marque} : {len(attendus - cles)} modèles manquants"


def test_toutes_les_marques_du_catalogue_sont_proposees():
    assert len(catalogue_brands_tous()) > 4 * len(catalogue_brands("bambu"))
    assert set(catalogue_brands("orca")) <= set(catalogue_brands_tous())


# ── La sortie suit la machine choisie ─────────────────────────────────────
def test_choisir_la_centauri_bascule_la_sortie_sur_elegooslicer(selecteur):
    sel, store = selecteur
    sel._printer_combo.set_current_key(CENTAURI, emit=False)
    messages = []
    sel.status_message.connect(messages.append)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "elegoo"
    assert sel.current_printer() == CENTAURI        # la sélection est gardée
    assert sel._slicer_combo.currentData() == "elegoo"
    assert messages and "ElegooSlicer" in messages[0]


def test_une_machine_sans_logiciel_maison_part_sur_orcaslicer(selecteur):
    """Flashforge n'a pas de logiciel maison dans CE catalogue : OrcaSlicer,
    qui couvre 367 modèles, prend le relais."""
    sel, store = selecteur
    cible = next(mk for _l, mk in models_for_brand_tous("Flashforge"))
    sel._printer_combo.set_current_key(cible, emit=False)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "orca"
    assert sel.current_printer() == cible


def test_une_machine_deja_geree_ne_deplace_rien(selecteur):
    """La Neptune 4 Max existe en sortie Bambu Studio : aucune raison de bouger."""
    sel, store = selecteur
    sel._printer_combo.set_current_key("Elegoo Neptune 4 Max", emit=False)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "bambu"


def test_une_bambu_lab_ne_declenche_jamais_de_bascule(selecteur):
    sel, store = selecteur
    sel._printer_combo.set_current_key("X1 Carbon", emit=False)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "bambu"


def test_apres_bascule_la_machine_est_bien_dans_le_catalogue_cible(selecteur):
    """Le piège de la bascule : atterrir sur une sortie où la machine choisie
    n'est plus sélectionnable laisserait l'utilisateur avec une autre machine."""
    sel, store = selecteur
    sel._printer_combo.set_current_key(CENTAURI, emit=False)
    sel._on_confirm_printer()
    from data.printers import brand_of
    dispo = {mk for _l, mk in models_for_brand(brand_of(CENTAURI),
                                               store["slicer_output"])}
    assert CENTAURI in dispo


# ── La fonction pure ──────────────────────────────────────────────────────
@pytest.mark.parametrize("modele,depuis,attendu", [
    (CENTAURI, "bambu", "elegoo"),            # la machine de Pascal
    (CENTAURI, "elegoo", ""),                 # déjà gérée : on ne bouge pas
    ("Elegoo Neptune 4 Max", "bambu", ""),    # déjà gérée
    ("Snapmaker A350", "bambu", "snapmaker"),
    ("X1 Carbon", "bambu", ""),               # Bambu Lab : hors catalogue tiers
    ("Machine inexistante", "bambu", ""),
])
def test_slicer_pour_modele(modele, depuis, attendu):
    assert slicer_pour_modele(modele, depuis) == attendu


def test_la_sortie_proposee_sait_toujours_produire_la_machine():
    """Sur TOUT le catalogue : ou bien la sortie courante convient, ou bien
    celle qu'on propose convient. Jamais un cul de sac."""
    for mk, v in _by_model().items():
        for depuis in ("bambu", "orca", "elegoo", "creality"):
            cible = slicer_pour_modele(mk, depuis)
            effectif = cible or depuis
            assert _slicer_supported(effectif, v["slicers"], v["marque"]), \
                f"{mk} depuis {depuis} : {effectif} ne sait pas la produire"


# ── Les autres écosystèmes ne bougent pas ─────────────────────────────────
@pytest.mark.parametrize("slicer", ["prusa", "cura", "flashprint"])
def test_les_catalogues_separes_restent_separes(app, monkeypatch, slicer):
    """PrusaSlicer, Cura et FlashPrint ont leurs propres listes de machines :
    y mélanger le catalogue OrcaSlicer donnerait des exports impossibles."""
    import core.prefs as _p
    import ui.components.filament_printer_selector as F
    store = {"slicer_output": slicer}
    monkeypatch.setattr(_p.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(_p.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(F, "PREFS", _p.PREFS)
    sel = F.FilamentPrinterSelector()
    sel.show()
    app.processEvents()
    try:
        assert CENTAURI not in sel._printer_combo._key_label
    finally:
        sel.deleteLater()
