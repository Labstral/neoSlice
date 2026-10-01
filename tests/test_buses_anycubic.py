# -*- coding: utf-8 -*-
"""Les buses d'une machine ne sont proposées que si la SORTIE sait les produire.

Bruno Guerin, Anycubic Kobra S1 Combo, 2026-10-01 : « le fichier 3mf n'est pas
pris en compte par mon imprimante. J'ai la version combo, prévoyez vous de la
mettre dans les imprimantes compatibles ? »

En lui répondant, deux trous sont apparus.

1. Le « Combo » n'existe nulle part : ni dans OrcaSlicer, ni dans ElegooSlicer,
   ni dans Cura, ni dans PrusaSlicer, ni même dans les profils d'Anycubic
   Slicer Next. Anycubic n'a que « Kobra S1 » et « Kobra S1 Max ». Le Combo est
   la même machine vendue avec l'unité multi-matière, il n'y a donc rien à
   ajouter.

2. En revanche Anycubic Slicer Next propose QUATRE buses pour la Kobra S1
   (0,25 / 0,4 / 0,6 / 0,8) là où OrcaSlicer n'en a qu'une. Le catalogue de
   neoSlice étant bâti sur Bambu Studio et OrcaSlicer, un possesseur de Kobra
   S1 en 0,6 ne trouvait pas sa buse. Anycubic Slicer est devenu une source de
   profils, ce qui a aussi fait entrer cinq machines Kobra absentes partout
   ailleurs.

⚠ Ces buses n'existent QUE chez Anycubic. Les proposer sous une sortie
OrcaSlicer écrirait dans le 3MF le nom d'un préréglage qu'Orca ne possède pas,
et le slicer retomberait sur une autre machine sans rien dire. D'où le filtrage
par logiciel de sortie, demandé explicitement par Emmanuel.
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.printers import (_by_model, is_catalogue_model,        # noqa: E402
                           machine_config_for, nozzles_for_model,
                           volume_impression)

KOBRA = "Anycubic Kobra S1"
RACINE = Path(__file__).resolve().parent.parent


# ── Le cas de Bruno ───────────────────────────────────────────────────────
def test_la_kobra_s1_a_bien_ses_quatre_buses():
    assert nozzles_for_model(KOBRA) == [0.25, 0.4, 0.6, 0.8]


def test_le_combo_n_est_pas_une_machine_a_part():
    """Si un « Combo » apparaît un jour dans les profils d'un slicer, ce test
    le signalera, et il faudra alors le proposer dans le menu."""
    combos = [mk for mk in _by_model() if "combo" in mk.lower()]
    assert not combos, f"un modèle « Combo » est apparu : {combos}"


def test_la_kobra_s1_est_une_vraie_machine_du_catalogue():
    assert is_catalogue_model(KOBRA)
    assert volume_impression(KOBRA) == (250.0, 250.0, 250.0)


# ── Le filtrage par logiciel de sortie ────────────────────────────────────
@pytest.mark.parametrize("slicer,attendu", [
    ("anycubic", [0.25, 0.4, 0.6, 0.8]),   # son logiciel maison les a toutes
    ("orca", [0.4]),                        # OrcaSlicer n'a que la 0,4
    ("elegoo", [0.4]),
])
def test_les_buses_suivent_la_sortie(slicer, attendu):
    assert nozzles_for_model(KOBRA, slicer) == attendu


def test_sans_sortie_precisee_on_voit_tout():
    """Le filtre est un choix de l'appelant, pas un comportement caché."""
    assert len(nozzles_for_model(KOBRA)) >= len(nozzles_for_model(KOBRA, "orca"))


def test_une_machine_presente_partout_garde_ses_buses():
    """La Kobra S1 Max existe en quatre buses dans OrcaSlicer aussi : le
    filtrage ne doit rien lui retirer."""
    mk = "Anycubic Kobra S1 Max"
    assert nozzles_for_model(mk, "orca") == nozzles_for_model(mk, "anycubic")


