# -*- coding: utf-8 -*-
"""Relances d'impayés (lettre PDF, langue du document) + export comptable CSV
par année — Espace Pro."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.business import store                        # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isole_store(tmp_path, monkeypatch):
    for attr in ("_INVOICES", "_COMPANY"):
        monkeypatch.setattr(store, attr, tmp_path / f"{attr.strip('_').lower()}.json")
    yield


def _facture(**kw):
    base = {"date": "2026-01-10", "currency": "EUR", "vat_rate": 20.0,
            "client": {"nom": "Atelier Dupont", "ville": "Lyon"},
            "items": [{"designation": "Pièce", "qty": 2, "unit_price_ht": 50.0}]}
    base.update(kw)
    return store.add_invoice(base)


def test_echeance_saisie_prime_sur_le_defaut():
    """Une échéance à +15 j saisie dans le formulaire (due_date) doit piloter la
    relance — avant, le défaut +30 j l'écrasait silencieusement."""
    inv = _facture(due_date="2026-01-25")
    assert inv["echeance"] == "2026-01-25"
    sans = _facture()                                   # pas de due_date → +30 j
    assert sans["echeance"] == "2026-02-09"


def test_client_label_rempli_depuis_la_fiche():
    inv = _facture()
    assert inv["client_label"] == "Atelier Dupont"


def test_overdue_et_relance():
    inv = _facture(due_date="2026-01-25")
    assert store.days_overdue(inv, ref="2026-02-04") == 10
    assert [i["id"] for i in store.invoices_overdue(ref="2026-02-04")] == [inv["id"]]
    store.set_invoice_status(inv["id"], "paid")
    assert store.invoices_overdue(ref="2026-02-04") == []
    store.mark_relance(inv["id"])
    assert store.get_invoice(inv["id"])["relance_le"]


def test_export_csv_par_annee(tmp_path):
    _facture(date="2025-06-01")
    _facture(date="2026-01-10")
    # facture HISTORIQUE sans client_label (créée avant le correctif) → repli
    items = store._load(store._INVOICES)
    items[0].pop("client_label", None)
    store._save(store._INVOICES, items)

    assert store.invoice_years() == [2026, 2025]
    tout = store.export_accounting_csv(tmp_path / "tout.csv")
    seul = store.export_accounting_csv(tmp_path / "2026.csv", annee=2026)
    lignes_tout = tout.read_text(encoding="utf-8-sig").strip().splitlines()
    lignes_2026 = seul.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lignes_tout) == 3 and len(lignes_2026) == 2     # en-tête + n
    assert "2026-01-10" in lignes_2026[1] and "2025" not in lignes_2026[1]
    # la colonne Client n'est jamais vide (repli sur la fiche imbriquée)
    assert all("Atelier Dupont" in l for l in lignes_tout[1:])


def test_termes_relance_6_langues():
    from core.business.doc_i18n import TERMS, DOC_LANGS
    for cle in ("reminder_title", "reminder_obj", "reminder_greeting",
                "reminder_body", "reminder_body2", "reminder_sign"):
        assert cle in TERMS, cle
        for lg in DOC_LANGS:
            assert TERMS[cle].get(lg), f"{cle}/{lg}"
    # les placeholders du corps sont identiques dans toutes les langues
    import re
    ref = set(re.findall(r"\{(\w+)\}", TERMS["reminder_body"]["fr"]))
    for lg in DOC_LANGS:
        assert set(re.findall(r"\{(\w+)\}", TERMS["reminder_body"][lg])) == ref, lg


def test_lettre_relance_pdf(app, tmp_path):
    """La lettre se génère (PDF non vide), dans la langue du pays de la facture."""
    from core.export.relance_pdf import render_relance
    store.save_company({"nom": "neoFab", "ville": "Annecy", "pays": "France",
                        "iban": "FR76 0000 0000 0000"})
    inv = _facture(due_date="2026-01-25", country="Allemagne")
    for pays, nom in (("Allemagne", "de.pdf"), ("France", "fr.pdf")):
        inv2 = dict(inv); inv2["country"] = pays
        out = tmp_path / nom
        render_relance(str(out), inv2, store.get_company())
        assert out.exists() and out.stat().st_size > 1000


def test_i18n_cles_ui():
    from core.i18n import _FR, _EN
    for cle in ("fact.relance_pdf", "fact.relance_last",
                "dash.export_year", "dash.export_all_years"):
        assert cle in _FR and cle in _EN, cle
