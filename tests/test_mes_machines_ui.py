"""« Mes machines » côté UI — un favori dont la clé n'existe plus doit pouvoir partir.

Régression Emmanuel (2026-08-23) : un favori « Snapmaker U1 0.4 nozzle » épinglé alors
que le catalogue expose la clé « U1 » restait dans le menu SANS jamais pouvoir être
sélectionné → l'étoile ne passait jamais en ★ → favori impossible à retirer.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication            # noqa: E402

from core import mes_machines as mm                    # noqa: E402
from core.i18n import _                                # noqa: E402
from ui.components.filament_printer_selector import FilamentPrinterSelector  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isole_prefs(monkeypatch):
    """PREFS en mémoire : aucun risque d'écrire dans les vraies préférences."""
    store = {"slicer_output": "bambu"}
    import core.prefs as _p
    monkeypatch.setattr(_p.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(_p.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(mm.PREFS, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(mm.PREFS, "set", lambda k, v: store.__setitem__(k, v))
    yield store


def test_favori_obsolete_est_retire_au_clic(app, _isole_prefs):
    """Clé absente du catalogue → l'entrée est purgée et l'utilisateur est prévenu."""
    mm.pin("snapmaker", "Snapmaker U1 0.4 nozzle", "Snapmaker U1")
    sel = FilamentPrinterSelector()
    sel._populate_printers()

    cle = mm.machine_key(mm.list_machines()[0])
    assert cle in sel._printer_combo._key_label, "le favori doit être proposé au menu"

    messages = []
    sel.status_message.connect(messages.append)

    sel._printer_combo.set_current_key(cle, emit=True)

    assert mm.list_machines() == [], "le favori mort doit être retiré, pas ignoré"
    assert messages and "Snapmaker U1" in messages[0]
    # et on ne reste pas bloqué sur une entrée @mm
    assert mm.parse_machine_key(sel._printer_combo.current_key()) is None


def test_favori_valide_reste_et_se_depingle(app, _isole_prefs):
    """Cas normal : le favori se sélectionne, l'étoile passe ★, un clic le retire."""
    sel = FilamentPrinterSelector()
    printer = sel.current_printer()
    assert printer, "une imprimante doit être sélectionnée par défaut"

    sel._on_pin_clicked()                       # épingle la machine courante
    assert mm.is_pinned("bambu", printer)
    sel._refresh_pin_btn()
    assert sel._pin_btn.text() == "★"
    assert sel._pin_btn.toolTip() == _("selector.unpin_tip")

    sel._on_pin_clicked()                       # re-clic = retrait
    assert mm.list_machines() == []
    assert sel._pin_btn.text() == "☆"
    assert sel._pin_btn.toolTip() == _("selector.pin_tip")


@pytest.mark.parametrize("depart,arrivee", [("dark", "light"), ("light", "dark")])
def test_etoile_suit_le_theme_dans_les_deux_sens(app, _isole_prefs, depart, arrivee):
    """L'étoile ★ doit se recolorer au changement de thème, sans re-clic.

    Régression : son style n'était posé que par _refresh_pin_btn (appelé au clic),
    et refresh_theme ne le rappelait pas → elle gardait la couleur de l'ancien thème.
    """
    from ui.styles.theme import MANAGER as _T
    initial = _T.name()
    try:
        _T.switch(depart)
        sel = FilamentPrinterSelector()
        sel._on_pin_clicked()                       # épinglée → ★, couleur ACCENT
        assert sel._pin_btn.text() == "★"
        acc_depart = _T.palette()["ACCENT"]
        assert acc_depart.lower() in sel._pin_btn.styleSheet().lower()

        _T.switch(arrivee)
        sel.refresh_theme()
        acc_arrivee = _T.palette()["ACCENT"]
        assert acc_arrivee.lower() != acc_depart.lower(), "les 2 thèmes doivent différer"
        style = sel._pin_btn.styleSheet().lower()
        assert acc_arrivee.lower() in style, "l'étoile garde la couleur de l'ancien thème"
        assert acc_depart.lower() not in style

        # la note imprimante (avertissement ambre) suit aussi le thème
        assert _T.palette()["AMBER"].lower() in sel._printer_note.styleSheet().lower()

        # même exigence pour l'étoile creuse (non épinglée)
        sel._on_pin_clicked()
        assert sel._pin_btn.text() == "☆"
        _T.switch(depart)
        sel.refresh_theme()
        assert _T.palette()["TEXT_LABEL"].lower() in sel._pin_btn.styleSheet().lower()
        assert _T.palette()["AMBER"].lower() in sel._printer_note.styleSheet().lower()
    finally:
        _T.switch(initial)


def test_note_imprimante_sans_couleur_en_dur(app, _isole_prefs):
    """La note ne doit plus porter l'orange codé en dur (invisible du thème)."""
    from ui.styles.theme import MANAGER as _T
    initial = _T.name()
    try:
        for nom in ("dark", "light"):
            _T.switch(nom)
            sel = FilamentPrinterSelector()
            style = sel._printer_note.styleSheet().lower()
            assert "#e07000" not in style, f"orange en dur encore présent en {nom}"
            assert _T.palette()["AMBER"].lower() in style
    finally:
        _T.switch(initial)


def test_favori_valide_bascule_le_slicer(app, _isole_prefs):
    """Un favori dont la clé existe bascule bien slicer + imprimante (non régressé)."""
    # La clé à épingler est celle du MENU (préfixée par la marque : « Creality
    # CR-10 Max »), pas celle du catalogue brut — c'est ce décalage qui produit
    # les favoris morts si on épingle depuis une autre source.
    _isole_prefs["slicer_output"] = "snapmaker"
    ref = FilamentPrinterSelector()
    ref._populate_printers()
    cible = next(k for k in ref._printer_combo._key_label
                 if mm.parse_machine_key(k) is None)
    _isole_prefs["slicer_output"] = "bambu"

    mm.pin("snapmaker", cible, cible)
    sel = FilamentPrinterSelector()
    sel._populate_printers()
    bascules = []
    sel.slicer_switched.connect(bascules.append)

    sel._printer_combo.set_current_key(mm.machine_key(mm.list_machines()[0]), emit=True)

    assert bascules == ["snapmaker"]
    assert mm.list_machines(), "un favori VALIDE ne doit surtout pas être purgé"
    assert sel.current_printer() == cible
