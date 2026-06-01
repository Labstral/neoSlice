"""Installe des profils de procédé directement dans Bambu Studio.

Stratégie :
  Bambu Studio lit les profils utilisateur dans
  %APPDATA%/BambuStudio/user/<user_id>/process/<nom>.json

  Chaque profil hérite d'un profil système et ne surcharge que les
  valeurs modifiées. Format exact reverse-engineerisé depuis les fichiers
  utilisateur réels de Bambu Studio 2.3.x.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

from loguru import logger

from ..parameters.print_config import PrintConfig

# Correspondance nom UI → suffixe BBL dans les noms de profils système
# (utilisé dans le champ "inherits" du profil user installé)
_UI_TO_BBL: dict[str, str] = {
    # Série H2
    "H2D":           "H2D",
    "H2C":           "H2D",
    "H2S":           "H2D",
    "H2D Pro":       "H2D",
    # Série X
    "X1 Carbon":     "X1C",
    "X1E":           "X1C",    # X1E partage les profils process X1C
    "X2D":           "X1C",    # X2D trop récent, fallback X1C
    # Série P
    "P2S":           "P1S",    # P2S trop récent, fallback P1S
    "P1S":           "P1S",
    "P1":            "P1P",
    # Série A
    "A1":            "A1",
    "A1 Mini":       "A1M",
}

# Correspondance layer_height → (label profil, GP setting_id)
_LAYER_TIERS = [
    (0.10, "0.08mm Extra Fine", "GP001"),
    (0.12, "0.12mm Fine",       "GP002"),
    (0.15, "0.12mm Fine",       "GP002"),
    (0.16, "0.16mm Optimal",    "GP003"),
    (0.20, "0.20mm Standard",   "GP004"),
    (0.24, "0.24mm Draft",      "GP006"),
    (0.28, "0.28mm Extra Draft","GP007"),
]


def _layer_to_base(layer_height: float, bbl_id: str) -> tuple[str, str]:
    """Retourne (nom_profil_système, gp_id) pour le layer_height et le modèle donnés."""
    closest = min(_LAYER_TIERS, key=lambda t: abs(t[0] - layer_height))
    return f"{closest[1]} @BBL {bbl_id}", closest[2]


class BambuProfileInstaller:
    """Génère et installe un profil de procédé Bambu Studio."""

    def __init__(self):
        self._bambu_user_dir = self._find_bambu_user_dir()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def install_profile(
        self,
        config: PrintConfig,
        profile_label: str = "",
        printer_ui_name: str = "X1 Carbon",
    ) -> tuple[bool, str, Path | None]:
        """Installe un profil dans Bambu Studio.

        Retourne (succès, message, chemin_fichier).
        """
        if self._bambu_user_dir is None:
            return False, "Bambu Studio non trouvé dans AppData", None

        process_dir = self._bambu_user_dir / "process"
        process_dir.mkdir(parents=True, exist_ok=True)

        bbl_id = _UI_TO_BBL.get(printer_ui_name, "X1C")
        name = profile_label or f"neoSlice - {config.neoslice_profile_name.replace('_', ' ').title()}"
        profile_json = self._build_profile_json(config, name, bbl_id)
        info_txt = self._build_info_file(name, bbl_id)

        json_path = process_dir / f"{name}.json"
        info_path = process_dir / f"{name}.info"

        try:
            json_path.write_text(
                json.dumps(profile_json, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            info_path.write_text(info_txt, encoding="utf-8")
            logger.info(f"Profil Bambu installé : {json_path}")
            return True, name, json_path
        except OSError as e:
            logger.error(f"Erreur d'écriture profil Bambu : {e}")
            return False, str(e), None

    def is_available(self) -> bool:
        return self._bambu_user_dir is not None

    def get_process_dir(self) -> Path | None:
        if self._bambu_user_dir:
            return self._bambu_user_dir / "process"
        return None

    # ------------------------------------------------------------------
    # Construction du profil JSON
    # ------------------------------------------------------------------

    def _build_profile_json(self, config: PrintConfig, name: str, bbl_id: str = "X1C") -> dict:
        """Construit le dict JSON au format exact Bambu Studio 2.3.x."""

        base_name, base_id = _layer_to_base(config.layer_height, bbl_id)

        profile = {
            "from": "User",
            "inherits": base_name,
            "name": name,
            "print_settings_id": name,
            "version": "2.3.0.2",
        }

        # --- Couches ---
        profile["layer_height"] = str(config.layer_height)
        profile["initial_layer_print_height"] = str(config.first_layer_height)

        # --- Structure ---
        profile["wall_loops"] = str(config.wall_loops)
        profile["top_shell_layers"] = str(config.top_shell_layers)
        profile["bottom_shell_layers"] = str(config.bottom_shell_layers)

        # --- Remplissage ---
        profile["sparse_infill_density"] = f"{config.infill_density}%"
        profile["sparse_infill_pattern"] = config.infill_pattern

        # --- Brim ---
        if config.brim_type != "no_brim" and config.brim_width > 0:
            profile["brim_type"] = config.brim_type
            profile["brim_width"] = str(config.brim_width)

        # --- Vitesses (format tableau ["val_standard", "val_high_flow"]) ---
        profile["outer_wall_speed"] = [str(config.outer_wall_speed), str(config.outer_wall_speed)]
        profile["inner_wall_speed"] = [str(config.inner_wall_speed), str(config.inner_wall_speed)]
        profile["sparse_infill_speed"] = [str(config.infill_speed), str(config.infill_speed)]
        profile["initial_layer_speed"] = [str(config.first_layer_speed), str(config.first_layer_speed)]

        # --- Qualité ---
        profile["seam_position"] = config.seam_position
        # Explicitement défini pour éviter d'hériter la valeur obsolète "rectilinear"
        # du profil système parent (qui provoque un avertissement BS)
        tsp = config.top_surface_pattern
        _LEGACY = {"rectilinear": "zig-zag", "alignedrectilinear": "zig-zag"}
        profile["top_surface_pattern"] = _LEGACY.get(tsp, tsp)

        # Identifiants extrudeur (obligatoires pour certaines versions BS)
        profile["print_extruder_id"] = ["1", "1"]
        profile["print_extruder_variant"] = [
            "Direct Drive Standard",
            "Direct Drive High Flow",
        ]

        return profile

    def _build_info_file(self, name: str, bbl_id: str = "X1C") -> str:
        """Construit le fichier .info au format Bambu Studio."""
        user_id = self._bambu_user_dir.name if self._bambu_user_dir else "default"
        _, base_id = _layer_to_base(0.20, bbl_id)
        timestamp = int(time.time())
        return (
            f"sync_info = \n"
            f"user_id = {user_id}\n"
            f"setting_id = NP_{name[:20].replace(' ', '_')}\n"
            f"base_id = {base_id}\n"
            f"updated_time = {timestamp}\n"
        )

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _find_bambu_user_dir(self) -> Path | None:
        """Trouve le dossier utilisateur actif de Bambu Studio."""
        from .bambu_config_resolver import _bbl_root
        bambu_user = _bbl_root() / "user"

        if not bambu_user.exists():
            logger.warning("Bambu Studio non trouvé")
            return None

        # Priorité aux dossiers numériques (compte connecté)
        user_dirs = sorted(
            [d for d in bambu_user.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

        if user_dirs:
            logger.info(f"Dossier Bambu utilisateur : {user_dirs[0]}")
            return user_dirs[0]

        default = bambu_user / "default"
        if default.exists():
            return default

        return None
