from __future__ import annotations
from pathlib import Path

import yaml
from loguru import logger

from .print_config import PrintConfig
from ..intent.intent_profiles import IntentProfile
from ..geometry.analysis_report import AnalysisReport

_PROFILES_DIR = Path(__file__).parent / "profiles"

# Intention dominante → fichier YAML de base
_INTENT_TO_PROFILE: dict[str, str] = {
    "strength":           "ultra_solid.yaml",
    "speed":              "ultra_fast.yaml",
    "quality":            "best_quality.yaml",
    "surface_finish":     "best_quality.yaml",
    "filament_saving":    "save_filament.yaml",
    "outdoor_resistance": "outdoor_resistant.yaml",
}

# Vitesses maximales absolues (mm/s) par matériau
# Source : Bambu Studio process profiles + validation terrain
_MATERIAL_SPEED_LIMITS: dict[str, tuple[int, int]] = {
    # matériau → (max_outer_wall, max_infill)
    "PLA":          (120, 200),
    "PLA+":         (120, 200),
    "PLA-CF":       (80,  150),
    "PLA Matte":    (100, 200),
    "PLA Silk":     (80,  150),
    "PETG":         (80,  150),
    "PETG-CF":      (60,  120),
    "ABS":          (60,  150),
    "ASA":          (60,  150),
    "Nylon":        (50,  100),
    "PC":           (40,  80),
    "PA":           (50,  100),
    "PA-CF":        (40,  80),
    "TPU":          (25,  60),
    "TPE":          (20,  50),
    "HIPS":         (80,  150),
    "PVA":          (40,  80),
}

# Matériaux haute température (enceinte requise, comportements spéciaux)
_HIGH_TEMP_MATERIALS = frozenset({"ABS", "ASA", "PC", "PA", "PA-CF", "Nylon"})
# Matériaux flexibles — limites vitesse et pattern infill
_FLEXIBLE_MATERIALS = frozenset({"TPU", "TPE"})
# Matériaux avec retrait élevé → brim recommandé
_WARP_PRONE_MATERIALS = frozenset({"ABS", "ASA", "PC", "PA", "PA-CF", "Nylon"})


