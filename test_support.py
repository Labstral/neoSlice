import sys
import os
sys.path.insert(0, r"C:\neoSlice")

try:
    import trimesh
    import numpy as np
    from core.geometry.support_detector import detect_support_by_raycast, support_face_colors
    print("Import OK")

    stl_path = r"D:\Impression 3D\Chute_Cover.stl"
    if not os.path.exists(stl_path):
        print(f"ERREUR: fichier introuvable: {stl_path}")
        sys.exit(1)

    mesh = trimesh.load(stl_path, force="mesh")
    print(f"Faces: {len(mesh.faces)}, watertight: {mesh.is_watertight}")
    print(f"Bounds: {mesh.bounds}")

    mask, ratio, severity = detect_support_by_raycast(mesh)
    print(f"Raw mask: {mask.sum()} faces en surplomb")
    print(f"Ratio: {ratio:.4f}, Severity: {severity:.4f}")

    colors = support_face_colors(mesh, mask)
    print(f"Shape couleurs: {colors.shape}")
    grey_count = sum(1 for row in colors if tuple(row) == (142, 155, 173, 255))
    yellow_count = sum(1 for row in colors if row[2] < 100 and row[0] > 180 and row[1] > 140)
    orange_count = sum(1 for row in colors if row[2] < 50 and row[0] > 180 and row[1] < 140 and row[1] > 60)
    red_count = sum(1 for row in colors if row[2] < 50 and row[1] < 60)
    print(f"Gris: {grey_count}, Jaune: {yellow_count}, Orange: {orange_count}, Rouge: {red_count}")

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
