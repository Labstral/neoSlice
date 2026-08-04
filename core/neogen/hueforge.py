# -*- coding: utf-8 -*-
"""HueForge — reproduit une IMAGE COULEUR par empilement de filaments translucides.

Principe : quelques filaments (clair -> foncé) sont imprimés en bandes horizontales,
du bas vers le haut, avec changement de filament PAR HAUTEUR. La couleur perçue à un
point vient de la SUPERPOSITION (mélange soustractif) des couches translucides au-dessus
du fond : c'est la **hauteur locale du relief** qui décide combien de couches de chaque
filament laissent passer / masquent la lumière → donc quelle couleur on voit.

Modèle : comme la pile de filaments (calendrier des swaps) est GLOBALE, la couleur
perçue ne dépend que de la HAUTEUR h. On calcule donc une **rampe** de couleurs perçues
C(h) (compositing « over » du bas vers le haut, opacité de chaque couche = 1-exp(-e/TD)).
Chaque pixel choisit la hauteur dont la couleur de rampe est la plus proche de sa cible.

Deux sorties :
  - `apercu`  : le relief avec une COULEUR PAR SOMMET = le rendu photo simulé (viewer).
  - `scene`   : les BANDES par filament (corps colorés distincts) = l'export multicouleur
                (swaps par hauteur via slots/extrudeurs — voir carte_multicouleur).
"""
from __future__ import annotations

import numpy as np
import trimesh

from core.neogen.relief_photo import _RES_MAX, _plaque_heightfield


def _hex_rgb(h: str) -> np.ndarray:
    """'RRGGBB' -> array float 0..1 (3,)."""
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def _charger_couleur(chemin: str) -> np.ndarray:
    """Image -> grille RGB 0..1 (ny, nx, 3), sous-échantillonnée, fond blanc sur alpha."""
    import cv2
    from PIL import Image
    im = Image.open(chemin).convert("RGBA")
    arr = np.asarray(im).astype(np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3:4]
    rgb = rgb * alpha + 1.0 * (1.0 - alpha)          # transparent -> blanc
    h, w = rgb.shape[:2]
    f = _RES_MAX / max(h, w)
    if f < 1.0:
        rgb = cv2.resize(rgb, (max(2, int(w * f)), max(2, int(h * f))),
                         interpolation=cv2.INTER_AREA)
    return np.clip(rgb, 0.0, 1.0)


