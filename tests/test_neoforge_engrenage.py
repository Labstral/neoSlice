# -*- coding: utf-8 -*-
"""Engrenage : nombre de dents et forme des dents au choix.

« Dans les formes j'aimerais aussi ajouter un engrenage, avec lequel dans les
réglages on peut choisir le nombre de dents ainsi que la forme de ces
dernières. Et bien entendu dans le viewer pouvoir modifier la taille sur tous
les axes » (Emmanuel, 2026-09-26).

Trois profils : droit (le plus solide), arrondi (il roule sans à coup) et
pointu (décoratif). Les rayons suivent la règle du module, et la dent occupe
un peu moins de la moitié du pas au pied, sans quoi deux engrenages
identiques ne pourraient pas s'engrener.
"""
import math

import numpy as np
import pytest
import trimesh

from neoforge.noyau import maillage as M, occ as O
from neoforge.noyau.primitives import solide
from neoforge.projet import ergonomie as E
from neoforge.projet.mesures import cotes, echelle_apercu
from neoforge.projet.modele import Forme, Projet

PROFILS = ("droit", "arrondi", "pointu")


def _roue(dents=16, profil="droit", dim=(40.0, 40.0, 6.0)):
    f = Forme("engrenage", "matiere", [0.0, 0.0, dim[2] / 2.0],
              [float(v) for v in dim])
    f.cotes, f.variante = dents, profil
    return f


def _maillee(f):
    V, F = M.trianguler(solide(f))
    return trimesh.Trimesh(vertices=V, faces=F)


@pytest.mark.parametrize("profil", PROFILS)
@pytest.mark.parametrize("dents", [6, 12, 20, 48, 120])
def test_la_roue_est_saine_a_tout_nombre_de_dents(profil, dents):
    s = solide(_roue(dents, profil))
    assert O.valide(s), (dents, profil)
    assert O.volume(s) > 0.0


@pytest.mark.parametrize("profil", PROFILS)
def test_la_boite_fait_les_cotes_demandees(profil):
    """Les chiffres du panneau doivent être les vraies cotes de la pièce."""
    m = _maillee(_roue(18, profil, (44.0, 30.0, 5.0)))
    etendue = m.bounds[1] - m.bounds[0]
    assert etendue[0] == pytest.approx(44.0, abs=0.05)
    assert etendue[1] == pytest.approx(30.0, abs=0.05)
    assert etendue[2] == pytest.approx(5.0, abs=0.05)


@pytest.mark.parametrize("dents", [10, 16, 24])
def test_il_y_a_bien_le_bon_nombre_de_dents(dents):
    """On compte les passages matière/vide sur un cercle au sommet des dents :
    deux par dent."""
    m = _maillee(_roue(dents, "droit"))
    rayon = 19.7                       # juste sous le sommet, pièce de Ø40
    a = np.linspace(0, 2 * math.pi, 3600, endpoint=False)
    dedans = m.contains(np.column_stack([rayon * np.cos(a), rayon * np.sin(a),
                                         np.full_like(a, 3.0)]))
    passages = int(np.sum(dedans != np.roll(dedans, 1)))
    assert passages == 2 * dents, (dents, passages)


@pytest.mark.parametrize("dents", [8, 12, 20, 40])
def test_deux_roues_identiques_peuvent_s_engrener(dents):
    """La dent doit occuper un peu moins de la moitié du pas au pied, sinon la
    dent de l'une ne rentre pas dans le creux de l'autre. Le premier jet
    donnait 60 % à la dent : deux roues se seraient bloquées."""
    m = _maillee(_roue(dents, "droit"))
    pied = 20.0 * (dents - 2.5) / (dents + 2) * 1.02
    a = np.linspace(0, 2 * math.pi, 3600, endpoint=False)
    part = float(m.contains(np.column_stack(
        [pied * np.cos(a), pied * np.sin(a), np.full_like(a, 3.0)])).mean())
    assert 0.38 <= part <= 0.50, (dents, part)


def test_les_trois_profils_donnent_des_pieces_differentes():
    volumes = dict(zip(PROFILS, (O.volume(solide(_roue(16, p))) for p in PROFILS)))
    assert len(set(round(v, 1) for v in volumes.values())) == 3, volumes
    # Les dents pointues sont les plus fines : c'est la roue la plus légère.
    # (Aucun ordre entre « droit » et « arrondi » : les bosses du profil
    # arrondi retiennent plus de matière que les trapèzes, MESURÉ, alors que
    # j'avais supposé l'inverse.)
    assert volumes["pointu"] < volumes["droit"], volumes
    assert volumes["pointu"] < volumes["arrondi"], volumes


def test_les_trois_axes_se_tirent_a_la_souris():
    """« Pouvoir modifier la taille sur tous les axes. »"""
    assert [c.axe for c in cotes(_roue())] == [0, 1, 2]


def test_l_apercu_suit_la_taille_sans_tout_refaire():
    f = _roue(16, "droit", (60.0, 40.0, 10.0))
    assert echelle_apercu(f, [40.0, 40.0, 6.0]) == pytest.approx(
        (1.5, 1.0, 10.0 / 6.0))


def test_une_roue_neuve_est_utilisable_telle_quelle():
    p = Projet.nouveau()
    f = E.nouvelle_forme(p, "engrenage", None)
    assert f.cotes == 16 and f.variante == "droit"
    assert f.dim[2] < f.dim[0] / 4.0                  # une roue, pas un tonneau
    assert f.pos[2] == pytest.approx(f.dim[2] / 2.0)  # posée sur le plateau


def test_le_profil_et_les_dents_sont_enregistres(tmp_path):
    from neoforge.projet import nfg
    p = Projet.nouveau()
    p.etapes = [_roue(37, "arrondi")]
    relu = nfg.lire(nfg.ecrire(p, tmp_path / "roue.nfg"))
    assert relu.etapes[0].cotes == 37
    assert relu.etapes[0].variante == "arrondi"


def test_la_roue_est_proposee_dans_le_menu():
    from neoforge.ui.pile import FORMES
    from neoforge.projet.modele import FORMES as MODELE
    assert "engrenage" in FORMES and "engrenage" in MODELE


def test_les_libelles_existent_dans_les_cinq_langues():
    from neoforge.ui.textes import LANGUES
    for code, mots in LANGUES.items():
        for cle in ("engrenage", "nombre_dents", "dents_n", "profil_dents",
                    "dent_droit", "dent_arrondi", "dent_pointu",
                    "epaisseur_roue"):
            assert mots.get(cle), f"{code} : {cle} manquant"
