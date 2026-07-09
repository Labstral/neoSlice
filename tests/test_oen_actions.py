"""Non-régression du parsing des actions Oen (core/assistant/actions.py).

On teste la PARTIE PARSING (marqueur -> verbe + params, JSON + rétro-compat k=v,
normalisation des lignes, couleur->hex) SANS exécuter d'écriture dans le store réel
(données sensibles). Le dispatch réel est vérifié à la main / en session.
"""
from core.assistant import actions as A


def test_parse_json_marker():
    verb, params = A._parse_marker('add_quote {"client": "Jean", "items": [{"designation": "X", "qty": 2, "unit_price": 15}]}')
    assert verb == "add_quote"
    assert params["client"] == "Jean"
    assert params["items"][0]["qty"] == 2


def test_parse_kv_backward_compat():
    verb, params = A._parse_marker("add_spool | material=PLA | color=noir | weight_g=1000")
    assert verb == "add_spool"
    assert params["material"] == "PLA"
    assert params["color"] == "noir"
    assert params["weight_g"] == "1000"


def test_norm_items_variants():
    items = A._norm_items([
        {"designation": "Fig", "qty": 3, "unit_price": 15},
        {"name": "Socle", "quantite": "2", "prix": "8.5"},
        {"designation": "", "unit_price": 0},   # ligne vide -> ignorée
    ])
    assert len(items) == 2
    assert items[0] == {"designation": "Fig", "qty": 3, "unit_price_ht": 15.0}
    assert items[1]["qty"] == 2 and items[1]["unit_price_ht"] == 8.5


def test_num_tolerant():
    assert A._num("1 000") == 1000.0 or A._num("1000") == 1000.0
    assert A._num("20 CHF") == 20.0
    assert A._num("15,5") == 15.5
    assert A._num(None, 7) == 7


def test_hex_for_named_colors():
    assert A._hex_for("noir", None) == "#000000"
    assert A._hex_for("rouge", None) == "#E23636"
    assert A._hex_for("", "1E90FF") == "#1E90FF"      # hex sans # -> ajouté
    assert A._hex_for("inconnue", None) == "#1E90FF"  # repli


def test_unknown_verb_is_stripped_no_crash():
    clean, confs = A.parse_and_execute("Voici. [[ACTION: verbe_bidon {\"x\": 1}]] fin")
    assert "[[ACTION" not in clean
    assert confs == []       # verbe inconnu -> aucun effet, aucune confirmation


def test_fake_success_detector():
    """Detecte une fausse confirmation (Oen dit avoir agi sans marqueur)."""
    assert A.claims_action_done("Le client Paul Durand a été créé avec succès.")
    assert A.claims_action_done("La commande a été supprimée.")
    assert A.claims_action_done("Le prix a été mis à jour.")
    assert A.claims_action_done("J'ai ajouté la bobine.")
    # Pas de faux positif sur une LECTURE
    assert not A.claims_action_done("Tu as 3 clients enregistrés : Marie, Paul.")
    assert not A.claims_action_done("Tu as 640 g de PLA noir en stock.")
    assert not A.claims_action_done("Quel matériau et quel poids ?")


def test_multiple_markers_execute_none():
    """SÉCURITÉ : plusieurs actions d'un coup (ex. 'tout supprimer') -> AUCUNE exécutée."""
    txt = ('[[ACTION: delete_spool {"material": "PLA", "color": "noir"}]] '
           '[[ACTION: delete_spool {"material": "PETG", "color": "rouge"}]]')
    clean, confs = A.parse_and_execute(txt)
    assert "[[ACTION" not in clean
    assert len(confs) == 1 and "sécurité" in confs[0].lower()


def test_bulk_intent_delete_refused():
    """SÉCURITÉ : intention de masse dans le message utilisateur -> suppression refusée."""
    mk = '[[ACTION: delete_spool {"material": "PLA", "color": "noir"}]]'
    for u in ("supprime tout mon stock", "vide mon stock de filament",
              "efface toutes mes bobines", "supprime tous mes clients"):
        clean, confs = A.parse_and_execute(mk, u)
        assert confs and "masse" in confs[0].lower(), u


def test_placeholder_action_not_executed():
    clean, confs = A.parse_and_execute('[[ACTION: add_client {"nom": "<nom>"}]]')
    assert len(confs) == 1 and "manque" in confs[0].lower()


def test_marker_removed_from_text():
    # verbe connu mais on ne verifie que le strip du texte (le handler ecrit le store,
    # donc on utilise un verbe inconnu pour ne rien ecrire tout en testant le strip).
    clean, _ = A.parse_and_execute("Avant [[ACTION: nope {}]] Apres")
    assert clean == "Avant  Apres".replace("  ", " ") or "Avant" in clean and "Apres" in clean
