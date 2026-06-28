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
    seam_gap: float = 15.0                # % rétraction au niveau de la couture (0 = collé)

    # --- Surplombs / Ponts (qualité des porte-à-faux) ---
    detect_overhang_wall: bool = True     # détecter les parois en surplomb (oblig. pour ralentir)
    slow_down_overhangs: bool = False     # ralentir les surplombs raides → moins d'affaissement
    overhang_1_4_speed: int = 0           # 0-25 % de surplomb : 0 = vitesse normale
    overhang_2_4_speed: int = 50          # 25-50 %
    overhang_3_4_speed: int = 30          # 50-75 %
    overhang_4_4_speed: int = 10          # 75-100 % (le plus raide → le plus lent)
    bridge_flow: float = 0.95             # ratio de débit sur les ponts (étirement à chaud)

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
    # Interface de supports — dessous propre + retrait facile (réglages "ajusté")
    support_interface_top_layers: int = 3       # couches solides de contact dessus
    support_interface_bottom_layers: int = 1
    support_interface_spacing: float = 0.2      # espacement serré → surface lisse
    support_interface_pattern: str = "rectilinear"  # auto | rectilinear | concentric
    support_object_xy_distance: float = 0.35    # gap horizontal support ↔ pièce (mm)

    # --- Températures (suggestions) ---
    nozzle_temperature: int = 220
    bed_temperature: int = 65

    # --- Métadonnées neoSlice ---
    filament_density_g_cm3: float = 1.24   # densité matériau (estimation du poids)
    neoslice_printer: str = ""             # imprimante cible (limites appliquées)
    neoslice_intent_text: str = ""
    neoslice_profile_name: str = ""
    neoslice_confidence: float = 1.0
    neoslice_support_mode: str = "auto"   # "auto" | "classic" | "tree"

    def estimated_filament_g(self, volume_cm3: float, surface_area_cm2: float = 0.0) -> float:
        """Estimation du poids de filament (g).

        Si la SURFACE réelle de la pièce est fournie (depuis l'analyse mesh), on
        utilise un modèle PHYSIQUE conscient de la taille :
            coque  ≈ surface × parois (les murs verticaux) + peaux haut/bas
            poids  ≈ densité × [ coque + remplissage × (volume − coque) ]
        Bien plus juste que l'ancien modèle de ratio sur petites ET grandes pièces.
        Coefficients calibrés sur des mesures PrusaSlicer (buse 0.4). Sans surface,
        on retombe sur un modèle de ratio (parois/peaux/remplissage)."""
        density = max(0.1, self.filament_density_g_cm3)
        infill = max(0.0, min(1.0, self.infill_density / 100.0))
        vol = max(0.0, volume_cm3)
        skins = self.top_shell_layers + self.bottom_shell_layers

        if surface_area_cm2 and surface_area_cm2 > 0:
            # Parois ∝ surface (~0.20 mm équivalent par paroi sur la surface totale,
            # calibré) ; peaux haut/bas ∝ volume (forfait par couche solide, plafonné).
            wall_vol = surface_area_cm2 * self.wall_loops * 0.020
            skin_vol = vol * min(0.30, skins * 0.02)
            shell_vol = min(vol, wall_vol + skin_vol)
            material_vol = shell_vol + infill * max(0.0, vol - shell_vol)
            material_vol = min(material_vol, vol * 0.92)   # un "plein" réel ≈ 92 % du géométrique
            return material_vol * density

        # Repli (pas de surface) : modèle de ratio parois/peaux/remplissage.
        shell_share = min(0.60, 0.10 + 0.04 * self.wall_loops + 0.02 * skins)
        effective = min(0.95, max(0.05, infill + (1.0 - infill) * shell_share))
        return vol * density * effective

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
