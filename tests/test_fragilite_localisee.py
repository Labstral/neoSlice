# -*- coding: utf-8 -*-
"""La fragilité est peinte LÀ OÙ ELLE EST, et le score global ne ment plus.

Emmanuel, 2026-09-29 : « sur le thermomap de fragilité, les couleurs indiquent
la fragilité des pièces mais dans leur globalité, ça n'indique pas à quels
endroits précisément c'est fragile. »

En creusant, un défaut plus grave est apparu. Mesuré avant correction, sur un
bloc de 40x40x10 portant une nervure :

    nervure 0,6 mm  -> sévérité 0,00  VERT   « épaisseur minimale 10,25 mm »
    nervure 1,0 mm  -> sévérité 0,00  VERT   « épaisseur minimale 10,25 mm »
    nervure 1,4 mm  -> sévérité 0,28  jaune
    nervure 2,0 mm  -> sévérité 0,15  vert

C'était inversé : plus la paroi était fine, plus elle échappait au filtre
d'axe médian, donc plus la pièce paraissait solide. La même plaque de 0,6 mm
SEULE sortait pourtant à 0,73. Les zones locales, elles, voyaient très bien la
nervure, mais leur résultat était jeté.

Deux corrections, testées ici :
  1. une pièce vaut au moins sa PIRE zone, et l'épaisseur annoncée en tient
     compte ;
  2. une sévérité par FACE, pour peindre la pièce au bon endroit.
"""
import numpy as np
import pytest
import trimesh

from core.geometry.fragility_detector import detect_fragility


def _bloc_avec_nervure(ep_mm: float) -> trimesh.Trimesh:
    """Un bloc massif portant une paroi fine : le cas qui trompait le moteur."""
    bloc = trimesh.creation.box(extents=(40, 40, 10))
    bloc.apply_translation((0, 0, 5))
    nerv = trimesh.creation.box(extents=(6, ep_mm, 40))
    nerv.apply_translation((15, 0, 30))
    return trimesh.boolean.union([bloc, nerv], engine="manifold")


# ── 1. Le score global ne se laisse plus noyer ─────────────────────────────
@pytest.mark.parametrize("ep", [0.6, 1.0])
def test_une_paroi_fine_sur_un_bloc_massif_alerte(ep):
    """Le cœur du défaut : ces pièces ressortaient VERTES, sévérité 0,00."""
    r = detect_fragility(_bloc_avec_nervure(ep))
    assert r.has_fragile_zones
    assert r.severity > 0.6, f"paroi de {ep} mm annoncée comme solide"


@pytest.mark.parametrize("ep", [0.6, 1.0])
def test_l_epaisseur_annoncee_est_celle_de_la_paroi_fine(ep):
    """Le panneau et le PDF affichent ce chiffre. Il disait 10,25 mm pour une
    pièce qui a une paroi de 0,6 mm."""
    r = detect_fragility(_bloc_avec_nervure(ep))
    assert r.min_thickness_mm < 2.0, f"{r.min_thickness_mm:.2f} mm annoncés"


def test_une_piece_franchement_massive_reste_verte():
    """Le garde-fou de l'autre côté : ne pas crier au loup."""
    r = detect_fragility(_bloc_avec_nervure(3.0))
    assert r.severity < 0.2


def test_plus_la_paroi_est_fine_plus_la_piece_est_alarmante():
    """C'était l'inverse avant : 1,4 mm sortait en jaune et 0,6 mm en vert."""
    fine = detect_fragility(_bloc_avec_nervure(0.6)).severity
    epaisse = detect_fragility(_bloc_avec_nervure(3.0)).severity
    assert fine > epaisse


# ── 2. La carte par face ───────────────────────────────────────────────────
def test_la_carte_est_alignee_sur_les_faces():
    """Le viewer l'injecte dans `cell_data` : un décalage colorierait les
    mauvaises faces, sans que rien ne plante."""
    m = _bloc_avec_nervure(1.0)
    r = detect_fragility(m, avec_faces=True)
    assert r.severites_faces is not None
    assert len(r.severites_faces) == len(m.faces)


