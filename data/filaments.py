"""Base de données complète des filaments Bambu Lab / FDM."""
from __future__ import annotations

FILAMENTS: dict[str, dict] = {

    "PLA": {
        "famille": "Standard",
        "buse_1ere": 220, "buse_autres": 215,
        "plateau": 60,
        "ventilateur_max": 100, "ventilation_active": True,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 20,
        "ventilateur_surplombs": 100,
        "ventiler_surplombs_depassant": 50,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 20,
        "volumetrique_max": 21,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 45,
        "enceinte_requise": False,
        "sechage": "45°C / 4h si humide",
        "mur_exterieur": 120, "remplissage": 200,
        "warnings": [],
        "notes": "Filament le plus facile à imprimer. Biodégradable. Non adapté à l'extérieur.",
    },

    "PETG": {
        "famille": "Standard",
        "buse_1ere": 250, "buse_autres": 250,
        "plateau": 70,
        "ventilateur_max": 40, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 10,
        "ventilateur_surplombs": 50,
        "ventiler_surplombs_depassant": 50,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 15,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 70,
        "enceinte_requise": False,
        "sechage": "65°C / 4h si humide",
        "mur_exterieur": 80, "remplissage": 150,
        "warnings": ["Ne jamais utiliser le Cool Plate sans release agent"],
        "notes": "Bon compromis résistance/facilité. Résistant aux intempéries.",
    },

    "ABS": {
        "famille": "Technique",
        "buse_1ere": 265, "buse_autres": 255,
        "plateau": 100,
        "ventilateur_max": 10, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 5,
        "ventilateur_surplombs": 30,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 18,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 95,
        "enceinte_requise": True,
        "sechage": "70°C / 4h si humide",
        "mur_exterieur": 60, "remplissage": 150,
        "warnings": [
            "Enceinte fermée OBLIGATOIRE — préchauffer à 40-45°C",
            "Fumées toxiques — ventiler la pièce",
        ],
        "notes": "Résistant aux chocs. Post-traitement à l'acétone possible.",
    },

    "ASA": {
        "famille": "Technique",
        "buse_1ere": 265, "buse_autres": 260,
        "plateau": 105,
        "ventilateur_max": 30, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 5,
        "ventilateur_surplombs": 55,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 12,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 98,
        "enceinte_requise": True,
        "sechage": "70°C / 4h si humide",
        "mur_exterieur": 60, "remplissage": 150,
        "warnings": [
            "Enceinte fermée OBLIGATOIRE — préchauffer à 40-45°C",
            "Plateau texturé à 105°C obligatoire",
        ],
        "notes": "Idéal pour pièces extérieures. Excellente résistance UV.",
    },

    "Nylon": {
        # `label` = nom AFFICHÉ (sélecteur, récapitulatif). La CLÉ « Nylon »
        # reste l'identifiant interne (moteur, tables sécurité, export 3MF).
        "label": "Nylon (PA)",
        "famille": "Technique",
        "buse_1ere": 260, "buse_autres": 255,
        "plateau": 70,
        "ventilateur_max": 20, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 5,
        "ventilateur_surplombs": 30,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 12,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 85,
        "enceinte_requise": True,
        "sechage": "80°C / 8h OBLIGATOIRE avant impression",
        "mur_exterieur": 50, "remplissage": 100,
        "warnings": [
            "Séchage OBLIGATOIRE — 80°C pendant 8h avant impression",
            "Stocker sous vide — filament très hygroscopique",
        ],
        "notes": "Résistance à l'usure extrême. Flexible et durable.",
    },

    "PC": {
        "famille": "Technique",
        "buse_1ere": 300, "buse_autres": 295,
        "plateau": 120,
        "ventilateur_max": 5, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 0,
        "ventilateur_surplombs": 20,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 10,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 115,
        "enceinte_requise": True,
        "sechage": "80°C / 8h OBLIGATOIRE avant impression",
        "mur_exterieur": 40, "remplissage": 80,
        "warnings": [
            "Enceinte OBLIGATOIRE — viser 50-60°C",
            "Buse hardened steel obligatoire",
            "Séchage OBLIGATOIRE — 80°C pendant 8h avant impression",
        ],
        "notes": "Rigidité extrême. Tenue thermique jusqu'à 120°C+.",
    },

    "TPU": {
        "famille": "Souple",
        "buse_1ere": 225, "buse_autres": 220,
        "plateau": 40,
        "ventilateur_max": 80, "ventilation_active": True,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 30,
        "ventilateur_surplombs": 80,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 15,
        "volumetrique_max": 5,
        "retraction_longueur": 0.5,
        "retraction_vitesse": 25,
        "retraction_reinsertion": 25,
        "retraction_longue_coupe": False,
        "retraction_distance_coupe": None,
        "rapport_debit": 0.98,
        "ramollissement": 60,
        "enceinte_requise": False,
        "sechage": "50°C / 4h si humide",
        "mur_exterieur": 25, "remplissage": 40,
        "warnings": [
            "INCOMPATIBLE AMS — charger en direct uniquement",
            "Vitesse maximale 25 mm/s — ne pas dépasser",
            "Forcer la rétraction dans l'onglet Forçage des réglages",
        ],
        "notes": "Très flexible. Idéal pour joints, coques, pneus.",
    },

    "TPE": {
        "famille": "Souple",
        "buse_1ere": 220, "buse_autres": 215,
        "plateau": 40,
        "ventilateur_max": 60, "ventilation_active": True,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 20,
        "ventilateur_surplombs": 60,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 15,
        "volumetrique_max": 4,
        "retraction_longueur": 0.5,
        "retraction_vitesse": 20,
        "retraction_reinsertion": 20,
        "retraction_longue_coupe": False,
        "retraction_distance_coupe": None,
        "rapport_debit": 0.98,
        "ramollissement": 55,
        "enceinte_requise": False,
        "sechage": "50°C / 4h si humide",
        "mur_exterieur": 20, "remplissage": 35,
        "warnings": [
            "INCOMPATIBLE AMS — charger en direct uniquement",
            "Plus souple que TPU — réduire encore les vitesses",
            "Forcer la rétraction dans l'onglet Forçage des réglages",
        ],
        "notes": "Plus souple que TPU. Mêmes précautions d'impression.",
    },

    "PLA-CF": {
        "famille": "Chargé",
        "buse_1ere": 225, "buse_autres": 220,
        "plateau": 60,
        "ventilateur_max": 100, "ventilation_active": True,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 20,
        "ventilateur_surplombs": 100,
        "ventiler_surplombs_depassant": 50,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 20,
        "volumetrique_max": 15,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 45,
        "enceinte_requise": False,
        "sechage": "45°C / 4h si humide",
        "mur_exterieur": 80, "remplissage": 150,
        "warnings": ["Buse hardened steel OBLIGATOIRE — filament très abrasif"],
        "notes": "Rigidité supérieure au PLA. Plus cassant. Non flexible.",
    },

    "PETG-CF": {
        "famille": "Chargé",
        "buse_1ere": 240, "buse_autres": 235,
        "plateau": 70,
        "ventilateur_max": 30, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 10,
        "ventilateur_surplombs": 40,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 12,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 75,
        "enceinte_requise": False,
        "sechage": "65°C / 4h si humide",
        "mur_exterieur": 60, "remplissage": 120,
        "warnings": ["Buse hardened steel OBLIGATOIRE — filament très abrasif"],
        "notes": "Excellent compromis rigidité/légèreté.",
    },

    "PA-CF": {
        "famille": "Chargé",
        "buse_1ere": 270, "buse_autres": 265,
        "plateau": 80,
        "ventilateur_max": 15, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 5,
        "ventilateur_surplombs": 25,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 10,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 90,
        "enceinte_requise": True,
        "sechage": "80°C / 8h OBLIGATOIRE avant impression",
        "mur_exterieur": 40, "remplissage": 80,
        "warnings": [
            "Buse hardened steel OBLIGATOIRE — filament très abrasif",
            "Séchage OBLIGATOIRE — 80°C pendant 8h avant impression",
            "Enceinte fortement recommandée",
        ],
        "notes": "Résistance mécanique maximale parmi les filaments FDM.",
    },

    "PLA Bois": {
        "famille": "Spécial",
        "buse_1ere": 220, "buse_autres": 215,
        "plateau": 60,
        "ventilateur_max": 100, "ventilation_active": True,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 20,
        "ventilateur_surplombs": 100,
        "ventiler_surplombs_depassant": 50,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 20,
        "volumetrique_max": 10,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.95,
        "ramollissement": 45,
        "enceinte_requise": False,
        "sechage": "45°C / 4h si humide",
        "mur_exterieur": 50, "remplissage": 100,
        "warnings": [
            "Buse 0.6mm recommandée pour éviter les bouchages",
            "Ne pas dépasser 230°C — risque de brûlure des fibres",
        ],
        "notes": "Aspect et odeur naturels. Ponçable et teignable.",
    },

    "PLA Métallique": {
        "famille": "Spécial",
        "buse_1ere": 220, "buse_autres": 215,
        "plateau": 60,
        "ventilateur_max": 100, "ventilation_active": True,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 20,
        "ventilateur_surplombs": 100,
        "ventiler_surplombs_depassant": 50,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 20,
        "volumetrique_max": 8,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.95,
        "ramollissement": 45,
        "enceinte_requise": False,
        "sechage": "45°C / 4h si humide",
        "mur_exterieur": 40, "remplissage": 80,
        "warnings": [
            "Buse hardened steel OBLIGATOIRE — filament très abrasif",
            "Polissable après impression pour effet métal",
        ],
        "notes": "Chargé en particules métalliques. Aspect réaliste.",
    },

    "HIPS": {
        "famille": "Support",
        "buse_1ere": 240, "buse_autres": 235,
        "plateau": 100,
        "ventilateur_max": 10, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 5,
        "ventilateur_surplombs": 30,
        "ventiler_surplombs_depassant": 25,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": True,
        "vitesse_min_impression": 20,
        "volumetrique_max": 15,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.98,
        "ramollissement": 90,
        "enceinte_requise": True,
        "sechage": "70°C / 4h si humide",
        "mur_exterieur": 60, "remplissage": 150,
        "warnings": [
            "Utiliser exclusivement comme support ABS via AMS",
            "Soluble dans le limonène — dissoudre après impression",
        ],
        "notes": "Filament de support pour ABS. Compatibilité thermique parfaite.",
    },

    "PVA": {
        "famille": "Support",
        "buse_1ere": 215, "buse_autres": 210,
        "plateau": 60,
        "ventilateur_max": 50, "ventilation_active": False,
        "ventilateur_1ere_couche": 0,
        "ventilateur_seuil_mini": 20,
        "ventilateur_surplombs": 50,
        "ventiler_surplombs_depassant": 50,
        "forcer_ventilation_surplombs": True,
        "ralentir_refroidir": True,
        "ne_pas_ralentir_parois": False,
        "vitesse_min_impression": 20,
        "volumetrique_max": 8,
        "retraction_longueur": None,
        "retraction_vitesse": None,
        "retraction_reinsertion": None,
        "retraction_longue_coupe": True,
        "retraction_distance_coupe": 18,
        "rapport_debit": 0.95,
        "ramollissement": 45,
        "enceinte_requise": False,
        "sechage": "45°C / 6h OBLIGATOIRE si exposé à l'air",
        "mur_exterieur": 30, "remplissage": 60,
        "warnings": [
            "Hygroscopique extrême — stocker sous vide impérativement",
            "Sécher 45°C / 6h si le filament a été exposé à l'air",
            "Soluble dans l'eau chaude — support PLA/PETG uniquement",
        ],
        "notes": "Filament de support soluble eau. Pour géométries complexes.",
    },
}

