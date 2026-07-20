# -*- coding: utf-8 -*-
"""Mode de performance AUTO — décision par pièce (core/perf.py).

Vérifie la logique machine × pièce : petite pièce → tout tourne même sur PC
lent ; grosse pièce sur PC lent → surplombs sautés avec la raison « auto » ;
modes manuels full/lite respectés ; legacy « balanced » traité comme auto ;
« Forcer » ignore tout.
"""
from __future__ import annotations

import pytest

from core import perf
from core.prefs import PREFS


@pytest.fixture(autouse=True)
def _sauver_prefs():
    """Sauvegarde/restaure les PREFS touchées par les tests."""
    avant = {k: PREFS.get(k, None) for k in ("perf_mode", "bench_ms")}
    yield
    for k, v in avant.items():
        if v is None:
            try:
                PREFS.set(k, "")
            except Exception:
                pass
        else:
            PREFS.set(k, v)
    PREFS.set("perf_mode", avant["perf_mode"] or "auto")


def _machine(bench_ms: float):
    PREFS.set("bench_ms", bench_ms)


def test_auto_petite_piece_meme_pc_lent():
    PREFS.set("perf_mode", "auto")
    _machine(80.0)                                   # PC très lent
    d = perf.decision(30_000)                        # porte-clés
    assert d["overhangs"] is True and d["skip_reason"] == ""


def test_auto_grosse_piece_pc_lent_saute_avec_raison():
    PREFS.set("perf_mode", "auto")
    _machine(80.0)
    d = perf.decision(400_000)                       # gros scan
    assert d["overhangs"] is False and d["skip_reason"] == "auto"


def test_auto_grosse_piece_pc_rapide_tourne():
    PREFS.set("perf_mode", "auto")
    _machine(1.0)                                    # machine rapide
    d = perf.decision(450_000)
    assert d["overhangs"] is True                    # plafond 500k sur PC rapide


def test_plafond_borne():
    _machine(1.0)
    assert perf.plafond_faces_auto() == perf.FACES_MAX_RAPIDE
    _machine(10_000.0)                               # machine absurde-lente
    assert perf.plafond_faces_auto() == perf.FACES_MIN


def test_mode_full_force_tout():
    PREFS.set("perf_mode", "full")
    _machine(80.0)
    d = perf.decision(499_000)
    assert d["overhangs"] is True and d["skip_reason"] == ""


def test_mode_lite_coupe_toujours():
    PREFS.set("perf_mode", "lite")
    _machine(1.0)
    d = perf.decision(5_000)
    assert d["overhangs"] is False and d["skip_reason"] == "lite"


def test_legacy_balanced_devient_auto():
    PREFS.set("perf_mode", "balanced")               # ancien réglage stocké
    _machine(1.0)
    d = perf.decision(5_000)
    assert d["overhangs"] is True and d["skip_reason"] == ""


def test_forcer_ignore_tout():
    PREFS.set("perf_mode", "lite")
    _machine(80.0)
    d = perf.decision(2_000_000, force_full=True)
    assert d["overhangs"] is True and d["skip_reason"] == ""


def test_bench_mesure_et_cache():
    PREFS.set("bench_ms", 0)                         # force une mesure
    v = perf.bench_ms()
    assert v > 0
    assert float(PREFS.get("bench_ms", 0)) == pytest.approx(v, abs=0.01)