def test_la_carte_designe_la_bonne_zone():
    """La nervure est en x > 13, le bloc en x < 5."""
    m = _bloc_avec_nervure(1.0)
    sev = detect_fragility(m, avec_faces=True).severites_faces
    centres = np.asarray(m.triangles_center)
    nervure = centres[:, 0] > 13.0
    bloc = centres[:, 0] < 5.0
    assert sev[nervure].max() > 0.6, "la nervure doit ressortir"
    assert sev[bloc].max() < 0.2, "le bloc massif ne doit pas rougir"


def test_la_carte_accompagne_toujours_la_mesure_au_rayon():
    """Depuis que tout le diagnostic vient du rayon, la carte par face sort du
    MÊME calcul : la produire ne coûte plus rien, on ne la demande donc plus.

    `avec_faces` ne sert plus que pour le repli sur la grille, où le sondage
    face par face est un vrai surcoût."""
    r = detect_fragility(_bloc_avec_nervure(1.0))
    assert r.severites_faces is not None
    assert len(r.severites_faces) == len(_bloc_avec_nervure(1.0).faces)


def test_le_chiffre_et_la_couleur_viennent_de_la_meme_mesure():
    """C'est tout l'objet de la migration : avant, la couleur était mesurée au
    rayon et le chiffre estimé par la grille, donc les deux pouvaient se
    contredire. Ici la sévérité annoncée doit se retrouver dans la carte."""
    m = _bloc_avec_nervure(1.0)
    r = detect_fragility(m, avec_faces=True)
    assert r.severites_faces.max() >= r.severity - 0.05, (
        f"la pièce est annoncée à {r.severity:.2f} mais sa face la plus "
        f"alarmante n'est qu'à {r.severites_faces.max():.2f}")


@pytest.mark.parametrize("epaisseur", [0.6, 1.0, 1.5, 2.5, 4.0])
def test_l_epaisseur_annoncee_est_la_vraie(epaisseur):
    """Le chiffre qui pilote le renfort automatique, le moteur de paramètres,
    le PDF et les réponses d'Oen. La grille annonçait 0,73 de sévérité pour une
    nervure de 2,5 mm, qui vaut en réalité 0,07 : elle la faisait renforcer
    pour rien."""
    r = detect_fragility(_bloc_avec_nervure(epaisseur))
    assert abs(r.min_thickness_mm - epaisseur) < 0.08,         f"{r.min_thickness_mm:.2f} mm annoncés pour {epaisseur} mm"


def test_le_drapeau_et_la_liste_des_zones_disent_la_meme_chose():
    """Une plaque de 1,2 mm annonçait deux zones tout en affirmant n'en avoir
    aucune, et le message « Parois fines » ne s'affichait donc pas."""
    for ep in (0.6, 1.0, 1.2, 1.5, 3.0):
        m = trimesh.creation.box(extents=(60, 60, ep))
        m.apply_translation([0.0, 0.0, ep / 2])
        r = detect_fragility(m)
        if r.fragile_zones:
            assert r.has_fragile_zones, f"{ep} mm : zones listées mais drapeau baissé"


def test_une_esquille_de_triangle_ne_fait_pas_une_piece_fragile():
    """Le minimum ABSOLU des faces vaut 0,00 mm sur un Baby Groot réel, à
    cause de triangles dégénérés. On retient donc la plus mince SURFACE qui
    compte, pas la plus mince facette."""
    m = trimesh.creation.box(extents=(30, 30, 30))
    m.apply_translation([0.0, 0.0, 15.0])
    r = detect_fragility(m)
    assert r.min_thickness_mm > 25.0, f"{r.min_thickness_mm:.2f} mm sur un cube de 30"
    assert not r.has_fragile_zones


def test_la_carte_ne_change_pas_le_score():
    """La demander ne doit RIEN changer au reste du diagnostic."""
    m = _bloc_avec_nervure(1.0)
    sans = detect_fragility(m)
    avec = detect_fragility(m, avec_faces=True)
    assert avec.severity == sans.severity
    assert avec.min_thickness_mm == sans.min_thickness_mm
    assert avec.has_fragile_zones == sans.has_fragile_zones


