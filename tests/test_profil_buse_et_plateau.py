# -*- coding: utf-8 -*-
"""Identité imprimante + plateau dans le 3MF exporté.

Retours d'une utilisatrice Snapmaker U1 (buse 0,4 / PLA / Smooth PEI Plate) :
  1. le slicer affichait « Snapmaker U1 (0.4+0.6 nozzle) » alors qu'elle avait
     choisi une seule buse de 0,4 ;
  2. Snapmaker Orca remplaçait silencieusement « Smooth PEI Plate » par
     « Engineering Plate » (nom de plateau trop récent pour ce fork) ;
  3. un avertissement « precise wall ignorée » s'affichait à chaque ouverture.
"""
import pytest

from data.printers import profile_name_for, _by_model, _catalogue
from core.export.tmf_builder import (
    _bed_type_sortie, _BED_TYPE_CODE, _config_to_bambu_overrides)
from core.parameters.print_config import PrintConfig


# ── 1. Variante de buse ──────────────────────────────────────────────────────
def test_u1_buse_04_choisit_le_profil_simple():
    assert profile_name_for("Snapmaker U1", 0.4) == "Snapmaker U1 (0.4 nozzle)"


def test_u1_autres_buses_inchangees():
    for d, attendu in ((0.2, "Snapmaker U1 (0.2 nozzle)"),
                       (0.6, "Snapmaker U1 (0.6 nozzle)"),
                       (0.8, "Snapmaker U1 (0.8 nozzle)")):
        assert profile_name_for("Snapmaker U1", d) == attendu


def test_aucune_variante_multibuses_ne_masque_une_simple():
    """Générique : pour TOUT modèle du catalogue, si une variante simple existe
    pour une buse, c'est elle qui doit être retenue — pas une variante composite
    (« 0.4+0.6 ») qui décrirait une machine à deux têtes."""
    simples = {}
    for nom, e in _catalogue().items():
        variante = str(e.get("printer_variant", "") or "")
        if "+" in variante:
            continue
        cle = (e.get("printer_model") or nom, str(e.get("nozzle_diameter", "0.4")))
        simples.setdefault(cle, nom)

    for modele, infos in _by_model().items():
        for nz, choisi in infos["nozzles"].items():
            if (modele, nz) in simples:
                variante = _catalogue().get(choisi, {}).get("printer_variant", "")
                assert "+" not in str(variante), (
                    f"{modele} buse {nz} → « {choisi} » (multi-buses) alors "
                    f"qu'une variante simple existe")


# ── 2. Nom de plateau écrit dans le 3MF ──────────────────────────────────────
def test_smooth_pei_ecrit_sous_son_nom_compatible():
    """« Smooth PEI Plate » est le libellé récent d'Orca ; on écrit le nom
    historique, compris de Bambu Studio comme des forks plus anciens."""
    assert _bed_type_sortie("Smooth PEI Plate") == "High Temp Plate"


def test_autres_plateaux_inchanges():
    for p in ("Textured PEI Plate", "Cool Plate", "Engineering Plate",
              "Textured Cool Plate"):
        assert _bed_type_sortie(p) == p


def test_code_interne_du_plateau_reste_coherent():
    """Le code du bloc <plate> (celui que le slicer lit vraiment) doit toujours
    désigner la plaque haute température."""
    assert _BED_TYPE_CODE["Smooth PEI Plate"] == "hot_plate"


# ── 3. Avertissement « precise wall » ────────────────────────────────────────
@pytest.mark.parametrize("sequence,attendu", [
    ("outer wall/inner wall", "0"),      # paroi extérieure d'abord → option ignorée
    ("inner wall/outer wall", None),     # cas standard → on ne touche à rien
])
def test_precise_wall_desactivee_quand_le_slicer_l_ignore(sequence, attendu):
    cfg = PrintConfig()
    cfg.wall_sequence = sequence
    ov = _config_to_bambu_overrides(cfg)
    assert ov.get("precise_outer_wall") == attendu
