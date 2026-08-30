"""Assistant d'orientation — moteur PUR (aucune dépendance UI).

Évalue des orientations candidates d'une pièce et les classe selon :
  - les SUPPORTS (surface en surplomb >45°, méthode proxy vectorisée) ;
  - l'ADHÉRENCE (aire posée sur le plateau) ;
  - la HAUTEUR (temps d'impression) ;
  - la SOLIDITÉ si l'utilisateur a marqué des ZONES DE CONTRAINTE sur la pièce
    (ou déclaré une direction d'effort) : les couches FDM doivent LONGER l'axe
    local de la matière à ces endroits — une pièce casse le long des couches
    quand la traction s'exerce perpendiculairement à elles.

Principe de performance : pour scorer une orientation, on ne tourne JAMAIS le
mesh — uniquement ses normales et centroïdes (produits matriciels numpy).
Benchmark : 24 orientations sur 786 000 faces ≈ 180 ms. Seul le top-N passe par
l'analyse fine (analyze_overhangs smooth=False, prévue pour cet usage).

L'axe local d'une zone est estimé par PCA du voisinage : direction d'allongement
de la matière (le corps du crochet, la lame du clip). Si la zone n'est pas
directionnelle (masse compacte, valeurs propres quasi égales), on ne prétend pas
connaître l'axe : la zone est alors seulement protégée des supports.

API principale :
    conseiller(mesh, zone_masks=…, force_axis=…) -> list[Proposition]
    rotation_pour_poser_face(mesh, face_index)   -> matrice 4×4 (« poser sur cette face »)
    appliquer_orientation(mesh, matrice)         -> mesh copié, tourné, posé à Z=0
    zone_axis(mesh, mask)                        -> (axe unitaire | None, fiabilité 0→1)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

# Seuil surplomb standard (aligné sur l'analyse principale : 45°)
_OVERHANG_COS = float(np.cos(np.radians(45.0)))
# Face « posée » : normale à moins de 15° de la verticale bas + proche du plateau
_CONTACT_COS = float(np.cos(np.radians(15.0)))
_PLATE_TOL_MM = 0.8
# Deux candidates sont identiques si leurs directions « dessous » sont à <5°
_DEDUP_COS = float(np.cos(np.radians(5.0)))
# PCA : l'axe est jugé fiable si l'allongement domine nettement
_PCA_RATIO_MIN = 2.0
# Au-delà, le marquage de zone bascule sur la sélection sphérique (rapide) :
# la croissance par adjacence dépasserait 150 ms par mouvement de souris.
_SEUIL_ZONE_RAPIDE = 600_000


@dataclass
class Proposition:
    matrice: np.ndarray            # rotation 4×4 à appliquer au mesh
    down: np.ndarray               # direction (repère pièce) qui pointera vers le bas
    label: str                     # code : actuelle | retournee | cote_x… | inclinee
    # Scores 0→1 (1 = idéal)
    score_solidite: float | None   # None si aucune zone/direction exploitable
    score_supports: float
    score_adherence: float         # fraction de l'empreinte posée (ABSOLU, affiché)
    score_hauteur: float
    score_global: float
    # Métriques brutes pour l'affichage
    overhang_ratio: float          # fraction de surface en surplomb
    contact_mm2: float
    hauteur_mm: float
    zones_en_surplomb: bool        # au moins une zone marquée subirait des supports
    axes_zones: list = field(default_factory=list)  # axes locaux utilisés (info/flèches)
    # aire de contact rapportée à la meilleure candidate : privilégie une pose
    # sur les GRANDES surfaces planes (classement seulement, non affiché)
    score_assise: float = 0.0
    # stabilité par le MÊME moteur que la jauge du panneau (renseignée lors de
    # l'affinage du top-N) → le chiffre affiché correspond à celui d'après coup
    score_stabilite: float | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Candidates : « quelle direction de la pièce devient le dessous ? »
# ──────────────────────────────────────────────────────────────────────────────
def _hull_down_dirs(mesh: trimesh.Trimesh, n_hull: int) -> list[np.ndarray]:
    try:
        hull = mesh.convex_hull
        order = np.argsort(-hull.area_faces)[:n_hull]
        return [hull.face_normals[i].copy() for i in order]
    except Exception:
        return []


def directions_candidates(mesh: trimesh.Trimesh, n_hull: int = 16) -> np.ndarray:
    """Directions unitaires (repère pièce) candidates au rôle de « dessous » :
    pose actuelle + 6 axes + normales sortantes des plus grandes facettes de
    l'enveloppe convexe (poses stables naturelles — algorithme lay-flat),
    dédupliquées à 5°."""
    dirs: list[np.ndarray] = [np.array([0.0, 0.0, -1.0])]
    for ax in (0, 1, 2):
        for sgn in (1.0, -1.0):
            v = np.zeros(3); v[ax] = sgn
            dirs.append(v)
    dirs.extend(_hull_down_dirs(mesh, n_hull))
    out: list[np.ndarray] = []
    for d in dirs:
        n = np.linalg.norm(d)
        if n < 1e-9:
            continue
        d = d / n
        if all(float(d @ e) < _DEDUP_COS for e in out):
            out.append(d)
    return np.asarray(out)


def _rotation_down(d: np.ndarray) -> np.ndarray:
    """Matrice 4×4 qui amène la direction `d` (repère pièce) sur -Z monde."""
    target = np.array([0.0, 0.0, -1.0])
    c = float(np.clip(d @ target, -1.0, 1.0))
    if c > 1.0 - 1e-9:                       # déjà vers le bas
        return np.eye(4)
    if c < -1.0 + 1e-9:                      # opposée : demi-tour autour de X
        return trimesh.transformations.rotation_matrix(np.pi, [1.0, 0.0, 0.0])
    axis = np.cross(d, target)
    angle = float(np.arccos(c))
    return trimesh.transformations.rotation_matrix(angle, axis)


def _label_for(d: np.ndarray) -> str:
    """Code lisible selon la composante dominante de la direction « dessous »."""
    ax = int(np.argmax(np.abs(d)))
    sgn = 1.0 if d[ax] >= 0 else -1.0
    if abs(d[ax]) < 0.9:
        return "inclinee"
    if ax == 2:
        return "actuelle" if sgn < 0 else "retournee"
    if ax == 0:
        return "cote_x_pos" if sgn > 0 else "cote_x_neg"
    return "cote_y_pos" if sgn > 0 else "cote_y_neg"


# ──────────────────────────────────────────────────────────────────────────────
# Zones de contrainte : axe local par PCA
# ──────────────────────────────────────────────────────────────────────────────
def zone_axis(mesh: trimesh.Trimesh, mask: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Axe local de la matière autour d'une zone (masque booléen par FACE).

    PCA sur un ÉCHANTILLONNAGE SURFACIQUE dense du voisinage (zone élargie à
    2× son rayon) — robuste aussi bien sur un maillage grossier type CAD
    (une boîte = 12 triangles, sommets trop rares pour une PCA) que sur un
    scan dense. Renvoie (axe unitaire, fiabilité 0→1) — axe None si la matière
    n'est pas directionnelle à cet endroit (« patate » : λ1 ≈ λ2)."""
    idx = np.where(np.asarray(mask, dtype=bool))[0]
    if idx.size == 0:
        return None, 0.0
    fa = mesh.area_faces[idx]
    centre = np.average(mesh.triangles_center[idx], axis=0, weights=np.maximum(fa, 1e-12))
    # rayon de la zone : distance max centroïde-zone ; voisinage = 2×
    d_zone = np.linalg.norm(mesh.triangles_center[idx] - centre, axis=1)
    rayon = float(d_zone.max()) if idx.size > 1 else 1.0
    rayon = max(rayon, float(mesh.scale) * 0.02, 1e-3) * 2.0
    try:
        pts_all, _fid = trimesh.sample.sample_surface(mesh, 4000, seed=0)
    except TypeError:                       # anciennes versions sans seed
        pts_all, _fid = trimesh.sample.sample_surface(mesh, 4000)
    dv = np.linalg.norm(pts_all - centre, axis=1)
    pts = pts_all[dv <= rayon]
    if len(pts) < 32:
        pts = pts_all[np.argsort(dv)[:200]]
    pts = pts - pts.mean(axis=0)
    try:
        cov = np.cov(pts.T)
        vals, vecs = np.linalg.eigh(cov)      # croissant
        l1, l2 = float(vals[-1]), float(vals[-2])
        if l2 <= 1e-12:
            ratio = np.inf
        else:
            ratio = l1 / l2
        axe = vecs[:, -1]
        n = np.linalg.norm(axe)
        if n < 1e-9 or not np.isfinite(ratio):
            return None, 0.0
        if ratio < _PCA_RATIO_MIN:
            return None, float(min(1.0, ratio / _PCA_RATIO_MIN)) * 0.5
        fiab = float(min(1.0, (ratio - 1.0) / 4.0))
        return axe / n, fiab
    except Exception:
        return None, 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────────────────────────────────────