def _rampe(palette: list[dict], hauteur_couche: float, couches_max: int):
    """Construit la rampe des couleurs perçues + le calendrier des bandes.

    Retour :
      ramp        : (L+1, 3) couleur perçue par nombre de couches empilées (0 = fond)
      schedule    : (L,) index de filament pour chaque couche au-dessus du fond
      couleurs    : (N, 3) couleurs des filaments
    """
    N = len(palette)
    couleurs = np.array([_hex_rgb(p["hex"]) for p in palette], dtype=np.float32)
    tds = np.array([max(0.05, float(p["td"])) for p in palette], dtype=np.float32)

    # Couches réparties équitablement sur les filaments 1..N-1 (le 0 = fond).
    par_filament = max(1, couches_max // max(1, N - 1))
    schedule = np.concatenate([np.full(par_filament, k, dtype=int)
                               for k in range(1, N)]) if N > 1 else np.array([], int)
    L = len(schedule)

    ramp = np.empty((L + 1, 3), dtype=np.float32)
    ramp[0] = couleurs[0]                              # fond = 1er filament
    C = couleurs[0].copy()
    for i in range(L):
        k = schedule[i]
        alpha = 1.0 - np.exp(-hauteur_couche / tds[k])  # opacité d'une couche de f_k
        C = alpha * couleurs[k] + (1.0 - alpha) * C
        ramp[i + 1] = C
    return ramp, schedule, couleurs


def _slab(top_mm: np.ndarray, bottom_z: float, largeur: float) -> trimesh.Trimesh:
    """Comme `_plaque_heightfield` mais fond plat à `bottom_z` (dalle d'une bande)."""
    m = _plaque_heightfield(np.clip(top_mm - bottom_z, 0.0, None), largeur)
    m.apply_translation([0, 0, bottom_z])
    return m


def generer_hueforge(image: str, palette: list[dict], largeur: float = 100.0,
                     hauteur_couche: float = 0.08, base_mm: float = 0.4,
                     couches_max: int = 30):
    """Génère l'aperçu couleur + la scène de bandes exportable.

    palette : liste ORDONNÉE clair->foncé, chaque item {'hex': 'RRGGBB', 'td': float,
              'nom': str}. palette[0] = fond (imprimé en premier, en bas).
    Retour  : (scene: trimesh.Scene bandes colorées, apercu: trimesh.Trimesh sommets colorés)
    """
    if len(palette) < 2:
        raise ValueError("HueForge : au moins 2 filaments requis.")
    largeur = max(20.0, float(largeur))
    hauteur_couche = max(0.04, float(hauteur_couche))
    base_mm = max(0.2, float(base_mm))
    couches_max = int(max(len(palette), couches_max))

    cible = _charger_couleur(image)                    # (ny, nx, 3)
    ny, nx = cible.shape[:2]
    ramp, schedule, couleurs = _rampe(palette, hauteur_couche, couches_max)

    # Pour chaque pixel : hauteur (nb de couches) dont la couleur de rampe est la plus
    # proche de la cible. Distance RGB au carré, vectorisée.
    plat = cible.reshape(-1, 3)                         # (P, 3)
    d = ((plat[:, None, :] - ramp[None, :, :]) ** 2).sum(-1)   # (P, L+1)
    hstar = d.argmin(1).reshape(ny, nx)                # (ny, nx) nb de couches

    # Carte de hauteurs (mm) : fond plein + couches choisies.
    h_mm = base_mm + hstar.astype(np.float32) * hauteur_couche

    # ── Aperçu : relief à couleur par sommet = rendu photo simulé ────────────
    apercu = _plaque_heightfield(h_mm, largeur)
    ntop = nx * ny
    col_top = (ramp[hstar].reshape(-1, 3) * 255).astype(np.uint8)   # (ntop, 3)
    vc = np.empty((len(apercu.vertices), 4), dtype=np.uint8)
    vc[:, 3] = 255
    vc[:ntop, :3] = col_top                            # sommets du dessus
    vc[ntop:, :3] = col_top                            # dessous/murs : même teinte
    apercu.visual.vertex_colors = vc

    # ── Bandes par filament : corps colorés distincts pour l'export ──────────
    scene = trimesh.Scene()
    couleurs_hex: list[str] = []
    # Fond (filament 0) : dalle pleine z 0..base_mm.
    fond = _slab(np.full((ny, nx), base_mm, np.float32), 0.0, largeur)
    fond.visual.face_colors = np.array([*(couleurs[0] * 255).astype(int), 255])
    scene.add_geometry(fond, geom_name=f"f0_{palette[0].get('nom','fond')}")
    couleurs_hex.append(palette[0]["hex"])

    # Bandes supérieures (filaments 1..N-1), par tranche Z du calendrier.
    z = base_mm
    for k in range(1, len(palette)):
        n_couches = int((schedule == k).sum())
        if n_couches == 0:
            continue
        z_low, z_high = z, z + n_couches * hauteur_couche
        top_k = np.clip(h_mm, z_low, z_high)
        if float(top_k.max() - z_low) < 1e-4:          # bande vide (aucun pixel) -> ignorée
            z = z_high
            continue
        bande = _slab(top_k, z_low, largeur)
        bande.visual.face_colors = np.array([*(couleurs[k] * 255).astype(int), 255])
        scene.add_geometry(bande, geom_name=f"f{k}_{palette[k].get('nom','')}")
        couleurs_hex.append(palette[k]["hex"])
        z = z_high

    # Centrage XY, base à z=0 (comme les autres objets neoGen).
    c = scene.bounds
    off = [-(c[0][0] + c[1][0]) / 2, -(c[0][1] + c[1][1]) / 2, 0.0]
    scene.apply_transform(trimesh.transformations.translation_matrix(off))
    apercu.apply_translation(off)

    scene.metadata["hueforge"] = True
    scene.metadata["hueforge_apercu"] = apercu
    scene.metadata["hueforge_couleurs"] = couleurs_hex
    return scene, apercu
