# -*- coding: utf-8 -*-
"""La moitié retirée par une découpe ne doit plus exister NULLE PART.

Retour d'Emmanuel : « quand on coupe l'objet, on a bien une moitié mais quand on
clique sur la moitié, on voit encore toute l'autre moitié en invisible qui
apparaît et qui crée une box de collision très pénible ». La cause était la même
partout : l'aperçu, les poignées et le clic travaillent sur la PRIMITIVE de
l'étape, qui ne sait rien des coupes qui la suivent."""
import numpy as np
import pytest

from neoforge.noyau.selection import etape_au_point
from neoforge.projet.decoupes import (coupes_apres, plans_locaux, retiree_par,
                                      sans_ecart, sur_le_plan)
from neoforge.projet.ergonomie import direction_axe
from neoforge.projet.modele import Arrondi, Coupe, Forme, Projet
from neoforge.ui.apercu import couper_maillage, maillage_local


def _cube(pos=(0, 0, 15), dim=(30, 30, 30), rot=(0, 0, 0)):
    return Forme("cube", "matiere", list(pos), list(dim), list(rot))


def _volume(V, F) -> float:
    """Volume signé d'un maillage fermé : six fois la somme des déterminants."""
    V, F = np.asarray(V, float), np.asarray(F)
    if not len(F):
        return 0.0
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return abs(float(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c)))) / 6.0)


# ── Quelles coupes concernent une étape ───────────────────────────────────
def test_seules_les_coupes_qui_SUIVENT_rognent_la_forme():
    """Une coupe faite avant que la forme n'existe ne la concerne pas."""
    avant, apres = Coupe(2, 5.0, "dessous"), Coupe(2, 10.0, "dessous")
    p = Projet([avant, _cube(), apres])
    assert coupes_apres(p, 1) == [apres]
    assert coupes_apres(p, 0) == [apres]
    assert coupes_apres(p, 2) == []


def test_une_coupe_masquee_ne_rogne_rien():
    coupe = Coupe(2, 10.0, "dessous")
    coupe.actif = False
    assert coupes_apres(Projet([_cube(), coupe]), 0) == []


def test_les_autres_etapes_ne_sont_pas_prises_pour_des_coupes():
    p = Projet([_cube(), Arrondi("conge", 2.0, "liste"), Coupe(2, 10.0, "dessus")])
    assert [type(c) for c in coupes_apres(p, 0)] == [Coupe]


# ── Le plan, vu depuis le repère propre de la forme ───────────────────────
def test_garder_les_deux_ne_rogne_aucun_apercu():
    """Rien n'est retiré : l'aperçu doit rester entier."""
    assert plans_locaux(_cube(), [Coupe(2, 10.0, "les_deux")]) == []


@pytest.mark.parametrize("rot", [(0, 0, 0), (90, 0, 0), (0, 45, 0), (30, 20, 10)])
@pytest.mark.parametrize("axe,position", [(2, 10.0), (0, -4.0), (1, 3.5)])
def test_le_plan_local_retombe_sur_le_plan_du_monde(rot, axe, position):
    """Le plan est exprimé dans le repère propre de la pièce, tournée comprise :
    son image dans le monde doit redonner exactement `position` sur `axe`."""
    f = _cube(rot=rot)
    (normale, origine), = plans_locaux(f, [Coupe(axe, position, "dessous")])
    base = np.array([direction_axe(f, k) for k in range(3)], float)
    monde = np.array(origine, float) @ base + np.array(f.pos, float)
    assert monde[axe] == pytest.approx(position, abs=1e-9)
    assert np.linalg.norm(normale) == pytest.approx(1.0, abs=1e-9)
    # La normale montre la matière CONSERVÉE : sous le plan, donc vers -axe.
    assert float(np.array(normale, float) @ base[:, axe]) < 0.0


def test_la_normale_change_de_sens_selon_le_morceau_garde():
    f = _cube()
    (bas, _o), = plans_locaux(f, [Coupe(2, 10.0, "dessous")])
    (haut, _o2), = plans_locaux(f, [Coupe(2, 10.0, "dessus")])
    assert np.allclose(bas, [-v for v in haut])


