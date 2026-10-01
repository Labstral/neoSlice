# -*- coding: utf-8 -*-
"""Chaque imprimante a SON plateau, pas celui d'une Bambu Lab.

eleovna BERGES, formulaire du site, 2026-10-01 : « la Elegoo Neptune 4 Max a un
plateau plus grand que la moyenne. Il serait judicieux que le logiciel en
tienne compte dans la répartition des éléments par plateau sur un projet
volumineux. »

Elle avait raison, et c'était bien pire que son cas : `volume_impression` ne
regardait QUE le dictionnaire PRINTERS, c'est à dire les 13 Bambu Lab écrites à
la main. Les 396 modèles du catalogue, les 578 machines Cura, les 27 FlashPrint
et les 255 PrusaSlicer retombaient toutes sur le repli de 256×256×256. Sa
Neptune 4 Max (420×420×480) était donc traitée comme une machine deux fois plus
petite.

Trois choses visibles en dépendent, toutes faussées de la même manière :
la série ×N (trop de plateaux), le garde-fou neoGen (refuse des pièces qui
tiennent) et le plateau annoncé à neoForge.

⚠ Pièges rencontrés en écrivant le lecteur de dimensions, tous testés ici :
  * la virgule de PrusaSlicer sépare les COINS, ce n'est pas une décimale
    (« 2.5x5,302.5x5,… » lu en décimales donnait un plateau de 5 mm) ;
  * certains plateaux delta portent « 2.54949e-15 » en guise de zéro, et
    couper l'exposant en deux décalait tous les coins suivants ;
  * 18 plateaux sont centrés sur l'origine, où la coordonnée maximale ne vaut
    que la MOITIÉ du plateau : il faut l'encombrement, pas le maximum.
"""
import pytest

from data.printers import (PRINTERS, VOLUME_REPLI, volume_impression,
                           _by_model, _cura_by_model, _flashprint_by_model,
                           _prusa_by_model)


# ── Le cas d'eleovna ──────────────────────────────────────────────────────
def test_la_neptune_4_max_a_bien_son_plateau_de_420():
    assert volume_impression("Elegoo Neptune 4 Max") == (420.0, 420.0, 480.0)


def test_la_serie_remplit_le_grand_plateau_au_lieu_d_empiler_les_plateaux():
    """Son cas concret : 24 pièces de 60 mm. Avant, neoSlice en faisait trois
    plateaux parce qu'il la croyait en 256 mm."""
    from core.geometry.serie import plan_grille
    bx, by, _ = volume_impression("Elegoo Neptune 4 Max")
    reel = plan_grille(60.0, 60.0, 24, bx, by)
    avant = plan_grille(60.0, 60.0, 24, 256.0, 256.0)
    assert reel["plateaux"] == 1
    assert avant["plateaux"] == 3
    assert reel["par_plateau"] > avant["par_plateau"]


def test_une_piece_de_400mm_passe_le_garde_fou_neogen_sur_cette_machine():
    """Le garde-fou prenait le plateau de l'imprimante cible : à 256 mm il
    refusait une pièce de 400 mm qui tient pourtant largement chez elle."""
    import numpy as np
    import trimesh
    from core.neogen.catalogue import piece_hors_plateau
    piece = trimesh.creation.box(extents=(400.0, 400.0, 100.0))
    piece.apply_translation(-piece.bounds[0] * np.array([0, 0, 1]))
    assert piece_hors_plateau(piece, volume_impression("Elegoo Neptune 4 Max")) is None
    assert piece_hors_plateau(piece, (256.0, 256.0, 256.0))


# ── Aucune régression sur les Bambu Lab ───────────────────────────────────
@pytest.mark.parametrize("modele,attendu", [
    ("X1 Carbon", (256.0, 256.0, 256.0)),
    ("A1 Mini", (180.0, 180.0, 180.0)),
    ("P1S", (256.0, 256.0, 256.0)),
])
def test_les_bambu_ne_bougent_pas(modele, attendu):
    assert volume_impression(modele) == attendu


def test_la_h2d_etait_cassee_elle_aussi():
    """Son champ volume dit « 350×320×325 mm (simple) / 300×320×325 mm
    (double) ». L'ancien découpage sur « × » donnait cinq morceaux au lieu de
    trois, donc le repli de 256 : la plus grande Bambu passait pour la plus
    petite. On garde la buse SIMPLE, le cas courant."""
    assert volume_impression("H2D") == (350.0, 320.0, 325.0)


@pytest.mark.parametrize("entree", ["", "Imprimante inconnue", None])
def test_un_modele_inconnu_retombe_sur_un_plateau_prudent(entree):
    """Mieux vaut sous-estimer le plateau que proposer une pièce qui ne rentre
    pas dans la machine de l'utilisateur."""
    assert volume_impression(entree) == VOLUME_REPLI


# ── Les pièges du lecteur de dimensions ───────────────────────────────────
def test_la_virgule_de_prusaslicer_separe_les_coins():
    """« 2.5x5,302.5x5,302.5x225,2.5x225 » = une CR-10 Mini, 300×220 utiles.
    Lue avec la virgule comme décimale, elle donnait un plateau de 5 mm."""
    x, y, _ = volume_impression("CR10MINI")
    assert (round(x), round(y)) == (300, 220)


def test_un_plateau_delta_en_notation_scientifique_reste_lisible():
    """Ces plateaux ronds portent un « 2.54949e-15 » en guise de zéro."""
    x, y, z = volume_impression("DQM")
    assert 100 < x < 400 and 100 < y < 400 and z > 0


def test_un_plateau_centre_sur_l_origine_donne_son_encombrement():
    """Sur ces plateaux la coordonnée maximale ne vaut que la moitié du
    plateau : il faut max moins min."""
    centres = [mk for mk, v in _prusa_by_model().items()
               if "-" in str(v.get("bed_shape", "")).replace("e-", "")]
    assert centres, "plus aucun plateau centré dans le catalogue"
    for mk in centres:
        x, y, _ = volume_impression(mk)
        assert x > 0 and y > 0


# ── Couverture : la correction doit profiter à TOUT le monde ──────────────
def test_presque_toutes_les_machines_connaissent_leur_plateau():
    """Avant la correction : 13 machines sur 1269. Le repli reste légitime
    pour les quelques modèles dont le catalogue ne donne aucune dimension."""
    toutes = (list(PRINTERS) + list(_by_model()) + list(_cura_by_model())
              + list(_flashprint_by_model()) + list(_prusa_by_model()))
    connues = sum(1 for k in toutes if volume_impression(k) != VOLUME_REPLI)
    assert connues > 1150, f"seulement {connues}/{len(toutes)} machines"


def test_aucune_dimension_absurde():
    """Un plateau mal lu se voit tout de suite : il devient minuscule ou
    kilométrique. Les trois machines géantes connues sont nommées."""
    geantes = {"SeeMeCNC BOSSdelta 500 0521", "modix_v3_big180X", "modix_v4_big180X"}
    toutes = (list(PRINTERS) + list(_by_model()) + list(_cura_by_model())
              + list(_flashprint_by_model()) + list(_prusa_by_model()))
    for k in toutes:
        if k in geantes:
            continue
        x, y, z = volume_impression(k)
        assert 40 <= x <= 1200 and 40 <= y <= 1200 and 40 <= z <= 1200, \
            f"{k} : plateau {x}×{y}×{z} invraisemblable"