def _proxy_metrics(FN, FA, C, total_area, R3, zone_mask_union):
    """Métriques rapides pour UNE orientation (rotation 3×3), sans tourner le mesh.

    Renvoie (ratio_surplomb, aire_contact_mm², aire_ombre_mm², hauteur, zones_over).
    L'aire d'OMBRE = surface projetée au sol (empreinte) : elle sert de référence
    ABSOLUE à l'adhérence — « combien de mon empreinte touche réellement le
    plateau ». Comparer les candidates entre elles donnerait 100 % à la moins
    mauvaise, même quand la pièce ne pose que sur quelques points (vécu)."""
    fnz = FN @ R3[2]                      # composante Z des normales tournées
    cz = C @ R3[2]                        # z des centroïdes tournés
    zmin = float(cz.min())
    near_plate = cz <= zmin + _PLATE_TOL_MM
    contact = near_plate & (fnz < -_CONTACT_COS)
    contact_area = float(FA[contact].sum())
    over = (fnz < -_OVERHANG_COS) & ~near_plate
    over_area = float(FA[over].sum())
    hauteur = float(cz.max() - zmin)
    # Empreinte au sol ≈ moitié de la surface projetée (dessus + dessous se
    # projettent sur la même ombre) — vectorisé, aucune géométrie à construire.
    ombre = float(np.abs(fnz * FA).sum()) / 2.0
    zones_over = False
    if zone_mask_union is not None:
        zones_over = bool(np.any(over & zone_mask_union))
    return (over_area / max(total_area, 1e-9), contact_area, ombre, hauteur, zones_over)


