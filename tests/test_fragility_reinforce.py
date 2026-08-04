"""Tests du renforcement automatique des pièces fragiles (édition multi-objets).

- Moteur pur `fragility_reinforce` (niveaux, renfort parois+remplissage, non-réduction).
- Logique d'application `MainWindow._auto_renforcer_pieces_fragiles` (liée à un faux
  `self`) : orange/rouge renforcées, vertes normales, éditions manuelles respectées,
  nettoyage des renforts auto obsolètes, pilotage par la préférence.
"""
from core.parameters.parameter_engine import PrintConfig
from core.parameters.fragility_reinforce import (
    FRAG_ORANGE, FRAG_RED, appliquer_renfort_auto, doit_renforcer,
    niveau_fragilite, renforcer_config,
)


# ── Moteur pur ────────────────────────────────────────────────────────────────
def test_niveaux():
    assert niveau_fragilite(0.0) == "green"
    assert niveau_fragilite(0.5) == "green"          # jaune → normal (choix Emmanuel)
    assert niveau_fragilite(FRAG_ORANGE) == "orange"
    assert niveau_fragilite(0.7) == "orange"
    assert niveau_fragilite(FRAG_RED) == "red"
    assert niveau_fragilite(0.95) == "red"
    assert niveau_fragilite("nan") == "green"        # robustesse


def test_doit_renforcer():
    assert not doit_renforcer(0.3)
    assert doit_renforcer(0.7)
    assert doit_renforcer(0.9)


def test_renforcer_green_returns_none():
    assert renforcer_config(PrintConfig(), 0.2) is None


def test_renforcer_orange_and_red():
    base = PrintConfig()
    o = renforcer_config(base, 0.70)
    assert o.wall_loops >= 4 and o.infill_density >= 30
    assert {"wall_loops", "infill_density"} <= o.model_fields_set
    r = renforcer_config(base, 0.90)
    assert r.wall_loops >= 5 and r.infill_density >= 40


def test_renforcer_never_reduces_below_base():
    strong = PrintConfig()
    strong.wall_loops = 8
    strong.infill_density = 60
    o = renforcer_config(strong, 0.70)     # renfort orange = 4/30 < base
    assert o.wall_loops == 8 and o.infill_density == 60


def test_renforcer_does_not_mutate_base():
    base = PrintConfig()
    w0, i0 = base.wall_loops, base.infill_density
    renforcer_config(base, 0.9)
    assert base.wall_loops == w0 and base.infill_density == i0


# ── Application (fonction PURE appliquer_renfort_auto — pas d'import UI) ────────
def test_apply_reinforces_orange_red_only():
    state, count, removed = appliquer_renfort_auto(
        {"a": 0.2, "b": 0.7, "c": 0.9}, PrintConfig(), {}, actif=True)
    assert count == 2
    assert "a" not in state                          # verte → pas de surcharge
    assert state["b"]["auto_reinforced"] and state["b"]["config"].wall_loops >= 4
    assert state["c"]["auto_reinforced"] and state["c"]["config"].wall_loops >= 5


def test_apply_respects_manual_edits():
    manual_cfg = PrintConfig(); manual_cfg.wall_loops = 2
    # 'b' fragile MAIS éditée manuellement (pas de drapeau auto) → intouchée
    state, count, _ = appliquer_renfort_auto(
        {"b": 0.9}, PrintConfig(), {"b": {"config": manual_cfg}}, actif=True)
    assert state["b"]["config"] is manual_cfg
    assert not state["b"].get("auto_reinforced")
    assert count == 0


def test_apply_removes_stale_auto_when_now_green():
    old = {"config": PrintConfig(), "auto_reinforced": True}
    state, count, removed = appliquer_renfort_auto(
        {"b": 0.2}, PrintConfig(), {"b": old}, actif=True)   # 'b' devenue verte
    assert "b" not in state and "b" in removed       # renfort auto retiré


def test_disabled_clears_auto_but_keeps_manual():
    manual = {"config": PrintConfig()}               # pas de drapeau auto
    auto = {"config": PrintConfig(), "auto_reinforced": True}
    state, count, removed = appliquer_renfort_auto(
        {"m": 0.9, "a": 0.9}, PrintConfig(),
        {"m": manual, "a": auto}, actif=False)
    assert "a" not in state and "a" in removed        # auto retiré
    assert state["m"] is manual                       # manuel conservé
    assert count == 0


def test_no_base_config_is_noop():
    state, count, _ = appliquer_renfort_auto(
        {"b": 0.9}, None, {}, actif=True)
    assert state == {} and count == 0                 # rien sans config commune


def test_input_state_not_mutated():
    original = {"b": {"config": PrintConfig(), "auto_reinforced": True}}
    appliquer_renfort_auto({"b": 0.2}, PrintConfig(), original, actif=True)
    assert "b" in original                            # l'appelant garde son dict
