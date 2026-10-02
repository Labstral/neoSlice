# -*- coding: utf-8 -*-
"""Le journal de développement ne doit JAMAIS partir dans le build.

Constaté le 2026-10-02 en diagnostiquant le lancement chez Bertrand Envois :
`data/neoslice.log` était embarqué dans la 2.4.0. 4,3 Mo, 30 314 lignes du
17 mai au 1er octobre, le nom de session Windows du développeur répété 2211
fois et 1195 chemins de fichiers 3D testés.

Rien de confidentiel au sens strict, aucune adresse, aucune clé, aucun jeton,
mais c'est de l'activité personnelle livrée à chaque utilisateur pour rien.

⚠ L'effet le plus gênant est ailleurs : loguru ouvre le fichier en AJOUT. Le
journal de l'utilisateur venait donc se coller après 30 000 lignes qui ne le
concernaient pas, ce qui rendait tout diagnostic illisible, exactement quand
on en a le plus besoin.

Les specs embarquent tout `data/` sauf `kb`. Toute exclusion doit donc être
posée explicitement, et ce test vérifie qu'elle y reste.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
SPECS = ("neoslice.spec", "neoslice_mac.spec")


@pytest.mark.parametrize("nom", SPECS)
def test_la_spec_exclut_le_journal(nom):
    src = (RACINE / nom).read_text(encoding="utf-8")
    assert "neoslice.log" in src, f"{nom} : le journal n'est plus exclu"
    assert re.search(r"startswith\(['\"]neoslice\.log\.", src), \
        f"{nom} : les fichiers tournés (neoslice.log.1…) ne sont pas exclus"


@pytest.mark.parametrize("nom", SPECS)
def test_la_spec_exclut_toujours_la_base_de_connaissance(nom):
    """data/kb pèse environ 5 Go : son exclusion ne doit pas sauter non plus."""
    assert "'kb'" in (RACINE / nom).read_text(encoding="utf-8")


def test_le_journal_ne_part_pas_dans_le_build_courant():
    """Le contrôle qui compte vraiment : la spec peut être juste et le build
    quand même contaminé.

    On ignore un build ANTÉRIEUR au correctif de la spec : il est forcément
    contaminé, c'est connu, et le faire échouer indéfiniment ne dit rien de
    neuf. Un build postérieur, lui, n'a aucune excuse."""
    livre = RACINE / "dist" / "neoSlice" / "_internal" / "data" / "neoslice.log"
    if not livre.exists():
        return                                   # rien à redire
    spec = RACINE / "neoslice.spec"
    if livre.stat().st_mtime < spec.stat().st_mtime:
        pytest.skip("build antérieur au correctif de la spec")
    pytest.fail("le journal de développement est présent dans ce build, "
                "reconstruire avant de publier")