def conseiller(
    mesh: trimesh.Trimesh,
    zone_masks: list[np.ndarray] | None = None,
    force_axis: np.ndarray | None = None,
    n_hull: int = 16,
    n_fine: int = 4,
    fine: bool = True,
) -> list[Proposition]:
    """Évalue les orientations candidates et renvoie les propositions CLASSÉES
    (meilleure d'abord). `zone_masks` : masques booléens par face (zones de
    contrainte marquées). `force_axis` : direction d'effort déclarée (repère
    pièce) si aucune zone — les deux peuvent coexister."""
    if mesh is None or len(mesh.faces) == 0:
        return []
    FN = np.asarray(mesh.face_normals, dtype=float)
    FA = np.asarray(mesh.area_faces, dtype=float)
    C = np.asarray(mesh.triangles_center, dtype=float)
    total_area = float(FA.sum())

    # Axes de solidité : un par zone exploitable (+ force déclarée éventuelle)
    axes: list[np.ndarray] = []
    if zone_masks:
        for m in zone_masks:
            ax, _fiab = zone_axis(mesh, m)
            if ax is not None:
                axes.append(ax)
    if force_axis is not None:
        fa = np.asarray(force_axis, dtype=float)
        n = np.linalg.norm(fa)
        if n > 1e-9:
            axes.append(fa / n)

    zone_union = None
    if zone_masks:
        zone_union = np.zeros(len(mesh.faces), dtype=bool)
        for m in zone_masks:
            zone_union |= np.asarray(m, dtype=bool)

    dirs = directions_candidates(mesh, n_hull=n_hull)
    props: list[Proposition] = []
    for d in dirs:
        R4 = _rotation_down(d)
        R3 = R4[:3, :3]
        over_ratio, contact, ombre, hauteur, zones_over = _proxy_metrics(
            FN, FA, C, total_area, R3, zone_union)
        # Solidité : pire zone (celle qui casse). Axe tourné → sa composante Z
        # doit être nulle (axe dans le plan des couches).
        if axes:
            s_sol = min(1.0 - abs(float((R3 @ a)[2])) for a in axes)
        else:
            s_sol = None
        props.append(Proposition(
            matrice=R4, down=d, label=_label_for(d),
            score_solidite=s_sol,
            score_supports=1.0 - min(1.0, over_ratio * 3.0),   # 33 % surplomb → 0
            # ABSOLU : fraction de l'empreinte au sol réellement posée sur le
            # plateau (0 = la pièce ne touche que par quelques points).
            score_adherence=min(1.0, contact / max(ombre, 1e-9)),
            score_hauteur=0.0,       # normalisé après (relatif aux candidates)
            score_global=0.0,
            overhang_ratio=over_ratio,
            contact_mm2=contact,
            hauteur_mm=hauteur,
            zones_en_surplomb=zones_over,
            axes_zones=[a.tolist() for a in axes],
        ))

    # Hauteur : normalisation relative (la plus basse = 1) — l'adhérence, elle,
    # est déjà ABSOLUE (fraction de l'empreinte posée) et n'est PAS renormalisée.
    hmin = min((p.hauteur_mm for p in props), default=0.0) or 1e-9
    # ASSISE : aire de contact ABSOLUE rapportée à la meilleure des candidates.
    # Indispensable au classement — la FRACTION seule ne distingue pas une plaque
    # posée à plat (2400 mm², 100 %) d'une plaque sur la tranche (120 mm², 100 %) :
    # sans ce critère, la pièce n'était pas posée sur ses plus grandes surfaces
    # planes (retour Emmanuel).
    cmax = max((p.contact_mm2 for p in props), default=0.0) or 1e-9
    for p in props:
        p.score_hauteur = min(1.0, hmin / max(p.hauteur_mm, 1e-9))
        p.score_assise = min(1.0, p.contact_mm2 / cmax)

    def _global(p: Proposition) -> float:
        if p.score_solidite is not None:
            g = (0.40 * p.score_solidite + 0.25 * p.score_supports
                 + 0.15 * p.score_assise + 0.12 * p.score_adherence
                 + 0.08 * p.score_hauteur)
        else:
            g = (0.38 * p.score_supports + 0.27 * p.score_assise
                 + 0.23 * p.score_adherence + 0.12 * p.score_hauteur)
        if p.zones_en_surplomb:
            g -= 0.15        # cicatrices de support sur une surface fonctionnelle
        return max(0.0, g)

    for p in props:
        p.score_global = _global(p)
    props.sort(key=lambda p: -p.score_global)

    # DÉDUPLICATION par résultat : deux candidates dont les scores affichés sont
    # identiques proposent la même chose à l'utilisateur (vécu : trois cartes
    # « Couchée côté Y, opposé » à la suite). On ne garde que la meilleure de
    # chaque combinaison (surplombs, adhérence, solidité) arrondie à l'affichage.
    _vus = set()
    _uniques = []
    for p in props:
        cle = (round(p.overhang_ratio, 2), round(p.score_adherence, 2),
               None if p.score_solidite is None else round(p.score_solidite, 2))
        if cle in _vus:
            continue
        _vus.add(cle)
        _uniques.append(p)
    props = _uniques

    # Affinage du top-N avec la MÊME analyse et la MÊME métrique que la jauge
    # « Surplombs » du panneau (smooth par défaut + fraction du display_mask) :
    # les % affichés dans les propositions sont IDENTIQUES à la jauge une fois
    # l'orientation appliquée (exigence de cohérence — retour Emmanuel).
    if fine and n_fine > 0:
        try:
            from core.geometry.overhang_detector import analyze_overhangs
            from core.geometry.stability_analyzer import analyze_stability
            for p in props[:n_fine]:
                # Évaluer le mesh EXACTEMENT tel qu'il sera après application
                # (rotation + repose sur le plateau) : sinon l'exclusion des
                # faces « posées » diffère et le % annoncé ne correspond pas à
                # la jauge après coup (écart 3 % vs 0 % constaté).
                m2 = appliquer_orientation(mesh, p.matrice)
                res = analyze_overhangs(m2, check_floating=False)
                dm = getattr(res, "display_mask", None)
                if dm is not None and len(dm) > 0:
                    p.overhang_ratio = float(dm.sum()) / len(dm)
                else:
                    p.overhang_ratio = float(res.overhang_ratio)
                p.score_supports = 1.0 - min(1.0, p.overhang_ratio * 3.0)
                # Stabilité par le MÊME moteur que la jauge du panneau : le
                # chiffre annoncé est exactement celui qui s'affichera après
                # application (cohérence exigée).
                try:
                    p.score_stabilite = float(analyze_stability(m2).score)
                except Exception:
                    p.score_stabilite = None
                p.score_global = _global(p)
            props[:n_fine] = sorted(props[:n_fine], key=lambda p: -p.score_global)
        except Exception:
            pass    # le classement proxy reste valable
    return props


