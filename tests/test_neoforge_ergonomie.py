# -*- coding: utf-8 -*-
"""neoForge : gestes de la console (collage, poser, centrer, trou) et
annuler/rétablir. Sans noyau."""
import pytest

from neoforge.projet import ergonomie as E
from neoforge.projet.historique import Historique
from neoforge.projet.modele import Arrondi, Forme, Projet


def _projet():
    return Projet([Forme("cube", "matiere", [0, 0, 5], [40, 40, 10]),      # socle
                   Forme("cube", "matiere", [0, 0, 40], [10, 10, 10])])    # en l'air


def test_poser_sur_la_piece_du_dessous_puis_sur_le_plateau():
    p = _projet()
    assert E.poser(p, 1) == "piece"
    assert E.boite(p.etapes[1])[0][2] == pytest.approx(10)        # sur le socle
    p.etapes[1].pos[0] = 100                                      # hors du socle
    p.etapes[1].pos[2] = 40
    assert E.poser(p, 1) == "plateau"
    assert E.boite(p.etapes[1])[0][2] == pytest.approx(0)


def test_collage_arrete_a_fleur_mais_un_creux_traverse():
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [10, 10, 10]),
                Forme("cube", "matiere", [30, 0, 5], [10, 10, 10])])
    assert E.limiter(p, 1, 0, -100) == pytest.approx(-20)         # s'arrête contre le 1er
    assert E.limiter(p, 1, 0, -100, collage=False) == -100
    p.etapes[1].op = "creux"
    assert E.limiter(p, 1, 0, -100) == -100                       # le creux passe


def test_la_fleche_de_deplacement_suit_l_axe_propre_de_la_piece():
    """Retour d'Emmanuel : « quand j'oriente un objet, les flèches n'ont plus
    aucun sens ». Le déplacement s'ajoutait à pos[axe], c'est à dire à l'axe du
    MONDE, alors que la flèche dessine l'axe de la pièce, qui a tourné."""
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [10, 10, 10], [0, 0, 90])])
    f = p.etapes[0]
    fait = E.deplacer_selon(p, 0, E.direction_axe(f, 0), 10.0, collage=False)
    assert fait == pytest.approx(10.0)
    assert f.pos == pytest.approx([0, 10, 5], abs=1e-6)        # X local = Y monde


def test_le_collage_arrete_aussi_un_deplacement_oblique():
    p = Projet([Forme("cube", "matiere", [0, 0, 5], [10, 10, 10]),
                Forme("cube", "matiere", [30, 0, 5], [10, 10, 10])])
    fait = E.deplacer_selon(p, 1, (-1, 0, 0), 100.0, collage=True)
    assert fait == pytest.approx(20.0)                          # à fleur du premier
    assert p.etapes[1].pos[0] == pytest.approx(10)


def test_les_deux_diametres_du_cylindre_sont_independants():
    """Le cylindre a DEUX diamètres depuis la 2.1 : tirer l'un ne doit plus
    entraîner l'autre, sinon on ne peut jamais l'ovaliser.

    Ce test gardait auparavant le comportement inverse (dim[1] recopié sur
    dim[0]), mis en place quand le second diamètre ne se réglait pas. Ce qu'il
    protégeait vraiment, c'est que la BOÎTE ENGLOBANTE suive la pièce, sinon
    les cotes se tracent à côté : on le vérifie toujours, mais par axe."""
    f = Forme("cylindre", "matiere", [0, 0, 10], [20, 20, 30])
    E.redimensionner(f, 0, 3.0)                   # un diamètre grandit des 2 côtés
    assert f.dim[0] == pytest.approx(26) and f.dim[1] == pytest.approx(20)
    assert f.demi_etendue()[:2] == pytest.approx([13, 10])
    E.redimensionner(f, 1, -2.0)
    assert f.dim[0] == pytest.approx(26) and f.dim[1] == pytest.approx(16)
    assert f.demi_etendue()[:2] == pytest.approx([13, 8])


def test_la_sphere_reste_ronde_elle():
    """Le rappel qui vaut encore : une sphère n'a qu'un diamètre."""
    f = Forme("sphere", "matiere", [0, 0, 10], [20, 20, 20])
    E.redimensionner(f, 0, 3.0)
    assert f.dim == pytest.approx([26, 26, 26])


