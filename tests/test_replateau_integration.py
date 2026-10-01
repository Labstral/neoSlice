# -*- coding: utf-8 -*-
"""Le rangement des plateaux, branché : bouton, données, export.

Suite de test_replateau.py, qui couvre le moteur seul. Ici on vérifie que la
fenêtre s'en sert correctement, que le bouton n'apparaît que quand il sert, et
surtout que l'EXPORT reproduit bien ce que l'écran montre.

La fenêtre principale n'est jamais construite dans les tests : trop lourde, et
une seule instance ferait traîner un viewer VTK. Ses méthodes sont appelées sur
un objet minimal qui porte les quelques attributs dont elles ont besoin. C'est
du vrai code de la fenêtre, pas une copie.
"""
import os
import re
import zipfile

import numpy as np
import pytest
import trimesh

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.geometry.threemf_data import MeshObject, ThreeMFData   # noqa: E402

NEPTUNE = "Elegoo Neptune 4 Max"      # 420 × 420 × 480


# ── Un projet de test ─────────────────────────────────────────────────────
def _projet(n: int, cote: float = 100.0, un_plateau_par_piece: bool = True):
    """n cubes, chacun sur son propre plateau, comme un 3MF venu d'ailleurs."""
    objets = []
    for i in range(n):
        m = trimesh.creation.box((cote, cote, 20.0))
        tr = np.eye(4)
        tr[0, 3] = i * 400.0          # positions absolues, loin les unes des autres
        objets.append(MeshObject(object_id=f"o{i}", name=f"Pièce {i + 1}",
                                 extruder=1, mesh=m, transform=tr,
                                 plate_index=i if un_plateau_par_piece else 0))
    poses = []
    for o in objets:
        m = o.mesh.copy()
        m.apply_transform(o.transform)
        poses.append(m)
    combine = trimesh.util.concatenate(poses)
    td = ThreeMFData(combined_mesh=combine, objects=objets,
                     source_path=None, plate_count=n if un_plateau_par_piece else 1)
    return td


class _Viewer:
    def __init__(self):
        self.recharges = 0

    def _load_multipart_mesh(self, td):
        self.recharges += 1


class _Barre:
    def __init__(self):
        self.replate = None
        self.messages = []

    def set_replate(self, texte, infobulle=""):
        self.replate = texte or None

    def set_message(self, texte, couleur=None):
        self.messages.append(texte)


def _fenetre(td, imprimante=NEPTUNE):
    """Objet minimal portant les VRAIES méthodes de la fenêtre principale."""
    from ui.main_window import MainWindow

    class _Faux:
        _empreintes_projet = MainWindow._empreintes_projet
        _plan_replateau = MainWindow._plan_replateau
        _maj_bouton_replateau = MainWindow._maj_bouton_replateau
        _reorganiser_plateaux = MainWindow._reorganiser_plateaux
        _object_mesh_sur_plateau = MainWindow._object_mesh_sur_plateau
        _object_mesh_posed = MainWindow._object_mesh_posed

    f = _Faux()
    f._threemf_data = td
    f._current_printer = imprimante
    f._viewer = _Viewer()
    f._statusbar = _Barre()
    return f


# ── Le plan ───────────────────────────────────────────────────────────────
def test_le_plan_voit_les_plateaux_gagnes():
    f = _fenetre(_projet(23))
    plan, avant = f._plan_replateau()
    assert avant == 23
    assert plan.plateaux == 3


def test_le_plan_suit_l_imprimante_choisie():
    """Sur une machine plus petite, le même projet demande plus de plateaux."""
    grand, _ = _fenetre(_projet(23), NEPTUNE)._plan_replateau()
    petit, _ = _fenetre(_projet(23), "X1 Carbon")._plan_replateau()
    assert petit.plateaux > grand.plateaux


def test_les_empreintes_tiennent_compte_de_la_transform():
    """Les positions d'un 3MF vivent dans la transform, pas dans le maillage."""
    f = _fenetre(_projet(3))
    emp = {e[0]: e for e in f._empreintes_projet(f._threemf_data)}
    assert emp["o0"][1] == pytest.approx(-50.0)       # cube centré, décalé de 0
    assert emp["o2"][1] == pytest.approx(750.0)       # décalé de 2 × 400


def test_un_projet_mono_objet_n_a_rien_a_ranger():
    plan, avant = _fenetre(_projet(1))._plan_replateau()
    assert plan is None and avant == 0


# ── Le bouton ─────────────────────────────────────────────────────────────
def test_le_bouton_apparait_quand_il_y_a_a_gagner():
    f = _fenetre(_projet(23))
    f._maj_bouton_replateau()
    assert f._statusbar.replate and "3" in f._statusbar.replate


