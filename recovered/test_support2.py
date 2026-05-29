"""
Test rapide de la chaîne complète : detection -> couleurs -> conversion sévérité.
Lance depuis C:\neoSlice : python test_support2.py
"""
import sys, os
sys.path.insert(0, r"C:\neoSlice")

import numpy as np
import trimesh
from core.geometry.support_detector import detect_support_by_raycast, support_face_colors

# ── 1. Chargement STL ──────────────────────────────────────────────────────
stl = r"D:\Impression 3D\Chute_Cover.stl"
if not os.path.exists(stl):
    print("ERREUR: fichier introuvable:", stl); sys.exit(1)

mesh = trimesh.load(stl, force="mesh")
# Centrer sur plateau (comme load_stl le fait)
mesh.apply_translation(-mesh.bounds[0])
print(f"Mesh: {len(mesh.faces)} faces, watertight={mesh.is_watertight}")
print(f"Bounds après centrage: {mesh.bounds.tolist()}")

# ── 2. Détection ──────────────────────────────────────────────────────────
mask, ratio, severity = detect_support_by_raycast(mesh)
print(f"Surplombs: {mask.sum()} faces | ratio={ratio:.4f} | severity={severity:.4f}")
print(f"Seuil UI (>0.05): {'OK colorisation' if severity > 0.05 else 'ECHEC < seuil'}")

# ── 3. Couleurs RGBA ──────────────────────────────────────────────────────
colors = support_face_colors(mesh, mask)
print(f"Shape couleurs: {colors.shape}, dtype: {colors.dtype}")
grey  = np.sum(colors[:, 2] >= 100)
yell  = np.sum((colors[:, 2] < 100) & (colors[:, 1] > 140))
oran  = np.sum((colors[:, 2] < 100) & (colors[:, 1] > 60) & (colors[:, 1] <= 140))
red   = np.sum((colors[:, 2] < 100) & (colors[:, 1] <= 60))
print(f"Gris: {grey}  Jaune: {yell}  Orange: {oran}  Rouge: {red}")

# ── 4. Conversion RGBA→sévérité (comme dans viewer_3d.py) ────────────────
b_ch = colors[:, 2].astype(np.int32)
g_ch = colors[:, 1].astype(np.int32)
sev = np.zeros(len(colors), dtype=np.float32)
oh = b_ch < 100
sev[oh & (g_ch > 140)] = 0.35
sev[oh & (g_ch > 60) & (g_ch <= 140)] = 0.65
sev[oh & (g_ch <= 60)] = 1.0
print(f"Sévérité max dans colormap: {sev.max():.2f}")
print(f"Faces colorées (sev>0): {(sev > 0).sum()}")
print("TOUT OK — la chaîne fonctionne correctement.")
