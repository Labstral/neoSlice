# -*- coding: utf-8 -*-
"""Point d'entrée du paquet neoForge : le lanceur de neoSlice appelle
creer_fenetre() après avoir vérifié la licence, l'installation et le noyau."""
from __future__ import annotations


def creer_fenetre(app=None):
    """Crée la fenêtre neoForge (sans l'afficher : le lanceur s'en charge)."""
    from neoforge.ui.fenetre import FenetreNeoForge, icone
    if app is not None:
        app.setApplicationName("neoForge")
        app.setWindowIcon(icone())
    return FenetreNeoForge()
