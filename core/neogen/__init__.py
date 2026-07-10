"""neoGen — génération d'objets 3D imprimables à partir de texte (Pro).

L'utilisateur décrit sa pièce en français ; Oen (modèle local) extrait des
paramètres ; la géométrie est calculée par du CODE déterministe (jamais par
l'IA) puis validée : chaque pièce sort étanche, sans surplomb ni région
flottante, prête pour le pipeline d'analyse/export de neoSlice.

API :
    from core.neogen import pilote
    objet, params, question = pilote.interpreter("un porte-clé Léa de 5 cm")
    chemin = pilote.generer(objet, params)      # -> Path du .3mf/.stl
"""
