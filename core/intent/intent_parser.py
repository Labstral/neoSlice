from __future__ import annotations
import unicodedata
import re

from .intent_profiles import IntentProfile

# ---------------------------------------------------------------------------
# Dictionnaire de mots-clés FR + EN par dimension d'intention
# Chaque groupe contient des mots-clés et leur poids (1.0 = normal, 2.0 = fort)
# ---------------------------------------------------------------------------
_KEYWORD_GROUPS: dict[str, list[tuple[str, float]]] = {
    "strength": [
        ("solide", 1.0), ("fort", 1.0), ("forte", 1.0), ("résistant", 1.0),
        ("résistante", 1.0), ("robuste", 1.0), ("dur", 1.0), ("dure", 1.0),
        ("rigide", 1.0), ("incassable", 2.0), ("durable", 1.0), ("costaud", 1.0),
        ("ultra solide", 2.0), ("très solide", 1.5), ("solide au maximum", 2.0),
        ("solid", 1.0), ("strong", 1.0), ("resistant", 1.0), ("robust", 1.0),
        ("hard", 1.0), ("rigid", 1.0), ("tough", 1.0), ("sturdy", 1.0),
        ("maximum strength", 2.0),
    ],
    "speed": [
        ("rapide", 1.0), ("vite", 1.0), ("rapidement", 1.0), ("vitesse", 1.0),
        ("urgent", 1.5), ("vitement", 1.0), ("au plus vite", 2.0),
        ("le plus vite", 2.0), ("économie de temps", 1.5), ("gain de temps", 1.5),
        ("fast", 1.0), ("quick", 1.0), ("quickly", 1.0), ("speed", 1.0),
        ("asap", 2.0), ("rapid", 1.0),
    ],
    "quality": [
        ("qualité", 1.0), ("meilleure qualité", 2.0), ("haute qualité", 2.0),
        ("beau", 1.0), ("belle", 1.0), ("précis", 1.0), ("précise", 1.0),
        ("lisse", 1.5), ("fin", 1.0), ("fine", 1.0), ("détail", 1.5),
        ("détails", 1.5), ("parfait", 1.5), ("parfaite", 1.5), ("propre", 1.0),
        ("esthétique", 1.5), ("joli", 1.0), ("jolie", 1.0),
        ("tolérance", 1.5), ("ajustement", 1.5), ("précision", 2.0),
        ("couvercle", 1.0), ("emboîtement", 2.0), ("assemblage", 1.5),
        ("dimensionnel", 1.5), ("exact", 1.5), ("fidèle", 1.0),
        ("quality", 1.0), ("beautiful", 1.0), ("precise", 1.0), ("smooth", 1.5),
        ("detail", 1.5), ("perfect", 1.5), ("clean", 1.0), ("aesthetic", 1.5),
        ("best quality", 2.0), ("high quality", 2.0), ("tolerance", 1.5),
        ("dimensional", 1.5), ("accurate", 2.0), ("fitting", 1.5),
    ],
    "filament_saving": [
        ("économiser", 1.5), ("économie", 1.0), ("filament", 0.5),
        ("matière", 0.5), ("moins de matière", 2.0), ("léger", 1.0),
        ("légère", 1.0), ("creux", 1.5), ("économique", 1.5),
        ("peu de filament", 2.0), ("minimaliste", 1.0),
        ("save filament", 2.0), ("save material", 2.0), ("light", 1.0),
        ("hollow", 1.5), ("economic", 1.5), ("minimal material", 2.0),
    ],
    "outdoor_resistance": [
        ("extérieur", 2.0), ("dehors", 2.0), ("outdoor", 2.0),
        ("uv", 1.5), ("soleil", 1.5), ("pluie", 1.5), ("intempéries", 2.0),
        ("météo", 1.5), ("eau", 1.0), ("humidité", 1.5), ("chaleur", 1.0),
        ("gel", 1.0), ("résistant aux intempéries", 2.0),
        ("outside", 2.0), ("sun", 1.5), ("rain", 1.5), ("weather", 2.0),
        ("water resistant", 2.0), ("heat resistant", 1.5),
    ],
    "surface_finish": [
        ("surface", 1.0), ("visible", 1.5), ("aspect", 1.5), ("apparence", 1.5),
        ("finition", 2.0), ("belle surface", 2.0), ("sans marques", 1.5),
        ("sans coutures", 1.5), ("côté visible", 2.0),
        ("brillant", 1.5), ("poli", 1.5), ("lustré", 1.5), ("miroir", 2.0),
        ("lisse dessus", 2.0), ("surface lisse", 2.0), ("dessus parfait", 2.0),
        ("ironing", 2.0), ("repassage", 2.0), ("repasser", 2.0),
        ("finish", 2.0), ("surface finish", 2.0), ("no seam", 1.5),
        ("appearance", 1.5), ("visible side", 2.0), ("glossy", 2.0), ("shiny", 1.5),
        ("top surface", 2.0), ("flat top", 2.0),
    ],
}

# Phrases négatives qui inversent l'intention suivante
_NEGATIONS = {"pas", "non", "ne", "sans", "aucun", "no", "not", "without"}


def _normalize(text: str) -> str:
    """Lowercase + suppression des accents pour matching robuste."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def parse_intent(text: str) -> IntentProfile:
    """Transforme un texte libre en IntentProfile.

    Algorithme :
    1. Normalise le texte
    2. Pour chaque groupe de mots-clés, calcule un score cumulé
    3. Normalise les scores entre 0 et 1
    4. Retourne l'IntentProfile
    """
    if len(text) > 10_000:
        text = text[:10_000]
    normalized = _normalize(text)

    raw_scores: dict[str, float] = {k: 0.0 for k in _KEYWORD_GROUPS}

    for dimension, keywords in _KEYWORD_GROUPS.items():
        for keyword, weight in keywords:
            kw_norm = _normalize(keyword)
            # Recherche de la phrase-clé dans le texte normalisé
            if re.search(r"\b" + re.escape(kw_norm) + r"\b", normalized):
                raw_scores[dimension] += weight

    # Si aucun signal → profil neutre (0.5 sur tout)
    total = sum(raw_scores.values())
    if total < 0.1:
        return IntentProfile()

    # Normalisation : max score → 1.0, les autres proportionnellement
    max_score = max(raw_scores.values())
    normalized_scores = {
        k: min(1.0, v / max_score) for k, v in raw_scores.items()
    }

    # Les dimensions sans signal restent à 0.1 (pas 0.0) pour éviter les extrêmes
    for k in normalized_scores:
        if normalized_scores[k] == 0.0:
            normalized_scores[k] = 0.1

    return IntentProfile(
        strength=normalized_scores["strength"],
        speed=normalized_scores["speed"],
        quality=normalized_scores["quality"],
        filament_saving=normalized_scores["filament_saving"],
        outdoor_resistance=normalized_scores["outdoor_resistance"],
        surface_finish=normalized_scores["surface_finish"],
    )
