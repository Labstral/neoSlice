# -*- coding: utf-8 -*-
"""Carte de visite — style gravé/lisse pour TOUS les éléments + export mono-couleur.

Retour utilisateur (Pierre M., 2026-08) : impossible de créer une carte
mono-couleur « tout en creux » — logo, trait et cadre étaient verrouillés en
relief (pas de bouton de choix) et l'export partait toujours en multicouleur.
"""
import dataclasses

import pytest

from core.neogen.carte_visite import (
    CarteSpec, ElementTexte, ElementLogo, ElementTrait, ElementCadre,
    construire, construire_apercu, generer_fichier_carte,
)


def _vol_socle_plein(spec: CarteSpec) -> float:
    """Volume du même socle SANS éléments (référence « rien n'a été creusé »)."""
    scene, _ = construire(CarteSpec(largeur=spec.largeur, hauteur=spec.hauteur,
                                    ep=spec.ep, rayon=spec.rayon,
                                    couleur_base=spec.couleur_base))
    return float(next(iter(scene.geometry.values())).volume)


def test_mode_present_sur_tous_les_elements():
    """Les 4 types portent `mode`, défaut « relief » = rétrocompatibilité des
    modèles enregistrés avant l'ajout du champ (asdict/charger roundtrip)."""
    for cls in (ElementTexte, ElementLogo, ElementTrait, ElementCadre):
        el = cls()
        assert el.mode == "relief", cls.__name__
        assert "mode" in dataclasses.asdict(el), cls.__name__


def test_trait_et_cadre_graves_creusent_le_socle():
    """Gravé sur trait/cadre : le socle est réellement creusé (il ne l'était
    jamais avant — ces éléments ignoraient le mode)."""
    spec = CarteSpec(couleur_base="#FFFFFF", elements=[
        ElementTrait(longueur=40, epaisseur=2.0, relief=0.8,
                     mode="grave", couleur="#111111"),
        ElementCadre(largeur=60, hauteur=35, epaisseur=2.0, relief=0.8,
                     mode="grave", couleur="#111111", align_v="milieu"),
    ])
    scene, couleurs = construire(spec)
    socle = scene.geometry["socle"]
    assert socle.is_watertight
    assert float(socle.volume) < _vol_socle_plein(spec) - 1.0     # mm³
    assert len(couleurs) == 2          # fond de creux noir : gravé bicolore assumé


def test_carte_ton_sur_ton_reste_mono_couleur():
    """LE cas de Pierre : tout gravé à la couleur du socle (casse hex différente,
    comme la renvoie le sélecteur Qt) → UNE couleur effective, socle seul, creux
    OUVERTS (aucun fond coloré qui viendrait les reboucher à ras)."""
    spec = CarteSpec(couleur_base="#F2EEE6", elements=[
        ElementTexte("Léa", hauteur=8, mode="grave", couleur="#f2eee6"),
        ElementTrait(longueur=40, epaisseur=2.0, mode="grave",
                     couleur="#f2eee6", align_v="bas"),
    ])
    scene, couleurs = construire(spec)
    assert couleurs == ["#F2EEE6"]
    assert list(scene.geometry) == ["socle"]        # aucun corps couleur séparé
    socle = scene.geometry["socle"]
    assert socle.is_watertight
    assert float(socle.volume) < _vol_socle_plein(spec) - 1.0     # creux présents
    # l'aperçu éditeur montre EXACTEMENT le même rendu (pas de corps fantôme)
    apercu = construire_apercu(spec)
    assert list(apercu.geometry) == ["socle"]


def test_relief_ton_sur_ton_garde_son_corps():
    """Un RELIEF de la couleur du socle reste une bosse visible : seul le fond
    de gravure ton sur ton est supprimé, pas les reliefs."""
    spec = CarteSpec(couleur_base="#FFFFFF", elements=[
        ElementTrait(longueur=40, epaisseur=2.0, mode="relief",
                     couleur="#ffffff"),
    ])
    scene, couleurs = construire(spec)
    assert couleurs == ["#FFFFFF"]                  # mono-couleur…
    assert len(scene.geometry) == 2                 # …mais la bosse existe


def test_generer_fichier_carte_renvoie_les_couleurs_effectives(tmp_path, monkeypatch):
    """(path, couleurs) : c'est sur CE retour que l'app route mono vs multi."""
    import core.neogen.pilote as pilote
    monkeypatch.setattr(pilote, "DOSSIER_SORTIES", tmp_path)

    mono = CarteSpec(couleur_base="#FFFFFF", elements=[
        ElementTrait(longueur=30, epaisseur=1.5, mode="grave",
                     couleur="#ffffff")])
    path, couleurs = generer_fichier_carte(mono)
    assert path.exists()
    assert len(couleurs) == 1                       # → pièce simple, un filament

    duo = CarteSpec(couleur_base="#FFFFFF", elements=[
        ElementTrait(longueur=30, epaisseur=1.5, couleur="#111111")])
    path2, couleurs2 = generer_fichier_carte(duo)
    assert path2.exists()
    assert len(couleurs2) == 2                      # → route multicouleur