def test_un_parent_emmene_ses_enfants_et_pas_l_inverse():
    """Choix d'Emmanuel (2026-09-12) : le lien est explicite et à SENS UNIQUE.
    Bouger le parent emmène l'enfant ; bouger l'enfant seul laisse le parent en
    place, sinon on ne pourrait plus ajuster une petite pièce contre une grande
    sans emmener la grande avec elle."""
    socle = Forme("cube", "matiere", [0, 0, 5], [40, 40, 10])
    p = Projet([socle,
                Forme("cube", "matiere", [0, 0, 15], [10, 10, 10], parent=socle.ident)])
    E.deplacer_selon(p, 0, (1, 0, 0), 7.0, collage=False)
    assert p.etapes[0].pos[0] == pytest.approx(7)
    assert p.etapes[1].pos[0] == pytest.approx(7)          # l'enfant a suivi
    E.deplacer_selon(p, 1, (1, 0, 0), 3.0, collage=False)
    assert p.etapes[1].pos[0] == pytest.approx(10)
    assert p.etapes[0].pos[0] == pytest.approx(7)          # le parent n'a pas bougé


def test_un_enfant_colle_ne_bloque_pas_son_parent():
    """Le collage doit ignorer les pièces qui VOYAGENT avec celle qu'on pousse :
    sinon un enfant posé contre son parent bloque tout dès le premier pas."""
    socle = Forme("cube", "matiere", [0, 0, 5], [20, 20, 10])
    p = Projet([socle,
                Forme("cube", "matiere", [20, 0, 5], [20, 20, 10], parent=socle.ident)])
    assert E.deplacer_selon(p, 0, (1, 0, 0), 15.0, collage=True) == pytest.approx(15.0)


def test_poser_fait_tomber_tout_l_assemblage():
    socle = Forme("cube", "matiere", [0, 0, 25], [40, 40, 10])
    p = Projet([socle,
                Forme("cube", "matiere", [0, 0, 35], [10, 10, 10], parent=socle.ident)])
    assert E.poser(p, 0) == "plateau"
    assert p.etapes[0].pos[2] == pytest.approx(5)
    assert p.etapes[1].pos[2] == pytest.approx(15)         # descendu d'autant


def test_un_enfant_verrouille_fait_bouger_tout_l_ensemble():
    """Demande d'Emmanuel : « si l'enfant est bloqué, même en le sélectionnant
    et en le tournant, c'est tout le parent qui se met à bouger »."""
    socle = Forme("cube", "matiere", [0, 0, 5], [40, 40, 10])
    enfant = Forme("cube", "matiere", [0, 0, 15], [10, 10, 10], parent=socle.ident)
    p = Projet([socle, enfant])
    assert E.cible_du_geste(p, 1) == 1            # libre, il se règle seul
    enfant.verrou = True
    assert E.cible_du_geste(p, 1) == 0            # soudé, le geste remonte
    E.deplacer_selon(p, E.cible_du_geste(p, 1), (1, 0, 0), 6.0, collage=False)
    assert p.etapes[0].pos[0] == pytest.approx(6)
    assert p.etapes[1].pos[0] == pytest.approx(6)


def test_le_verrou_ne_tourne_pas_en_rond():
    """Deux pièces verrouillées l'une sur l'autre ne doivent pas faire boucler
    la remontée vers le parent."""
    a = Forme("cube", "matiere", [0, 0, 5], [10, 10, 10], verrou=True)
    b = Forme("cube", "matiere", [20, 0, 5], [10, 10, 10], verrou=True)
    a.parent, b.parent = b.ident, a.ident
    p = Projet([a, b])
    assert E.cible_du_geste(p, 0) in (0, 1)
    assert E.cible_du_geste(p, 1) in (0, 1)


def test_chaque_piece_est_suivie_de_sa_descendance():
    a = Forme("cube", "matiere", [0, 0, 5], [10, 10, 10])
    b = Forme("cube", "matiere", [30, 0, 5], [10, 10, 10])
    c = Forme("cube", "matiere", [60, 0, 5], [10, 10, 10])
    p = Projet([a, b, c])
    assert E.rattacher(p, 2, 0)                   # c devient enfant de a
    E.ranger_hierarchie(p)
    assert [e.ident for e in p.etapes] == [a.ident, c.ident, b.ident]


def test_detacher_un_enfant_du_milieu_ne_laisse_pas_d_intrus():
    """Retour d'Emmanuel : en sortant un enfant coincé entre le parent et un
    autre enfant, il restait une pièce étrangère au milieu de l'assemblage."""
    socle = Forme("cube", "matiere", [0, 0, 5], [40, 40, 10])
    un = Forme("cube", "matiere", [0, 0, 15], [8, 8, 8], parent=socle.ident)
    deux = Forme("cube", "matiere", [12, 0, 15], [8, 8, 8], parent=socle.ident)
    p = Projet([socle, un, deux])
    assert E.rattacher(p, 1, None)                # on sort « un » de l'assemblage
    E.ranger_hierarchie(p)
    # le socle et son enfant restant sont collés, l'autre passe derrière
    assert [e.ident for e in p.etapes] == [socle.ident, deux.ident, un.ident]


