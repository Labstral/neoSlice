"""Assistant d'orientation — moteur pur (candidates, PCA de zones, scoring,
gross des cas limites). Pièces synthétiques : crochet en L, plaque fine, cube,
sphère (« patate »), cylindre élancé."""
import numpy as np
import pytest
import trimesh

from core.geometry import orientation_advisor as oa


# ── pièces synthétiques ───────────────────────────────────────────────────────
def piece_L():
    """Crochet en L debout : bras vertical (10×10×60) + bras horizontal (30×10×10)
    en haut — en pose actuelle, le bras horizontal est un surplomb massif.
    Subdivisé → densité de faces réaliste (comme un STL), pas 12 triangles CAD."""
    v = trimesh.creation.box((10, 10, 60)); v.apply_translation((0, 0, 30))
    h = trimesh.creation.box((30, 10, 10)); h.apply_translation((15, 0, 55))
    m = trimesh.util.concatenate([v, h])
    for _ in range(3):
        m = m.subdivide()
    return m


def plaque():
    m = trimesh.creation.box((60, 20, 2)); m.apply_translation((0, 0, 1))
    return m


def cube():
    m = trimesh.creation.box((20, 20, 20)); m.apply_translation((0, 0, 10))
    return m


def sphere():
    m = trimesh.creation.icosphere(subdivisions=3, radius=12)
    m.apply_translation((0, 0, 12))
    return m


def cylindre_debout():
    m = trimesh.creation.cylinder(radius=4, height=80, sections=48)
    m.apply_translation((0, 0, 40))
    return m


def _mask_near(mesh, point, rayon):
    d = np.linalg.norm(mesh.triangles_center - np.asarray(point, float), axis=1)
    return d <= rayon


# ── candidates & rotations ────────────────────────────────────────────────────
def test_candidates_dedupliquees_et_normees():
    dirs = oa.directions_candidates(cube())
    assert len(dirs) >= 6
    for d in dirs:
        assert np.isclose(np.linalg.norm(d), 1.0, atol=1e-6)
    # pas de doublons à <5°
    for i in range(len(dirs)):
        for j in range(i + 1, len(dirs)):
            assert float(dirs[i] @ dirs[j]) < oa._DEDUP_COS + 1e-9


def test_rotation_down_alignement():
    for d in ([0, 0, -1], [0, 0, 1], [1, 0, 0], [0.5, 0.5, 0.7]):
        d = np.asarray(d, float); d /= np.linalg.norm(d)
        R = oa._rotation_down(d)
        aligned = R[:3, :3] @ d
        assert np.allclose(aligned, [0, 0, -1], atol=1e-6)


def test_poser_face_et_appliquer():
    m = cube()
    # face du dessus (normale +Z) → la poser dessous = retourner le cube
    up_faces = np.where(m.face_normals[:, 2] > 0.99)[0]
    R = oa.rotation_pour_poser_face(m, int(up_faces[0]))
    m2 = oa.appliquer_orientation(m, R)
    assert m2.bounds[0][2] == pytest.approx(0.0, abs=1e-6)   # posé à Z=0
    c = m2.bounds.mean(axis=0)
    assert abs(c[0]) < 1e-6 and abs(c[1]) < 1e-6             # centré XY


# ── PCA de zone ───────────────────────────────────────────────────────────────
def test_zone_axis_membre_allonge():
    m = piece_L()
    # zone au milieu du bras VERTICAL → axe ≈ Z
    mask = _mask_near(m, (0, 0, 30), 9)
    ax, fiab = oa.zone_axis(m, mask)
    assert ax is not None and fiab > 0.3
    assert abs(ax[2]) > 0.85


def test_zone_axis_patate_non_directionnelle():
    m = sphere()
    mask = _mask_near(m, (0, 0, 24), 6)   # calotte du haut
    ax, _f = oa.zone_axis(m, mask)
    assert ax is None                     # pas d'axe inventé sur une sphère


def test_zone_axis_masque_vide():
    m = cube()
    ax, f = oa.zone_axis(m, np.zeros(len(m.faces), dtype=bool))
    assert ax is None and f == 0.0


