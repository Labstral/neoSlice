# -*- coding: utf-8 -*-
"""Ce que les BUILDS doivent garantir pour neoForge.

1. QtNetwork est embarqué : sans lui, le pont neoSlice ↔ neoForge ne peut pas
   exister. Le piège est invisible en développement (tout marche depuis les
   sources) et ne casserait que l'application distribuée.
2. Le logiciel neoForge lui-même n'entre PAS dans l'exécutable : promesse faite
   à l'utilisateur, neoSlice ne grossit pas tant que le module n'est pas
   installé. Il est téléchargé puis chargé depuis ~/.neoslice/neoforge.
"""
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
SPECS = [RACINE / "neoslice.spec", RACINE / "neoslice_mac.spec"]


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.name)
def test_qtnetwork_embarque(spec: Path):
    texte = spec.read_text(encoding="utf-8")
    assert "'PySide6.QtNetwork'," in texte, "QtNetwork doit être en hiddenimports"
    # …et il ne doit être dans AUCUNE liste de modules retirés du paquet.
    for ligne in texte.splitlines():
        nu = ligne.strip()
        if nu.startswith("#"):
            continue
        assert "'QtNetwork'" not in nu, f"QtNetwork retiré du build : {nu}"


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.name)
def test_qtnetwork_pas_dans_les_exclusions(spec: Path):
    texte = spec.read_text(encoding="utf-8")
    debut = texte.find("excludes=[")
    fin = texte.find("]", debut)
    assert debut > 0 and "QtNetwork" not in texte[debut:fin]


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.name)
def test_le_logiciel_neoforge_n_est_pas_embarque(spec: Path):
    """Aucune référence au paquet téléchargeable (« neoforge.xxx » ou le dossier
    neoforge/) : seules les briques core.neoforge de neoSlice sont dans l'exe."""
    for ligne in spec.read_text(encoding="utf-8").splitlines():
        nu = ligne.strip()
        if nu.startswith("#"):
            continue
        assert "'neoforge" not in nu and '"neoforge' not in nu, nu
        assert "neoforge/" not in nu.replace("core/neoforge/", ""), nu


def test_le_lanceur_charge_le_paquet_sans_import_statique():
    """Le lanceur doit importer neoforge de façon que PyInstaller ne l'embarque
    pas dans l'exe : l'import vit DANS la fonction, après ajout du chemin."""
    source = (RACINE / "core" / "neoforge" / "lanceur.py").read_text(encoding="utf-8")
    lignes_module = [l for l in source.splitlines()
                     if l.startswith("import ") or l.startswith("from ")]
    assert not any("neoforge." in l and "core.neoforge" not in l for l in lignes_module)
    assert "import neoforge" in source          # bien importé, mais dans la fonction