# Familles ordonnées pour l'affichage groupé
FAMILLES_ORDRE = ["Standard", "Technique", "Souple", "Chargé", "Spécial", "Support"]


# ── Densité du matériau imprimé (g/cm³) ─────────────────────────────────────────
# Sert à estimer le POIDS de la pièce (volume × densité × taux de remplissage).
# Valeurs moyennes constructeur/communauté ; injectées dans chaque entrée FILAMENTS.
_DENSITES: dict[str, float] = {
    "PLA":            1.24,
    "PETG":           1.27,
    "ABS":            1.04,
    "ASA":            1.07,
    "Nylon":          1.14,
    "PC":             1.20,
    "TPU":            1.21,
    "TPE":            1.20,
    "PLA-CF":         1.24,
    "PETG-CF":        1.28,
    "PA-CF":          1.15,
    "PLA Bois":       1.15,
    "PLA Métallique": 1.30,
    "HIPS":           1.04,
    "PVA":            1.23,
}
for _n, _d in _DENSITES.items():
    if _n in FILAMENTS:
        FILAMENTS[_n]["densite"] = _d


# ── Températures & débit OFFICIELS Bambu Studio ─────────────────────────────────
# Alignés (2026-06-22) sur les profils system/BBL de Bambu Studio (X1C 0.4) :
# (buse_1ère_couche, buse_autres, plateau, débit_volumétrique_max). Source
# autoritative — corrige nos valeurs approximatives (surtout PC/PA-CF/PETG-CF/PVA).
# Nylon et TPE conservent leurs valeurs internes (pas de profil Bambu dédié).
_BAMBU_OFFICIAL: dict[str, tuple[int, int, int, int]] = {
    "PLA":            (220, 220,  60, 21),   # plateau 60° (meilleur que le 55 Bambu en pratique)
    "PETG":           (245, 255,  70, 15),
    "ABS":            (260, 270,  90, 16),
    "ASA":            (270, 270, 100, 18),
    "PC":             (270, 280, 110, 18),
    "TPU":            (230, 230,  35,  4),
    "PLA-CF":         (230, 230,  55, 15),
    "PETG-CF":        (255, 255,  70, 12),
    "PA-CF":          (290, 290, 100,  8),
    "PLA Bois":       (220, 220,  55, 18),
    "PLA Métallique": (220, 220,  55, 21),
    "HIPS":           (240, 240,  90,  8),
    "PVA":            (240, 240,  55,  6),
}
for _n, (_b1, _bn, _bed, _vol) in _BAMBU_OFFICIAL.items():
    if _n in FILAMENTS:
        FILAMENTS[_n]["buse_1ere"] = _b1
        FILAMENTS[_n]["buse_autres"] = _bn
        FILAMENTS[_n]["plateau"] = _bed
        FILAMENTS[_n]["volumetrique_max"] = _vol