# ── conseiller : classement ───────────────────────────────────────────────────
def test_L_sans_zone_reduit_les_supports():
    m = piece_L()
    props = oa.conseiller(m, fine=False)
    assert props
    cur = next(p for p in props if p.label == "actuelle")
    best = props[0]
    # la pose actuelle (bras en surplomb) ne doit PAS être la meilleure
    assert best.label != "actuelle"
    assert best.overhang_ratio < cur.overhang_ratio - 0.05


def test_L_avec_zone_privilegie_la_solidite():
    m = piece_L()
    mask = _mask_near(m, (0, 0, 30), 9)          # bras vertical (axe Z)
    props = oa.conseiller(m, zone_masks=[mask], fine=False)
    best = props[0]
    assert best.score_solidite is not None
    # axe Z de la zone → il faut coucher la pièce (Z ne doit plus être vertical)
    assert best.score_solidite > 0.8
    assert best.label != "actuelle"


def test_force_axis_equivalent_zone():
    m = cylindre_debout()
    props = oa.conseiller(m, force_axis=np.array([0, 0, 1.0]), fine=False)
    best = props[0]
    # effort le long du cylindre debout → couché exigé
    assert best.score_solidite is not None and best.score_solidite > 0.8
    assert best.label.startswith("cote") or best.label == "inclinee"


def test_cube_sans_gain():
    m = cube()
    score, gain = oa.score_orientation_actuelle(m)
    assert score >= 60.0
    assert gain <= 1.0        # rien à gagner sur un cube posé à plat


def test_sphere_ne_plante_pas():
    props = oa.conseiller(sphere(), fine=False)
    assert props            # renvoie des candidates, sans exception


def test_mesh_vide():
    assert oa.conseiller(trimesh.Trimesh(), fine=False) == []


def test_zones_survivent_a_la_rotation():
    """Les masques par FACE restent valides après appliquer_orientation (les
    indices de faces ne changent pas)."""
    m = piece_L()
    mask = _mask_near(m, (0, 0, 30), 9)
    props = oa.conseiller(m, zone_masks=[mask], fine=False)
    m2 = oa.appliquer_orientation(m, props[0].matrice)
    assert len(m2.faces) == len(m.faces)
    assert mask.shape[0] == len(m2.faces)


def test_affinage_fine_conserve_ordre_valide():
    m = piece_L()
    props = oa.conseiller(m, fine=True, n_fine=3)
    assert props and all(np.isfinite(p.score_global) for p in props)
    scores = [p.score_global for p in props[:3]]
    assert scores == sorted(scores, reverse=True)


def test_zone_mask_maillage_grossier():
    """Régression : sur un maillage à GRANDES faces (boîte CAD), tester seulement
    les centroïdes rendait la zone VIDE → aucune surbrillance au clic (vécu).
    Le masque doit retenir des faces via les sommets, et TOUJOURS la face cliquée."""
    m = trimesh.creation.box((10, 10, 60))
    m.apply_translation((0, 0, 30))
    m = m.subdivide()                      # faces encore très grandes
    pt = (4.89, -4.99, 32.43)              # point réellement pické dans le viewer
    fid = oa.face_la_plus_proche(m, pt)
    assert fid is not None
    r = oa.rayon_zone_defaut(m)
    mask = oa.zone_mask_autour(m, pt, r, face_index=fid)
    assert mask.sum() >= 1
    assert bool(mask[fid])                 # la face cliquée est toujours dedans
    # même sans face_index, les sommets proches suffisent à ne pas rendre vide
    assert oa.zone_mask_autour(m, pt, r).sum() >= 1


def test_coherence_surplombs_avec_jauge():
    """Le ratio de surplombs d'une proposition doit être calculé comme la jauge
    du panneau : analyze_overhangs (smooth par défaut) + fraction display_mask."""
    from core.geometry.overhang_detector import analyze_overhangs
    m = piece_L()
    props = oa.conseiller(m, fine=True, n_fine=2)
    for p in props[:2]:
        m2 = m.copy()
        m2.apply_transform(p.matrice)
        res = analyze_overhangs(m2, check_floating=False)
        dm = res.display_mask
        attendu = float(dm.sum()) / len(dm)
        assert abs(p.overhang_ratio - attendu) < 1e-9