# ── 3. Aucune fausse alerte sur des pièces saines ──────────────────────────
@pytest.mark.parametrize("nom,forme", [
    ("cube", trimesh.creation.box(extents=(20, 20, 20))),
    ("sphere", trimesh.creation.icosphere(subdivisions=3, radius=15)),
    ("cylindre", trimesh.creation.cylinder(radius=10, height=40)),
    ("tore", trimesh.creation.torus(major_radius=20, minor_radius=6)),
])
def test_une_piece_saine_ne_rougit_nulle_part(nom, forme):
    """Le vrai risque de la carte par face : des arêtes vives ou des faces
    concaves d'où la normale sort de la matière, qui ressortiraient en rouge.
    Les sondes hors matière sont neutralisées, ce test le prouve."""
    m = forme.copy()
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    sev = detect_fragility(m, avec_faces=True).severites_faces
    assert sev is not None, nom
    assert sev.max() < 0.35, f"{nom} : {100 * float((sev > 0.35).mean()):.1f} % de faces rouges"


def test_une_plaque_fine_rougit_PARTOUT():
    """L'inverse du test précédent : quand toute la pièce est fine, toute la
    pièce doit être rouge, pas seulement un bord.

    On compte la SURFACE VUE, pas le nombre de faces. Une plaque est faite de
    deux grandes faces et de quatre tranches minuscules ; les tranches sont
    légitimement vertes, car en les regardant de face on a 60 mm de matière
    derrière. Compter les faces donnait 33 % et ne voulait rien dire : à
    l'écran, la plaque est rouge à 97 %.
    """
    m = trimesh.creation.box(extents=(60, 60, 0.8))
    m.apply_translation([0.0, 0.0, 0.4])
    sev = detect_fragility(m, avec_faces=True).severites_faces
    aires = np.asarray(m.area_faces)
    part_rouge = float(aires[sev > 0.5].sum() / aires.sum())
    assert part_rouge > 0.9, f"{100 * part_rouge:.0f} % de surface rouge"


# ── 4. Le coût, parce que la thermomap a déjà gelé l'application ──────────
def test_la_carte_ne_coute_presque_rien():
    """Elle réutilise le champ de distance déjà calculé. Si quelqu'un la
    refactorise en voxelisant une seconde fois, ce test le verra."""
    import time
    m = _bloc_avec_nervure(1.0)
    detect_fragility(m)                      # chauffe
    t0 = time.perf_counter(); detect_fragility(m); sans = time.perf_counter() - t0
    t0 = time.perf_counter(); detect_fragility(m, avec_faces=True)
    avec = time.perf_counter() - t0
    assert avec < sans * 1.6, f"{sans * 1000:.0f} ms -> {avec * 1000:.0f} ms"


# ── 5. Le raccourci « structure fine » ne se déclenche plus sur un maillage
#       simplement dense ────────────────────────────────────────────────────
def _dense_mais_massif():
    """Une pièce épaisse au maillage très fin : c'est le cas qui trompait le
    raccourci. Une sphère subdivisée a des milliers de micro-triangles et
    pourtant 30 mm de matière au centre."""
    m = trimesh.creation.icosphere(subdivisions=5, radius=15)
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    return m


def test_un_maillage_dense_mais_massif_ne_declenche_pas_le_raccourci():
    """Le défaut vu par Emmanuel sur un Baby Groot de 490 000 faces : aire
    moyenne par face 0,071 mm², donc sous le seuil, donc sévérité 0,89 rendue
    en 0 ms et pièce entièrement orange. La pièce faisait pourtant 12,8 mm
    d'épaisseur moyenne."""
    m = _dense_mais_massif()
    aire_moy = float(m.area) / len(m.faces)
    assert aire_moy < 0.64, "témoin : le raccourci DOIT être tenté ici"

    r = detect_fragility(m, avec_faces=True)
    assert r.severity < 0.2, f"pièce massive annoncée fragile ({r.severity:.2f})"
    assert r.severites_faces is not None, \
        "le raccourci a coupé court, aucune carte produite"


def test_le_raccourci_repond_toujours_present_sur_une_vraie_structure_fine():
    """Il ne faut pas jeter le bébé : une coque très mince au maillage dense
    doit rester détectée, et vite."""
    ext = trimesh.creation.icosphere(subdivisions=4, radius=20)
    coque = ext.copy()
    coque.vertices *= 0.97          # paroi d'environ 0,6 mm
    m = trimesh.util.concatenate([ext, coque])
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    r = detect_fragility(m)
    assert r.severity > 0.5, f"coque mince annoncée solide ({r.severity:.2f})"


