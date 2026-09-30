# -*- coding: utf-8 -*-
"""Le viewer reçoit bien UNE COULEUR PAR FACE, et la pièce seule aussi.

Deux choses que les tests du moteur ne couvrent pas et qui ont failli passer
à l'as :

  1. le tableau envoyé au viewer doit avoir exactement autant de valeurs que
     le maillage affiché a de faces. Un décalage ne plante pas, il colorie
     simplement les mauvaises faces, et personne ne s'en aperçoit ;

  2. une pièce d'UN SEUL corps n'avait aucune thermomap : les trois
     constructeurs exigeaient au moins deux corps. C'est pourtant le cas le
     plus courant, et celui où savoir OÙ ça casse sert le plus.

On appelle la vraie méthode de la fenêtre principale sans construire la
fenêtre, en instanciant la classe par `__new__` et en lui posant les seuls
attributs qu'elle lit. Même procédé que pour les panneaux de neoForge.
"""
import numpy as np
import pytest
import trimesh


def _fenetre_bouchon(mesh):
    """Une MainWindow non construite, avec le strict nécessaire."""
    from ui.main_window import MainWindow
    f = MainWindow.__new__(MainWindow)
    f._mesh = mesh
    f._current_nozzle_diameter = 0.4
    f._threemf_data = None
    f._neogen_scene = None
    f._overview_cache = None
    return f


def _bloc_avec_nervure(ep_mm=1.0, decalage_x=15.0):
    bloc = trimesh.creation.box(extents=(40, 40, 10))
    bloc.apply_translation((0, 0, 5))
    nerv = trimesh.creation.box(extents=(6, ep_mm, 40))
    nerv.apply_translation((decalage_x, 0, 30))
    return trimesh.boolean.union([bloc, nerv], engine="manifold")


# ── La pièce seule a enfin une thermomap ───────────────────────────────────
def test_une_piece_d_un_seul_corps_est_peinte():
    """Avant, la case « Fragilité » n'apparaissait même pas."""
    m = _bloc_avec_nervure()
    assert len(trimesh.graph.connected_components(
        m.face_adjacency, nodes=np.arange(len(m.faces)))) == 1, "témoin : un seul corps"

    sev, mx = _fenetre_bouchon(m)._build_bodysplit_fragility_severity()
    assert sev is not None, "une pièce seule doit avoir sa thermomap"
    assert len(sev) == len(m.faces)
    assert mx > 0.6


def test_la_piece_seule_est_peinte_au_bon_endroit():
    m = _bloc_avec_nervure()
    sev, _mx = _fenetre_bouchon(m)._build_bodysplit_fragility_severity()
    centres = np.asarray(m.triangles_center)
    assert sev[centres[:, 0] > 13.0].max() > 0.6, "la nervure doit ressortir"
    assert sev[centres[:, 0] < 5.0].max() < 0.2, "le bloc ne doit pas rougir"


def test_la_piece_n_est_plus_d_une_seule_teinte():
    """Le cœur de la demande : avant, TOUTES les faces recevaient la même
    valeur, donc la pièce était d'une seule couleur."""
    m = _bloc_avec_nervure()
    sev, _mx = _fenetre_bouchon(m)._build_bodysplit_fragility_severity()
    assert len(np.unique(np.round(sev, 2))) > 1


# ── Deux corps séparés : chacun peint chez lui ─────────────────────────────
def test_deux_corps_gardent_chacun_leur_carte():
    """Une pièce fragile et une pièce saine sur le même plateau : la carte de
    l'une ne doit pas déborder sur l'autre."""
    fragile = trimesh.creation.box(extents=(30, 30, 0.8))
    fragile.apply_translation((-40, 0, 0.4))
    solide = trimesh.creation.box(extents=(20, 20, 20))
    solide.apply_translation((40, 0, 10))
    m = trimesh.util.concatenate([fragile, solide])

    sev, mx = _fenetre_bouchon(m)._build_bodysplit_fragility_severity()
    assert sev is not None and len(sev) == len(m.faces)
    centres = np.asarray(m.triangles_center)
    aires = np.asarray(m.area_faces)
    gauche = centres[:, 0] < 0
    # Surface VUE, pas nombre de faces : les quatre tranches de la plaque sont
    # légitimement vertes, elles ont 30 mm de matière derrière elles.
    part = float(aires[gauche & (sev > 0.5)].sum() / aires[gauche].sum())
    assert part > 0.9, f"la plaque fine doit être rouge ({100 * part:.0f} %)"
    assert sev[centres[:, 0] > 0].max() < 0.3, "le cube massif doit rester vert"


