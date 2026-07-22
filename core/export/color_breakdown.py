"""Repartition du filament estime par couleur (slot), pour la fenetre d'export.

Trois cas, du plus fiable au plus approximatif :
  1. 3MF multi-objets (chaque partie a un slot `extruder`) : on calcule le volume
     et la surface par slot, on estime les grammes par slot avec le meme modele
     physique que l'estimation globale, puis on NORMALISE pour que la somme colle
     exactement a l'estimation globale affichee. -> fiable.
  2. 3MF peint (peinture MMU/AMS sur un maillage) : on repartit l'estimation
     globale au PRORATA de la surface peinte par couleur (voir paint_scan).
     -> approximatif (surface, pas volume), etiquete comme tel.
  3. STL / mono-couleur : une seule couleur = toute l'estimation. Saisie manuelle
     possible cote UI.

Le poids EXACT au gramme n'existe qu'apres slicing dans le slicer : ce module ne
produit qu'une ESTIMATION, corrigeable par l'utilisateur.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# Palette de secours par slot (identique a celle du viewer pour la coherence
# visuelle de la previsualisation).
DEFAULT_SLOT_HEX = {
    1: "#F0EBE0", 2: "#2E86C1", 3: "#E67E22", 4: "#27AE60",
    5: "#8E44AD", 6: "#F1C40F", 7: "#E74C3C", 8: "#1ABC9C",
}


@dataclass
class ColorSlot:
    slot: int                 # index extruder (1..N)
    grams: float              # estimation (g)
    volume_cm3: float = 0.0
    area_cm2: float = 0.0
    default_hex: str = "#AABBCC"


@dataclass
class ColorBreakdown:
    kind: str                 # "multiobject" | "painted" | "single"
    total_g: float
    slots: list[ColorSlot] = field(default_factory=list)
    approximate: bool = False # True pour le cas peint (repartition de surface)


def _est_g(config, vol_cm3: float, area_cm2: float) -> float:
    try:
        return float(config.estimated_filament_g(max(0.0, vol_cm3), max(0.0, area_cm2)))
    except Exception:
        return 0.0


def from_scene(scene, config) -> ColorBreakdown:
    """Répartition couleur d'une Scene trimesh bicolore (carte, QR, texte…) : un
    slot par couleur de face présente, volume estimé depuis les corps. Sert à
    afficher les slots dans la fenêtre d'export même si l'aperçu est fusionné."""
    from collections import OrderedDict
    vol_by_colour: "OrderedDict[str, float]" = OrderedDict()
    for _nom, g in scene.geometry.items():
        try:
            c = g.visual.face_colors[0][:3]
            hexa = "#{:02X}{:02X}{:02X}".format(int(c[0]), int(c[1]), int(c[2]))
        except Exception:
            hexa = "#FFFFFF"
        vol_by_colour[hexa] = vol_by_colour.get(hexa, 0.0) + float(g.volume) / 1000.0
    slots, total_g = [], 0.0
    for i, (hexa, vol) in enumerate(vol_by_colour.items()):
        grams = _est_g(config, vol, 0.0)
        total_g += grams
        slots.append(ColorSlot(slot=i + 1, grams=round(grams, 1),
                               volume_cm3=round(vol, 2), default_hex=hexa))
    if len(slots) <= 1:
        return ColorBreakdown("single", round(total_g, 1), slots, approximate=False)
    return ColorBreakdown("multiobject", round(total_g, 1), slots, approximate=False)


def from_carte(spec, config) -> ColorBreakdown:
    """Répartition couleur d'une CARTE DE VISITE (construit la scène puis délègue)."""
    from core.neogen.carte_visite import construire
    scene, _couleurs = construire(spec)
    return from_scene(scene, config)


def compute(threemf_data, mesh, analysis, config) -> ColorBreakdown:
    """Construit la repartition couleur a partir de l'etat courant."""
    vol = float(getattr(analysis, "volume_cm3", 0.0) or 0.0)
    area = float(getattr(analysis, "surface_area_cm2", 0.0) or 0.0)
    total_g = _est_g(config, vol, area) if vol > 0 else 0.0

    # ── Cas 1 : 3MF multi-objets avec plusieurs slots ────────────────────────
    slot_count = getattr(threemf_data, "slot_count", 1) if threemf_data else 1
    if threemf_data and slot_count > 1:
        by_slot: dict[int, list[float]] = {}   # slot -> [vol_cm3, area_cm2]
        for o in getattr(threemf_data, "objects", []):
            m = getattr(o, "mesh", None)
            if m is None:
                continue
            try:
                v = abs(float(m.volume)) / 1000.0   # mm3 -> cm3
                a = float(m.area) / 100.0           # mm2 -> cm2
            except Exception:
                v = a = 0.0
            acc = by_slot.setdefault(int(o.extruder), [0.0, 0.0])
            acc[0] += v
            acc[1] += a
        if len(by_slot) > 1:
            raw = {s: _est_g(config, v, a) for s, (v, a) in by_slot.items()}
            tot_raw = sum(raw.values()) or 1.0
            slots = [
                ColorSlot(
                    slot=s,
                    grams=round(total_g * raw[s] / tot_raw, 1),
                    volume_cm3=round(by_slot[s][0], 2),
                    area_cm2=round(by_slot[s][1], 2),
                    default_hex=DEFAULT_SLOT_HEX.get(s, "#AABBCC"),
                )
                for s in sorted(by_slot)
            ]
            return ColorBreakdown("multiobject", round(total_g, 1), slots, approximate=False)

    # ── Cas 2 : 3MF peint (repartition de surface) ───────────────────────────
    # La peinture (paint_color/mmu_segmentation) est souvent dans un sous-modele
    # externe 3D/Objects/*.model → on scanne TOUT le 3MF via son chemin source.
    src_path = getattr(threemf_data, "source_path", None) if threemf_data else None
    if src_path is not None:
        try:
            from core.geometry.paint_scan import scan_paint
            painted = scan_paint(src_path)
        except Exception:
            painted = None
        if painted and len(painted) > 1:
            tot_a = sum(painted.values()) or 1.0
            slots = [
                ColorSlot(
                    slot=s,
                    grams=round(total_g * painted[s] / tot_a, 1),
                    area_cm2=round(painted[s], 2),
                    default_hex=DEFAULT_SLOT_HEX.get(s, "#AABBCC"),
                )
                for s in sorted(painted)
            ]
            return ColorBreakdown("painted", round(total_g, 1), slots, approximate=True)

    # ── Cas 3 : mono-couleur / STL ───────────────────────────────────────────
    return ColorBreakdown(
        "single", round(total_g, 1),
        [ColorSlot(slot=1, grams=round(total_g, 1), volume_cm3=round(vol, 2),
                   area_cm2=round(area, 2), default_hex=DEFAULT_SLOT_HEX.get(1))],
        approximate=False,
    )