def rayon_zone_defaut(mesh: trimesh.Trimesh) -> float:
    """Rayon de marquage par défaut : ~8 % de la diagonale de la pièce, borné."""
    return float(min(max(mesh.scale * 0.08, 1.5), 25.0))


def zone_mask_autour(mesh: trimesh.Trimesh, point, rayon: float,
                     face_index: int | None = None) -> np.ndarray:
    """Masque booléen par face : zone autour du point cliqué (inclut l'épaisseur
    locale de matière — la zone représente le VOLUME local qui subit la
    contrainte, pas seulement la peau visible).

    Une face est retenue si son centroïde OU l'un de ses SOMMETS est dans le
    rayon : tester seulement les centroïdes rate toutes les faces d'un maillage
    grossier (boîte, pièce CAD : triangles de plusieurs cm → centroïdes hors
    rayon = zone VIDE, vécu). La face réellement cliquée est toujours incluse,
    donc un clic sur la pièce marque forcément quelque chose."""
    p = np.asarray(point, dtype=float)
    r = float(rayon)
    dc = np.linalg.norm(mesh.triangles_center - p, axis=1)
    dv = np.linalg.norm(mesh.vertices - p, axis=1) <= r        # sommets proches
    mask = (dc <= r) | dv[mesh.faces].any(axis=1)
    if face_index is not None and 0 <= int(face_index) < len(mask):
        mask[int(face_index)] = True
    return mask


