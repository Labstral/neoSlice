# -*- coding: utf-8 -*-
"""AnycubicSlicerNext doit reconnaître le 3MF de neoSlice comme un PROJET.

Eric Nauche, Anycubic Kobra S1, 2026-10-01 : « le logiciel Anycubic slice Next
n'apprécie pas le fichier 3MF que je lui soumets depuis NeoSlice, et je dois
paramétrer tout à la main ». Sa capture montre le message du slicer : « Le
fichier 3mf n'est pas supporté par AnycubicSlicerNext, chargement des données
de géométrie uniquement ».

Cause : neoSlice signait le fichier « AnycubicSlicerNext-<version> », ce qui
paraît logique mais que le slicer d'Anycubic REFUSE. Son chargeur, hérité de
BambuStudio, ne traite le fichier comme un projet que si la métadonnée
« Application » commence par un préfixe connu, et son propre nom n'en fait pas
partie. Le slicer d'Anycubic signe d'ailleurs ses propres projets
« BambuStudio-1.4.1.2 », avec sa version à lui.

MESURÉ sur AnycubicSlicerNext 1.4.1.2 réellement installé, en ne changeant que
le producteur d'un même 3MF et en relisant les réglages par --export-settings :

    AnycubicSlicerNext-1.4.1.2   refusé      (ce que neoSlice écrivait)
    AnycubicSlicer-1.4.1.2       refusé
    BambuStudio-1.4.1.2          accepté, réglages relus
    OrcaSlicer-02.03.00.58       accepté

⚠ Le binaire du slicer contient bien la chaîne « AnycubicSlicer- » à côté de
« BambuStudio- » et « OrcaSlicer- », ce qui laissait croire qu'elle était
acceptée. La mesure dit le contraire : ne pas se fier à la lecture du binaire.

Les autres sorties ont été vérifiées de la même façon et sont bonnes :
ElegooSlicer accepte « ElegooSlicer- », OrcaSlicer accepte « OrcaSlicer- ».
Snapmaker Orca n'est pas installé ici, donc non vérifié.
"""
import json
import os
import re
import shutil
import subprocess
import zipfile

import pytest
import trimesh

ANYCUBIC_EXE = r"C:\Program Files\AnycubicSlicerNext\AnycubicSlicerNext.exe"

# Préfixes que le chargeur du fork accepte. Le sien n'en fait PAS partie.
PREFIXES_ACCEPTES = ("BambuStudio-", "OrcaSlicer-")


def _construire(tmp_path, slicer: str, printer: str, monkeypatch):
    from core.export.tmf_builder import ThreeMFBuilder, _find_bambu_template
    from core.parameters.print_config import PrintConfig
    if not _find_bambu_template():
        pytest.skip("Bambu Studio non installé (pas de template)")
    import core.prefs as _p
    vrai = _p.PREFS.get
    monkeypatch.setattr(_p.PREFS, "get",
                        lambda k, d=None: slicer if k == "slicer_output" else vrai(k, d))
    out = tmp_path / f"{slicer}.3mf"
    ThreeMFBuilder().build(trimesh.creation.box((20, 20, 10)), PrintConfig(),
                           out, printer_ui_name=printer, filament_ui_name="PLA")
    return out


def _producteur(chemin) -> str:
    mod = zipfile.ZipFile(chemin).read("3D/3dmodel.model").decode("utf-8", "replace")
    m = re.search(r'name="Application">([^<]*)<', mod)
    return m.group(1) if m else ""


# ── La signature écrite ───────────────────────────────────────────────────
def test_la_sortie_anycubic_est_signee_comme_le_slicer_se_signe(tmp_path, monkeypatch):
    prod = _producteur(_construire(tmp_path, "anycubic", "Anycubic Kobra S1", monkeypatch))
    assert prod.startswith(PREFIXES_ACCEPTES), f"producteur refusé : {prod!r}"
    from core.export.tmf_builder import _ANYCUBIC_APP_VERSION
    assert prod.endswith(_ANYCUBIC_APP_VERSION), "la version d'Anycubic doit rester"


def test_le_nom_du_fork_ne_doit_jamais_revenir(tmp_path, monkeypatch):
    """Le piège est de « corriger » vers le nom du logiciel, qui est refusé."""
    prod = _producteur(_construire(tmp_path, "anycubic", "Anycubic Kobra S1", monkeypatch))
    assert not prod.startswith("AnycubicSlicer")


@pytest.mark.parametrize("slicer,printer,prefixe", [
    ("bambu", "X1 Carbon", "BambuStudio-"),
    ("orca", "Anycubic Kobra S1", "OrcaSlicer-"),
    ("elegoo", "Elegoo Centauri Carbon 2", "ElegooSlicer-"),
])
def test_les_autres_sorties_ne_bougent_pas(tmp_path, monkeypatch, slicer,
                                           printer, prefixe):
    """Vérifiées une à une sur les logiciels installés : elles fonctionnent,
    on n'y touche pas."""
    assert _producteur(_construire(tmp_path, slicer, printer, monkeypatch)).startswith(prefixe)


# ── La preuve, sur le vrai logiciel ───────────────────────────────────────
@pytest.mark.skipif(not os.path.exists(ANYCUBIC_EXE),
                    reason="AnycubicSlicerNext non installé")
def test_le_vrai_anycubicslicernext_relit_les_reglages(tmp_path, monkeypatch):
    """Le seul test qui prouve vraiment quelque chose : on demande au slicer
    d'Anycubic de REXPORTER les réglages qu'il a lus. S'il avait refusé le
    fichier, il n'écrirait rien du tout."""
    projet = _construire(tmp_path, "anycubic", "Anycubic Kobra S1", monkeypatch)
    reglages = tmp_path / "relus.json"
    try:
        subprocess.run([ANYCUBIC_EXE, "--export-settings", str(reglages), str(projet)],
                       capture_output=True, timeout=180,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        pytest.skip("AnycubicSlicerNext n'a pas répondu à temps")
    assert reglages.exists(), "le 3mf a été refusé : géométrie seule"
    lus = json.loads(reglages.read_text(encoding="utf-8"))
    assert lus.get("printer_model") == "Anycubic Kobra S1"
    assert lus.get("layer_height") == "0.2"
    assert "neoSlice" in str(lus.get("print_settings_id", ""))
