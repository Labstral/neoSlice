# -*- coding: utf-8 -*-
"""Objets neoGen AJOUTÉS/CORRIGÉS PAR MISE À JOUR — SANS rebuild de l'app.

Un fichier téléchargeable `neogen_objets.json` (même canal que la base d'Oen et
le cookbook) définit des objets neoGen COMPLETS : identifiant, noms FR/EN,
domaine, paramètres réglables, options, et un `code` géométrique écrit avec le
KIT neoGen (les mêmes fonctions sûres que la création libre : boite_3d,
cylindre, cone, tube, extrusion, percer, fusionner, deplacer, poser_au_sol…).

Cycle de vie :
  - TÉLÉCHARGEMENT (core/neogen/maj.py) : chaque objet est EXÉCUTÉ dans le bac à
    sable clos (aucun import/exec/fichier) puis passé au vérificateur (étanche,
    d'un seul tenant, imprimable). Seuls les objets prouvés sains sont écrits.
  - CHARGEMENT (ici) : les objets validés sont convertis en entrées de catalogue
    neoGen ; le formulaire de la bibliothèque et la recherche les prennent en
    charge AUTOMATIQUEMENT (mêmes schémas que les objets natifs).
  - GÉNÉRATION : le `code` tourne dans le bac à sable, les valeurs des
    paramètres choisies par l'utilisateur y étant injectées comme variables.

Un objet téléchargé dont l'`id` correspond à un objet natif le REMPLACE : on
peut donc corriger un objet existant sans republier toute l'application.

→ « Réglages → Gestion des modules → Mettre à jour la base » enrichit ou corrige
   la bibliothèque neoGen sans réinstaller le logiciel.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

FICHIER_LOCAL = Path.home() / ".neoslice" / "neogen" / "objets_extra.json"


def _defauts(obj: dict) -> dict:
    """Namespace de départ = valeur par défaut de chaque paramètre / option."""
    ns: dict = {}
    for t in obj.get("params", []):
        if len(t) >= 6:
            ns[t[0]] = t[5]                 # (id, fr, en, min, max, defaut, pas)
    for t in obj.get("flags", []):
        if len(t) >= 4:
            ns[t[0]] = t[3]                 # (id, fr, en, defaut)
    for t in obj.get("choix", []):
        if len(t) >= 5:
            ns[t[0]] = t[4]                 # (id, fr, en, [options], defaut)
    return ns


def _make_builder(obj: dict):
    """Fabrique le constructeur d'un objet-recette : exécute son `code` dans le
    bac à sable avec les paramètres de l'utilisateur injectés."""
    code = str(obj.get("code", ""))
    a_texte = obj.get("texte", "aucun") != "aucun"

    def _build(p: dict):
        from core.neogen import libre as L        # import paresseux (sandbox)
        ns = _defauts(obj)
        for k in list(ns.keys()):                 # valeurs du formulaire → écrasent
            if k in p and p[k] is not None:
                ns[k] = p[k]
        if a_texte:
            ns["texte"] = p.get("texte", "")
        return L.poser_au_sol(L.executer_sandbox(code, ns))

    return _build


def charger_objets() -> list[dict]:
    """Objets installés (fichier local déjà validé au téléchargement)."""
    try:
        data = json.loads(FICHIER_LOCAL.read_text(encoding="utf-8"))
        objs = data.get("objets", [])
        return objs if isinstance(objs, list) else []
    except Exception:
        return []


def entrees_catalogue() -> list[dict]:
    """Convertit les objets téléchargés en entrées de catalogue neoGen (même
    forme que le helper `_e` de catalogue.py)."""
    entrees: list[dict] = []
    for obj in charger_objets():
        try:
            oid = str(obj.get("id", "")).strip()
            if not oid or not obj.get("code"):
                continue
            entrees.append({
                "id": oid,
                "fr": obj.get("fr", oid), "en": obj.get("en", oid),
                "domaine": obj.get("domaine", "bureau"),
                "texte": obj.get("texte", "aucun"),
                "image": False,
                "params": list(obj.get("params", [])),
                "flags": list(obj.get("flags", [])),
                "choix": list(obj.get("choix", [])),
                "couleurs": list(obj.get("couleurs", [])),
                "construire": _make_builder(obj),
                "_module": True,      # marque : objet issu d'une mise à jour de base
                "_synonymes": obj.get("synonymes", ""),
            })
        except Exception as e:
            logger.debug(f"objet module '{obj.get('id')}' ignoré : {e}")
    return entrees
