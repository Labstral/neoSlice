# -*- coding: utf-8 -*-
"""Cotes affichées sur la pièce et redimensionnement à la souris (sans noyau).

Demandes d'Emmanuel (2026-09-12) : régler la taille d'une pièce directement
dans la vue 3D, avec une cote par côté, et une seule quand deux côtés sont
identiques."""
import pytest

from neoforge.projet import ergonomie as E
from neoforge.projet.mesures import cotes, est_diametre
from neoforge.projet.modele import Forme


def _libelles(f):
    return [c.libelle for c in cotes(f)]


def test_cube_aux_cotes_egales_n_affiche_qu_un_chiffre():
    assert _libelles(Forme("cube", "matiere", [0, 0, 10], [20, 20, 20])) == ["20", None, None]
    assert _libelles(Forme("cube", "matiere", [0, 0, 5], [30, 20, 10])) == ["30", "20", "10"]
    # deux côtés égaux sur trois : le troisième garde son chiffre
    assert _libelles(Forme("cube", "matiere", [0, 0, 5], [20, 20, 10])) == ["20", None, "10"]


def test_formes_rondes():
    assert _libelles(Forme("sphere", "matiere", [0, 0, 10], [20, 20, 20])) == ["Ø20"]
    # un diamètre et une hauteur de même valeur restent deux cotes distinctes
    # Le cylindre a DEUX diamètres depuis la 2.1 (il peut être ovale) : rond,
    # le second ne réaffiche pas le chiffre, mais sa poignée existe bien.
    assert _libelles(Forme("cylindre", "matiere", [0, 0, 10], [20, 20, 20]))         == ["Ø20", None, "20"]
    assert _libelles(Forme("cylindre", "matiere", [0, 0, 10], [40, 20, 30]))         == ["Ø40", "Ø20", "30"]
    assert [c.axe for c in cotes(Forme("cylindre", "matiere", [0, 0, 10],
                                       [40, 20, 30]))] == [0, 1, 2]
    assert _libelles(Forme("cone", "matiere", [0, 0, 12], [20, 10, 24])) == ["Ø20", "Ø10", "24"]
    # cône pointu : aucune poignée pour un diamètre nul
    assert [c.axe for c in cotes(Forme("cone", "matiere", [0, 0, 12], [20, 0, 24]))] == [0, 2]


def test_les_cotes_sont_tracees_hors_de_la_piece():
    """Sinon les poignées se posent au milieu des faces et on ne peut plus
    attraper la pièce pour la déplacer (retour d'Emmanuel)."""
    from neoforge.projet.mesures import geometrie_cotes
    f = Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])
    mini, maxi = E.boite(f)
    lignes = geometrie_cotes(f)
    assert len(lignes) == 3
    for ligne in lignes:
        for bout in ("p0", "p1"):
            point = ligne[bout]
            dehors = any(point[a] > maxi[a] + 1e-6 or point[a] < mini[a] - 1e-6
                         for a in range(3))
            assert dehors, f"{bout} {point} est dans la pièce"
    # la longueur de chaque trait reste la mesure du côté
    for ligne in lignes:
        longueur = sum((a - b) ** 2 for a, b in zip(ligne["p0"], ligne["p1"])) ** 0.5
        assert longueur == pytest.approx(30)


def test_les_cotes_suivent_la_rotation():
    from neoforge.projet.mesures import geometrie_cotes
    f = Forme("cube", "matiere", [0, 0, 15], [40, 20, 10], [0, 0, 90])
    lignes = {l["axe"]: l for l in geometrie_cotes(f)}
    direction = lignes[0]["direction"]
    assert direction == pytest.approx([0, 1, 0], abs=1e-6)      # X local → Y monde


def test_echelle_de_l_apercu_selon_la_forme():
    """Les dimensions ne sont pas des longueurs par axe : un diamètre vaut pour
    X ET Y, et le cône a deux diamètres indépendants (retour d'Emmanuel : le
    redimensionnement d'un cône ne marchait pas du tout)."""
    from neoforge.projet.mesures import echelle_apercu
    cube = Forme("cube", "matiere", [0, 0, 5], [20, 30, 10])
    assert echelle_apercu(cube, [10, 30, 10]) == pytest.approx((2, 1, 1))

    sphere = Forme("sphere", "matiere", [0, 0, 5], [30, 30, 30])
    assert echelle_apercu(sphere, [10, 10, 10]) == pytest.approx((3, 3, 3))

    cylindre = Forme("cylindre", "matiere", [0, 0, 5], [30, 30, 20])
    assert echelle_apercu(cylindre, [10, 10, 10]) == pytest.approx((3, 3, 2))

    cone = Forme("cone", "matiere", [0, 0, 5], [30, 10, 20])
    assert echelle_apercu(cone, [30, 10, 10]) == pytest.approx((1, 1, 2))  # hauteur seule
    assert echelle_apercu(cone, [20, 10, 20]) is None                      # diamètre bas
    assert echelle_apercu(cone, [30, 5, 20]) is None                       # diamètre haut

    pointu = Forme("cone", "matiere", [0, 0, 12], [20, 0, 24])
    assert echelle_apercu(pointu, [20, 0, 24]) == pytest.approx((1, 1, 1))  # jamais zéro


def test_tirer_un_cote_garde_la_face_opposee_immobile():
    f = Forme("cube", "matiere", [0, 0, 10], [20, 20, 20])
    gauche_avant = E.boite(f)[0][0]
    assert E.redimensionner(f, 0, 5.0) == pytest.approx(5.0)
    assert f.dim[0] == pytest.approx(25) and f.pos[0] == pytest.approx(2.5)
    assert E.boite(f)[0][0] == pytest.approx(gauche_avant)        # face opposée fixe
    assert E.boite(f)[1][0] == pytest.approx(15)                  # face tirée suit


def test_tirer_le_cote_negatif():
    f = Forme("cube", "matiere", [0, 0, 10], [20, 20, 20])
    E.redimensionner(f, 0, 4.0, sens=-1)
    assert f.dim[0] == pytest.approx(24) and f.pos[0] == pytest.approx(-2.0)
    assert E.boite(f)[1][0] == pytest.approx(10)                  # face + inchangée


def test_un_diametre_grandit_des_deux_cotes_sans_bouger_le_centre():
    f = Forme("cylindre", "matiere", [3, 0, 10], [20, 20, 30])
    assert est_diametre(f, 0) and not est_diametre(f, 2)
    assert E.redimensionner(f, 0, 3.0) == pytest.approx(6.0)
    assert f.dim[0] == pytest.approx(26) and f.pos[0] == pytest.approx(3)


def test_forme_pivotee_le_cote_suit_sa_propre_direction():
    f = Forme("cube", "matiere", [0, 0, 10], [20, 20, 20], [0, 0, 90])
    E.redimensionner(f, 0, 6.0)
    assert f.dim[0] == pytest.approx(26)
    assert f.pos[0] == pytest.approx(0) and f.pos[1] == pytest.approx(3)   # X local = Y monde


def test_taille_minimale_respectee():
    f = Forme("cube", "matiere", [0, 0, 10], [20, 20, 20])
    applique = E.redimensionner(f, 2, -100.0)
    assert f.dim[2] == pytest.approx(E.MINI_DIM)
    assert applique == pytest.approx(E.MINI_DIM - 20)


def test_sphere_reste_ronde():
    f = Forme("sphere", "matiere", [0, 0, 10], [20, 20, 20])
    E.redimensionner(f, 0, 2.0)
    assert f.dim == [pytest.approx(24)] * 3
