# -*- coding: utf-8 -*-
"""Tranchage réel : faire trancher la pièce par le slicer de l'utilisateur.

Jusqu'ici le temps d'impression et le poids de filament annoncés par neoSlice
étaient CALCULÉS, à partir du volume et de quelques règles. Ici on demande au
vrai slicer de trancher en arrière-plan, sans ouvrir sa fenêtre, et on lit les
valeurs qu'il écrit lui-même dans le gcode.

Voir `tranchage_reel` pour l'interface.
"""
from .tranchage_reel import (Resultat, Slicer, lire_gcode, profils_orca,
                             slicers_installes, trancher)

__all__ = ["Resultat", "Slicer", "lire_gcode", "profils_orca",
           "slicers_installes", "trancher"]