def test_un_arrondi_reste_une_frontiere():
    """Déplacer une forme par dessus un arrondi changerait la pièce."""
    a = Forme("cube", "matiere", [0, 0, 5], [20, 20, 10])
    arrondi = Arrondi("conge", 1.0, "toutes")
    b = Forme("cube", "matiere", [40, 0, 5], [10, 10, 10])
    p = Projet([a, arrondi, b])
    assert E.rattacher(p, 2, 0)                   # b devient enfant de a
    E.ranger_hierarchie(p)
    assert p.etapes[1] is arrondi                 # l'arrondi n'a pas bougé
    assert p.etapes[2] is b                       # b non plus, il est derrière


def test_les_liens_survivent_a_l_enregistrement():
    socle = Forme("cube", "matiere", [0, 0, 5], [40, 40, 10])
    p = Projet([socle,
                Forme("cube", "matiere", [0, 0, 15], [10, 10, 10], parent=socle.ident)])
    relu = Projet.depuis_dico(p.dico())
    assert relu.etapes[1].parent == relu.etapes[0].ident
    assert E.descendants(relu, 0) == [1]


def test_un_fichier_abime_ne_fait_pas_de_boucle():
    """Deux pièces qui se déclarent parentes l'une de l'autre feraient tourner
    un déplacement sans fin : la lecture casse le lien."""
    from neoforge.projet.modele import nettoyer_liens
    a = Forme("cube", "matiere", [0, 0, 5], [10, 10, 10])
    b = Forme("cube", "matiere", [30, 0, 5], [10, 10, 10])
    a.parent, b.parent = b.ident, a.ident
    nettoyer_liens([a, b])
    assert not (a.parent and b.parent)
    p = Projet([a, b])
    assert E.descendants(p, 0) in ([], [1])               # fini, aucune boucle


def test_centrer_sur_la_piece_du_dessous():
    p = _projet()
    p.etapes[0].pos[:2] = [15, -7]
    p.etapes[1].pos = [3, 3, 15]
    assert E.centrer(p, 1) == "piece"
    assert p.etapes[1].pos[:2] == pytest.approx([15, -7])


def test_une_forme_a_cote_ne_touche_rien():
    """Creuser avec une forme posée à côté ne retire rien : l'interface le DIT
    (barre d'état) au lieu de déplacer la forme, Emmanuel ne voulant pas qu'elle
    bouge toute seule."""
    socle = Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])
    cone = Forme("cone", "creux", [31, 0, 12], [20, 0, 24])
    p = Projet([socle, cone])
    assert not E.se_touchent(socle, cone)
    assert p.etapes[1].pos == pytest.approx([31, 0, 12])       # elle reste où elle est


def test_une_forme_neuve_ne_passe_jamais_en_tete():
    """Retour d'Emmanuel : un cône ajouté sans rien de sélectionné se retrouvait
    AVANT le cube. Or le moteur traite toujours la première forme comme de la
    matière, donc Creuser restait grisé et sans effet."""
    etapes = [Forme("cube", "matiere", [0, 0, 5], [30, 30, 30]),
              Forme("cube", "matiere", [40, 0, 5], [10, 10, 10])]
    assert E.position_insertion(etapes, -1) == 2       # rien de sélectionné : à la fin
    assert E.position_insertion(etapes, 0) == 1        # juste après la sélection
    assert E.position_insertion(etapes, 1) == 2
    assert E.position_insertion(etapes, 9) == 2        # sélection aberrante : à la fin
    assert E.position_insertion([], -1) == 0


def test_nouvelle_forme_posee_a_cote_de_la_selection():
    """Le « trou traversant » a été retiré le 2026-09-12 : n'importe quelle forme
    réglée sur « Creuser » fait la même chose (choix d'Emmanuel)."""
    p = _projet()
    n = E.nouvelle_forme(p, "sphere", 0)
    assert E.boite(n)[0][0] > E.boite(p.etapes[0])[1][0]          # posée à droite
    assert E.boite(n)[0][2] == pytest.approx(0)                   # sur le plateau


def test_arrondis_ignores_par_les_gestes():
    p = _projet()
    p.etapes.insert(1, Arrondi("conge", 1, "toutes"))
    assert E.poser(p, 2) == "piece"


def test_annuler_retablir_restaure_exactement():
    p = Projet([Forme("cube", "matiere", [0, 0, 15], [30, 30, 30])])
    h = Historique()
    h.memoriser(p)
    p.etapes[0].dim = [50, 50, 50]
    h.memoriser(p)
    p.etapes.append(Arrondi("chanfrein", 2, "haut"))
    q = h.annuler(p)
    assert len(q.etapes) == 1 and q.etapes[0].dim == [50, 50, 50]
    q = h.annuler(q)
    assert q.etapes[0].dim == [30, 30, 30]
    assert not h.peut_annuler and h.peut_retablir
    q = h.retablir(q)
    assert q.etapes[0].dim == [50, 50, 50]
    h.memoriser(q)                      # une nouvelle action efface le futur
    assert not h.peut_retablir