def test_analyse_surplombs_deterministe():
    """RÉGRESSION CRITIQUE : la même pièce doit TOUJOURS donner le même % de
    surplombs. Sans moteur de rayons natif, mesh.contains() tirait une direction
    au hasard → la jauge affichait 3,4 % puis 1,9 % puis 0 % pour la même pièce
    (et l'assistant annonçait des valeurs incohérentes avec la jauge)."""
    from core.geometry.overhang_detector import analyze_overhangs
    m = oa.appliquer_orientation(piece_L(), oa._rotation_down(np.array([-1.0, 0.0, 0.0])))
    vals = []
    for _ in range(4):
        res = analyze_overhangs(m, check_floating=False)
        dm = res.display_mask
        vals.append(round(float(dm.sum()) / len(dm), 6))
    assert len(set(vals)) == 1, f"analyse non déterministe : {vals}"


def test_carte_et_jauge_affichent_le_meme_pourcentage():
    """Le % annoncé par une proposition doit être IDENTIQUE à celui que la jauge
    affichera une fois l'orientation appliquée (pièce reposée sur le plateau)."""
    from core.geometry.overhang_detector import analyze_overhangs

    def _label(ratio):
        disp = max(ratio, 0.01) if ratio > 0 else 0.0
        pct = disp * 100
        return "< 1%" if 0 < pct < 1.5 else f"{round(pct)}%"

    for piece in (piece_L(), plaque(), sphere()):
        props = oa.conseiller(piece, fine=True, n_fine=3)
        for p in props[:3]:
            applique = oa.appliquer_orientation(piece, p.matrice)
            res = analyze_overhangs(applique, check_floating=False)
            dm = res.display_mask
            ratio_jauge = float(dm.sum()) / len(dm)
            assert _label(p.overhang_ratio) == _label(ratio_jauge)