def test_le_veto_ne_se_fie_pas_a_un_volume_absurde():
    """Un maillage ouvert peut donner un volume faux. Le garde-fou : une
    épaisseur moyenne supérieure à la plus petite dimension de la pièce n'a
    aucun sens, on ne s'en sert pas."""
    plaque = trimesh.creation.box(extents=(60, 60, 0.8))
    plaque.apply_translation([0.0, 0.0, 0.4])
    ouverte = plaque.submesh([np.arange(len(plaque.faces) - 2)], append=True)
    r = detect_fragility(ouverte)
    assert r.severity > 0.4, "une plaque de 0,8 mm reste fragile, ouverte ou non"


# ── 6. Une même surface, une même couleur ─────────────────────────────────
"""Emmanuel, 2026-09-29, après deux tentatives ratées de ma part : « sur une
même surface lisse on a un triangle jaune et une partie verte, ce n'est pas
normal, il faut choisir une couleur unie ».

Un grand panneau plat n'est souvent fait que de deux triangles, et il suffit
que leurs points de sonde tombent à des endroits légèrement différents pour
que la surface se retrouve coupée en deux tons.

Ma PREMIÈRE tentative moyennait aux sommets : elle a empiré les choses, parce
qu'un sommet appartient à plusieurs surfaces et que le coin d'un panneau
héritait de la fragilité des nervures. La bonne réponse ne franchit jamais une
arête vive.
"""


def _etagere():
    """Panneau plat, tablette et nervures : la pièce d'Emmanuel."""
    morceaux = [trimesh.creation.box(extents=(200, 3.0, 70)),
                trimesh.creation.box(extents=(200, 60, 3.0))]
    morceaux[0].apply_translation((0, 1.5, 35))
    morceaux[1].apply_translation((0, 30, 1.5))
    # Nervures de 1,0 mm : à 2,5 mm elles ne sont PAS fragiles, et le
    # détecteur a raison de les dire vertes depuis qu'il mesure juste
    # (2,5 mm donnent 0,07 de sévérité, valeur théorique 0,074).
    for x in (-90, -30, 30, 90):
        n = trimesh.creation.box(extents=(1.0, 56, 60))
        n.apply_translation((x, 31, 31))
        morceaux.append(n)
    return trimesh.boolean.union(morceaux, engine="manifold")


def _ecart_dans_les_surfaces_planes(mesh, sev, degres=2.0):
    """Le pire écart entre deux faces COPLANAIRES voisines. C'est exactement
    ce qu'Emmanuel voit : deux tons sur une surface qui n'en mérite qu'un."""
    paires = np.asarray(mesh.face_adjacency)
    angles = np.asarray(mesh.face_adjacency_angles)
    plat = angles < np.radians(degres)
    if not plat.any():
        return 0.0
    return float(np.abs(sev[paires[plat, 0]] - sev[paires[plat, 1]]).max())


def test_une_surface_plane_est_strictement_d_un_seul_ton():
    m = _etagere()
    sev = detect_fragility(m, avec_faces=True).severites_faces
    assert _ecart_dans_les_surfaces_planes(m, sev) == 0.0


@pytest.mark.parametrize("nom,forme", [
    ("cube", trimesh.creation.box(extents=(20, 20, 20))),
    ("cylindre", trimesh.creation.cylinder(radius=10, height=40)),
    ("plaque", trimesh.creation.box(extents=(60, 60, 0.8))),
])
def test_aucune_surface_plane_ne_reste_bicolore(nom, forme):
    m = forme.copy()
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    sev = detect_fragility(m, avec_faces=True).severites_faces
    assert _ecart_dans_les_surfaces_planes(m, sev) == 0.0, nom


def test_les_nervures_fines_restent_alarmantes():
    """L'unification ne doit pas noyer ce qui est vraiment fragile."""
    m = _etagere()
    sev = detect_fragility(m, avec_faces=True).severites_faces
    centres = np.asarray(m.triangles_center)
    assert sev[np.abs(centres[:, 0]) > 25].max() > 0.6