def test_chaque_buse_proposee_a_un_profil_machine():
    """Une buse sans profil machine produirait un 3MF qui nomme un préréglage
    inexistant. On vérifie sur TOUT le catalogue, pas seulement Anycubic."""
    manquants = []
    for mk, e in _by_model().items():
        for nz, nom in e["nozzles"].items():
            if not machine_config_for(nom):
                manquants.append(f"{mk} / {nz} → {nom}")
    assert not manquants, f"{len(manquants)} buses sans profil : {manquants[:5]}"


# ── Le sélecteur ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _selecteur(app, monkeypatch, slicer):
    import core.prefs as _p
    import ui.components.filament_printer_selector as F
    store = {"slicer_output": slicer}
    monkeypatch.setattr(_p.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(_p.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(F, "PREFS", _p.PREFS)
    sel = F.FilamentPrinterSelector()
    sel.show()
    app.processEvents()
    return sel, store


def test_le_combo_de_buses_suit_la_sortie(app, monkeypatch):
    sel, store = _selecteur(app, monkeypatch, "bambu")
    try:
        sel._printer_combo.set_current_key(KOBRA, emit=True)
        app.processEvents()
        # Bambu Studio ne sait pas produire cette machine → bascule automatique
        assert store["slicer_output"] == "anycubic"
        buses = [sel._nozzle_combo.itemData(i) for i in range(sel._nozzle_combo.count())]
        assert buses == [0.25, 0.4, 0.6, 0.8]

        store["slicer_output"] = "orca"
        sel.refresh_printers()
        sel._printer_combo.set_current_key(KOBRA, emit=True)
        app.processEvents()
        buses = [sel._nozzle_combo.itemData(i) for i in range(sel._nozzle_combo.count())]
        assert buses == [0.4], "OrcaSlicer n'a qu'une buse pour cette machine"
    finally:
        sel.deleteLater()


def test_le_combo_de_buses_n_est_jamais_vide(app, monkeypatch):
    """Repli : si aucune buse ne correspond à la sortie courante, mieux vaut
    montrer la liste complète qu'un menu vide dont on ne peut rien faire."""
    sel, _store = _selecteur(app, monkeypatch, "bambu")
    try:
        for mk in list(_by_model())[:40]:
            sel._printer_combo.set_current_key(mk, emit=True)
            app.processEvents()
            assert sel._nozzle_combo.count() > 0, f"{mk} : aucune buse proposée"
    finally:
        sel.deleteLater()


# ── Les ajouts manuels ne doivent plus disparaître ────────────────────────
def test_l_eryone_thinker_se_survit_a_une_regeneration():
    """Elle ne vient d'AUCUN slicer installé : elle avait été ajoutée à la main
    en 0.1.8.2, et régénérer le catalogue l'effaçait en silence. La machine
    d'un utilisateur disparaissait du menu à la release suivante."""
    assert "Eryone Thinker SE" in _by_model()
    extra = json.loads((RACINE / "data" / "printers_catalog_extra.json")
                       .read_text(encoding="utf-8"))
    assert "Eryone Thinker SE 0.4 nozzle" in extra


def test_les_ajouts_manuels_portent_catalogue_et_machine():
    """Sans le bloc machine, le modèle serait proposé au menu mais l'export
    n'aurait aucun profil à écrire."""
    extra = json.loads((RACINE / "data" / "printers_catalog_extra.json")
                       .read_text(encoding="utf-8"))
    for nom, bloc in extra.items():
        assert bloc.get("catalogue") and bloc.get("machine"), nom
        assert machine_config_for(nom), f"{nom} : profil machine introuvable"


def test_l_extracteur_moissonne_bien_anycubic():
    src = (RACINE / "tools" / "extract_printers.py").read_text(encoding="utf-8")
    assert '"anycubic"' in src and "AnycubicSlicerNext" in src
    assert "fusionner_ajouts_manuels" in src, "les ajouts manuels seraient reperdus"