# ── L'aperçu rogné ────────────────────────────────────────────────────────
def test_sans_coupe_l_apercu_est_intact():
    V, F = maillage_local(_cube())
    V2, F2 = couper_maillage(V, F, [])
    assert V2 is V and F2 is F


def test_l_apercu_perd_exactement_la_moitie_retiree():
    f = _cube()                                    # de z = 0 à z = 30
    V, F = couper_maillage(*maillage_local(f),
                           plans_locaux(f, [Coupe(2, 10.0, "dessous")]))
    assert _volume(V, F) == pytest.approx(30 * 30 * 10, rel=1e-6)
    # Le repère est PROPRE : le cube y va de -15 à +15, la coupe à -5.
    assert float(np.max(np.asarray(V)[:, 2])) == pytest.approx(-5.0, abs=1e-6)


def test_l_apercu_rogne_reste_ferme():
    """Ouvert, un aperçu translucide laisse voir son intérieur et redessine
    « un cube dans un cube » : chaque arête doit servir deux fois."""
    f = _cube()
    V, F = couper_maillage(*maillage_local(f),
                           plans_locaux(f, [Coupe(2, 10.0, "dessous")]))
    bords: dict[tuple[int, int], int] = {}
    for a, b, c in np.asarray(F):
        for i, j in ((a, b), (b, c), (c, a)):
            cle = (min(int(i), int(j)), max(int(i), int(j)))
            bords[cle] = bords.get(cle, 0) + 1
    assert bords and all(n == 2 for n in bords.values())


def test_deux_coupes_se_cumulent_sur_l_apercu():
    f = _cube()
    V, F = couper_maillage(*maillage_local(f),
                           plans_locaux(f, [Coupe(2, 20.0, "dessous"),
                                            Coupe(2, 10.0, "dessus")]))
    assert _volume(V, F) == pytest.approx(30 * 30 * 10, rel=1e-6)


def test_une_coupe_qui_ne_laisse_rien_donne_un_apercu_vide():
    """Et non une erreur : l'étape le signale déjà de son côté."""
    f = _cube()
    V, F = couper_maillage(*maillage_local(f),
                           plans_locaux(f, [Coupe(2, 100.0, "dessus")]))
    assert len(V) == 0 and len(F) == 0


@pytest.mark.parametrize("forme,dim", [("cylindre", [30, 30, 30]),
                                       ("cone", [30, 0, 30]),
                                       ("sphere", [30, 30, 30]),
                                       ("tore", [30, 10, 10]),
                                       ("coin", [30, 30, 30]),
                                       ("prisme", [30, 0, 30])])
def test_toutes_les_formes_se_rognent_sans_casser(forme, dim):
    f = Forme(forme, "matiere", [0, 0, 15], dim, [0, 0, 0])
    entier = _volume(*maillage_local(f))
    V, F = couper_maillage(*maillage_local(f),
                           plans_locaux(f, [Coupe(2, 15.0, "dessous")]))
    assert len(F) and 0.0 < _volume(V, F) < entier


# ── Le plan que l'on VOIT ─────────────────────────────────────────────────
def test_le_plan_se_dessine_a_la_taille_de_la_piece():
    """« J'aimerais qu'on puisse voir le plan de coupe » : borné à la pièce, avec
    une marge, pour qu'on voie qu'il la traverse de part en part."""
    from neoforge.projet.decoupes import quadrilatere
    centre, direction, c1, c2 = quadrilatere(2, 10.0, ((0, 0, 0), (30, 30, 30)),
                                             marge=6.0)
    assert centre == [15.0, 15.0, 10.0]          # à la hauteur de la coupe
    assert direction == [0.0, 0.0, 1.0]
    assert (c1, c2) == (42.0, 42.0)              # 30 + deux fois 6


@pytest.mark.parametrize("axe,direction", [(0, [1.0, 0.0, 0.0]),
                                           (1, [0.0, 1.0, 0.0]),
                                           (2, [0.0, 0.0, 1.0])])
def test_le_plan_s_oriente_selon_l_axe(axe, direction):
    """Cliquer X, Y ou Z doit faire pivoter le plan."""
    from neoforge.projet.decoupes import quadrilatere
    centre, vu, c1, c2 = quadrilatere(axe, 4.0, ((0, 0, 0), (10, 20, 30)))
    assert vu == direction
    assert centre[axe] == 4.0
    restants = [10.0, 20.0, 30.0]
    restants.pop(axe)
    assert [c1 - 12.0, c2 - 12.0] == restants    # la marge par défaut vaut 6


