# -*- coding: utf-8 -*-
"""Extrait les types de plateau PAR imprimante depuis les profils OrcaSlicer →
data/bed_types.json.

OrcaSlicer définit par machine (au niveau modèle) :
  - `default_bed_type`        : plateau par défaut (quasi toujours « Textured PEI Plate ») ;
  - `not_support_bed_type`    : liste « ; » des plateaux que CETTE machine ne supporte PAS
                                (ex. Bambu A1 mini : « Smooth Cool Plate;Engineering Plate »).

Seule une cinquantaine de machines déclarent ces champs (les autres héritent du
défaut). On capture donc une table CREUSE : la logique du sélecteur applique le
plein ensemble moins `not_support` pour les machines listées, et l'ensemble complet
par défaut sinon. Clé = nom du profil machine (= nom de modèle au niveau modèle),
ce qui correspond au champ `printer_model` du catalogue neoSlice et, pour Bambu,
à « Bambu Lab <modèle> ».

Usage : python tools/extract_bed_types.py
"""
from __future__ import annotations

import json
import glob
import os
from pathlib import Path

ORCA = Path(r"C:\Program Files\OrcaSlicer\resources\profiles")
OUT = Path(__file__).parent.parent / "data" / "bed_types.json"


def main() -> None:
    if not ORCA.exists():
        raise SystemExit(f"OrcaSlicer introuvable : {ORCA}")
    table: dict[str, dict] = {}
    universe: set[str] = set()
    for f in glob.glob(str(ORCA / "*" / "machine" / "*.json")):
        try:
            j = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        name = j.get("name")
        db = j.get("default_bed_type")
        ns = j.get("not_support_bed_type")
        if not name or (db is None and ns is None):
            continue
        not_support = [b.strip() for b in (ns or "").split(";") if b.strip()]
        # ignorer les valeurs aberrantes (ex. default_bed_type == "4")
        if db and not db[0].isdigit():
            universe.add(db)
        universe.update(not_support)
        entry = {}
        if db and not db[0].isdigit():
            entry["default"] = db
        if not_support:
            entry["not_support"] = not_support
        if entry:
            table[name] = entry

    OUT.write_text(json.dumps({
        "_source": "OrcaSlicer resources/profiles (default_bed_type + not_support_bed_type)",
        "_universe": sorted(universe),
        "printers": dict(sorted(table.items())),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    restr = sum(1 for v in table.values() if v.get("not_support"))
    print(f"{len(table)} machines avec info plateau ({restr} avec restriction) -> {OUT}")
    print(f"univers: {sorted(universe)}")


if __name__ == "__main__":
    main()
