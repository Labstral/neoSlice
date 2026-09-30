# -*- coding: utf-8 -*-
"""neoForge : modeleur 3D pour débutants, module Pro de neoSlice.

Ce paquet n'est PAS embarqué dans l'exécutable neoSlice : il est téléchargé
depuis GitHub à l'installation du module (voir core/neoforge/installation.py)
puis chargé au lancement de neoForge (core/neoforge/lanceur.py). neoSlice ne
l'importe jamais par son nom, PyInstaller ne le voit donc pas.

Organisation :
  noyau/   géométrie (OpenCascade) : formes, booléens, congés, maillage
  projet/  modèle de projet, fichiers .nfg, historique
  ui/      fenêtre, viewer, panneaux
"""

VERSION = "1.0.1"
# Version minimale de neoSlice qui sait lancer ce paquet (API du lanceur).
NEOSLICE_MIN = "2.3.0"