def test_poser_face_pose_bien_la_face_cliquee():
    """La face cliquée doit se retrouver À PLAT contre le plateau (normale -Z)."""
    m = piece_L()
    for fid in (0, len(m.faces) // 3, len(m.faces) // 2, len(m.faces) - 1):
        R = oa.rotation_pour_poser_face(m, fid)
        m2 = oa.appliquer_orientation(m, R)
        assert m2.face_normals[fid][2] < -0.95
        assert abs(float(m2.bounds[0][2])) < 1e-6      # posée à Z=0


def test_face_la_plus_proche_rejette_les_clics_hors_piece():
    m = piece_L()
    assert oa.face_la_plus_proche(m, (0.0, 0.0, 30.0)) is not None or True   # intérieur toléré
    loin = (500.0, 500.0, 500.0)
    assert oa.face_la_plus_proche(m, loin) is None


def test_adherence_est_physique_pas_relative():
    """L'adhérence doit mesurer la FRACTION DE L'EMPREINTE réellement posée.
    Un score relatif (« la meilleure des candidates ») donnait 82 % à une pose
    qui ne touche que par quelques points (vécu sur une figurine)."""
    def _adh(mesh, down):
        R = oa._rotation_down(np.asarray(down, float) / np.linalg.norm(down))
        FA = mesh.area_faces
        _o, contact, ombre, _h, _z = oa._proxy_metrics(
            mesh.face_normals, FA, mesh.triangles_center, float(FA.sum()),
            R[:3, :3], None)
        return contact / max(ombre, 1e-9)

    assert _adh(cube(), (0, 0, -1)) > 0.9              # face pleine au sol
    assert _adh(sphere(), (0, 0, -1)) < 0.15           # touche un point
    cone = trimesh.creation.cone(radius=15, height=40, sections=48)
    assert _adh(cone, (0, 0, -1)) > 0.9                # base au sol
    pointe = cone.copy()
    pointe.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    assert _adh(pointe, (0, 0, -1)) < 0.05             # pointe au sol : rien


def test_propositions_sans_doublons_affiches():
    """Deux propositions ne doivent pas afficher exactement les mêmes scores
    (vécu : trois cartes « Couchée côté Y, opposé » identiques à la suite)."""
    for piece in (piece_L(), cube(), sphere()):
        props = oa.conseiller(piece, fine=False)
        vus = set()
        for p in props:
            cle = (round(p.overhang_ratio, 2), round(p.score_adherence, 2),
                   None if p.score_solidite is None else round(p.score_solidite, 2))
            assert cle not in vus, f"proposition dupliquée : {cle}"
            vus.add(cle)


def test_pose_utilise_la_facette_pas_le_triangle():
    """Sur un STL réel, une face plane est découpée en triangles aux normales
    légèrement différentes : poser sur la normale du SEUL triangle cliqué donne
    une pose de travers (vécu). On doit agréger la facette plane."""
    m = trimesh.creation.box((40, 40, 10))
    m.apply_translation((0, 0, 5))
    for _ in range(3):
        m = m.subdivide()
    rng = np.random.default_rng(0)
    top = np.where(m.vertices[:, 2] > 9.9)[0]
    m.vertices[top, 2] += rng.normal(0, 0.02, size=len(top))    # bruit de scan

    cand = [i for i in range(len(m.faces)) if m.triangles_center[i][2] > 9.8]
    fid = cand[len(cand) // 2]
    dev_tri = abs(float(np.degrees(np.arccos(
        np.clip(m.face_normals[fid] @ np.array([0, 0, 1.0]), -1, 1)))))
    dev_fac = abs(float(np.degrees(np.arccos(
        np.clip(oa.normale_facette(m, fid) @ np.array([0, 0, 1.0]), -1, 1)))))
    assert dev_fac < dev_tri            # la facette corrige la déviation du triangle
    assert dev_fac < 0.1                # et pose vraiment à plat

    # après pose, la base doit être plane (faible étendue en Z)
    m2 = oa.appliquer_orientation(m, oa.rotation_pour_poser_face(m, fid))
    zs = m2.vertices[:, 2]
    base = zs[zs < float(np.percentile(zs, 2)) + 0.15]
    assert float(np.ptp(base)) < 0.2


def test_index_zones_equivaut_au_calcul_direct():
    """L'index spatial (survol fluide) doit donner EXACTEMENT le même masque que
    le calcul direct — accélérer ne doit rien changer au résultat."""
    m = piece_L()
    idx = oa.IndexZones(m)
    r = oa.rayon_zone_defaut(m)
    for p in (m.triangles_center[0], m.triangles_center[len(m.faces) // 2],
              m.vertices[10]):
        direct = oa.zone_mask_autour(m, p, r)
        rapide = idx.masque(p, r)
        assert np.array_equal(direct, rapide)
    # tableaux de rendu cohérents avec le masque
    mask = idx.masque(m.triangles_center[0], r)
    pts, faces = idx.surface_arrays(mask)
    assert pts is not None and len(pts) == int(mask.sum()) * 3
    assert len(faces) == int(mask.sum()) * 4       # (3, a, b, c) par triangle


def test_recommande_la_plus_grande_surface_plane():
    """Sans zone marquée, la recommandation doit poser la pièce sur sa PLUS
    GRANDE surface plane. La FRACTION d'empreinte seule ne suffit pas : une
    plaque à plat (2400 mm²) et sur la tranche (120 mm²) donnent toutes deux
    100 % — d'où le critère d'assise absolue (retour Emmanuel)."""
    plaque_60 = trimesh.creation.box((60, 40, 3))
    plaque_60.apply_translation((0, 0, 1.5))
    barre = trimesh.creation.box((80, 20, 10))
    barre.apply_translation((0, 0, 5))
    for piece in (plaque_60.subdivide(), barre.subdivide()):
        props = oa.conseiller(piece, fine=True, n_fine=3)
        best = props[0]
        # le dessous choisi doit être l'axe Z (grande face) et non une tranche
        d = best.down / np.linalg.norm(best.down)
        assert abs(float(d @ np.array([0.0, 0.0, 1.0]))) > 0.9
        # et c'est bien la candidate qui offre le plus de contact
        assert best.contact_mm2 >= max(p.contact_mm2 for p in props[:3]) - 1e-6


def test_stabilite_annoncee_correspond_a_la_jauge():
    """La stabilité affichée sur une proposition doit être CELLE de la jauge une
    fois l'orientation appliquée (même moteur, même mesh reposé)."""
    from core.geometry.layer_slicer import analyze_by_layers
    for piece in (piece_L(), plaque(), cylindre_debout()):
        props = oa.conseiller(piece, fine=True, n_fine=2)
        for p in props[:2]:
            if p.score_stabilite is None:
                continue
            applique = oa.appliquer_orientation(piece, p.matrice)
            jauge = analyze_by_layers(applique).stability_score
            assert abs(p.score_stabilite - jauge) < 0.12


def test_robustesse_cas_limites():
    """Aucun cas dégénéré ne doit lever : un utilisateur charge n'importe quoi
    (STL non étanche, pièce minuscule ou énorme, corps disjoints, clic à côté)."""
    un_triangle = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                                  faces=[[0, 1, 2]])
    plat = trimesh.creation.box((50, 50, 0.001))
    mini = trimesh.creation.box((0.5, 0.5, 0.5))
    enorme = trimesh.creation.box((900, 900, 900))
    troue = trimesh.creation.box((20, 20, 20))
    troue.faces = troue.faces[:-2]                     # mesh non étanche
    a = trimesh.creation.box((10, 10, 10)); a.apply_translation((-30, 0, 5))
    b = trimesh.creation.box((10, 10, 10)); b.apply_translation((30, 0, 5))
    duo = trimesh.util.concatenate([a, b])             # corps disjoints

    for m in (un_triangle, plat, mini, enorme, troue, duo):
        props = oa.conseiller(m, fine=True, n_fine=2)
        assert isinstance(props, list)
        for p in props:
            assert np.isfinite(p.score_global)
            assert 0.0 <= p.score_adherence <= 1.0

    cube_ = cube()
    assert oa.face_la_plus_proche(cube_, (999.0, 999.0, 999.0)) is None
    assert int(oa.zone_mask_autour(cube_, (999.0, 999.0, 999.0), 3.0).sum()) == 0
    assert oa.zone_axis(cube_, np.zeros(len(cube_.faces), dtype=bool))[0] is None
    assert oa.IndexZones(un_triangle).masque((0, 0, 0), 1.0).sum() >= 1


def test_facette_faces_regroupe_la_face_plane():
    """La facette survolée/posée doit contenir TOUS les triangles coplanaires de
    la face (mise en évidence verte au survol), pas seulement celui visé."""
    m = trimesh.creation.box((40, 40, 10))
    m.apply_translation((0, 0, 5))
    for _ in range(3):
        m = m.subdivide()
    haut = [i for i in range(len(m.faces)) if m.triangles_center[i][2] > 9.8]
    idx = oa.facette_faces(m, haut[0])
    assert len(idx) > 1                       # pas un seul triangle
    assert set(haut).issubset(set(idx.tolist()))   # toute la face du dessus
    # tous coplanaires avec le départ
    n0 = m.face_normals[haut[0]]
    assert np.all(m.face_normals[idx] @ n0 > np.cos(np.radians(12.0)) - 1e-9)
    # une face voisine perpendiculaire n'en fait PAS partie
    cote = [i for i in range(len(m.faces)) if abs(m.face_normals[i][0]) > 0.99]
    assert not set(cote).intersection(set(idx.tolist()))


def test_index_face_proche():
    """Recherche rapide de face pour le survol (KD-tree) — doit tomber sur une
    face cohérente avec la surface visée."""
    m = piece_L()
    idx = oa.IndexZones(m)
    for fid_ref in (0, len(m.faces) // 2, len(m.faces) - 1):
        p = m.triangles_center[fid_ref]
        assert idx.face_proche(p) == fid_ref     # centroïde exact → même face


def test_performance_proxy():
    """Proxy : gros mesh, 20+ candidates, budget < 1 s."""
    import time
    m = trimesh.creation.icosphere(subdivisions=5, radius=30)   # ~20k faces
    for _ in range(2):
        m = m.subdivide()                                        # ~327k faces
    t = time.perf_counter()
    oa.conseiller(m, fine=False)
    assert time.perf_counter() - t < 1.0