class IndexZones:
    """Index spatial d'un mesh pour un marquage de zones FLUIDE au survol.

    Sans lui, chaque mouvement de souris re-parcourt tous les centroïdes et tous
    les sommets (~50 ms sur 327 k faces) puis reconstruit un sous-maillage
    trimesh (~37 ms) → ~90 ms/mouvement, saccadé. Avec les KD-trees et une
    construction directe des tableaux de rendu, on tombe à quelques ms.

    Construit une fois à l'entrée du mode marquage (en arrière-plan), jeté dès
    que le mesh change."""

    def __init__(self, mesh: trimesh.Trimesh):
        from scipy.spatial import cKDTree
        self.mesh = mesh
        self.n_faces = len(mesh.faces)
        self.faces = np.asarray(mesh.faces)
        self.vertices = np.asarray(mesh.vertices, dtype=float)
        self.face_normals = np.asarray(mesh.face_normals, dtype=float)
        self._tree_c = cKDTree(np.asarray(mesh.triangles_center, dtype=float))
        self._tree_v = cKDTree(self.vertices)

    def masque(self, point, rayon: float, face_index: int | None = None) -> np.ndarray:
        """Même sémantique que `zone_mask_autour`, mais en O(voisinage)."""
        p = np.asarray(point, dtype=float)
        m = np.zeros(self.n_faces, dtype=bool)
        ic = self._tree_c.query_ball_point(p, float(rayon))
        if ic:
            m[np.asarray(ic, dtype=int)] = True
        iv = self._tree_v.query_ball_point(p, float(rayon))
        if iv:
            vmask = np.zeros(len(self.vertices), dtype=bool)
            vmask[np.asarray(iv, dtype=int)] = True
            m |= vmask[self.faces].any(axis=1)
        if face_index is not None and 0 <= int(face_index) < self.n_faces:
            m[int(face_index)] = True
        return m

    def face_proche(self, point) -> int | None:
        """Face la plus proche d'un point, en O(log n) via le KD-tree des
        centroïdes — assez précis pour identifier une facette au survol, et bien
        plus rapide que `nearest.on_surface` (µs contre des dizaines de ms)."""
        try:
            _d, i = self._tree_c.query(np.asarray(point, dtype=float))
            return int(i)
        except Exception:
            return None

    def surface_arrays(self, mask: np.ndarray, offset: float = 0.15):
        """(points, faces_vtk) prêts pour un PolyData, sans reconstruire de
        Trimesh : sommets dupliqués par triangle et décalés le long de la normale
        de face (anti z-fighting)."""
        idx = np.where(np.asarray(mask, dtype=bool))[0]
        if idx.size == 0:
            return None, None
        tri = self.faces[idx]                       # (k, 3)
        pts = self.vertices[tri].reshape(-1, 3)     # (3k, 3)
        nrm = np.repeat(self.face_normals[idx], 3, axis=0)
        pts = pts + nrm * float(offset)
        k = idx.size
        faces = np.hstack([np.full((k, 1), 3, dtype=np.int64),
                           np.arange(k * 3, dtype=np.int64).reshape(k, 3)]).ravel()
        return pts, faces


