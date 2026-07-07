"""Detection de la peinture multicouleur dans un 3MF (Bambu/Orca/Prusa).

Une piece "peinte" porte, sur chaque triangle du maillage, un attribut indiquant
la couleur appliquee : `paint_color` (Bambu Studio / OrcaSlicer) ou
`mmu_segmentation` (PrusaSlicer, souvent prefixe `slic3rpe:`). C'est une info de
SURFACE, pas un decoupage de volume : la repartition qu'on en tire est donc
APPROXIMATIVE (voir core/export/color_breakdown.py).

IMPORTANT : la geometrie (et donc la peinture) peut etre dans le fichier principal
`3D/3dmodel.model` OU dans des sous-modeles externes `3D/Objects/*.model`
(references par des <component p:path=...>). On scanne donc TOUS les .model du zip.

On ne cherche pas a decoder l'index de couleur exact de Bambu (encodage non
documente). On regroupe par CODE de peinture distinct (chaque code = une zone de
couleur), on somme les aires, et on numerote les slots par aire decroissante.
L'utilisateur associe ensuite chaque zone a une vraie bobine dans la fenetre
d'export ; l'index absolu de Bambu est donc inutile ici.
"""
from __future__ import annotations
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

# Une zone dont l'aire est sous ce seuil (fraction de l'aire totale) est fusionnee
# dans la couleur de base : evite d'inventer des couleurs a partir des triangles
# partiellement peints (codes d'encodage a rallonge, un par triangle de bord).
_MIN_ZONE_FRACTION = 0.02
_MAX_SLOTS = 8


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paint_code(attrib: dict) -> str | None:
    for k, v in attrib.items():
        lk = _local(k)
        if lk in ("paint_color", "mmu_segmentation") and v and v.strip():
            return v.strip()
    return None


def _accumulate_from_xml(model_xml: str, area_by_code: dict, base_holder: list) -> None:
    """Ajoute a `area_by_code` (code -> aire) et `base_holder[0]` (aire non peinte)
    les triangles peints trouves dans un contenu .model."""
    if not model_xml or ("paint_color" not in model_xml and "mmu_segmentation" not in model_xml):
        return
    try:
        root = ET.fromstring(model_xml)
    except Exception:
        return
    for mesh_el in root.iter():
        if _local(mesh_el.tag) != "mesh":
            continue
        verts: list[tuple[float, float, float]] = []
        tri_parent = None
        for child in mesh_el:
            lc = _local(child.tag)
            if lc == "vertices":
                for v in child:
                    if _local(v.tag) == "vertex":
                        verts.append((float(v.get("x", 0) or 0),
                                      float(v.get("y", 0) or 0),
                                      float(v.get("z", 0) or 0)))
            elif lc == "triangles":
                tri_parent = child
        if tri_parent is None:
            continue
        V = np.asarray(verts, dtype=float) if verts else None
        for t in tri_parent:
            if _local(t.tag) != "triangle":
                continue
            area = 0.0
            if V is not None:
                try:
                    i1 = int(t.get("v1")); i2 = int(t.get("v2")); i3 = int(t.get("v3"))
                    p1, p2, p3 = V[i1], V[i2], V[i3]
                    area = 0.5 * float(np.linalg.norm(np.cross(p2 - p1, p3 - p1)))
                except Exception:
                    area = 0.0
            code = _paint_code(t.attrib)
            if code:
                # Le DERNIER caractere du code encode l'index de couleur/extruder
                # (Bambu). Les differents codes d'une meme couleur (etats de
                # decoupe recursive des triangles partiellement peints) finissent
                # tous par le meme caractere → on regroupe la-dessus pour ne pas
                # sur-decouper une couleur unique en plusieurs slots.
                area_by_code[code[-1]] = area_by_code.get(code[-1], 0.0) + area
            else:
                base_holder[0] += area


def _finalize(area_by_code: dict, base_area: float) -> dict[int, float] | None:
    if not area_by_code:
        return None
    total = base_area + sum(area_by_code.values())
    if total <= 0:
        return None
    # Fusionner les zones minuscules (triangles partiellement peints) dans la base.
    big = {c: a for c, a in area_by_code.items() if a / total >= _MIN_ZONE_FRACTION}
    merged_small = sum(a for c, a in area_by_code.items() if c not in big)
    base_area += merged_small
    if not big:
        return None
    ordered = sorted(big.items(), key=lambda kv: kv[1], reverse=True)[:_MAX_SLOTS - 1]
    result: dict[int, float] = {}
    if base_area > 0:
        result[1] = base_area / 100.0   # mm2 -> cm2
    slot = 2
    for _code, a in ordered:
        result[slot] = a / 100.0
        slot += 1
    if len(result) < 2:
        return None
    return result


def scan_paint_from_xml(model_xml: str) -> dict[int, float] | None:
    """Analyse un seul contenu .model (cas geometrie INLINE dans 3dmodel.model)."""
    area_by_code: dict[str, float] = {}
    base_holder = [0.0]
    _accumulate_from_xml(model_xml, area_by_code, base_holder)
    return _finalize(area_by_code, base_holder[0])


def scan_paint(threemf_path) -> dict[int, float] | None:
    """Analyse un 3MF complet : scanne TOUS les fichiers `.model` (principal ET
    sous-modeles externes 3D/Objects/*.model, ou vit souvent la peinture des STL
    peints dans Bambu Studio). Renvoie {slot: aire_cm2} (slot 1 = base non peinte,
    slots 2..N = zones peintes par aire decroissante) s'il y a >= 2 couleurs, sinon
    None (repli sur la saisie manuelle cote UI)."""
    try:
        path = Path(threemf_path)
        if not path.exists() or not zipfile.is_zipfile(path):
            return None
        area_by_code: dict[str, float] = {}
        base_holder = [0.0]
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".model"):
                    continue
                try:
                    xml = zf.read(name).decode("utf-8", "replace")
                except Exception:
                    continue
                _accumulate_from_xml(xml, area_by_code, base_holder)
        return _finalize(area_by_code, base_holder[0])
    except Exception:
        return None
