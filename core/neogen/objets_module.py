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

import base64
import gzip
import io
import json
from pathlib import Path

from loguru import logger

FICHIER_LOCAL = Path.home() / ".neoslice" / "neogen" / "objets_extra.json"


def mesh_depuis_champ(champ: dict):
    """Décode un maillage IMPORTÉ embarqué dans la base : {format, gz_b64} →
    trimesh. Permet de livrer un modèle tout fait (3mf/STL/OBJ d'Emmanuel) par
    mise à jour de base, SANS rebuild — l'app 0.1.8.4+ sait le charger. Le
    maillage est posé (base z=0) et centré en XY, prêt à imprimer."""
    import trimesh
    fmt = str(champ.get("format", "stl")).lower()
    raw = gzip.decompress(base64.b64decode(champ["gz_b64"]))
    m = trimesh.load(io.BytesIO(raw), file_type=fmt, process=True)
    if isinstance(m, trimesh.Scene):
        m = m.to_geometry()
    m.apply_translation(-m.bounds[0])                 # coin en 0
    c = (m.bounds[0] + m.bounds[1]) / 2
    m.apply_translation([-c[0], -c[1], 0])            # centré XY, base z=0
    return m


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
    # Objet IMPORTÉ (maillage embarqué) : pas de recette, on charge le mesh tel
    # quel. Une échelle optionnelle (param « echelle » en %) peut le redimensionner.
    mesh_champ = obj.get("mesh")
    if mesh_champ:
        def _build_mesh(p: dict):
            m = mesh_depuis_champ(mesh_champ)
            ech = p.get("echelle")
            if ech and abs(float(ech) - 100.0) > 1e-6:
                m.apply_scale(float(ech) / 100.0)
                m.apply_translation(-m.bounds[0] * [0, 0, 1])  # rebase z=0
            return m
        return _build_mesh

    code = str(obj.get("code", ""))
    a_texte = obj.get("texte", "aucun") != "aucun"
    a_image = bool(obj.get("image", False))

    def _build(p: dict):
        from core.neogen import libre as L        # import paresseux (sandbox)
        ns = _defauts(obj)
        for k in list(ns.keys()):                 # valeurs du formulaire → écrasent
            if k in p and p[k] is not None:
                ns[k] = p[k]
        if a_texte:
            ns["texte"] = p.get("texte", "")
        if a_image:
            ns["image"] = p.get("image")          # chemin fichier choisi par l'utilisateur
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


def domaines_module() -> list[dict]:
    """Catégories (domaines) définies par la base téléchargée : [{id, fr, en}, …].
    Permet d'ajouter une NOUVELLE catégorie neoGen sans rebuild — le catalogue les
    fusionne avec les domaines natifs (voir catalogue.par_domaine)."""
    try:
        data = json.loads(FICHIER_LOCAL.read_text(encoding="utf-8"))
        doms = data.get("domaines", [])
        return [d for d in doms if isinstance(d, dict) and d.get("id")]
    except Exception:
        return []


def entrees_catalogue() -> list[dict]:
    """Convertit les objets téléchargés en entrées de catalogue neoGen (même
    forme que le helper `_e` de catalogue.py)."""
    entrees: list[dict] = []
    for obj in charger_objets():
        try:
            oid = str(obj.get("id", "")).strip()
            if not oid or not (obj.get("code") or obj.get("mesh")):
                continue
            entrees.append({
                "id": oid,
                "fr": obj.get("fr", oid), "en": obj.get("en", oid),
                "domaine": obj.get("domaine", "bureau"),
                "texte": obj.get("texte", "aucun"),
                "image": bool(obj.get("image", False)),
                "params": list(obj.get("params", [])),
                "flags": list(obj.get("flags", [])),
                "choix": list(obj.get("choix", [])),
                "couleurs": list(obj.get("couleurs", [])),
                "construire": _make_builder(obj),
                "_module": True,      # marque : objet issu d'une mise à jour de base
                "_synonymes": obj.get("synonymes", ""),
                # visibilité conditionnelle de champs (voir neogen_dialog) :
                # {champ: flag} -> visible seulement si flag coché / caché si coché.
                "visible_si": dict(obj.get("visible_si", {})),
                "cache_si": dict(obj.get("cache_si", {})),
            })
        except Exception as e:
            logger.debug(f"objet module '{obj.get('id')}' ignoré : {e}")
    return entrees