def filament_density(name: str | None) -> float:
    """Densité (g/cm³) du matériau imprimé. Défaut PLA (1.24) si inconnu."""
    if not name:
        return 1.24
    fil = FILAMENTS.get(name)
    if fil and "densite" in fil:
        return float(fil["densite"])
    return _DENSITES.get(name, 1.24)


# ═══════════════ Bibliothèque de MARQUES (produits fabricants) ═══════════════
# Un PRODUIT (« Sunlu Easy PA ») = un matériau de BASE (« Nylon ») + les
# surcharges de la fiche technique fabricant. Il HÉRITE de toutes les
# protections de sa base (ventilation, vitesses, warnings) — le code borne
# chaque valeur : une fiche aberrante est simplement écartée.
# Sources : data/filament_brands.json (embarqué) puis
# ~/.neoslice/filaments/brands.json (mise à jour distante, sans rebuild —
# voir core/filaments_maj.py) si sa version est plus récente.
MARQUES_VERSION: str = ""

_BORNES_PRODUIT: dict[str, tuple[float, float]] = {
    "buse_1ere": (170, 320), "buse_autres": (170, 320),
    "plateau": (0, 120), "volumetrique_max": (2, 40),
    "rapport_debit": (0.85, 1.15), "densite": (0.8, 2.0),
    "ventilateur_max": (0, 100), "ventilateur_seuil_mini": (0, 100),
}
_CHAMPS_PRODUIT = set(_BORNES_PRODUIT) | {
    "sechage", "enceinte_requise", "notes", "warnings", "bs_preset",
}


