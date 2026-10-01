# -*- coding: utf-8 -*-
"""La série sur un projet qui contient PLUSIEURS objets différents.

Emmanuel, 2026-10-01 : « comment faire pour que le nombre de série fonctionne
avec plusieurs objets différents dans un 3mf ? car actuellement si je change
la valeur et que je clique sur ok rien ne se passe. Si j'isole un objet et que
j'augmente la valeur, j'en vois bien plusieurs qui se créent, seulement quand
je reviens à la vue d'ensemble ils disparaissent. »

Modèle retenu avec lui : DEUX compteurs qui se multiplient.
  * `_serie_objet[oid]` — combien d'exemplaires de CETTE pièce là, réglé quand
    elle est isolée, mémorisé comme ses autres réglages ;
  * `_serie_globale`    — combien de fois le JEU complet, réglé depuis la vue
    d'ensemble.
Total d'une pièce = son compteur × le compteur global.

⚠ Deux nombres séparés, surtout pas une multiplication en place : remettre la
vue d'ensemble à ×1 doit redonner exactement les compteurs par objet. Une
multiplication cumulative serait impossible à défaire au clic suivant.

⚠ Un projet à modificateurs ou multi-couleurs n'est PAS reconstruit : y ajouter
des exemplaires lui ferait perdre la structure qui fait sa valeur. On le dit.
"""
import os

import numpy as np
import pytest
import trimesh

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.geometry.threemf_data import MeshObject, ThreeMFData   # noqa: E402

NEPTUNE = "Elegoo Neptune 4 Max"
NOMS = ("Support", "Couvercle", "Entretoise")


class _Viewer:
    def __init__(self):
        self.recu = None

    def load_mesh(self, m):
        self.recu = m


class _Barre:
    def __init__(self, n=1):
        self.n = n
        self.messages = []
        self.pose = None

    def serie_count(self):
        return self.n

    def set_message(self, texte, couleur=None):
        self.messages.append(texte)

    def set_serie(self, n):
        self.pose = n

    def set_replate(self, texte, infobulle=""):
        pass


def _projet(cote=50.0, **drapeaux):
    objets = []
    for i, nom in enumerate(NOMS):
        m = trimesh.creation.box((cote, cote, 15.0))
        tr = np.eye(4)
        tr[0, 3] = i * 200.0
        objets.append(MeshObject(object_id=f"o{i}", name=nom, extruder=1,
                                 mesh=m, transform=tr, plate_index=i))
    return ThreeMFData(
        combined_mesh=trimesh.util.concatenate([o.mesh for o in objets]),
        objects=objets, source_path=None, plate_count=len(objets), **drapeaux)


def _fenetre(td, imprimante=NEPTUNE, isole=None):
    from ui.main_window import MainWindow

    class _Faux:
        pass

    for nom in ("_apercu_serie", "_objets_serie", "_td_serie", "_serie_active",
                "_compte_serie", "_projet_structure", "_object_mesh_sur_plateau",
                "_empreintes_projet", "_plan_replateau", "_maj_bouton_replateau"):
        setattr(_Faux, nom, getattr(MainWindow, nom))

    f = _Faux()
    f._threemf_data = td
    f._mesh = td.combined_mesh if td is not None else None
    f._stl_path = None
    f._current_printer = imprimante
    f._viewer = _Viewer()
    f._statusbar = _Barre()
    f._active_object_id = isole
    f._serie_objet = {}
    f._serie_globale = 1
    f._neogen_multiplate_profils = None
    return f


def _compter(vue):
    return {n: sum(1 for o in vue.objects if o.name.startswith(n)) for n in NOMS}


# ── Les deux compteurs ────────────────────────────────────────────────────
def test_le_total_est_le_produit_des_deux_compteurs():
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 3, "o2": 6}
    f._serie_globale = 2
    assert f._compte_serie("o0") == 6
    assert f._compte_serie("o1") == 2       # pas de compteur propre → global seul
    assert f._compte_serie("o2") == 12


def test_sans_rien_demander_la_serie_est_inactive():
    f = _fenetre(_projet())
    assert f._serie_active() is False
    f._serie_objet = {"o1": 2}
    assert f._serie_active() is True