def test_trait_coins_arrondis_capsule():
    """Trait arrondi = capsule aux bouts en demi-cercle, longueur HORS TOUT
    conservée ; le brut reste le rectangle exact d'avant (rétrocompat)."""
    from core.neogen.carte_visite import _forme_element
    spec = CarteSpec()
    brut = _forme_element(ElementTrait(longueur=40, epaisseur=2.0), spec)
    rond = _forme_element(ElementTrait(longueur=40, epaisseur=2.0,
                                       coins="arrondi"), spec)
    assert brut.area == pytest.approx(40 * 2.0)             # rectangle exact
    assert rond.area < brut.area                            # bouts adoucis
    minx, miny, maxx, maxy = rond.bounds
    assert (maxx - minx) == pytest.approx(40, abs=0.05)     # hors tout inchangé
    assert (maxy - miny) == pytest.approx(2.0, abs=0.05)
    # vertical : mêmes dimensions transposées
    rond_v = _forme_element(ElementTrait(longueur=40, epaisseur=2.0,
                                         orientation="vertical",
                                         coins="arrondi"), spec)
    minx, miny, maxx, maxy = rond_v.bounds
    assert (maxy - miny) == pytest.approx(40, abs=0.05)
    assert (maxx - minx) == pytest.approx(2.0, abs=0.05)


def test_cadre_coins_arrondis():
    from core.neogen.carte_visite import _forme_element
    spec = CarteSpec()
    brut = _forme_element(ElementCadre(largeur=60, hauteur=35, epaisseur=2.0), spec)
    rond = _forme_element(ElementCadre(largeur=60, hauteur=35, epaisseur=2.0,
                                       coins="arrondi"), spec)
    assert rond.area < brut.area                            # coins adoucis
    minx, miny, maxx, maxy = rond.bounds
    assert (maxx - minx) == pytest.approx(60, abs=0.05)     # encombrement conservé
    assert (maxy - miny) == pytest.approx(35, abs=0.05)
    # et la carte se construit toujours étanche avec un cadre arrondi gravé
    scene, _ = construire(CarteSpec(elements=[
        ElementCadre(largeur=60, hauteur=35, epaisseur=2.0, coins="arrondi",
                     mode="grave", couleur="#111111")]))
    assert all(g.is_watertight for g in scene.geometry.values())


def test_carte_coins_carres():
    """Socle : « arrondi » reste le défaut (identique à avant), « brut » donne
    la plaque rectangulaire exacte."""
    arrondi, _ = construire(CarteSpec())                      # défaut historique
    carre, _ = construire(CarteSpec(coins="brut"))
    va = float(next(iter(arrondi.geometry.values())).volume)
    vc = float(next(iter(carre.geometry.values())).volume)
    assert vc == pytest.approx(85 * 55 * 1.6, rel=1e-3)      # rectangle plein
    assert va < vc                                            # coins retirés