# ── L'alignement, le risque silencieux ─────────────────────────────────────
@pytest.mark.parametrize("forme", [
    trimesh.creation.box(extents=(25, 25, 25)),
    trimesh.creation.icosphere(subdivisions=3, radius=12),
    trimesh.creation.cylinder(radius=8, height=30),
])
def test_le_tableau_a_toujours_la_taille_du_maillage(forme):
    m = forme.copy()
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    sev, _mx = _fenetre_bouchon(m)._build_bodysplit_fragility_severity()
    assert sev is not None
    assert len(sev) == len(m.faces), "un décalage colorierait les mauvaises faces"
    assert sev.dtype == np.float32
    assert float(sev.min()) >= 0.0 and float(sev.max()) <= 1.0


def test_un_maillage_enorme_est_toujours_refuse():
    """Le garde-fou de coût ne doit pas avoir sauté avec la nouvelle carte."""
    from ui.main_window import MainWindow
    f = MainWindow.__new__(MainWindow)
    faux = type("M", (), {"faces": np.zeros((300_000, 3), dtype=np.int64)})()
    f._mesh = faux
    sev, mx = MainWindow._build_bodysplit_fragility_severity(f)
    assert sev is None and mx == -1.0


# ── La couleur reste PAR FACE, et c'est voulu ─────────────────────────────
def test_la_couleur_reste_posee_par_face():
    """J'avais reporté la couleur aux sommets pour effacer les arêtes des
    triangles. C'était une erreur, et elle a empiré le rendu : un sommet
    appartient à plusieurs surfaces, donc le coin d'un grand panneau plat
    héritait d'une part de la fragilité des nervures fines qui s'y rattachent,
    et l'interpolation étalait cette contamination sur tout le panneau.

    Mesuré sur une équerre : panneau arrière parfaitement uniforme par face
    (0,090 partout, écart nul), et dégradé de 0,104 à 0,138 une fois passé aux
    sommets, parce que ses quatre coins touchent des joues à 0,58.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "ui" / "components" / "viewer_3d.py").read_text(encoding="utf-8")
    bloc = src[src.index("def colorize_fragility"):]
    bloc = bloc[:bloc.index("def set_loading")]
    assert 'cell_data["fragility"]' in bloc
    assert 'point_data["fragility"]' not in bloc,         "le report aux sommets contamine les surfaces voisines"
    assert "_severite_aux_sommets" not in src, "la fonction doit avoir disparu"


def test_une_surface_plane_reste_d_un_seul_ton():
    """Le cas exact d'Emmanuel : un grand panneau plat bordé de nervures
    fines. Par face, le panneau doit sortir parfaitement uniforme."""
    from core.geometry.fragility_detector import detect_fragility
    morceaux = [trimesh.creation.box(extents=(160, 3.0, 60)),
                trimesh.creation.box(extents=(160, 40, 3.0))]
    morceaux[0].apply_translation((0, 1.5, 30))
    morceaux[1].apply_translation((0, 20, 1.5))
    for x in (-70, 70):
        joue = trimesh.creation.box(extents=(2.0, 36, 50))
        joue.apply_translation((x, 21, 26))
        morceaux.append(joue)
    equerre = trimesh.boolean.union(morceaux, engine="manifold")

    sev = detect_fragility(equerre, avec_faces=True).severites_faces
    centres = np.asarray(equerre.triangles_center)
    panneau = (centres[:, 1] < 0.4) & (np.abs(centres[:, 0]) < 60) & (centres[:, 2] > 10)
    assert panneau.sum() >= 2, "témoin : on a bien trouvé le panneau"
    ecart = float(sev[panneau].max() - sev[panneau].min())
    assert ecart < 1e-6, f"le panneau doit être d'un seul ton, écart {ecart:.3f}"

    joues = np.abs(centres[:, 0]) > 68
    assert sev[joues].max() > sev[panneau].max(),         "les joues fines doivent rester plus alarmantes que le panneau"