def test_le_bouton_reste_cache_quand_c_est_deja_optimal():
    """Un projet déjà bien rangé ne doit pas afficher un bouton inutile."""
    f = _fenetre(_projet(4, cote=100.0, un_plateau_par_piece=False))
    f._maj_bouton_replateau()
    assert f._statusbar.replate is None


def test_le_bouton_disparait_apres_rangement():
    f = _fenetre(_projet(23))
    f._maj_bouton_replateau()
    assert f._statusbar.replate
    f._reorganiser_plateaux()
    assert f._statusbar.replate is None, "il n'y a plus rien à gagner"


# ── Le rangement appliqué ─────────────────────────────────────────────────
def test_le_rangement_reecrit_plateaux_et_positions():
    f = _fenetre(_projet(23))
    avant_tr = [o.transform[0, 3] for o in f._threemf_data.objects]
    f._reorganiser_plateaux()
    td = f._threemf_data
    assert len({o.plate_index for o in td.objects}) == 3
    assert td.plate_count == 3
    assert td.reagence is True, "le viewer doit savoir qu'il ne faut pas recompacter"
    assert [o.transform[0, 3] for o in td.objects] != avant_tr
    assert f._viewer.recharges == 1
    assert any("3" in m for m in f._statusbar.messages)


def test_les_pieces_rangees_ne_se_chevauchent_pas():
    """Le test qui compte : deux pièces l'une sur l'autre casseraient l'impression."""
    f = _fenetre(_projet(23))
    f._reorganiser_plateaux()
    par_plateau = {}
    for mo in f._threemf_data.objects:
        m = f._object_mesh_sur_plateau(mo)
        lo, hi = m.bounds
        par_plateau.setdefault(mo.plate_index, []).append(
            (mo.object_id, lo[0], lo[1], hi[0], hi[1]))
    for plateau, rects in par_plateau.items():
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                assert not (a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6
                            and a[2] < b[4] - 1e-6 and b[2] < a[4] - 1e-6), \
                    f"plateau {plateau} : {a[0]} chevauche {b[0]}"


def test_chaque_plateau_tient_dans_le_plateau_physique():
    f = _fenetre(_projet(23))
    f._reorganiser_plateaux()
    from data.printers import volume_impression
    bx, by, _ = volume_impression(NEPTUNE)
    par = {}
    for mo in f._threemf_data.objects:
        lo, hi = f._object_mesh_sur_plateau(mo).bounds
        par.setdefault(mo.plate_index, []).append((lo, hi))
    for plateau, bornes in par.items():
        larg = max(h[0] for _l, h in bornes) - min(l[0] for l, _h in bornes)
        prof = max(h[1] for _l, h in bornes) - min(l[1] for l, _h in bornes)
        assert larg <= bx and prof <= by, f"plateau {plateau} déborde"


def test_le_maillage_combine_suit_le_rangement():
    """Il sert aux dimensions affichées : le laisser tel quel annoncerait
    l'encombrement d'avant, soit plusieurs mètres."""
    f = _fenetre(_projet(23))
    avant = float(f._threemf_data.combined_mesh.bounding_box.extents[0])
    f._reorganiser_plateaux()
    apres = float(f._threemf_data.combined_mesh.bounding_box.extents[0])
    assert avant > 2000.0 and apres < 500.0


# ── L'export ──────────────────────────────────────────────────────────────
def test_la_pose_d_export_conserve_la_position_contrairement_a_l_isolement():
    """Piège central : `_object_mesh_posed` ramène CHAQUE pièce au centre, ce
    qui les empile toutes au même endroit. L'export multi-plateaux doit
    utiliser la pose qui garde la position."""
    f = _fenetre(_projet(3))
    f._reorganiser_plateaux()
    objets = f._threemf_data.objects
    isoles = [tuple(f._object_mesh_posed(mo).bounds.mean(axis=0)[:2].round(6))
              for mo in objets]
    plateau = [tuple(f._object_mesh_sur_plateau(mo).bounds.mean(axis=0)[:2].round(6))
               for mo in objets]
    assert set(isoles) == {(0.0, 0.0)}, "la pose isolée centre, c'est son rôle"
    assert len(set(plateau)) == 3, f"pièces empilées : {plateau}"


def test_la_fenetre_utilise_bien_la_pose_plateau_pour_le_multi_plateaux():
    """Garde-fou de lecture : si quelqu'un remet `_object_mesh_posed` dans
    l'export multi-plateaux, les pièces se superposeront en silence."""
    import inspect
    from ui.main_window import MainWindow
    src = inspect.getsource(MainWindow)
    bloc = src[src.index('items.append({"mesh"'):][:200]
    assert "_object_mesh_sur_plateau" in bloc