def test_le_lissage_ne_franchit_pas_une_arete_vive():
    """Le défaut de ma première tentative : le panneau prenait la couleur des
    nervures. Ici le panneau doit rester franchement plus vert qu'elles."""
    m = _etagere()
    sev = detect_fragility(m, avec_faces=True).severites_faces
    c = np.asarray(m.triangles_center)
    panneau = (c[:, 1] < 0.4) & (np.abs(c[:, 0]) < 95) & (c[:, 2] > 8)
    nervures = np.abs(c[:, 0]) > 25
    assert sev[panneau].max() < 0.3, "le panneau ne doit pas être contaminé"
    assert sev[nervures].max() - sev[panneau].max() > 0.3


def test_le_pic_de_fragilite_survit_a_l_unification():
    """Mesuré sur un Baby Groot réel de 490 000 faces : pic à 0,90 avant comme
    après, faces rouges 2,31 % puis 1,97 %."""
    m = trimesh.creation.box(extents=(60, 60, 0.8))
    m.apply_translation([0.0, 0.0, 0.4])
    sev = detect_fragility(m, avec_faces=True).severites_faces
    # 0,77 est la valeur EXACTE pour 0,8 mm d'après la calibration du
    # détecteur. L'ancienne attente de 0,8 venait de la mesure par grille, qui
    # lisait 0,5 mm au lieu de 0,8 et sur-alarmait donc.
    assert sev.max() > 0.70
    aires = np.asarray(m.area_faces)
    assert float(aires[sev > 0.5].sum() / aires.sum()) > 0.9


def test_l_unification_ne_coute_presque_rien():
    """Elle s'ajoute au calcul le plus cher de l'application. Mesuré sur un
    Baby Groot : 6,3 s avant, 6,1 s après, donc dans le bruit."""
    import time
    m = _etagere()
    detect_fragility(m, avec_faces=True)
    t0 = time.perf_counter(); detect_fragility(m); sans = time.perf_counter() - t0
    t0 = time.perf_counter(); detect_fragility(m, avec_faces=True)
    avec = time.perf_counter() - t0
    assert avec < sans * 1.8, f"{sans * 1000:.0f} ms -> {avec * 1000:.0f} ms"


# ── 7. La mesure par RAYON : exacte, et identique sur des pièces identiques ─
"""Emmanuel, 2026-09-29 : « les fils dans la main sont censés être tous
rouges, or on en voit des jaunes et même des verts, c'est insensé car ils ont
tous le même diamètre ».

La mesure par grille de voxels est biaisée sur les sections RONDES et FINES, et
le biais dépend de l'orientation par rapport à la grille. Éliminé, mesures à
l'appui : ce n'était ni le lissage (la mesure brute était aussi dispersée), ni
la finesse de la grille (testée de 0,80 à 0,30 mm, même écart), ni la règle de
combinaison des sondes, ni l'absence d'unification par surface.

La réponse est de MESURER au lieu d'estimer : un rayon perpendiculaire depuis
chaque face jusqu'à la paroi opposée. Exact, et 7 fois plus rapide.
"""


def _epaisseur_mesuree(mesh, selection=None):
    from core.geometry.fragility_detector import _epaisseur_par_rayon
    ep = _epaisseur_par_rayon(mesh)
    if ep is None:
        pytest.skip("embreex absent : mesure par rayon indisponible")
    return ep if selection is None else ep[selection]


@pytest.mark.parametrize("epaisseur", [0.6, 0.8, 1.2, 2.0, 3.0, 8.0])
def test_une_plaque_est_mesuree_au_centieme(epaisseur):
    """La grille se trompait de 40 % sur les parois fines."""
    p = trimesh.creation.box(extents=(60, 60, epaisseur))
    p.apply_translation([0.0, 0.0, epaisseur / 2])
    dessus = np.asarray(p.triangles_center)[:, 2] > epaisseur * 0.9
    mesure = float(np.median(_epaisseur_mesuree(p, dessus)))
    assert abs(mesure - epaisseur) < 0.02, f"{mesure:.2f} au lieu de {epaisseur}"


@pytest.mark.parametrize("diametre", [0.8, 1.2, 2.0, 3.0, 6.0])
def test_un_fil_rond_est_mesure_au_centieme(diametre):
    """C'est exactement le cas qui clochait : la grille rendait 1,2 mm pour un
    fil de 2,0 mm, et pas la même valeur selon son orientation."""
    fil = trimesh.creation.cylinder(radius=diametre / 2, height=40, sections=24)
    fil.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0)))
    fil.apply_translation([0.0, 0.0, diametre])
    lateral = np.abs(np.asarray(fil.face_normals)[:, 1]) < 0.5
    mesure = float(np.median(_epaisseur_mesuree(fil, lateral)))
    assert abs(mesure - diametre) < 0.06, f"{mesure:.2f} au lieu de {diametre}"


