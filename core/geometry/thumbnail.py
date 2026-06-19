"""Génération de miniatures d'aperçu pour les fichiers chargés (STL/OBJ/3MF).

- .3mf Bambu Studio : on extrait la miniature PNG déjà embarquée (instantané).
- STL / OBJ / 3MF sans miniature : rendu hors-écran du maillage via PyVista.

Toutes les fonctions renvoient des octets PNG (ou None en cas d'échec), pour
rester indépendantes de Qt — la conversion en QPixmap se fait côté UI.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from loguru import logger


def thumbnail_png_from_3mf(path: Path) -> bytes | None:
    """Extrait la miniature PNG embarquée d'un .3mf (Bambu Studio en place une
    dans Metadata/). Retourne la plus grande image trouvée, ou None."""
    try:
        with zipfile.ZipFile(path) as z:
            pngs = [n for n in z.namelist() if n.lower().endswith(".png")]
            if not pngs:
                return None
            # Préférer une vraie vignette (plate/thumbnail), sinon la plus grande
            preferred = [n for n in pngs
                         if any(k in n.lower() for k in ("thumbnail", "plate", "metadata"))]
            pool = preferred or pngs
            best = max(pool, key=lambda n: z.getinfo(n).file_size)
            return z.read(best)
    except Exception as e:
        logger.debug(f"Pas de miniature embarquée dans le 3MF : {e}")
        return None


def render_mesh_png(mesh, size: tuple[int, int] = (240, 170), dark: bool = True) -> bytes | None:
    """Rendu hors-écran d'un maillage (trimesh) → octets PNG."""
    try:
        import pyvista as pv
        from PIL import Image

        pv_mesh = pv.wrap(mesh)
        bg = (11, 15, 20) if dark else (235, 236, 238)
        plotter = pv.Plotter(off_screen=True, window_size=[size[0] * 2, size[1] * 2])
        plotter.background_color = tuple(c / 255 for c in bg)
        plotter.add_mesh(pv_mesh, color=(255, 140, 60), smooth_shading=True)
        plotter.view_isometric()
        arr = plotter.screenshot(return_img=True)
        plotter.close()
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"Rendu de miniature échoué : {e}")
        return None


def make_thumbnail_png(path, mesh=None, dark: bool = True,
                       size: tuple[int, int] = (240, 170)) -> bytes | None:
    """Miniature PNG d'un fichier chargé.

    3MF → miniature embarquée si dispo (rapide), sinon rendu du maillage.
    STL/OBJ → rendu du maillage.
    """
    p = Path(path)
    if p.suffix.lower() == ".3mf":
        emb = thumbnail_png_from_3mf(p)
        if emb:
            return emb
    if mesh is not None:
        return render_mesh_png(mesh, size=size, dark=dark)
    return None
