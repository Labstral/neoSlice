# -*- coding: utf-8 -*-
"""La carte d'import garde la pièce quand l'étape ① est à revalider.

Emmanuel, 2026-10-01 : changer d'imprimante avec une pièce déjà chargée
reverrouille l'import, et la carte affichait alors « VALIDEZ L'IMPRIMANTE » à
la place du nom du fichier. « oui ça me gêne, change ça pour que ce soit le
plus logique ».

Le plus logique : la pièce est toujours là, toujours à l'écran, toujours la
pièce de travail. On garde donc sa miniature et son nom, et on explique
seulement pourquoi on ne peut pas en charger une autre.

⚠ Le piège du retour : l'état « chargé » normal est posé par `_set_file`, pas
par `_refresh_labels`. Sans le remettre explicitement, « validez l'étape ①
pour en changer » restait affiché après qu'on venait justement de revalider.
"""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FICHIER = Path("Chute_Cover.stl")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def zone(app):
    from ui.components.drop_zone import DropZone
    z = DropZone()
    z.resize(360, 170)
    z.show()
    app.processEvents()
    yield z
    z.deleteLater()


@pytest.fixture
def zone_chargee(zone, app):
    zone.set_locked(False)
    zone._set_file(FICHIER)
    app.processEvents()
    return zone


# ── Les quatre états ──────────────────────────────────────────────────────
def test_verrouillee_sans_piece_demande_de_valider(zone):
    assert "VALIDEZ" in zone._main_label.text().upper()
    assert not zone.acceptDrops()


def test_chargee_montre_le_fichier(zone_chargee):
    assert zone_chargee._main_label.text() == FICHIER.name
    assert zone_chargee.acceptDrops()
    assert not zone_chargee._step_label.isVisible()


def test_reverrouillee_garde_le_nom_du_fichier(zone_chargee, app):
    zone_chargee.set_locked(True)
    app.processEvents()
    assert zone_chargee._main_label.text() == FICHIER.name, \
        "le nom de la pièce a disparu derrière le cadenas"
    assert not zone_chargee.acceptDrops(), "on ne doit pas pouvoir en charger une autre"
    assert zone_chargee._step_label.isVisible(), "l'étape à revalider doit être visible"
    assert "①" in zone_chargee._sub_label.text()


def test_revalidee_revient_a_l_etat_normal(zone_chargee, app):
    zone_chargee.set_locked(True)
    app.processEvents()
    zone_chargee.set_locked(False)
    app.processEvents()
    assert zone_chargee._main_label.text() == FICHIER.name
    assert zone_chargee._sub_label.text() == "cliquer pour changer"
    assert zone_chargee.acceptDrops()
    assert not zone_chargee._step_label.isVisible()


def test_la_miniature_survit_au_verrouillage(zone_chargee, app):
    """Elle est posée après coup par le worker d'aperçu : la reperdre ferait
    clignoter la carte à chaque changement d'imprimante."""
    from PySide6.QtCore import QBuffer, QByteArray
    from PySide6.QtGui import QPixmap
    pix = QPixmap(64, 64)
    pix.fill()
    octets = QByteArray()
    tampon = QBuffer(octets)
    tampon.open(QBuffer.WriteOnly)
    pix.save(tampon, "PNG")
    zone_chargee.set_thumbnail(bytes(octets))
    app.processEvents()
    assert zone_chargee._thumb.isVisible() and not zone_chargee._icon.isVisible()

    zone_chargee.set_locked(True)
    app.processEvents()
    assert zone_chargee._thumb.isVisible(), "la miniature a disparu"
    assert not zone_chargee._icon.isVisible(), "le cadenas a repris la place"


def test_une_nouvelle_session_repart_de_zero(zone_chargee, app):
    zone_chargee.reset()
    app.processEvents()
    assert zone_chargee._main_label.text() != FICHIER.name


# ── Le thème ──────────────────────────────────────────────────────────────
def test_les_deux_themes_tiennent(zone_chargee, app):
    import re
    from ui.styles.theme import MANAGER as _T
    depart = _T.name()
    try:
        couleurs = {}
        for nom in ("dark", "light"):
            _T.switch(nom)
            zone_chargee.set_locked(True)
            app.processEvents()
            couleurs[nom] = re.findall(r"#[0-9A-Fa-f]{6}",
                                       zone_chargee._sub_label.styleSheet())
            assert couleurs[nom], f"aucune couleur en {nom}"
        assert couleurs["dark"] != couleurs["light"], "palette figée"
    finally:
        _T.switch(depart)