def _voisins_faces(mesh: trimesh.Trimesh) -> dict:
    """Liste d'adjacence face → voisines (mise en cache sur le mesh)."""
    voisins = getattr(mesh, "_neo_face_voisins", None)
    if voisins:
        return voisins
    voisins = {}
    try:
        for a, b in np.asarray(mesh.face_adjacency):
            voisins.setdefault(int(a), []).append(int(b))
            voisins.setdefault(int(b), []).append(int(a))
        mesh._neo_face_voisins = voisins
    except Exception:
        pass
    return voisins


def zone_mask_geodesique(mesh: trimesh.Trimesh, face_index: int, rayon: float,
                         lissage: bool = True) -> np.ndarray:
    """Zone de contrainte « propre » : croissance le long de la SURFACE.

    Une boule euclidienne découpe le maillage sans tenir compte de la géométrie →
    contour en dents de scie et zone qui saute de l'autre côté d'une paroi fine.
    Ici on part du triangle visé et on progresse de proche en proche (distance
    cumulée entre centroïdes), comme une tache posée sur la peau de l'objet — le
    rendu est net, comme la mise en évidence d'une face.

    `lissage` : fermeture morphologique — on ajoute les triangles dont au moins
    deux voisins appartiennent déjà à la zone, ce qui gomme les dentelures et
    bouche les micro-trous du contour."""
    n = len(mesh.faces)
    m = np.zeros(n, dtype=bool)
    fi = int(face_index)
    if not (0 <= fi < n):
        return m
    m[fi] = True
    # Maillage très dense : la croissance par adjacence coûterait > 150 ms par
    # mouvement de souris. Les triangles y sont si petits que la sélection
    # sphérique donne déjà un contour lisse à l'œil → on privilégie la fluidité.
    if n > _SEUIL_ZONE_RAPIDE:
        return zone_mask_autour(mesh, np.asarray(mesh.triangles_center)[fi],
                                rayon, face_index=fi)
    try:
        adjacency = np.asarray(mesh.face_adjacency)
        if adjacency.size == 0:
            return m
    except Exception:
        return m

    centres = np.asarray(mesh.triangles_center, dtype=float)
    sommets = np.asarray(mesh.vertices, dtype=float)
    faces_idx = np.asarray(mesh.faces)
    r = float(rayon)
    origine = centres[fi]
    # Critère de taille : distance EUCLIDIENNE au point de départ (une distance
    # cumulée le long des triangles zigzague et rétrécit fortement la zone).
    dans_rayon = (np.linalg.norm(centres - origine, axis=1) <= r)
    dv = np.linalg.norm(sommets - origine, axis=1) <= r
    dans_rayon |= dv[faces_idx].any(axis=1)      # inclut les grandes faces

    # Propagation par ADJACENCE, restreinte au voisinage : la zone reste d'un
    # seul tenant sur la surface (elle ne réapparaît pas de l'autre côté d'une
    # paroi fine). On filtre d'abord les arêtes utiles en numpy — parcourir tout
    # le maillage en Python coûtait ~190 ms sur 327 k faces.
    A, B = adjacency[:, 0], adjacency[:, 1]
    utile = dans_rayon[A] & dans_rayon[B]
    sub = {}
    for a, b in adjacency[utile]:
        sub.setdefault(int(a), []).append(int(b))
        sub.setdefault(int(b), []).append(int(a))
    pile = [fi]
    while pile:
        cur = pile.pop()
        for v in sub.get(cur, ()):
            if not m[v]:
                m[v] = True
                pile.append(v)

    if lissage:
        # Fermeture morphologique VECTORISÉE : une face rejointe par au moins
        # deux voisins de la zone y entre aussi → gomme les dentelures et bouche
        # les micro-trous du contour. `bincount` sur les seules arêtes utiles
        # (np.add.at sur tout le maillage coûtait ~40 ms par passe).
        Au, Bu = A[utile], B[utile]
        for _ in range(2):
            cnt = (np.bincount(Au, weights=m[Bu], minlength=n)
                   + np.bincount(Bu, weights=m[Au], minlength=n))
            ajout = (~m) & (cnt >= 2) & dans_rayon
            if not ajout.any():
                break
            m |= ajout
    return m


