# -*- coding: utf-8 -*-
"""L'arrondi se voit EN DIRECT, même pendant qu'on choisit les arêtes.

« Pour arrondir les arêtes, j'aimerais bien que dès lors qu'on a cliqué sur une
des flèches pour augmenter ou diminuer le rayon, on voie la modification en
direct plutôt que de devoir cliquer sur Terminé » (Emmanuel, 2026-09-26).

Cause : pendant le choix des arêtes, le calcul affichait volontairement la
pièce d'AVANT l'arrondi, pour qu'on voie ses angles vifs et qu'on puisse les
cliquer. Changer le rayon ne se voyait donc nulle part. Désormais la pièce
affichée est la pièce ARRONDIE, et les arêtes proposées restent celles d'avant
l'arrondi : elles se dessinent juste au dessus du congé, là où l'angle vif se
trouvait, et restent donc cliquables.

Mesuré au pilote sur un cube de 20 : en mode choix, volume 7804 mm³ à un rayon
de 2 et 6880 mm³ à un rayon de 5. Avant la correction, 8000 dans les deux cas,
c'est à dire le cube brut.
"""
import pytest

from neoforge.noyau import aretes as A, occ as O
from neoforge.noyau.construction import Constructeur
from neoforge.projet.modele import Arrondi, Forme, Projet


def _projet(rayon):
    p = Projet.nouveau()
    p.etapes = [Forme("cube", "matiere", [0, 0, 10], [20.0, 20.0, 20.0]),
                Arrondi("conge", rayon, "toutes")]
    return p


def _sortie(projet, mode_aretes):
    """Rejoue ce que fait le fil de calcul, sans interface ni fenêtre."""
    from neoforge.ui.fenetre import _Calcul
    calcul = _Calcul.__new__(_Calcul)          # pas de QThread à démarrer
    calcul._c = Constructeur()
    calcul._projet = projet
    calcul._selection = 1                      # l'arrondi est sélectionné
    calcul._mode = mode_aretes
    recu = {}
    calcul.fini = type("S", (), {"emit": lambda _s, v: recu.update(v)})()
    _Calcul.run(calcul)
    return recu


@pytest.mark.parametrize("mode", [False, True])
def test_le_rayon_change_le_volume_affiche(mode):
    """LE test de la demande : en mode choix comme en dehors, deux rayons
    différents doivent donner deux pièces différentes à l'écran."""
    petit = _sortie(_projet(2.0), mode)
    grand = _sortie(_projet(5.0), mode)
    assert petit["erreur"] is None and grand["erreur"] is None
    assert petit["volume"] > grand["volume"] + 100.0, (mode, petit["volume"],
                                                       grand["volume"])


def test_pendant_le_choix_la_piece_est_bien_arrondie():
    """Elle ne doit plus être le cube brut : c'était tout le défaut."""
    brut = O.volume(Constructeur().construire(
        Projet([Forme("cube", "matiere", [0, 0, 10], [20.0, 20.0, 20.0])]))[-1].forme)
    assert brut == pytest.approx(8000.0)
    en_choix = _sortie(_projet(2.0), True)
    assert en_choix["volume"] < brut - 100.0


def test_les_aretes_a_cliquer_restent_celles_de_la_piece_brute():
    """Sinon on ne pourrait plus en choisir : une arête déjà arrondie n'existe
    plus. Un cube a douze arêtes, et elles doivent toutes rester proposées."""
    en_choix = _sortie(_projet(2.0), True)
    assert len(en_choix["aretes"]) == 12
    assert len(en_choix["signatures"]) == 12


def test_hors_du_choix_seules_les_aretes_retenues_sont_soulignees():
    p = _projet(2.0)
    p.etapes[1].regle = "liste"
    brut = Constructeur().construire(Projet([p.etapes[0]]))[-1].forme
    candidates = A.aretes_arrondissables(brut)
    boite = O.boite(brut)
    p.etapes[1].aretes = [A.signature(candidates[0], boite)]
    sortie = _sortie(p, False)
    assert len(sortie["aretes"]) == 1