# ── La vue d'ensemble montre le total ─────────────────────────────────────
def test_les_compteurs_par_objet_apparaissent_en_vue_d_ensemble():
    """Le reproche exact : les exemplaires réglés sur un objet isolé
    disparaissaient dès qu'on revenait à l'ensemble."""
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 3, "o2": 6}
    f._statusbar.n = 1
    f._apercu_serie()
    vue = f._viewer.recu
    assert isinstance(vue, ThreeMFData)
    assert len(vue.objects) == 10
    assert _compter(vue) == {"Support": 3, "Couvercle": 1, "Entretoise": 6}


def test_le_compteur_de_la_vue_d_ensemble_multiplie_le_jeu_complet():
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 3, "o2": 6}
    f._statusbar.n = 2
    f._apercu_serie()
    assert _compter(f._viewer.recu) == {"Support": 6, "Couvercle": 2, "Entretoise": 12}


def test_revenir_a_un_rend_exactement_les_compteurs_par_objet():
    """L'invariant qui a dicté le modèle : deux nombres séparés plutôt qu'une
    multiplication en place, sinon ×2 puis ×1 laisserait le double."""
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 3, "o2": 6}
    f._statusbar.n = 1
    f._apercu_serie()
    depart = _compter(f._viewer.recu)
    f._statusbar.n = 4
    f._apercu_serie()
    f._statusbar.n = 1
    f._apercu_serie()
    assert _compter(f._viewer.recu) == depart
    assert f._serie_objet == {"o0": 3, "o2": 6}


def test_un_objet_isole_memorise_son_compteur():
    f = _fenetre(_projet(), isole="o1")
    f._statusbar.n = 5
    f._apercu_serie()
    assert f._serie_objet["o1"] == 5


# ── Le rangement sur les plateaux ─────────────────────────────────────────
def test_les_exemplaires_sont_ranges_sans_se_chevaucher():
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 8, "o1": 8, "o2": 8}
    f._statusbar.n = 1
    f._apercu_serie()
    par = {}
    for o in f._viewer.recu.objects:
        lo, hi = o.mesh.bounds
        par.setdefault(o.plate_index, []).append(
            (o.object_id, lo[0], lo[1], hi[0], hi[1]))
    for plateau, rects in par.items():
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                assert not (a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6
                            and a[2] < b[4] - 1e-6 and b[2] < a[4] - 1e-6), \
                    f"plateau {plateau} : {a[0]} chevauche {b[0]}"


def test_la_serie_deborde_sur_plusieurs_plateaux_quand_il_faut():
    grand = _fenetre(_projet(cote=120.0))
    grand._serie_objet = {"o0": 10, "o1": 10, "o2": 10}
    grand._statusbar.n = 1
    grand._apercu_serie()
    assert len({o.plate_index for o in grand._viewer.recu.objects}) > 1


def test_la_vue_developpee_ne_doit_pas_etre_recompactee():
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 4}
    f._statusbar.n = 1
    f._apercu_serie()
    assert f._viewer.recu.reagence is True


# ── Retrouver les réglages de la pièce d'origine ──────────────────────────
def test_chaque_exemplaire_sait_de_quelle_piece_il_vient():
    """L'export donne à chaque copie les réglages de SA pièce d'origine."""
    f = _fenetre(_projet())
    f._serie_objet = {"o0": 3}
    objets, bases, _plan = f._objets_serie(f._threemf_data)
    assert len(objets) == 5
    assert sum(1 for o in objets if bases[o.object_id] == "o0") == 3
    assert len({o.object_id for o in objets}) == 5, "identifiants en double"


# ── Les projets qu'on ne touche pas ───────────────────────────────────────
def test_un_projet_multicouleur_refuse_la_serie():
    """Le reconstruire lui ferait perdre ses slots de couleur."""
    td = _projet()
    td.objects[1].extruder = 2                 # deux slots → multicolore
    f = _fenetre(td)
    assert f._projet_structure() is True
    f._statusbar.n = 4
    f._apercu_serie()
    assert f._viewer.recu is None
    assert f._statusbar.messages, "il faut le dire, pas l'ignorer"


def test_un_projet_a_modificateurs_refuse_la_serie():
    td = _projet()
    td.modifier_meshes = [td.objects[0]]
    f = _fenetre(td)
    assert f._projet_structure() is True
    f._statusbar.n = 3
    f._apercu_serie()
    assert f._viewer.recu is None


def test_un_projet_simple_de_trois_pieces_est_accepte():
    f = _fenetre(_projet())
    assert f._projet_structure() is False