def base_materiau(nom: str) -> str:
    """Matériau GÉNÉRIQUE d'un nom de filament : un produit de marque renvoie
    sa base (« Sunlu Easy PA » -> « Nylon »), un générique se renvoie lui-même.
    Sert aux tables de sécurité du moteur et aux presets des slicers."""
    e = FILAMENTS.get(nom)
    if not e:
        return nom
    return e.get("base", nom)


def _charger_marques() -> None:
    global MARQUES_VERSION
    import json as _json
    from pathlib import Path as _Path
    sources = (_Path(__file__).parent / "filament_brands.json",
               _Path.home() / ".neoslice" / "filaments" / "brands.json")
    data = None
    for src in sources:            # la version la plus récente gagne
        try:
            d = _json.loads(src.read_text(encoding="utf-8"))
            if isinstance(d.get("marques"), dict) and (
                    data is None
                    or str(d.get("version", "")) > str(data.get("version", ""))):
                data = d
        except Exception:
            continue
    if not data:
        return
    MARQUES_VERSION = str(data.get("version", ""))
    for marque, produits in data["marques"].items():
        if not isinstance(produits, dict):
            continue
        for produit, spec in produits.items():
            base = FILAMENTS.get(spec.get("base", "")) if isinstance(spec, dict) else None
            if not base:
                continue                      # base inconnue -> produit écarté
            entree = dict(base)
            entree["warnings"] = list(base.get("warnings", []))
            valide = True
            for k, v in spec.items():
                if k in ("base", "source", "label") or k not in _CHAMPS_PRODUIT:
                    continue
                if k in _BORNES_PRODUIT:
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        valide = False
                        break
                    lo, hi = _BORNES_PRODUIT[k]
                    if not (lo <= v <= hi):
                        valide = False
                        break
                    if k not in ("rapport_debit", "densite"):
                        v = int(v)
                if k == "warnings":
                    entree["warnings"] += [str(w) for w in v]
                else:
                    entree[k] = v
            if not valide:
                continue
            entree["base"] = str(spec["base"])
            entree["marque"] = str(marque)
            entree["famille"] = str(marque)   # groupe d'affichage = la marque
            entree["label"] = spec.get("label", f"{marque} {produit}")
            FILAMENTS[f"{marque} {produit}"] = entree
            if marque not in FAMILLES_ORDRE:
                FAMILLES_ORDRE.append(str(marque))


def recharger_marques() -> None:
    """Recharge la bibliothèque après une mise à jour distante : retire les
    anciens produits (entrées avec `marque`) puis recharge les sources."""
    for cle in [k for k, v in FILAMENTS.items() if v.get("marque")]:
        del FILAMENTS[cle]
    del FAMILLES_ORDRE[6:]                    # les 6 familles génériques restent
    _charger_marques()


_charger_marques()
