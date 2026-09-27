# -*- coding: utf-8 -*-
"""Annuler / rétablir : chaque action mémorise l'état COMPLET du projet avant
de le modifier (comme la console). Simple et sûr : rien ne peut se perdre, et
un état restauré est exactement celui d'avant."""
from __future__ import annotations

import json

from neoforge.projet.modele import Projet

LIMITE = 200


class Historique:
    def __init__(self, limite: int = LIMITE):
        self._passe: list[str] = []
        self._futur: list[str] = []
        self._limite = limite

    @staticmethod
    def _photo(projet: Projet) -> str:
        return json.dumps(projet.dico(), sort_keys=True)

    def memoriser(self, projet: Projet) -> None:
        """À appeler JUSTE AVANT de modifier le projet."""
        photo = self._photo(projet)
        if self._passe and self._passe[-1] == photo:
            return                          # rien n'a changé depuis
        self._passe.append(photo)
        if len(self._passe) > self._limite:
            self._passe.pop(0)
        self._futur.clear()

    def annuler(self, actuel: Projet) -> Projet | None:
        if not self._passe:
            return None
        self._futur.append(self._photo(actuel))
        return Projet.depuis_dico(json.loads(self._passe.pop()))

    def retablir(self, actuel: Projet) -> Projet | None:
        if not self._futur:
            return None
        self._passe.append(self._photo(actuel))
        return Projet.depuis_dico(json.loads(self._futur.pop()))

    def vider(self) -> None:
        self._passe.clear()
        self._futur.clear()

    @property
    def peut_annuler(self) -> bool:
        return bool(self._passe)

    @property
    def peut_retablir(self) -> bool:
        return bool(self._futur)
