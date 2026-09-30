# -*- coding: utf-8 -*-
"""neoForge embarque des bibliothèques libres : elles doivent être créditées.

Le noyau de neoForge est Open CASCADE Technology, sous LGPL 2.1 avec exception,
utilisé via les liaisons OCP sous Apache 2.0. Ces licences imposent que leur
texte accompagne le programme.

Ce qui manquait, et qui a justifié ces tests : la roue `cadquery-ocp-novtk` ne
contient AUCUN fichier de licence (son `.dist-info` n'a que RECORD, WHEEL,
METADATA et top_level.txt), et le script de paquetage écarte de toute façon
`.dist-info`. Le noyau installé sur la machine d'Emmanuel ne contenait donc
strictement rien. Le texte doit venir de nous, à deux endroits : dans la
fenêtre « Licences et mentions » et dans un fichier livré avec le module.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
LANGUES = ("fr", "en", "es", "de", "it")


# ── Le fichier livré avec le module ────────────────────────────────────────
def test_le_module_embarque_un_fichier_de_licences():
    f = RACINE / "neoforge" / "LICENCES.txt"
    assert f.exists(), "neoForge doit être livré avec ses licences"
    t = f.read_text(encoding="utf-8")
    for attendu in ("Open CASCADE", "LGPL", "Apache 2.0", "OPEN CASCADE SAS",
                    "cadquery-ocp-novtk"):
        assert attendu in t, attendu


def test_le_fichier_part_bien_dans_le_paquet_de_code():
    """`paquet_code` zippe tout le dossier neoforge/ sauf les caches : le
    fichier doit donc suivre, sans qu'on ait à toucher au script."""
    src = (RACINE / "tools" / "publier_neoforge.py").read_text(encoding="utf-8")
    bloc = src[src.index("def paquet_code"):src.index("def roue")]
    exclus = re.findall(r'"(__pycache__|\.pyc)"', bloc)
    assert exclus, "le script doit continuer d'exclure les caches"
    assert "LICENCES" not in bloc, "rien ne doit exclure le fichier de licences"


def test_la_licence_donne_des_liens_qui_ont_un_sens():
    t = (RACINE / "neoforge" / "LICENCES.txt").read_text(encoding="utf-8")
    liens = re.findall(r"https://\S+", t)
    assert any("gnu.org" in u and "lgpl-2.1" in u for u in liens), "texte de la LGPL"
    assert any("dev.opencascade.org" in u for u in liens), "licences Open CASCADE"
    assert any("github.com/CadQuery/OCP" in u for u in liens), "les liaisons OCP"


# ── La fenêtre « Licences et mentions » ────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _html(app):
    from ui.components.licenses_dialog import LicensesDialog
    d = LicensesDialog()
    try:
        return d._build_html()
    finally:
        d.close()


def test_la_fenetre_cite_occt_et_ocp(app):
    h = _html(app)
    for attendu in ("Open CASCADE Technology", "LGPL 2.1", "OPEN CASCADE SAS",
                    "OCP", "cadquery-ocp-novtk", "Apache 2.0"):
        assert attendu in h, attendu


def test_la_fenetre_donne_le_texte_de_la_notice_pas_seulement_un_lien(app):
    """Un lien ne suffit pas : la LGPL demande que la notice accompagne le
    programme. Elle doit donc être dans la page, en clair."""
    h = _html(app)
    assert "This library is free software" in h
    assert "OCCT_LGPL_EXCEPTION.txt" in h


def test_la_fenetre_dit_ou_sont_les_bibliotheques_remplacables(app):
    """La LGPL suppose que l'utilisateur puisse substituer sa propre version de
    la bibliothèque. On lui dit au moins où elle se trouve."""
    h = _html(app)
    assert "replaced by another build" in h
    assert "kernel installation folder" in h


def test_la_section_neoforge_arrive_avant_le_texte_apache(app):
    """Le texte Apache 2.0 affiché plus bas vaut aussi pour OCP : il doit venir
    après, sinon la page se lit à l'envers."""
    h = _html(app)
    assert h.index("cadquery-ocp-novtk") < h.index("Apache License")


def test_les_liens_de_la_fenetre_sont_cliquables(app):
    h = _html(app)
    for u in ("dev.opencascade.org/resources/licensing", "github.com/CadQuery/OCP"):
        assert f"href='https://{u}'" in h, u


# ── Les traductions ────────────────────────────────────────────────────────
@pytest.mark.parametrize("langue", LANGUES)
def test_le_titre_de_section_est_traduit(langue):
    from core import i18n
    avant = i18n.lang()
    i18n.set_lang(langue)
    try:
        titre = i18n._("licenses.sec_neoforge")
        assert titre != "licenses.sec_neoforge", f"{langue} : clé absente"
        assert "neoForge" in titre, f"{langue} : {titre!r}"
    finally:
        i18n.set_lang(avant)


@pytest.mark.parametrize("langue", LANGUES)
def test_aucune_section_de_la_fenetre_ne_reste_en_clef_brute(app, langue):
    """Le piège habituel : une clé ajoutée en français seulement, et les autres
    langues affichent « licenses.sec_neoforge » en toutes lettres."""
    from core import i18n
    avant = i18n.lang()
    i18n.set_lang(langue)
    try:
        h = _html(app)
        orphelines = re.findall(r"licenses\.[a-z_]+", h)
        assert not orphelines, f"{langue} : clés non traduites {set(orphelines)}"
    finally:
        i18n.set_lang(avant)
