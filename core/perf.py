"""Mode de performance — décision AUTO par pièce.

Ancien système : un mode global choisi par l'utilisateur (Complet/Équilibré/
Économique) appliqué à toutes les pièces. Problème : la bonne décision dépend du
COUPLE machine × pièce — un PC lent analyse très bien un porte-clés de 5 000
faces, un PC rapide peine sur un scan de 3 M de faces. Un mode global se trompe
dans les deux sens (et « Équilibré » ne différait de « Complet » que par le
nombre de threads — les mêmes analyses tournaient).

Nouveau système :
  - « auto » (défaut)  : décision PAR PIÈCE ci-dessous ;
  - « full »           : tout forcer (l'utilisateur assume, garde-fou 500k
                         faces du worker conservé) ;
  - « lite »           : surplombs toujours coupés (petits PC, choix manuel) ;
  - « balanced » (legacy, encore stocké chez d'anciens utilisateurs) → « auto ».

Décision auto : l'analyse lourde (surplombs, O(faces)) ne tourne que si la pièce
reste sous un plafond de faces PROPORTIONNÉ à la vitesse de la machine. La
vitesse vient d'un micro-benchmark (matmul numpy ~quelques ms), mesuré UNE fois
puis mis en cache dans PREFS (« bench_ms ») — silencieux, aucune action
utilisateur requise. Étalonnage : machine rapide (bench ≈ 1-4 ms) → plafond
500 000 faces (le garde-fou historique du worker « même sur PC rapide ») ;
machine lente → plafond réduit proportionnellement, plancher 60 000 faces.
"""
from __future__ import annotations

import time

from core.prefs import PREFS

# Plafond du garde-fou historique (au-delà : fallbacks rapides même en Complet)
FACES_MAX_RAPIDE = 500_000
# Plancher : même la machine la plus lente analyse jusqu'ici (qq secondes max)
FACES_MIN = 60_000
# bench de référence « machine rapide » (ms) : en-dessous, plein plafond
BENCH_RAPIDE_MS = 4.0


def bench_ms() -> float:
    """Vitesse machine (ms au micro-benchmark). Mesurée UNE fois, cache PREFS.
    Coût de la mesure : < 100 ms → faisable en plein worker sans impact."""
    v = float(PREFS.get("bench_ms", 0) or 0)
    if v > 0:
        return v
    try:
        import numpy as np
        a = np.random.rand(512, 512).astype(np.float32)
        b = np.random.rand(512, 512).astype(np.float32)
        np.dot(a, b)                                   # échauffement
        t0 = time.perf_counter()
        for _ in range(3):
            np.dot(a, b)
        v = (time.perf_counter() - t0) * 1000 / 3
        PREFS.set("bench_ms", round(v, 2))
    except Exception:
        v = 8.0                                        # inconnu → machine moyenne
    return v


def plafond_faces_auto() -> int:
    """Plafond de faces pour l'analyse lourde, proportionné à la machine."""
    ms = max(bench_ms(), BENCH_RAPIDE_MS)
    return int(max(FACES_MIN, min(FACES_MAX_RAPIDE,
                                  FACES_MAX_RAPIDE * BENCH_RAPIDE_MS / ms)))


def decision(n_faces: int, force_full: bool = False) -> dict:
    """Décision pour CETTE pièce.

    Renvoie {"overhangs": bool, "n_workers": int, "skip_reason": str} :
      skip_reason ∈ {"", "auto", "lite"} — « auto » = trop lourde pour cette
      machine (le panneau l'affiche + propose « Forcer l'analyse complète »).
    (Le cas > 500k faces reste géré par le garde-fou du worker, inchangé.)"""
    if force_full:
        return {"overhangs": True, "n_workers": 3, "skip_reason": ""}
    mode = PREFS.get("perf_mode", "auto")
    if mode == "balanced":                             # legacy → auto
        mode = "auto"
    if mode == "full":
        return {"overhangs": True, "n_workers": 3, "skip_reason": ""}
    if mode == "lite":
        return {"overhangs": False, "n_workers": 1, "skip_reason": "lite"}
    # AUTO
    if n_faces <= plafond_faces_auto():
        return {"overhangs": True, "n_workers": 3, "skip_reason": ""}
    return {"overhangs": False, "n_workers": 2, "skip_reason": "auto"}
