"""« Mes machines » — stockage des imprimantes épinglées + clés spéciales du menu."""
import pytest

from core import mes_machines as mm


@pytest.fixture(autouse=True)
def _isole_prefs(monkeypatch):
    """Isole les prefs : mes_machines vit en mémoire pendant le test."""
    store = {}
    from core import mes_machines as _m
    monkeypatch.setattr(_m.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(_m.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    yield


def test_pin_unpin_toggle():
    assert mm.list_machines() == []
    assert mm.pin("bambu", "X1 Carbon", "X1 Carbon")
    assert mm.pin("snapmaker", "Snapmaker U1 (0.4 nozzle)", "Snapmaker U1")
    assert len(mm.list_machines()) == 2
    assert mm.pin("bambu", "X1 Carbon") is False          # dédupliqué
    assert mm.is_pinned("bambu", "X1 Carbon")
    assert not mm.is_pinned("orca", "X1 Carbon")          # slicer différent
    assert mm.toggle("bambu", "X1 Carbon") is False        # dé-épinglée
    assert len(mm.list_machines()) == 1
    assert mm.toggle("bambu", "X1 Carbon", "X1C") is True  # ré-épinglée


def test_entrees_invalides_filtrees():
    mm.PREFS.set("mes_machines", [{"slicer": "", "printer": "X"}, "junk",
                                  {"slicer": "bambu", "printer": "P1S"}])
    ms = mm.list_machines()
    assert len(ms) == 1 and ms[0]["printer"] == "P1S"
    assert ms[0]["label"] == "P1S"                         # label par défaut


def test_machine_key_roundtrip():
    m = {"slicer": "snapmaker", "printer": "Snapmaker U1 (0.4 nozzle)", "label": "U1"}
    k = mm.machine_key(m)
    assert k.startswith(mm.MM_PREFIX)
    assert mm.parse_machine_key(k) == ("snapmaker", "Snapmaker U1 (0.4 nozzle)")
    # les clés normales du catalogue ne sont jamais interprétées
    assert mm.parse_machine_key("X1 Carbon") is None
    assert mm.parse_machine_key("") is None
    assert mm.parse_machine_key("@mm:sansprinter") is None


def test_slicer_labels():
    assert mm.slicer_label("bambu") == "Bambu Studio"
    assert mm.slicer_label("snapmaker") == "Snapmaker Orca"
    assert mm.slicer_label("inconnu") == "inconnu"
