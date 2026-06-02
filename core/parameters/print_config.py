from __future__ import annotations
from pydantic import BaseModel, Field


class PrintConfig(BaseModel):
    """Paramètres Bambu Studio complets générés par neoSlice."""

    # --- Couches ---
    layer_height: float = 0.20
    first_layer_height: float = 0.20

    # --- Structure ---
    wall_loops: int = 3
    wall_generator: str = "classic"        # classic | arachne
    wall_sequence: str = "inner wall/outer wall"  # inner wall/outer wall | outer wall/inner wall
    top_shell_layers: int = 5
    bottom_shell_layers: int = 4
    top_one_wall_type: str = "not apply"     # not apply | all top | topmost

    # --- Remplissage ---
    infill_density: int = 20              # %
    infill_pattern: str = "grid"          # grid | gyroid | honeycomb | cubic | lightning | adaptivecubic

    # --- Surfaces ---
    top_surface_pattern: str = "monotonicline"  # monotonic | monotonicline | rectilinear | concentric

    # --- Repassage (ironing) ---
    ironing_type: str = "no ironing"      # no ironing | top | topmost | solid
    ironing_speed: float = 20.0           # mm/s
    ironing_flow: float = 15.0            # %
    ironing_spacing: float = 0.1          # mm

    # --- Adhérence plateau ---
    brim_type: str = "no_brim"            # no_brim | outer_only | inner_only | outer_and_inner
    brim_width: float = 0.0               # mm
    brim_object_gap: float = 0.0          # mm

    # --- Vitesses (mm/s) ---
    outer_wall_speed: int = 60
    inner_wall_speed: int = 100
    infill_speed: int = 200
    top_surface_speed: int = 100
    bridge_speed: int = 50
    first_layer_speed: int = 30

    # --- Qualité / Précision ---
    seam_position: str = "aligned"        # aligned | back | nearest | random
    enable_arc_fitting: bool = True
    xy_contour_compensation: float = 0.0  # mm (-0.1 à 0.1)
    elefant_foot_compensation: float = 0.1  # mm (compensation patte éléphant)

    # --- Multi-filament / AMS ---
    flush_into_infill: bool = False
    flush_into_support: bool = False
    enable_prime_tower: bool = False

    # --- Support ---
    support_type: str = "none"              # none | normal(auto) | tree(auto)
    support_threshold_angle: float = 30.0   # degrés depuis l'horizontale
    support_on_build_plate_only: bool = False
    support_top_z_distance: float = 0.20    # gap dessus support → pièce (mm)
    support_bottom_z_distance: float = 0.20 # gap pièce → dessous support (mm)

    # --- Températures (suggestions) ---
    nozzle_temperature: int = 220
    bed_temperature: int = 65

    # --- Métadonnées neoSlice ---
    neoslice_intent_text: str = ""
    neoslice_profile_name: str = ""
    neoslice_confidence: float = 1.0
    neoslice_support_mode: str = "auto"   # "auto" | "classic" | "tree"

    def estimated_filament_g(self, volume_cm3: float) -> float:
        """Estimation du filament en grammes, calibrée sur données Bambu Studio réelles."""
        # Les pièces complexes ont beaucoup de parois → wall_factor dominant vs volume
        infill_factor = 0.25 + (self.infill_density / 100) * 0.75
        wall_factor   = 0.25 + self.wall_loops * 0.10
        # Plafonné à 0.98 × densité solide (le FDM ne peut pas dépasser le plein)
        total_factor = min(infill_factor + wall_factor, 0.98)
        return volume_cm3 * 1.24 * total_factor

    def estimated_time_minutes(self, volume_cm3: float, height_mm: float, support_ratio: float = 0.0) -> int:
        """Estimation du temps total en minutes (impression + chauffe + calibration Bambu)."""
        import math
        volume_mm3 = volume_cm3 * 1000
        n_layers = max(1.0, height_mm / max(self.layer_height, 0.05))
        avg_section_mm2 = volume_mm3 / max(height_mm, 1.0)
        # Facteur 4.0 → 4.5 : les pièces complexes ont un périmètre plus long qu'un carré
        perimeter_mm = 4.5 * math.sqrt(max(avg_section_mm2, 1.0))

        wall_s   = perimeter_mm * self.wall_loops * n_layers / max(self.outer_wall_speed, 10)
        infill_s = (avg_section_mm2 * self.infill_density / 100 / 0.4) * n_layers / max(self.infill_speed, 10)
        shells_s = perimeter_mm * (self.top_shell_layers + self.bottom_shell_layers) * 0.8 / max(self.outer_wall_speed, 10)
        layer_change_s = n_layers * 3.5       # accélérations + dégagements (était 2.5)
        base_s = (wall_s + infill_s + shells_s) * 2.0 + layer_change_s  # overhead 1.35 → 2.0

        support_factor = 1.0 + min(support_ratio, 0.6) * 1.0
        print_s = base_s * support_factor

        # Temps fixe Bambu : chauffe plateau + buse + calibration 1ère couche + purge
        startup_s = 420
        return max(1, int((print_s + startup_s) / 60))
