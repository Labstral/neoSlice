# -*- coding: utf-8 -*-
"""Journal d'impressions — taux d'échec RÉEL par machine/filament, alimenté à la
main ou automatiquement par les commandes arrivées à « Terminé »."""
import pytest

from core.business import store


@pytest.fixture(autouse=True)
def _isole_store(tmp_path, monkeypatch):
    """Toutes les collections dans un dossier temporaire — zéro écriture réelle."""
    for attr in ("_IMPRESSIONS", "_ORDERS", "_SPOOLS"):
        monkeypatch.setattr(store, attr, tmp_path / f"{attr.strip('_').lower()}.json")
    yield


def test_add_list_delete():
    p = store.add_print({"piece": "Support", "machine": "X1C",
                         "filament": "PLA", "statut": "ok", "grams": 30})
    assert p["id"] and p["date"]
    e = store.add_print({"piece": "Boîtier", "machine": "X1C",
                         "filament": "PETG", "statut": "echec",
                         "defaut": "warping"})
    assert len(store.list_prints()) == 2
    assert store.delete_print(e["id"]) is True
    assert len(store.list_prints()) == 1


def test_failure_stats():
    assert store.failure_stats()["taux_pct"] is None      # pas de données ≠ 0 %
    for statut, machine, fil in [("ok", "X1C", "PLA"), ("ok", "X1C", "PLA"),
                                 ("ok", "X1C", "PLA"), ("echec", "X1C", "PETG"),
                                 ("ok", "U1", "PLA")]:
        store.add_print({"statut": statut, "machine": machine, "filament": fil})
    s = store.failure_stats()
    assert s["n"] == 5 and s["echecs"] == 1
    assert s["taux_pct"] == pytest.approx(20.0)
    assert s["par_machine"]["X1C"]["taux_pct"] == pytest.approx(25.0)
    assert s["par_machine"]["U1"]["echecs"] == 0
    assert s["par_filament"]["PETG"]["taux_pct"] == pytest.approx(100.0)
    assert store.failure_stats(machine="U1")["taux_pct"] == 0.0


def test_commande_terminee_alimente_le_journal():
    """« Terminé » → une entrée « réussie », UNE seule fois même en revenant
    en arrière puis en avançant à nouveau (drapeau print_logged)."""
    sp = store.add_spool({"materiau": "PETG", "poids_total_g": 1000,
                          "poids_restant_g": 1000})
    o = store.add_order({"items": [{"designation": "Presse-agrumes", "qty": 1,
                                    "unit_price_ht": 12.0}],
                         "status": "todo",
                         "consumptions": [{"spool_id": sp["id"], "grams": 80}]})
    assert store.list_prints() == []                     # todo → rien
    store.set_order_status(o["id"], "printing")
    assert store.list_prints() == []                     # imprimer ≠ terminé
    store.set_order_status(o["id"], "done")
    prints = store.list_prints()
    assert len(prints) == 1
    assert prints[0]["statut"] == "ok"
    assert prints[0]["piece"] == "Presse-agrumes"
    assert prints[0]["filament"] == "PETG"               # via la bobine liée
    assert prints[0]["source"] == "commande"
    # aller-retour de statut : pas de doublon
    store.set_order_status(o["id"], "printing")
    store.set_order_status(o["id"], "done")
    store.set_order_status(o["id"], "paid")
    assert len(store.list_prints()) == 1


def test_commande_annulee_jamais_loguee():
    o = store.add_order({"status": "todo"})
    store.set_order_status(o["id"], "cancelled")
    assert store.list_prints() == []