def test_ui_coins_pour_trait_cadre_et_carte():
    """Combo « Coins » sur trait, cadre ET la carte ; défauts = comportement
    d'avant (trait/cadre carrés, carte arrondie) ; roundtrip sauvegarde."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ui.components.carte_visite_panel import _ElementEditor, CartePanel
    from ui.styles.theme import MANAGER

    pal = MANAGER.palette()
    for t in ("trait", "cadre"):
        ed = _ElementEditor(t, pal)
        assert ed.element().coins == "brut", f"{t} : défaut changé"
        ed._selc(ed.cb_coins, "arrondi")
        el = ed.element()
        assert el.coins == "arrondi", t
        ed2 = _ElementEditor(t, pal)
        ed2.charger(dataclasses.asdict(el))
        assert ed2.element().coins == "arrondi", f"{t} : coins perdus au rechargement"
    # texte et logo : PAS de combo coins (n'aurait aucun sens)
    for t in ("texte", "logo"):
        assert not hasattr(_ElementEditor(t, pal), "cb_coins"), t

    panel = CartePanel()
    assert panel._spec().coins == "arrondi"                  # défaut historique
    d = panel.to_dict()
    d["coins"] = "brut"
    panel.from_dict(d)
    assert panel._spec().coins == "brut"
    panel.from_dict({})                                       # ancien modèle sans clé
    assert panel._spec().coins == "arrondi"


def test_element_qr_footprint_et_integration():
    """QR sur la carte : même moteur local (segno) que l'objet neoGen. Modules
    étanches, taille hors tout respectée, agrandissement auto si lien trop long
    (module >= 1,1 mm), et gravure ton sur ton = mono-couleur comme le reste."""
    from core.neogen.carte_visite import ElementQR, _forme_element
    spec = CarteSpec()
    assert _forme_element(ElementQR(lien=""), spec) is None       # lien requis
    from core.neogen.qrcode_3d import _matrice
    lien = "https://neoslice-ai.com"
    n = int(_matrice(lien).shape[0])
    attendu = max(18.0, n * 0.8)          # garde scan : module >= 0,8 mm
    mp = _forme_element(ElementQR(lien=lien, taille=18.0), spec)
    assert mp is not None and len(mp.geoms) >= 1
    minx, miny, maxx, maxy = mp.bounds
    assert (maxx - minx) == pytest.approx(attendu, abs=0.2)
    assert abs((maxx - minx) - (maxy - miny)) < 0.5    # carré
    # lien très long → QR dense → le carré S'AGRANDIT au lieu de devenir illisible
    long_lien = "https://neoslice-ai.com/" + "x" * 180
    n2 = int(_matrice(long_lien).shape[0])
    mp2 = _forme_element(ElementQR(lien=long_lien, taille=12.0), spec)
    b = mp2.bounds
    assert (b[2] - b[0]) == pytest.approx(max(12.0, n2 * 0.8), abs=0.2)
    assert (b[2] - b[0]) > 12.0
    # intégration complète : QR gravé ton sur ton → mono-couleur, socle creusé
    tst = CarteSpec(couleur_base="#FFFFFF", elements=[
        ElementQR(lien="https://neoslice-ai.com", taille=16.0,
                  mode="grave", couleur="#ffffff")])
    scene, couleurs = construire(tst)
    assert couleurs == ["#FFFFFF"]
    assert list(scene.geometry) == ["socle"]
    socle = scene.geometry["socle"]
    assert socle.is_watertight
    assert float(socle.volume) < _vol_socle_plein(tst) - 1.0
    # et en relief bicolore : corps modules présent, étanche
    tst2 = CarteSpec(elements=[ElementQR(lien="https://neoslice-ai.com",
                                         taille=16.0, couleur="#111111")])
    scene2, couleurs2 = construire(tst2)
    assert len(couleurs2) == 2
    assert all(g.is_watertight for g in scene2.geometry.values())


def test_ui_element_qr_et_menu_ajouter():
    """L'éditeur QR (lien + taille) fonctionne comme les autres, et le panneau
    expose le bouton unique « Ajouter » (menu) à la place des 4 boutons."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ui.components.carte_visite_panel import _ElementEditor, CartePanel
    from ui.styles.theme import MANAGER

    pal = MANAGER.palette()
    ed = _ElementEditor("qr", pal)
    assert hasattr(ed, "cb_mode")                       # style commun présent
    ed.le.setText("https://neoslice-ai.com")
    ed.sp_h.setValue(20.0)
    el = ed.element()
    assert el.type == "qr" and el.lien == "https://neoslice-ai.com"
    assert el.taille == 20.0
    ed2 = _ElementEditor("qr", pal)
    ed2.charger(dataclasses.asdict(el))
    assert ed2.element().lien == el.lien and ed2.element().taille == 20.0

    panel = CartePanel()
    assert hasattr(panel, "_btn_ajouter")               # bouton menu unique
    assert len(panel._btns_ajout) == 1                  # plus de rangée de 4
    ed_qr = panel._ajouter("qr")                        # le type qr s'ajoute
    assert ed_qr.type_el == "qr"
    # roundtrip modèle complet avec un QR dedans
    ed_qr.le.setText("https://neoslice-ai.com")
    d = panel.to_dict()
    panel.from_dict(d)
    assert any(e.get("type") == "qr" and e.get("lien") == "https://neoslice-ai.com"
               for e in panel.to_dict()["elements"])


def test_ui_style_disponible_pour_les_quatre_types():
    """Le combo Style existe sur les 5 types d'éléments, et le mode survit
    au roundtrip élément → dict (modèle enregistré) → rechargement."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ui.components.carte_visite_panel import _ElementEditor
    from ui.styles.theme import MANAGER

    pal = MANAGER.palette()
    for t in ("texte", "logo", "trait", "cadre", "qr"):
        ed = _ElementEditor(t, pal)
        assert hasattr(ed, "cb_mode"), f"{t} : pas de combo Style"
        ed._selc(ed.cb_mode, "grave")
        el = ed.element()
        assert el.mode == "grave", t
        ed2 = _ElementEditor(t, pal)
        ed2.charger(dataclasses.asdict(el))
        assert ed2.element().mode == "grave", f"{t} : mode perdu au rechargement"