class ParameterEngine:
    """Traduit IntentProfile + AnalysisReport + filament en PrintConfig Bambu Studio.

    Ordre de priorité (décroissant) :
      1. Sécurité matériau   — vitesse max, température, retrait
      2. Géométrie           — surplombs, fragilité, stabilité
      3. Mission/intention   — profil de base + intentions secondaires
      4. Defaults Bambu      — tout le reste
    """

    # Hauteurs de couche min/max par diamètre de buse (valeurs Bambu Studio)
    _NOZZLE_LAYER_LIMITS: dict[float, tuple[float, float]] = {
        0.2: (0.05, 0.10),
        0.4: (0.08, 0.28),
        0.6: (0.15, 0.45),
        0.8: (0.20, 0.60),
    }

    def generate(
        self,
        intent: IntentProfile,
        analysis: AnalysisReport,
        filament_name: str = "",
        printer_name: str = "",
        nozzle_diameter_mm: float = 0.4,
    ) -> PrintConfig:
        # 1. Profil de base selon l'intention dominante
        base = self._load_base_profile(intent)
        logger.info(f"Profil de base : {base.neoslice_profile_name}")

        # 2. Intentions secondaires
        base = self._blend_secondary_intents(base, intent)

        # 3. Modificateurs géométriques (priorité > mission)
        base = self._apply_geometry_modifiers(base, analysis, intent)

        # 4. Profil matériau (priorité > géométrie sur les vitesses / temps)
        if filament_name:
            base = self._apply_material_profile(base, filament_name, analysis)

        # 5. Validation finale (avec contraintes buse)
        base = self._validate_constraints(base, filament_name, nozzle_diameter_mm)

        # 6. Métadonnées
        base.neoslice_intent_text = intent.human_summary()
        base.neoslice_confidence = intent.dominant_score

        return base

    # ──────────────────────────────────────────────────────────────────
    # Chargement du profil de base
    # ──────────────────────────────────────────────────────────────────

    def _load_base_profile(self, intent: IntentProfile) -> PrintConfig:
        if intent.dominant_score < 0.1:
            config = PrintConfig()
            config.neoslice_profile_name = "standard"
            return config

        # Score trop faible pour déterminer une intention claire → standard
        if intent.dominant_score <= 0.5:
            config = PrintConfig()
            config.neoslice_profile_name = "standard"
            return config

        intent_name = intent.dominant_intent
        score = intent.dominant_score

        if intent_name == "strength":
            profile_file = "ultra_solid.yaml" if score >= 0.9 else "strong.yaml"
        elif intent_name == "speed":
            profile_file = "ultra_fast.yaml" if score >= 0.9 else "fast.yaml"
        elif intent_name == "quality":
            profile_file = "best_quality.yaml" if score >= 0.9 else "fine.yaml"
        else:
            profile_file = _INTENT_TO_PROFILE.get(intent_name, "standard.yaml")

        path = _PROFILES_DIR / profile_file
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        valid_keys = PrintConfig.model_fields.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        config = PrintConfig(**filtered)
        config.neoslice_profile_name = data.get("name", profile_file)
        return config

    # ──────────────────────────────────────────────────────────────────
    # Intentions secondaires
    # ──────────────────────────────────────────────────────────────────

    def _blend_secondary_intents(
        self, config: PrintConfig, intent: IntentProfile
    ) -> PrintConfig:
        dom = intent.dominant_intent

        # Vitesse secondaire → accélérer couche haute + infill
        if intent.speed > 0.5 and dom != "speed":
            factor = (intent.speed - 0.5) * 0.8          # 0.0 → 0.4
            config.outer_wall_speed = int(config.outer_wall_speed * (1 + factor * 0.5))
            config.infill_speed = int(config.infill_speed * (1 + factor))
            config.layer_height = round(min(0.28, config.layer_height + factor * 0.08), 2)

        # Qualité surface secondaire
        if intent.surface_finish > 0.5 and dom not in ("quality", "surface_finish"):
            config.seam_position = "back"
            config.outer_wall_speed = int(config.outer_wall_speed * 0.85)
        if intent.surface_finish > 0.7:
            config.ironing_type = "top"
            config.top_one_wall_type = "all top"
            config.top_surface_pattern = "monotonic"
            config.wall_generator = "arachne"
            config.wall_sequence = "outer wall/inner wall"

        # Économie filament secondaire
        if intent.filament_saving > 0.6 and dom != "filament_saving":
            config.infill_density = max(5, int(config.infill_density * 0.7))
            if config.infill_pattern in ("gyroid", "grid", "honeycomb"):
                config.infill_pattern = "lightning"

        # Solidité secondaire → parois + pattern isotrope
        if intent.strength > 0.6 and dom != "strength":
            config.wall_loops = max(config.wall_loops, 3)
            # Gyroid dès que résistance est demandée, quelle que soit la densité
            if config.infill_pattern in ("grid", "honeycomb", "lightning"):
                config.infill_pattern = "gyroid"

        # Résistance extérieure secondaire
        if intent.outdoor_resistance > 0.5 and dom != "outdoor_resistance":
            config.wall_loops = max(config.wall_loops, 4)
            config.infill_density = max(config.infill_density, 35)
            config.infill_pattern = "gyroid"
            config.top_shell_layers = max(config.top_shell_layers, 6)
            config.bottom_shell_layers = max(config.bottom_shell_layers, 5)

        # Précision dimensionnelle → arachne + coutures alignées + compensation XY
        if getattr(intent, "precision", 0.0) > 0.5:
            config.wall_generator = "arachne"
            config.wall_sequence = "outer wall/inner wall"
            config.seam_position = "aligned"
            config.wall_loops = max(config.wall_loops, 4)
            config.layer_height = round(min(config.layer_height, 0.15), 3)
            config.infill_pattern = "adaptivecubic"
            config.top_surface_pattern = "monotonic"
            if getattr(intent, "precision", 0.0) > 0.8:
                config.xy_contour_compensation = -0.05   # compense l'expansion plastique
                config.elefant_foot_compensation = 0.05

        # Silencieux → -40% vitesses sur tous les axes
        if getattr(intent, "silent", 0.0) > 0.5:
            factor = 0.60
            config.outer_wall_speed = int(config.outer_wall_speed * factor)
            config.inner_wall_speed = int(config.inner_wall_speed * factor)
            config.infill_speed = int(config.infill_speed * factor)
            config.top_surface_speed = int(config.top_surface_speed * factor)
            config.bridge_speed = int(config.bridge_speed * factor)
            config.first_layer_speed = int(config.first_layer_speed * factor)

        # Multicolore AMS → prime tower + flush management
        if getattr(intent, "multicolor", 0.0) > 0.5:
            config.enable_prime_tower = True
            config.flush_into_infill = True
            config.flush_into_support = False
            config.seam_position = "back"
            if config.infill_density < 15:
                config.infill_density = 15   # flush nécessite un infill minimum

        return config

    # ──────────────────────────────────────────────────────────────────
    # Modificateurs géométriques
    # ──────────────────────────────────────────────────────────────────

    def _apply_geometry_modifiers(
        self,
        config: PrintConfig,
        analysis: AnalysisReport,
        intent: IntentProfile,
    ) -> PrintConfig:
        """Règles géométriques — priorité sur mission, sous priorité matériau."""

        # ── Stabilité / Brim ─────────────────────────────────────────
        if analysis.stability_score < 0.30:
            config.brim_type = "outer_only"
            config.brim_width = max(12.0, analysis.brim_recommendation_mm)
            config.first_layer_speed = min(config.first_layer_speed, 25)
            config.elefant_foot_compensation = 0.15
        elif analysis.stability_score < 0.50:
            config.brim_type = "outer_only"
            config.brim_width = max(8.0, analysis.brim_recommendation_mm)
            config.first_layer_speed = min(config.first_layer_speed, 30)
        elif analysis.stability_score < 0.65 or analysis.is_large_flat_part:
            config.brim_type = "outer_only"
            config.brim_width = max(5.0, analysis.brim_recommendation_mm)

        # ── Grande pièce plate → warping ─────────────────────────────
        if analysis.is_large_flat_part:
            if config.brim_type == "no_brim":
                config.brim_type = "outer_only"
                config.brim_width = max(config.brim_width, 5.0)
            config.bottom_shell_layers = max(config.bottom_shell_layers, 5)
            config.first_layer_speed = min(config.first_layer_speed, 30)

        # ── Fragilité → arachne + parois + bridge lent ───────────────
        if analysis.has_fragile_zones:
            config.wall_loops = max(config.wall_loops, 4)
            config.outer_wall_speed = min(config.outer_wall_speed, 45)
            config.top_shell_layers = max(config.top_shell_layers, 6)
            config.wall_generator = "arachne"
            if analysis.fragility_severity > 0.6:
                config.wall_loops = max(config.wall_loops, 5)
                config.outer_wall_speed = min(config.outer_wall_speed, 35)
                config.bridge_speed = min(config.bridge_speed, 25)

        # ── Surplombs → bridge speed + support ───────────────────────
        if analysis.overhang_severity > 0.0:
            if analysis.max_overhang_angle > 60:
                config.bridge_speed = min(config.bridge_speed, 25)
            elif analysis.max_overhang_angle > 45:
                config.bridge_speed = min(config.bridge_speed, 35)
            elif analysis.max_overhang_angle > 30:
                config.bridge_speed = min(config.bridge_speed, 45)

        if analysis.support_needed:
            # Arborescents par défaut — plus faciles à retirer, meilleure qualité de surface
            config.support_type = "tree(auto)"
            # Angle de déclenchement basé sur l'analyse réelle
            raw_angle = 90.0 - analysis.max_overhang_angle
            config.support_threshold_angle = float(max(20.0, min(45.0, raw_angle + 5.0)))
            # Toujours False : impossible de déterminer fiablement si les surplombs
            # sont tous au-dessus du plateau sans simulation couche par couche
            config.support_on_build_plate_only = False

        # ── Mission solidité → minimum structurel ────────────────────
        if intent.strength > 0.7:
            config.wall_loops = max(config.wall_loops, 4)
            config.infill_density = max(config.infill_density, 40)
            if config.infill_density >= 50 and config.infill_pattern in ("grid", "honeycomb"):
                config.infill_pattern = "gyroid"

        # ── Volume important → optimiser le pattern ───────────────────
        if analysis.volume_cm3 > 150 and config.infill_density < 15:
            config.infill_pattern = "lightning"

        return config

    # ──────────────────────────────────────────────────────────────────
    # Profil matériau
    # ──────────────────────────────────────────────────────────────────

    def _apply_material_profile(
        self,
        config: PrintConfig,
        filament_name: str,
        analysis: AnalysisReport,
    ) -> PrintConfig:
        """Applique les contraintes physiques du matériau. Priorité maximale."""
        try:
            from data.filaments import FILAMENTS
            fil = FILAMENTS.get(filament_name, {})
        except Exception:
            fil = {}

        if not fil:
            # Fallback sur la table interne si filament inconnu
            return self._apply_speed_limits(config, filament_name)

        # Températures depuis la base de données filaments
        config.nozzle_temperature = fil.get("buse_1ere", 220)
        config.bed_temperature = fil.get("plateau", 60)

        # Vitesses maximales absolues du matériau
        mat_max_outer = fil.get("mur_exterieur", 150)
        mat_max_infill = fil.get("remplissage", 300)
        self._cap_speeds(config, mat_max_outer, mat_max_infill)

        # Filaments flexibles — contraintes spécifiques
        if filament_name in _FLEXIBLE_MATERIALS:
            config.outer_wall_speed = min(config.outer_wall_speed, 25)
            config.inner_wall_speed = min(config.inner_wall_speed, 40)
            config.infill_speed = min(config.infill_speed, 60)
            config.bridge_speed = min(config.bridge_speed, 20)
            config.first_layer_speed = min(config.first_layer_speed, 20)
            config.wall_loops = max(config.wall_loops, 3)
            # Gyroid = seul pattern fiable sur TPU/TPE (flexible, pas de ponts droits)
            if config.infill_pattern in ("lightning", "adaptivecubic", "grid"):
                config.infill_pattern = "gyroid"
            config.infill_density = max(config.infill_density, 15)

        # Matériaux haute temp → première couche lente + min parois
        if filament_name in _HIGH_TEMP_MATERIALS:
            config.wall_loops = max(config.wall_loops, 3)
            config.first_layer_speed = min(config.first_layer_speed, 30)

        # Matériaux sujets au warping → forcer brim si pas déjà déclenché
        if filament_name in _WARP_PRONE_MATERIALS and config.brim_type == "no_brim":
            config.brim_type = "outer_only"
            config.brim_width = max(config.brim_width, 5.0)

        # ABS/ASA → top shells supplémentaires (retrait cause underextrusion surface)
        if filament_name in ("ABS", "ASA"):
            config.top_shell_layers = max(config.top_shell_layers, 5)
            config.bottom_shell_layers = max(config.bottom_shell_layers, 4)

        return config

    def _apply_speed_limits(self, config: PrintConfig, filament_name: str) -> PrintConfig:
        """Fallback : applique les limites de vitesse depuis la table interne."""
        limits = _MATERIAL_SPEED_LIMITS.get(filament_name)
        if limits:
            self._cap_speeds(config, limits[0], limits[1])
        return config

    def _cap_speeds(self, config: PrintConfig, max_outer: int, max_infill: int) -> None:
        """Cap les vitesses sans dépasser les maxima matériau."""
        fields = config.model_fields_set
        if "outer_wall_speed" in fields:
            config.outer_wall_speed = min(config.outer_wall_speed, max_outer)
        if "inner_wall_speed" in fields:
            config.inner_wall_speed = min(config.inner_wall_speed, max_infill)
        if "infill_speed" in fields:
            config.infill_speed = min(config.infill_speed, max_infill)
        if "top_surface_speed" in fields:
            config.top_surface_speed = min(config.top_surface_speed, max_outer)

    # ──────────────────────────────────────────────────────────────────
    # Validation finale
    # ──────────────────────────────────────────────────────────────────

    def _validate_constraints(
        self,
        config: PrintConfig,
        filament_name: str = "",
        nozzle_diameter_mm: float = 0.4,
    ) -> PrintConfig:
        fields = config.model_fields_set

        # Hauteur de couche — clamping selon le diamètre de buse (valeurs Bambu Studio)
        if "layer_height" in fields:
            closest_nozzle = min(self._NOZZLE_LAYER_LIMITS, key=lambda n: abs(n - nozzle_diameter_mm))
            lh_min, lh_max = self._NOZZLE_LAYER_LIMITS[closest_nozzle]
            config.layer_height = round(max(lh_min, min(lh_max, config.layer_height)), 3)
            logger.debug(f"Buse {nozzle_diameter_mm}mm → couche clamped [{lh_min}, {lh_max}] → {config.layer_height}")

            # Distance Z support proportionnelle à la hauteur de couche (≈1.2× layer_height)
            # → ~1 couche et quart de gap quelle que soit la résolution
            # Min 0.10mm, Max 0.30mm
            z_dist = round(max(0.10, min(0.30, config.layer_height * 1.2)), 2)
            config.support_top_z_distance = z_dist
            config.support_bottom_z_distance = z_dist

        # Première couche
        if "first_layer_height" in fields:
            config.first_layer_height = round(max(0.15, config.first_layer_height), 3)
            # Toujours >= layer_height (sinon Bambu Studio refuse)
            if "layer_height" in fields:
                config.first_layer_height = round(
                    max(config.first_layer_height, config.layer_height), 3
                )

        # AMS : flush dans infill impossible si infill nul
        if "flush_into_infill" in fields and config.flush_into_infill and config.infill_density == 0:
            config.flush_into_infill = False

        # Cohérence brim
        if "brim_type" in fields and config.brim_type != "no_brim":
            if config.brim_width <= 0:
                config.brim_width = 5.0

        # Top one wall nécessite au moins 2 parois
        if "top_one_wall_type" in fields and config.top_one_wall_type != "not apply":
            if config.wall_loops < 2:
                config.top_one_wall_type = "not apply"

        # Vitesses minimales absolues (Bambu Studio instable en dessous)
        if "outer_wall_speed" in fields:
            config.outer_wall_speed = max(15, config.outer_wall_speed)
        if "inner_wall_speed" in fields:
            config.inner_wall_speed = max(20, config.inner_wall_speed)
        if "infill_speed" in fields:
            config.infill_speed = max(30, config.infill_speed)
        if "bridge_speed" in fields:
            config.bridge_speed = max(15, min(80, config.bridge_speed))
        if "first_layer_speed" in fields:
            config.first_layer_speed = max(15, config.first_layer_speed)

        # Cohérence support : threshold entre 20° et 60°
        if "support_threshold_angle" in fields:
            config.support_threshold_angle = max(20.0, min(60.0, config.support_threshold_angle))

        return config
