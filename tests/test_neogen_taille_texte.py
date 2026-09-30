# -*- coding: utf-8 -*-
"""neoGen : pouvoir régler la TAILLE du texte posé sur un objet.

Kevin, utilisateur, 2026-09-30, après avoir généré une médaille : « je ne vois
pas d'outils pour modifier manuellement la taille du texte que l'on met
dessus, y a-t-il quelque chose qui m'échappe ? ».

Rien ne lui échappait. Sur 23 objets porteurs de texte, 20 n'offraient AUCUN
réglage : la taille était toujours calculée pour remplir la zone disponible.

Le réglage est un POURCENTAGE de cette taille automatique, entre 50 et 125 %.
Il est porté par le contexte et lu par les deux seules fonctions par lesquelles
tout le texte passe, ce qui évite d'ajouter un paramètre à des dizaines de
constructeurs répartis dans quatre fichiers.

⚠ Le facteur ne doit jamais se cumuler : `ajuster_dans` remet le texte à
l'échelle depuis zéro, donc il efface ce que `texte_multilignes` avait déjà
appliqué. Ce piège est testé explicitement.
"""
import pytest
import trimesh

from core.neogen import catalogue as C
from core.neogen import goodies as G


@pytest.fixture(autouse=True)
def _echelle_rendue():
    """Le réglage ne doit jamais déborder d'un objet sur le suivant."""
    yield
    assert G.echelle_texte() == 1.0, "l'échelle n'a pas été rendue"


def _volume(m):
    if isinstance(m, trimesh.Scene):
        return sum(float(g.volume) for g in m.geometry.values()
                   if isinstance(g, trimesh.Trimesh))
    return float(m.volume)


def _construire(oid, taille):
    return C.construire(oid, {"texte": "TEST", "taille_texte": taille})


# ── Le réglage agit ───────────────────────────────────────────────────────
def test_la_medaille_de_kevin_repond_au_reglage():
    """L'objet exact de son message : le badge, alias médaille."""
    petit = _volume(_construire("badge", 50))
    normal = _volume(_construire("badge", 100))
    grand = _volume(_construire("badge", 125))
    assert petit < normal < grand


@pytest.mark.parametrize("oid", [
    "badge", "plaque", "magnet", "sousverre", "marque_page", "jeton",
    "trophee", "numero_maison", "lettre_3d", "panneau_bienvenue",
])
def test_les_objets_a_texte_repondent(oid):
    C.recharger_objets_module()
    if oid not in C.PAR_ID:
        pytest.skip(f"{oid} absent du catalogue")
    v = [_volume(_construire(oid, t)) for t in (50, 100, 125)]
    assert (max(v) - min(v)) / max(v) > 1e-5, f"{oid} : aucun effet"


def test_le_facteur_ne_s_applique_jamais_deux_fois():
    """`texte_multilignes` agrandit, puis `ajuster_dans` renormalise : si les
    deux appliquaient le facteur, une demande de 125 % en donnerait 156."""
    from shapely.affinity import scale as _s
    jeton = G.regler_echelle_texte(1.25)
    try:
        mp = G.texte_multilignes("ABC", 10.0)
        ajuste = G.ajuster_dans(mp, 40.0, 10.0)
    finally:
        G.restaurer_echelle_texte(jeton)
    larg = ajuste.bounds[2] - ajuste.bounds[0]
    haut = ajuste.bounds[3] - ajuste.bounds[1]
    # La zone fait 40 × 10 : à 125 % on attend au plus 50 × 12,5, jamais 62 × 15.
    assert larg <= 40.0 * 1.25 + 0.01, f"largeur {larg:.1f}"
    assert haut <= 10.0 * 1.25 + 0.01, f"hauteur {haut:.1f}"


# ── Les bornes ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("demande,attendu", [
    (10, 0.5), (50, 0.5), (100, 1.0), (125, 1.25), (400, 1.25),
])
def test_le_facteur_est_borne(demande, attendu):
    """Au delà de 125 % le texte déborderait de l'objet, en dessous de 50 % il
    deviendrait illisible à l'impression."""
    jeton = G.regler_echelle_texte(demande / 100.0)
    try:
        assert G.echelle_texte() == pytest.approx(attendu)
    finally:
        G.restaurer_echelle_texte(jeton)


def test_une_valeur_absurde_ne_fait_pas_tomber():
    jeton = G.regler_echelle_texte("grand")
    try:
        assert G.echelle_texte() == 1.0
    finally:
        G.restaurer_echelle_texte(jeton)


def test_l_echelle_est_rendue_meme_si_la_construction_echoue():
    """Sinon l'objet suivant hériterait du réglage du précédent."""
    C.recharger_objets_module()
    with pytest.raises(Exception):
        C.construire("lettre_3d", {"texte": "", "taille_texte": 50})
    assert G.echelle_texte() == 1.0