def test_deux_pieces_sur_un_meme_plateau_sortent_a_des_endroits_differents(tmp_path):
    """Bout en bout sur l'écrivain 3MF : deux pièces d'un même plateau doivent
    recevoir des translations DIFFÉRENTES. Avant, l'écrivain recevait des
    maillages déjà centrés et les deux atterrissaient au même endroit."""
    from core.export.multiplate_3mf import build_multiplate_bambu
    from core.export.tmf_builder import _find_bambu_template
    from core.parameters.print_config import PrintConfig
    if not _find_bambu_template():
        pytest.skip("Bambu Studio non installé (pas de template)")

    f = _fenetre(_projet(2, cote=60.0))
    f._reorganiser_plateaux()
    assert len({o.plate_index for o in f._threemf_data.objects}) == 1, \
        "les deux pièces doivent tenir sur UN plateau"

    cfg = PrintConfig()
    objets = [{"mesh": f._object_mesh_sur_plateau(mo), "config": cfg,
               "plate": int(mo.plate_index), "name": f"p{i}"}
              for i, mo in enumerate(f._threemf_data.objects)]
    sortie = build_multiplate_bambu(objets, cfg, tmp_path / "deux.3mf",
                                    "X1 Carbon", "PLA", 0.4)
    xml = zipfile.ZipFile(sortie).read("3D/3dmodel.model").decode("utf-8", "replace")
    # La position d'une pièce vit dans ses SOMMETS. Le transform, lui, est le
    # MÊME pour tout le plateau : il recentre le groupe sur le plateau physique.
    etendues = []
    for bloc in re.split(r"(?=<object id=)", xml)[1:]:
        xs = [float(x) for x in re.findall(r'<vertex x="([-\d.eE]+)"', bloc)]
        if xs:
            etendues.append((min(xs), max(xs)))
    assert len(etendues) == 2, f"{len(etendues)} objets dans le 3MF"
    (a0, a1), (b0, b1) = sorted(etendues)
    assert a1 <= b0 + 1e-6, f"les deux pièces se chevauchent : {etendues}"

    poses = re.findall(r'transform="([^"]+)"', xml)
    assert len({tuple(p.split()[9:11]) for p in poses}) == 1,         "un même plateau = un seul recentrage de groupe"


# ── Le bouton, en vrai ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def barre(app):
    from ui.main_window import _StatusBar
    b = _StatusBar()
    b.resize(1200, 40)
    b.show()
    app.processEvents()
    yield b
    b.deleteLater()


def test_le_bouton_est_cache_tant_qu_on_ne_le_demande_pas(barre):
    assert not barre._replate_btn.isVisible()


def test_set_replate_affiche_et_masque(barre, app):
    barre.set_replate("RANGER SUR 3 PLATEAUX", "infobulle")
    app.processEvents()
    assert barre._replate_btn.isVisible()
    assert barre._replate_btn.text() == "RANGER SUR 3 PLATEAUX"
    barre.set_replate("")
    app.processEvents()
    assert not barre._replate_btn.isVisible()


def test_le_clic_remonte_a_la_fenetre(barre):
    recus = []
    barre.replate_clicked.connect(lambda: recus.append(1))
    barre.set_replate("RANGER SUR 2 PLATEAUX")
    barre._replate_btn.click()
    assert recus == [1]


def test_rien_d_exportable_rien_a_ranger(barre, app):
    """Le bouton ne doit pas survivre au chargement d'un autre fichier."""
    barre.set_replate("RANGER SUR 3 PLATEAUX")
    barre.set_export_enabled(False)
    app.processEvents()
    assert not barre._replate_btn.isVisible()


def test_le_bouton_suit_le_theme(barre):
    """Un bouton créé en sombre reste sombre en clair s'il n'est pas rejoué
    au changement de thème : c'est arrivé assez souvent pour être testé."""
    import re
    from ui.main_window import _THEME
    depart = _THEME.name()
    try:
        barre.set_replate("RANGER SUR 3 PLATEAUX")
        couleurs = {}
        for nom in ("dark", "light"):
            _THEME.switch(nom)
            barre.refresh_theme()
            couleurs[nom] = set(re.findall(r"#[0-9A-Fa-f]{6}",
                                           barre._replate_btn.styleSheet()))
        assert couleurs["dark"] != couleurs["light"], "palette figée"
    finally:
        _THEME.switch(depart)


def test_une_scene_neogen_garde_ses_plateaux_voulus():
    """Une recette neoGen répartit ses corps par le tag plateau() : couvercle
    lithophane d'un côté, boîte de l'autre, chacun son profil. Proposer de les
    réunir défairait un choix délibéré de l'auteur de la recette."""
    f = _fenetre(_projet(6))
    assert f._plan_replateau()[0] is not None          # projet importé : on propose
    f._neogen_multiplate_profils = {"o0": "lithophanie", "o1": "standard"}
    assert f._plan_replateau() == (None, 0)
    f._maj_bouton_replateau()
    assert f._statusbar.replate is None
