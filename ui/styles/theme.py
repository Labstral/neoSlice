"""Palette NASA Mission Control — NeuroPrint v2.0.

Toutes les couleurs centralisées ici. Zéro valeur codée en dur dans les widgets.
"""

# ── Fonds ──────────────────────────────────────────────────────────────────
BG_VOID     = "#020408"   # Noir spatial — fond fenêtre principale
BG_PANEL    = "#070D14"   # Panneaux, topbar, statusbar
BG_SURFACE  = "#0A1628"   # Cartes, widgets
BG_ELEVATED = "#0F1F35"   # Hover, éléments actifs
BG_INPUT    = "#060E1A"   # Champs de saisie

# ── Accents ────────────────────────────────────────────────────────────────
ACCENT        = "#1E90FF"  # Bleu NASA — interactifs
ACCENT_BRIGHT = "#4DAFFF"  # Accent éclairé / hover

# ── Couleurs télémétriques ─────────────────────────────────────────────────
TELE_GREEN = "#00FF9F"   # Valeurs numériques actives
AMBER      = "#FFB800"   # Warnings
ERROR_RED  = "#FF3B3B"   # Erreurs

# ── Texte ──────────────────────────────────────────────────────────────────
TEXT_PRIMARY   = "#C8DCF0"  # Corps principal
TEXT_SECONDARY = "#4A7A9B"  # Labels, descriptions
TEXT_LABEL     = "#2A5F8A"  # Labels secondaires, titres sections vides
INACTIVE       = "#1A3550"  # États vides, valeurs en attente

# ── Typographie ────────────────────────────────────────────────────────────
FONT_MAIN  = "Segoe UI"
FONT_MONO  = "Courier New"

RADIUS = 4  # px border-radius standard


def score_color(score: float) -> str:
    """Retourne une couleur télémétriqe selon le score 0→1."""
    if score >= 0.7:
        return TELE_GREEN
    elif score >= 0.4:
        return AMBER
    return ERROR_RED


# ── Alias de compatibilité (anciens noms utilisés par les composants v1) ───
BG_PRIMARY      = BG_VOID
BG_CARD         = BG_SURFACE
BG_CARD_HOVER   = BG_ELEVATED
BORDER_DEFAULT  = INACTIVE
BORDER_FOCUS    = ACCENT_BRIGHT
ACCENT_PRIMARY  = ACCENT
ACCENT_SECONDARY = ACCENT_BRIGHT
ACCENT_SUCCESS  = TELE_GREEN
ACCENT_WARNING  = AMBER
ACCENT_DANGER   = ERROR_RED
TEXT_MUTED      = TEXT_LABEL

COLOR_SCORE_GOOD   = TELE_GREEN
COLOR_SCORE_MEDIUM = AMBER
COLOR_SCORE_BAD    = ERROR_RED