def _facet_labels(mesh: trimesh.Trimesh) -> np.ndarray:
    """Étiquette de facette plane par face (-1 = surface courbe), mise en cache.
    `mesh.facets` regroupe les triangles coplanaires ADJACENTS : sur une pièce
    mécanique, une boîte donne exactement ses 6 faces."""
    lab = getattr(mesh, "_neo_facet_labels", None)
    if lab is not None and len(lab) == len(mesh.faces):
        return lab
    lab = np.full(len(mesh.faces), -1, dtype=np.int32)
    try:
        for i, f in enumerate(mesh.facets):
            lab[np.asarray(f, dtype=int)] = i
    except Exception:
        pass
    try:
        mesh._neo_facet_labels = lab
    except Exception:
        pass
    return lab


def etendre_aux_faces(mesh: trimesh.Trimesh, mask: np.ndarray,
                      part_max: float = 0.35) -> np.ndarray:
    """Étend une zone aux FACES PLANES qu'elle touche — le rendu épouse alors la
    géométrie (bords sur les arêtes de l'objet) au lieu de laisser apparaître des
    triangles coupés (retour Emmanuel : « on a toujours des zones triangulaires »).

    Une facette n'est absorbée que si elle reste raisonnable (≤ `part_max` du
    maillage) : sinon un clic sur une grande plaque sélectionnerait toute sa
    surface. Sur une pièce courbe (figurine), aucune facette n'existe → la zone
    reste telle quelle."""
    m = np.asarray(mask, dtype=bool).copy()
    if not m.any():
        return m
    # Maillage très dense : l'étiquetage des facettes coûterait des secondes et
    # les triangles y sont si petits que le contour paraît déjà lisse.
    if len(mesh.faces) > _SEUIL_ZONE_RAPIDE:
        return m
    lab = _facet_labels(mesh)
    ids = np.unique(lab[m])
    ids = ids[ids >= 0]
    if ids.size == 0:
        return m
    limite = max(1, int(len(mesh.faces) * float(part_max)))
    for fid in ids:
        sel = (lab == fid)
        if int(sel.sum()) <= limite:
            m |= sel
    return m


