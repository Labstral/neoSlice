# -*- coding: utf-8 -*-
"""L'archive macOS doit garder les liens symboliques du bundle.

Yannick Lebeau Fraisse, MacBook Air M4, 2026-09-30 : « cela fait 10 jours que
je télécharge votre logiciel, à la fin il indique échec décompression […] le
format n'est pas pris en charge […] je n'ai pas d'autre choix que de vous
déranger ». Débutant complet, dix jours de tentatives.

Le fichier publié était pourtant intact, vérifié octet par octet sur GitHub.
Le problème était sa TAILLE. Un bundle .app de PyInstaller repose sur des
liens symboliques : `Contents/Resources` pointe sur `Contents/Frameworks`.
Le pipeline l'archivait avec `zip -r`, qui SUIT les liens et recopie leur
cible. Mesuré sur l'archive 2.3.1 :

    78 % du contenu dupliqué (5,07 Go de doublons sur 6,46 Go)
    1,91 Go à télécharger, 6,46 Go une fois décompressé
    soit 8,4 Go de place libre nécessaire pour installer

Avec les liens préservés : 0,41 Go à télécharger, 1,39 Go sur le disque.

`ditto -c -k` est l'outil d'Apple pour archiver un bundle. Il garde les liens,
les permissions et les attributs étendus.

⚠ Si l'archivage reperd les liens un jour, RIEN ne casse visiblement :
l'application s'installe et fonctionne, l'archive triple simplement de taille.
D'où le garde-fou dans le pipeline, et ce test qui vérifie qu'il y est.
"""
import re
import stat
import zipfile
from pathlib import Path

import pytest
import yaml

RACINE = Path(__file__).resolve().parent.parent
CODEMAGIC = RACINE / "codemagic.yaml"


@pytest.fixture(scope="module")
def etapes():
    d = yaml.safe_load(CODEMAGIC.read_text(encoding="utf-8"))
    wf = d["workflows"]["neoslice-macos"]
    return {e["name"]: e["script"] for e in wf["scripts"]}


# ── Le pipeline ───────────────────────────────────────────────────────────
def test_l_archive_est_faite_avec_ditto(etapes):
    script = etapes["Create ZIP (auto-update)"]
    assert "ditto -c -k" in script
    assert "--keepParent" in script, "sans --keepParent l'app perd son dossier racine"


def test_zip_r_sans_y_ne_doit_jamais_revenir(etapes):
    """C'est l'erreur exacte à ne pas refaire. `zip -r` seul déroule les liens ;
    il faudrait `zip -r -y`, mais ditto est l'outil prévu pour ça."""
    for nom, script in etapes.items():
        for ligne in script.splitlines():
            nu = ligne.strip()
            if nu.startswith("#") or "zip " not in nu:
                continue
            if re.search(r"\bzip\s+(-\w+\s+)*-?r", nu) and " -y" not in nu:
                pytest.fail(f"étape « {nom} » : archivage qui déroule les liens\n  {nu}")


def test_le_garde_fou_refuse_une_archive_gonflee(etapes):
    """Sans ce garde-fou, une régression passerait inaperçue : l'application
    fonctionnerait, l'archive serait juste quatre fois trop grosse."""
    script = etapes["Verify ZIP keeps symlinks"]
    assert "exit 1" in script, "le garde-fou doit faire ÉCHOUER la construction"
    assert "zipinfo" in script, "il faut compter les liens de l'archive produite"
    seuils = [int(n) for n in re.findall(r"\b(\d{6,})\b", script)]
    assert seuils and max(seuils) < 1_500_000_000, \
        "le seuil de taille doit rester bien en dessous de l'ancienne archive"


def test_le_dmg_est_toujours_construit(etapes):
    """Le .dmg se monte sans rien décompresser : c'est le chemin le plus simple
    pour un débutant, et il ne doit pas disparaître du pipeline."""
    assert "hdiutil create" in etapes["Create DMG (drag-to-Applications)"]


# ── L'archive réelle, quand elle est là ───────────────────────────────────
def _archives_locales():
    d = RACINE / "dist" / "installer"
    return sorted(d.glob("neoSlice*macOS*.zip")) if d.is_dir() else []


@pytest.mark.skipif(not _archives_locales(), reason="aucune archive macOS locale")
@pytest.mark.skipif("not config.getoption('--verif-archive-mac', default=False)",
                    reason="contrôle de publication : --verif-archive-mac")
@pytest.mark.parametrize("archive", _archives_locales(), ids=lambda p: p.name)
def test_l_archive_livree_garde_ses_liens(archive):
    """À lancer avant de publier, avec --verif-archive-mac. Hors release il
    reste au repos : une archive construite par l'ancien pipeline traîne
    longtemps dans dist/ et ferait échouer la suite sans rien apprendre."""
    infos = zipfile.ZipFile(archive).infolist()
    liens = [i for i in infos if stat.S_ISLNK(i.external_attr >> 16)]
    assert len(liens) >= 50, f"{archive.name} : {len(liens)} liens, bundle déroulé"
    brut = sum(i.file_size for i in infos)
    assert brut < 3 * 1024 ** 3, f"{archive.name} : {brut/1e9:.2f} Go décompressés"
