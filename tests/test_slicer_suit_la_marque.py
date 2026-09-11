# -*- coding: utf-8 -*-
"""Le slicer de sortie doit suivre la MARQUE de l'imprimante choisie.

Retour utilisatrice : « j'ai voulu utiliser neoSlice pour ma Centauri Carbon
mais il m'a fait le 3MF pour Snapmaker Orca alors que j'avais bien rempli que
c'était pour la Elegoo ». Cause : Snapmaker Orca embarque toute la bibliothèque
OrcaSlicer, donc neoSlice y proposait 367 machines (19 Snapmaker seulement) —
on pouvait choisir une Elegoo avec une sortie restée sur Snapmaker.

Règle : un slicer PROPRE à une marque (Snapmaker Orca, ElegooSlicer,
CrealityPrint…) bascule vers celui de la marque choisie ; les slicers
GÉNÉRIQUES (OrcaSlicer, Bambu Studio…) ne sont jamais touchés.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.printers import (marque_du_slicer, slicer_de_marque,      # noqa: E402
                           brand_of, _slicer_supported, _by_model)


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def selecteur(app, monkeypatch):
    """Sélecteur avec des PRÉFÉRENCES EN MÉMOIRE (aucune écriture réelle)."""
    import core.prefs as _p
    import ui.components.filament_printer_selector as F
    store = {"slicer_output": "snapmaker"}
    monkeypatch.setattr(_p.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(_p.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(F, "PREFS", _p.PREFS)
    sel = F.FilamentPrinterSelector()
    sel.setFixedWidth(360)
    sel.show()                       # sans affichage, le layout n'est pas calculé
    app.processEvents()              # (toutes les positions resteraient à 0)
    yield sel, store
    sel.deleteLater()


# ── Table marque ↔ slicer ────────────────────────────────────────────────────
def test_slicers_de_marque_et_generiques():
    assert marque_du_slicer("snapmaker") == "Snapmaker"
    assert marque_du_slicer("elegoo") == "Elegoo"
    # génériques : ils acceptent légitimement toutes les marques
    for generique in ("orca", "bambu", ""):
        assert marque_du_slicer(generique) == ""
    assert slicer_de_marque("Elegoo") == "elegoo"
    assert slicer_de_marque("Sovol") == ""          # pas de slicer maison


def test_le_piege_existe_bien_dans_le_catalogue():
    """Documente la cause : la sortie Snapmaker propose surtout des machines
    d'AUTRES marques — d'où l'erreur possible."""
    proposees = [v for v in _by_model().values()
                 if _slicer_supported("snapmaker", v["slicers"], v["marque"])]
    autres = [v for v in proposees if v["marque"] != "Snapmaker"]
    assert len(autres) > 100, "le catalogue Snapmaker devrait rester large"


# ── Bascule ──────────────────────────────────────────────────────────────────
def test_elegoo_choisie_bascule_sur_elegooslicer(selecteur):
    sel, store = selecteur
    sel._printer_combo.set_current_key("Elegoo Centauri Carbon", emit=False)
    messages = []
    sel.status_message.connect(messages.append)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "elegoo"
    assert sel.current_printer() == "Elegoo Centauri Carbon"   # sélection gardée
    assert messages and "ElegooSlicer" in messages[0]


def test_machine_de_la_meme_marque_ne_bascule_pas(selecteur):
    sel, store = selecteur
    sel._printer_combo.set_current_key("Snapmaker U1", emit=False)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "snapmaker"


def test_slicer_generique_jamais_touche(selecteur):
    """OrcaSlicer ouvre toutes les marques : c'est un choix légitime."""
    sel, store = selecteur
    store["slicer_output"] = "orca"
    sel._printer_combo.set_current_key("Elegoo Centauri Carbon", emit=False)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "orca"


def test_le_logiciel_est_dans_la_colonne_pas_dans_les_reglages(selecteur):
    """Le choix du logiciel a quitté les Réglages (où il était invisible au
    moment de choisir la machine) pour la tête de la colonne de gauche."""
    sel, store = selecteur
    assert sel._slicer_combo.currentData() == "snapmaker"      # reflète la préf
    # ordre visuel : le logiciel est AU-DESSUS de l'imprimante
    y_slicer = sel._lbl_slicer.mapTo(sel, sel._lbl_slicer.rect().topLeft()).y()
    y_printer = sel._lbl_p.mapTo(sel, sel._lbl_p.rect().topLeft()).y()
    assert y_slicer < y_printer

    import inspect
    from ui.components import settings_dialog
    src = inspect.getsource(settings_dialog)
    assert "_slicer_combo" not in src, "le réglage doublon subsiste dans les Réglages"


def test_changer_de_logiciel_recharge_le_catalogue(selecteur):
    sel, store = selecteur
    codes = [sel._slicer_combo.itemData(i) for i in range(sel._slicer_combo.count())]
    assert codes == [c for c, _k in __import__(
        "ui.components.filament_printer_selector", fromlist=["x"])._SLICERS_SORTIE]
    sel._slicer_combo.setCurrentIndex(codes.index("prusa"))
    assert store["slicer_output"] == "prusa"
    # le catalogue a suivi : on ne propose plus que des machines PrusaSlicer
    from data.printers import is_prusa_model
    assert is_prusa_model(sel.current_printer())


def test_la_bascule_auto_met_a_jour_le_combo(selecteur):
    """Cohérence : après une bascule automatique, le combo en tête doit montrer
    le NOUVEAU logiciel — sinon il afficherait encore Snapmaker Orca."""
    sel, store = selecteur
    sel._printer_combo.set_current_key("Elegoo Centauri Carbon", emit=False)
    sel._on_confirm_printer()
    assert store["slicer_output"] == "elegoo"
    assert sel._slicer_combo.currentData() == "elegoo"


def test_tutoriel_ne_renvoie_plus_aux_reglages_pour_le_logiciel():
    from ui.components.tutorial_overlay import _STEPS_FR, _STEPS_EN
    for steps in (_STEPS_FR, _STEPS_EN):
        cibles = [s.target for s in steps]
        assert "config" in cibles
        # plus d'étape « ouvrez les Réglages pour choisir le slicer »
        etape_reglages = [s for s in steps if s.target == "settings"]
        assert not etape_reglages, "l'étape Réglages du tuto est obsolète"
    # et le nombre de logiciels annoncé est à jour (9, plus 5)
    assert "9" in _STEPS_FR[0].body and "5 slicers" not in _STEPS_FR[0].body


def test_bascule_reste_coherente(selecteur):
    """Après bascule, l'imprimante doit rester sélectionnable ET ses buses
    disponibles (sinon on l'enverrait dans un catalogue où elle n'existe pas)."""
    sel, store = selecteur
    sel._printer_combo.set_current_key("Elegoo Centauri Carbon", emit=False)
    sel._on_confirm_printer()
    buses = [sel._nozzle_combo.itemData(i) for i in range(sel._nozzle_combo.count())]
    assert 0.4 in buses
    assert brand_of(sel.current_printer()) == "Elegoo"
    assert slicer_de_marque(brand_of(sel.current_printer())) == store["slicer_output"]
