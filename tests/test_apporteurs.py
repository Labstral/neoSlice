"""Apporteurs d'affaires : attribution au client (période) + cumul des commissions
par période. Isolé sur des fichiers temporaires (aucune donnée réelle touchée)."""
from datetime import date, timedelta

import pytest


@pytest.fixture
def st(tmp_path, monkeypatch):
    from core.business import store
    monkeypatch.setattr(store, "_APPORTEURS", tmp_path / "apporteurs.json")
    monkeypatch.setattr(store, "_CLIENTS", tmp_path / "clients.json")
    monkeypatch.setattr(store, "_QUOTES", tmp_path / "devis.json")
    return store


def test_apporteur_actif_du_client(st):
    today = date.today()
    a = st.add_apporteur({"nom": "Jean", "commission": 10})
    actif = st.add_client({"nom": "Actif", "apporteur_id": a["id"],
                           "apporteur_debut": (today - timedelta(days=10)).isoformat(),
                           "apporteur_fin": (today + timedelta(days=100)).isoformat()})
    expire = st.add_client({"nom": "Expiré", "apporteur_id": a["id"],
                            "apporteur_debut": (today - timedelta(days=400)).isoformat(),
                            "apporteur_fin": (today - timedelta(days=10)).isoformat()})
    pas_commence = st.add_client({"nom": "Futur", "apporteur_id": a["id"],
                                  "apporteur_debut": (today + timedelta(days=10)).isoformat(),
                                  "apporteur_fin": (today + timedelta(days=100)).isoformat()})
    sans = st.add_client({"nom": "Sans"})

    assert st.apporteur_actif_du_client(actif["id"]) == a["id"]
    assert st.apporteur_actif_du_client(expire["id"]) == ""
    assert st.apporteur_actif_du_client(pas_commence["id"]) == ""
    assert st.apporteur_actif_du_client(sans["id"]) == ""
    assert st.apporteur_actif_du_client("") == ""
    # champs d'attribution bien persistés
    assert st.get_client(actif["id"])["apporteur_id"] == a["id"]


def test_commissions_par_periode(st):
    today = date.today()
    a = st.add_apporteur({"nom": "Jean", "commission": 10})
    m_deb = today.replace(day=1).isoformat()
    last = today.replace(day=1) - timedelta(days=1)
    lm_deb, lm_fin = last.replace(day=1).isoformat(), last.isoformat()

    def q(amount, d, converti=None):
        x = st.add_quote({"apporteur_id": a["id"], "commission_amount": amount,
                          "currency": "CHF", "total_price": amount * 10})
        items = st._load(st._QUOTES)
        for it in items:
            if it["id"] == x["id"]:
                it["date"] = d
                if converti:
                    it["status"] = "converted"
                    it["converti_le"] = converti
        st._save(st._QUOTES, items)

    q(24.44, today.isoformat(), converti=today.isoformat())   # ce mois, facturé
    q(50.00, today.isoformat())                               # ce mois, non facturé
    q(30.00, lm_deb, converti=lm_deb)                         # mois dernier, facturé

    total = st.commissions_for_apporteur(a["id"])
    assert total["total_prevu"] == pytest.approx(104.44)
    assert total["total_realise"] == pytest.approx(54.44)

    # fin de période = AUJOURD'HUI (pas le 28 : lancé un 29/30/31, la conversion
    # du jour sortait de la fenêtre et le test cassait en fin de mois)
    mois = st.commissions_for_apporteur(a["id"], m_deb, today.isoformat())
    assert mois["total_realise"] == pytest.approx(24.44)      # à régler ce mois
    assert mois["n_invoiced"] == 1

    lastm = st.commissions_for_apporteur(a["id"], lm_deb, lm_fin)
    assert lastm["total_realise"] == pytest.approx(30.00)


def test_mark_quote_converted_stamp(st):
    a = st.add_apporteur({"nom": "Jean", "commission": 10})
    x = st.add_quote({"apporteur_id": a["id"], "commission_amount": 12.0, "currency": "CHF"})
    st.mark_quote_converted(x["id"], "F-2026-0001")
    q = next(q for q in st._load(st._QUOTES) if q["id"] == x["id"])
    assert q["status"] == "converted"
    assert q["invoice_number"] == "F-2026-0001"
    assert q.get("converti_le")            # date de réalisation posée