# ── Le formulaire ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_le_formulaire_propose_le_reglage(app):
    from PySide6.QtWidgets import QDoubleSpinBox
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    panneau = NeoGenPanel()
    form = panneau._construire_formulaire(C.PAR_ID["badge"])
    pourcents = [w for w in form.findChildren(QDoubleSpinBox)
                 if w.suffix().strip() == "%"]
    assert pourcents, "aucun champ de taille de texte"
    w = pourcents[0]
    assert (w.minimum(), w.maximum(), w.value()) == (50.0, 125.0, 100.0)


def test_un_objet_qui_a_DEJA_son_reglage_n_en_recoit_pas_un_second(app):
    """La pancarte de porte a son propre « taille_texte », en millimètres.
    Deux champs du même nom se seraient écrasés, et la valeur en pourcentage
    serait partie se faire ramener dans une plage en millimètres."""
    from PySide6.QtWidgets import QDoubleSpinBox
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    if "pancarte_porte" not in C.PAR_ID:
        pytest.skip("pancarte absente du catalogue")
    panneau = NeoGenPanel()
    form = panneau._construire_formulaire(C.PAR_ID["pancarte_porte"])
    pourcents = [w for w in form.findChildren(QDoubleSpinBox)
                 if w.suffix().strip() == "%"]
    assert not pourcents, "doublon avec le réglage propre de l'objet"


def test_un_objet_sans_texte_n_a_pas_ce_reglage(app):
    from PySide6.QtWidgets import QDoubleSpinBox
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    sans = next((e for e in C.PAR_ID.values() if e.get("texte") == "aucun"), None)
    if sans is None:
        pytest.skip("aucun objet sans texte")
    panneau = NeoGenPanel()
    form = panneau._construire_formulaire(sans)
    assert not [w for w in form.findChildren(QDoubleSpinBox)
                if w.suffix().strip() == "%"]


# ── Ouvrir un résultat de recherche ───────────────────────────────────────
"""Emmanuel, 2026-09-30 : « je tape médaille, il me trouve badge, et quand je
clique sur badge il m'affiche la carte de visite », puis « une fois que j'ai
fait une recherche plus rien ne s'affiche ».

Pour aller à l'objet demandé, le code passait TOUJOURS par l'objet numéro 1 de
sa catégorie. Or dans « Accessoires & cadeaux », cet objet est la CARTE DE
VISITE, qui a un panneau à elle : elle était donc réveillée au passage, et son
panneau venait ensuite recouvrir le formulaire de l'objet réellement demandé,
qui restait vide.
"""


def test_ouvrir_un_resultat_ne_reveille_pas_la_carte_de_visite(app):
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    p = NeoGenPanel()
    p._ready = True
    appels = []
    p.ouvrir_carte.connect(lambda: appels.append(1))
    p._choisir_resultat("badge")
    app.processEvents()
    assert not appels, "la carte de visite a été ouverte à la place du badge"


def test_ouvrir_un_resultat_remplit_bien_le_formulaire(app):
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    p = NeoGenPanel()
    p._ready = True
    p._choisir_resultat("badge")
    app.processEvents()
    assert p._form_lay.count() > 0, "le formulaire est resté vide"
    assert len(p._champs_courant or {}) > 0


def test_enchainer_plusieurs_recherches_fonctionne(app):
    """Son second symptôme : après une recherche, plus rien ne s'affichait."""
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    p = NeoGenPanel()
    p._ready = True
    for oid in ("badge", "plaque", "magnet", "badge"):
        if oid not in C.PAR_ID:
            continue
        p._choisir_resultat(oid)
        app.processEvents()
        assert p._form_lay.count() > 0, f"formulaire vide après {oid}"
        assert len(p._champs_courant or {}) > 0, f"aucun champ après {oid}"


def test_la_carte_de_visite_reste_accessible_normalement(app):
    """Le correctif ne doit pas l'avoir rendue inatteignable : la choisir
    explicitement doit toujours ouvrir son panneau."""
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    p = NeoGenPanel()
    p._ready = True
    appels = []
    p.ouvrir_carte.connect(lambda: appels.append(1))
    for i, (_dom, entrees) in enumerate(p._donnees):
        for j, e in enumerate(entrees):
            if e["id"] == "carte_visite":
                p._choisir_domaine(i, auto=False)
                p._choisir_objet(j)
                app.processEvents()
                assert appels, "la carte de visite ne s'ouvre plus"
                return
    pytest.skip("carte de visite absente du catalogue")


def test_choisir_une_categorie_a_la_main_selectionne_toujours_le_premier(app):
    """Le comportement normal de la bibliothèque ne doit pas avoir changé."""
    from ui.components.neogen_dialog import NeoGenPanel
    C.recharger_objets_module()
    p = NeoGenPanel()
    p._ready = False
    cible = next((i for i, (_d, es) in enumerate(p._donnees)
                  if es and es[0]["id"] != "carte_visite"), None)
    if cible is None:
        pytest.skip("aucune catégorie sans carte en tête")
    # Comme dans l'application : c'est le MENU qui pilote, `_choisir_objet`
    # relit son index. L'appeler sans le positionner retomberait sur la
    # catégorie 0.
    p._combo_domaine.setCurrentIndex(cible)
    p._choisir_domaine(cible)
    app.processEvents()
    assert p._form_lay.count() > 0
