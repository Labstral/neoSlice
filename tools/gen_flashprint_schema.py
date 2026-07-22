# -*- coding: utf-8 -*-
"""Génère data/flashprint_profile_schema.json depuis un profil FlashPrint canonique.

Un profil utilisateur FlashPrint (.cfg) a une structure FIXE que le dépôt doit
respecter : section [General] avec ~200 clés, chaque valeur étant soit un flottant
encodé QVariant (`@Variant(\\0\\0\\0\\x87<4 octets BE float>)`), soit une valeur
« texte » (booléen true/false, tableau [], petit entier d'énumération).

Ce schéma (ordre des clés + type + valeur par défaut brute) NE PEUT PAS venir de
profile.dat (qui utilise un format texte différent, interne). Il est relevé d'un
profil EXPORTÉ par FlashPrint lui-même (bouton « Exporter » du dialogue de
tranchage → .fcfg). Le builder part de ce schéma, surcharge les valeurs par le
préréglage constructeur de la machine (profile.dat) puis par les paramètres
neoSlice, et ré-encode les flottants surchargés en QVariant.

Provenance du fichier source : FlashPrint 5.8.7, machine Adventurer 3 Pro 2, PLA
Standard, exporté le 2026-07-20. Validé en GUI (valeurs relues correctement).

Usage : python tools/gen_flashprint_schema.py <chemin_canon.fcfg>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "flashprint_profile_schema.json"


def main() -> None:
    src = Path(sys.argv[1])
    general_order: list[str] = []
    keys: dict[str, dict] = {}
    custom_order: list[str] = []
    custom: dict[str, dict] = {}
    section = None
    for line in src.read_text(encoding="utf-8").splitlines():
        if line.startswith("["):
            section = line.strip("[]")
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        is_variant = "@Variant(" in v
        entry = {"type": "variant" if is_variant else "plain", "raw": v}
        if section == "General":
            general_order.append(k)
            keys[k] = entry
        elif section == "Custom":
            custom_order.append(k)
            custom[k] = entry

    OUT.write_text(json.dumps({
        "_source": f"FlashPrint canonical export ({src.name}), machine Adventurer 3 Pro 2 PLA",
        "custom_order": custom_order,
        "custom": custom,
        "general_order": general_order,
        "general": keys,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(general_order)} cles General, {len(custom_order)} cles Custom -> {OUT}")


if __name__ == "__main__":
    main()