def test_un_plan_sur_une_piece_plate_reste_visible():
    """Une pièce très fine ne doit pas donner un plan invisible."""
    from neoforge.projet.decoupes import quadrilatere
    _c, _d, c1, c2 = quadrilatere(2, 0.0, ((0, 0, 0), (0, 0, 0)), marge=0.0)
    assert c1 >= 4.0 and c2 >= 4.0


# ── Le clic ───────────────────────────────────────────────────────────────
def test_cliquer_dans_le_vide_laisse_par_la_coupe_ne_selectionne_RIEN():
    """C'était la « box de collision » : la moitié retirée attrapait encore le
    clic, alors qu'il n'y a plus de matière à cet endroit."""
    p = Projet([_cube(), Coupe(2, 10.0, "dessous")])
    assert etape_au_point(p, (15.0, 0.0, 20.0)) is None


def test_la_moitie_qui_reste_se_selectionne_toujours():
    p = Projet([_cube(), Coupe(2, 10.0, "dessous")])
    assert etape_au_point(p, (15.0, 0.0, 5.0)) == 0


def test_la_face_ouverte_par_la_coupe_se_selectionne():
    """Le dessus tout plat d'une pièce coupée n'appartient à aucune surface de
    la primitive : sans traitement, ce clic ne sélectionnait rien."""
    p = Projet([_cube(), Coupe(2, 10.0, "dessous")])
    assert etape_au_point(p, (0.0, 0.0, 10.0)) == 0


def test_la_face_de_coupe_n_attrape_pas_une_forme_qu_elle_ne_traverse_pas():
    """Le plan est infini, la pièce non : une forme posée ailleurs sur le plan
    ne doit pas capter le clic."""
    loin = _cube(pos=(200, 0, 15))
    p = Projet([_cube(), loin, Coupe(2, 10.0, "dessous")])
    assert etape_au_point(p, (0.0, 0.0, 10.0)) == 0


def test_garder_les_deux_rend_le_morceau_du_haut_selectionnable():
    """Il est ÉCARTÉ de 2 mm, pour 1 mm de tolérance : aucun clic ne l'atteignait
    plus."""
    from neoforge.noyau.construction import ECART_COUPE
    p = Projet([_cube(), Coupe(2, 10.0, "les_deux")])
    assert etape_au_point(p, (15.0, 0.0, 20.0 + ECART_COUPE)) == 0
    assert etape_au_point(p, (15.0, 0.0, 5.0)) == 0


# ── Les briques élémentaires ──────────────────────────────────────────────
@pytest.mark.parametrize("garder,dedans,dehors", [
    ("dessous", (0.0, 0.0, 20.0), (0.0, 0.0, 5.0)),
    ("dessus", (0.0, 0.0, 5.0), (0.0, 0.0, 20.0)),
])
def test_retiree_par(garder, dedans, dehors):
    c = Coupe(2, 10.0, garder)
    assert retiree_par(dedans, c) and not retiree_par(dehors, c)


def test_garder_les_deux_ne_retire_jamais_rien():
    c = Coupe(2, 10.0, "les_deux")
    assert not retiree_par((0, 0, 99), c) and not sur_le_plan((0, 0, 10), c, 1.0)


def test_sur_le_plan():
    c = Coupe(2, 10.0, "dessous")
    assert sur_le_plan((0, 0, 10.4), c, 1.0)
    assert not sur_le_plan((0, 0, 12.0), c, 1.0)


def test_sans_ecart_ne_touche_que_le_morceau_du_haut():
    from neoforge.noyau.construction import ECART_COUPE
    coupes = [Coupe(2, 10.0, "les_deux")]
    assert sans_ecart((1.0, 2.0, 25.0), coupes)[2] == pytest.approx(
        25.0 - ECART_COUPE)
    assert sans_ecart((1.0, 2.0, 5.0), coupes)[2] == pytest.approx(5.0)
    assert sans_ecart((1.0, 2.0, 25.0), [Coupe(2, 10.0, "dessous")])[2] == 25.0