@pytest.mark.parametrize("diametre", [1.0, 2.0, 3.0])
def test_toutes_les_faces_d_un_fil_ont_LA_MEME_valeur(diametre):
    """Le cœur de sa remarque. Mesuré : écart 0,000 entre les faces d'un fil."""
    fil = trimesh.creation.cylinder(radius=diametre / 2, height=40, sections=24)
    fil.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0)))
    fil.apply_translation([0.0, 0.0, diametre])
    lateral = np.abs(np.asarray(fil.face_normals)[:, 1]) < 0.5
    ep = _epaisseur_mesuree(fil, lateral)
    assert float(ep.max() - ep.min()) < 0.01, f"écart {ep.max() - ep.min():.3f} mm"


def test_deux_fils_identiques_mais_orientes_autrement_se_valent():
    """Le biais de la grille dépendait de l'orientation : un fil aligné sur un
    axe et un fil en biais ne se mesuraient pas pareil."""
    def fil(axe):
        c = trimesh.creation.cylinder(radius=0.75, height=40, sections=24)
        c.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], axe))
        c.apply_translation([0.0, 0.0, 30.0])
        return c
    droit = fil([0.0, 0.0, 1.0])
    biais = fil([1.0, 1.0, 1.0])
    a = float(np.median(_epaisseur_mesuree(droit)))
    b = float(np.median(_epaisseur_mesuree(biais)))
    assert abs(a - b) < 0.05, f"{a:.2f} contre {b:.2f}"


def test_la_mesure_par_rayon_est_plus_rapide_que_la_grille():
    """Mesuré sur un Baby Groot de 490 000 faces : 0,83 s contre 6,1 s. Si
    quelqu'un retire embreex, ce test le dira."""
    from core.geometry.fragility_detector import _epaisseur_par_rayon
    m = trimesh.creation.icosphere(subdivisions=4, radius=20)
    assert _epaisseur_par_rayon(m) is not None, \
        "embreex doit être installé, il est dans requirements.txt"


def test_sans_le_moteur_accelere_on_retombe_sur_la_grille(monkeypatch):
    """L'application ne doit JAMAIS tomber parce qu'une dépendance manque :
    sans embreex, la mesure par grille reprend la main, moins juste mais
    toujours là."""
    import trimesh.ray as _tr
    from core.geometry import fragility_detector as FD
    monkeypatch.setattr(_tr, "has_embree", False, raising=False)
    m = trimesh.creation.box(extents=(60, 60, 0.8))
    m.apply_translation([0.0, 0.0, 0.4])
    assert FD._epaisseur_par_rayon(m) is None
    sev = FD.detect_fragility(m, avec_faces=True).severites_faces
    assert sev is not None and len(sev) == len(m.faces)
    assert sev.max() > 0.5, "la grille doit continuer de voir une plaque fine"


def test_l_absence_du_moteur_de_rayon_est_DITE_dans_le_journal(monkeypatch, caplog):
    """Le 2026-09-29, embreex avait été installé dans l'environnement de BUILD
    mais pas dans celui qui lance l'application, et rien ne le signalait.
    Emmanuel a simplement constaté que « ça ne change rien ». Il faut que le
    journal le dise."""
    import logging
    import trimesh.ray as _tr
    from core.geometry import fragility_detector as FD
    monkeypatch.setattr(_tr, "has_embree", False, raising=False)
    monkeypatch.setattr(FD, "_SANS_EMBREE_DIT", False, raising=False)
    messages = []
    poignee = FD.logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        FD._epaisseur_par_rayon(trimesh.creation.box(extents=(10, 10, 10)))
    finally:
        FD.logger.remove(poignee)
    assert any("embreex" in m for m in messages), messages


def test_l_avertissement_ne_se_repete_pas_a_chaque_piece():
    """Un plateau de 38 pièces ne doit pas noyer le journal."""
    from core.geometry import fragility_detector as FD
    assert hasattr(FD, "_SANS_EMBREE_DIT")
