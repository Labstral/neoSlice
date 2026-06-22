"""Calculateur de coût de revient et de devis pour impressions 3D (neoSlice Pro).

Logique pure, sans UI : prend des paramètres chiffrés et renvoie le détail du
coût poste par poste, plus un prix de vente conseillé.

Postes pris en compte :
  - Matière      : poids (g) × prix au kg
  - Électricité  : puissance moyenne (W) × durée (h) × tarif kWh
  - Usure machine: prix machine ÷ durée de vie (h) × durée (h)
  - Main d'œuvre : temps (min) × taux horaire
  - Marge échec  : % appliqué au sous-total (impressions ratées amorties)
  - Marge        : % de bénéfice pour le prix de vente

Les tarifs électricité / devises par défaut dépendent du pays mais restent
modifiables par l'utilisateur (ils évoluent dans le temps).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────────────────
# Valeurs par défaut par pays — tarif kWh (en devise locale) + code devise.
# Moyennes résidentielles 2025-2026 (sources : GlobalPetrolPrices, Eurostat,
# tarifs réglementés). INDICATIVES : varient selon fournisseur, région, heures
# creuses/pleines → l'utilisateur ajuste dans la fenêtre. Mis à jour 2026-06.
# ──────────────────────────────────────────────────────────────────────────────

COUNTRY_DEFAULTS: dict[str, dict] = {
    "Suisse":          {"kwh": 0.32, "devise": "CHF"},
    "France":          {"kwh": 0.25, "devise": "EUR"},
    "Belgique":        {"kwh": 0.37, "devise": "EUR"},
    "Luxembourg":      {"kwh": 0.23, "devise": "EUR"},
    "Allemagne":       {"kwh": 0.37, "devise": "EUR"},
    "Canada":          {"kwh": 0.17, "devise": "CAD"},
    "États-Unis":      {"kwh": 0.18, "devise": "USD"},
    "Royaume-Uni":     {"kwh": 0.25, "devise": "GBP"},
    "Autre / manuel":  {"kwh": 0.25, "devise": "EUR"},
}

PAYS_ORDRE = list(COUNTRY_DEFAULTS.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Puissance moyenne consommée pendant l'impression (watts), par modèle.
# Moyenne réaliste sur impression PLA/PETG (le chauffage plateau domine), pas le
# pic de chauffe (~400 W les 1res minutes). Valeurs cohérentes avec mesures
# communautaires (forum Bambu, pea3d) : X1C ~103-135 W, P1S ~100 W, A1 ~90 W.
# La série H2 (plus grande, double extrudeur, chambre chauffée) reste estimée
# faute de mesures publiées. INDICATIF — l'ABS/grandes surfaces consomment plus.
# ──────────────────────────────────────────────────────────────────────────────

_PRINTER_POWER_W: dict[str, int] = {
    "A1 mini":     75,
    "A1":          90,
    "P1P":         95,
    "P1S":         100,
    "X1 Carbon":   120,
    "X1C":         120,
    "X1E":         130,
    "X1":          120,
    "H2S":         150,   # estimé (pas de mesure publiée)
    "H2C":         150,   # estimé
    "H2D":         165,   # estimé
    "H2D Pro":     165,   # estimé
}

_DEFAULT_POWER_W = 120


def printer_power_w(model: str | None) -> int:
    """Puissance moyenne (W) d'un modèle. Tolérant aux variantes de nom."""
    if not model:
        return _DEFAULT_POWER_W
    if model in _PRINTER_POWER_W:
        return _PRINTER_POWER_W[model]
    low = model.lower()
    for name, watts in _PRINTER_POWER_W.items():
        if name.lower() in low or low in name.lower():
            return watts
    return _DEFAULT_POWER_W


# NOTE : le poids et la durée ne sont PAS estimés ici. Ils proviennent de
# PrintConfig.estimated_filament_g() / estimated_time_minutes() — les MÊMES
# valeurs que le panneau « EN RÉSUMÉ » — et sont transmis au calculateur, pour
# garantir des chiffres identiques partout dans l'application.


# ──────────────────────────────────────────────────────────────────────────────
# Modèle de coût
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CostInputs:
    weight_g: float = 0.0
    time_h: float = 0.0
    filament_price_kg: float = 25.0
    printer_power_w: float = _DEFAULT_POWER_W
    kwh_rate: float = 0.25
    machine_price: float = 0.0
    machine_lifespan_h: float = 5000.0
    labor_minutes: float = 0.0
    labor_rate_h: float = 0.0
    packaging_cost: float = 0.0
    failure_rate_pct: float = 0.0
    margin_pct: float = 0.0
    currency: str = "EUR"


@dataclass
class CostBreakdown:
    material: float = 0.0
    electricity: float = 0.0
    wear: float = 0.0
    labor: float = 0.0
    packaging: float = 0.0
    subtotal: float = 0.0
    failure_buffer: float = 0.0
    total_cost: float = 0.0
    margin_amount: float = 0.0
    sale_price: float = 0.0
    currency: str = "EUR"
    # Détails utiles pour l'affichage
    energy_kwh: float = 0.0


# Paliers de prix suggérés (clé i18n → marge bénéficiaire %). Façon « stratégie
# de prix » : l'utilisateur voit plusieurs prix possibles d'un coup d'œil.
PRICE_TIERS: tuple[tuple[str, float], ...] = (
    ("eco", 20.0),
    ("standard", 40.0),
    ("premium", 60.0),
)


def sale_price_for(total_cost: float, margin_pct: float) -> float:
    """Prix de vente = coût de revient + marge bénéficiaire (%)."""
    return max(0.0, total_cost) * (1.0 + max(0.0, margin_pct) / 100.0)


def compute_cost(inp: CostInputs) -> CostBreakdown:
    """Calcule le détail du coût et le prix de vente conseillé."""
    material = max(0.0, inp.weight_g) / 1000.0 * max(0.0, inp.filament_price_kg)

    energy_kwh = max(0.0, inp.printer_power_w) / 1000.0 * max(0.0, inp.time_h)
    electricity = energy_kwh * max(0.0, inp.kwh_rate)

    if inp.machine_lifespan_h > 0:
        wear = max(0.0, inp.machine_price) / inp.machine_lifespan_h * max(0.0, inp.time_h)
    else:
        wear = 0.0

    labor = max(0.0, inp.labor_minutes) / 60.0 * max(0.0, inp.labor_rate_h)
    packaging = max(0.0, inp.packaging_cost)

    subtotal = material + electricity + wear + labor + packaging
    failure_buffer = subtotal * max(0.0, inp.failure_rate_pct) / 100.0
    total_cost = subtotal + failure_buffer
    margin_amount = total_cost * max(0.0, inp.margin_pct) / 100.0
    sale_price = total_cost + margin_amount

    return CostBreakdown(
        material=material,
        electricity=electricity,
        wear=wear,
        labor=labor,
        packaging=packaging,
        subtotal=subtotal,
        failure_buffer=failure_buffer,
        total_cost=total_cost,
        margin_amount=margin_amount,
        sale_price=sale_price,
        currency=inp.currency,
        energy_kwh=energy_kwh,
    )
