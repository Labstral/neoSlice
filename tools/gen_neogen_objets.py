# -*- coding: utf-8 -*-
"""Génère `neogen_objets.json` — la BASE d'objets neoGen téléchargeable.

But : ajouter/corriger des objets de la bibliothèque neoGen SANS republier
l'application. Le fichier produit est à téléverser sur la release d'assets
GitHub (`neoslice-assets`, tag `assistant-latest`), à côté de `neogen_cookbook.json`
et de la KB d'Oen. Les utilisateurs le reçoivent via
« Réglages → Gestion des modules → Mettre à jour la base ».

Chaque objet est un dict :
  id, fr, en, domaine, texte("aucun"|"optionnel"|"requis"), synonymes,
  params : [[id, fr, en, min, max, defaut, pas], ...]
  flags  : [[id, fr, en, defaut], ...]            (optionnel)
  choix  : [[id, fr, en, [[val,fr,en],...], defaut], ...]  (optionnel)
  code   : script géométrique du KIT neoGen (voir core/neogen/libre.py : API).
           Les noms de params deviennent des variables ; finir par piece = ...

Ce script VALIDE chaque objet exactement comme le fera l'app au téléchargement
(sandbox clos + vérificateur : étanche, un seul tenant, imprimable). Un objet
qui échoue est ÉCARTÉ et signalé — jamais publié.

Usage :  python tools/gen_neogen_objets.py
         (écrit tools/out/neogen_objets.json ; incrémenter VERSION à chaque MAJ)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VERSION = "2026-07-23"
NOTES = "Objets d'atelier : entretoise hexagonale, passe-fil de bureau."

# ── Objets à publier ────────────────────────────────────────────────────────
OBJETS = [
    {
        "id": "entretoise_hex",
        "fr": "Entretoise hexagonale", "en": "Hex standoff",
        "domaine": "atelier", "texte": "aucun",
        "synonymes": "entretoise standoff colonnette plot ecarteur hexagonale visserie",
        "params": [
            ["diametre", "Diamètre (sur plats)", "Diameter (across flats)", 8, 40, 18, 1],
            ["hauteur", "Hauteur", "Height", 4, 60, 20, 1],
            ["d_trou", "Ø trou traversant", "Through hole ø", 2, 20, 6, 0.5],
        ],
        "code": (
            "corps = prisme(6, diametre, hauteur)\n"
            "trou = deplacer(cylindre(d_trou, hauteur + 4), 0, 0, -2)\n"
            "piece = poser_au_sol(percer(corps, trou))"
        ),
    },
    {
        "id": "passe_fil_bureau",
        "fr": "Passe-fil de bureau", "en": "Desk cable grommet",
        "domaine": "bureau", "texte": "aucun",
        "synonymes": "passe fil cable bureau trou oeillet grommet gestion cables collerette",
        "params": [
            ["d_trou_bureau", "Ø trou du bureau", "Desk hole ø", 20, 80, 40, 1],
            ["d_cables", "Ø passage des câbles", "Cable opening ø", 8, 60, 24, 1],
            ["hauteur", "Hauteur (épaisseur plateau)", "Height (desktop)", 8, 40, 18, 1],
        ],
        "code": (
            "col = cylindre(d_trou_bureau, hauteur)\n"
            "bride = cylindre(d_trou_bureau + 12, 3)\n"
            "corps = fusionner(col, bride)\n"
            "trou = deplacer(cylindre(d_cables, hauteur + 10), 0, 0, -2)\n"
            "piece = poser_au_sol(percer(corps, trou))"
        ),
    },
]


def main() -> int:
    from core.neogen import libre as L
    from core.neogen.objets_module import _defauts

    valides, ecartes = [], []
    for obj in OBJETS:
        try:
            ns = _defauts(obj)
            if obj.get("texte", "aucun") != "aucun":
                ns["texte"] = "Test"
            piece = L.poser_au_sol(L.executer_sandbox(obj["code"], ns))
            err = L.verifier(piece)
            if err is None:
                valides.append(obj)
                d = piece.extents
                print(f"  OK   {obj['id']:20} {d[0]:.0f}x{d[1]:.0f}x{d[2]:.0f} mm "
                      f"(watertight={piece.is_watertight})")
            else:
                ecartes.append((obj["id"], err))
                print(f"  KO   {obj['id']:20} → {err}")
        except Exception as e:
            ecartes.append((obj["id"], str(e)))
            print(f"  KO   {obj['id']:20} → EXCEPTION {e}")

    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "neogen_objets.json"
    out.write_text(json.dumps({"version": VERSION, "notes": NOTES, "objets": valides},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(valides)} objet(s) valide(s), {len(ecartes)} ecarte(s).")
    print(f"-> {out}")
    print("  Televerse ce fichier sur la release d'assets (tag assistant-latest)"
          " sous le nom neogen_objets.json.")
    return 0 if not ecartes else 1


if __name__ == "__main__":
    raise SystemExit(main())