def face_la_plus_proche(mesh: trimesh.Trimesh, point) -> int | None:
    """Index de la face la plus proche d'un point monde (clic viewer). None si
    le point est trop loin de la surface (> 5 % de la diagonale : clic raté)."""
    try:
        p = np.asarray(point, dtype=float).reshape(1, 3)
        _pts, dist, tid = mesh.nearest.on_surface(p)
        if float(dist[0]) > mesh.scale * 0.05:
            return None
        return int(tid[0])
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Actions
# ──────────────────────────────────────────────────────────────────────────────
def facette_faces(mesh: trimesh.Trimesh, face_index: int,
                  tol_deg: float = 12.0, max_faces: int = 20000) -> np.ndarray:
    """Indices des triangles formant la FACETTE PLANE du triangle `face_index`.

    Croissance de région sur l'adjacence : on agrège les voisins dont la normale
    reste à moins de `tol_deg` de celle du triangle de départ. Un STL découpe une
    face plane en dizaines de triangles aux normales légèrement différentes
    (tessellation, bruit de scan) — c'est cette facette entière qu'il faut poser
    à plat, et c'est elle qu'on met en évidence au survol."""
    fi = int(face_index)
    normals = np.asarray(mesh.face_normals, dtype=float)
    try:
        adjacency = np.asarray(mesh.face_adjacency)
        if adjacency.size == 0:
            return np.asarray([fi], dtype=int)
        voisins = getattr(mesh, "_neo_face_voisins", None)
        if voisins is None or len(voisins) == 0:
            voisins = {}
            for a, b in adjacency:
                voisins.setdefault(int(a), []).append(int(b))
                voisins.setdefault(int(b), []).append(int(a))
            try:                       # cache : la BFS est appelée à chaque survol
                mesh._neo_face_voisins = voisins
            except Exception:
                pass
        n0 = normals[fi]
        cos_tol = float(np.cos(np.radians(tol_deg)))
        vus = {fi}
        pile = [fi]
        groupe = [fi]
        while pile and len(groupe) < max_faces:
            cur = pile.pop()
            for v in voisins.get(cur, ()):
                if v in vus:
                    continue
                if float(normals[v] @ n0) >= cos_tol:   # quasi coplanaire
                    vus.add(v)
                    groupe.append(v)
                    pile.append(v)
        return np.asarray(groupe, dtype=int)
    except Exception:
        return np.asarray([fi], dtype=int)


def normale_facette(mesh: trimesh.Trimesh, face_index: int,
                    tol_deg: float = 12.0) -> np.ndarray:
    """Normale de la FACETTE PLANE contenant le triangle `face_index` (moyenne
    pondérée par l'aire) : poser la pièce sur la normale du SEUL triangle cliqué
    donne une pose de travers (vécu : « la pièce n'est pas parfaitement posée »)."""
    fi = int(face_index)
    normals = np.asarray(mesh.face_normals, dtype=float)
    n0 = normals[fi]
    try:
        idx = facette_faces(mesh, fi, tol_deg)
        aires = np.asarray(mesh.area_faces, dtype=float)[idx]
        n = (normals[idx] * aires[:, None]).sum(axis=0)
        norme = float(np.linalg.norm(n))
        if norme > 1e-9:
            return n / norme
    except Exception:
        pass
    return n0 / max(float(np.linalg.norm(n0)), 1e-9)


def rotation_pour_poser_face(mesh: trimesh.Trimesh, face_index: int) -> np.ndarray:
    """« Poser sur cette face » : rotation qui met À PLAT contre le plateau la
    facette plane contenant le triangle cliqué (pas seulement ce triangle)."""
    n = normale_facette(mesh, face_index)
    return _rotation_down(n)


def appliquer_orientation(mesh: trimesh.Trimesh, matrice: np.ndarray) -> trimesh.Trimesh:
    """Applique la rotation puis repose la pièce : centrée en XY sur l'origine,
    posée à Z=0 (convention du pipeline de chargement)."""
    m2 = mesh.copy()
    m2.apply_transform(np.asarray(matrice, dtype=float))
    lo, hi = m2.bounds
    m2.apply_translation([-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, -lo[2]])
    return m2


def score_orientation_actuelle(mesh: trimesh.Trimesh) -> tuple[float, float]:
    """(score 0→100 de la pose actuelle, gain de surplomb possible en points de %)
    — pour la carte ORIENTATION du panneau d'analyse. Proxy pur (~quelques ms)."""
    props = conseiller(mesh, fine=False)
    if not props:
        return 100.0, 0.0
    cur = next((p for p in props if p.label == "actuelle"), props[0])
    best = props[0]
    gain = max(0.0, (cur.overhang_ratio - best.overhang_ratio) * 100.0)
    return round(cur.score_global * 100.0), round(gain, 1)
