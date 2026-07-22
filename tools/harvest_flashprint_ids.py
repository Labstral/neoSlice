# -*- coding: utf-8 -*-
"""Re-relève les machineId internes de FlashPrint (après une MAJ qui ajoute/retire
des machines). Ces ids ne sont NI dans profile.dat NI extractibles du binaire ; la
seule source fiable est FlashPrint lui-même : sélectionner une machine écrit son
machineId dans ~/.FlashPrint5/config.

Méthode (celle qui a marché le 2026-07-20, le clic auto étant non fiable — menus Qt
imperméables au clavier, slot du coché variable) :

  1. Lance ce script : il surveille ~/.FlashPrint5/config et journalise chaque
     machineId dès qu'il change.
  2. Dans FlashPrint : bouton machine (bas-gauche) → « Type Machine » → clique
     CHAQUE machine, une par une, de HAUT en BAS, sans en sauter.
  3. Le script imprime la séquence d'ids dans l'ordre du sous-menu. Zippe-la avec
     l'ordre des noms (le sous-menu est trié comme data/flashprint_printers.json)
     et reporte la table dans _MACHINE_IDS de tools/extract_flashprint_printers.py.

Ancre de validation : le 1er doit être Adventurer 3 Pro 2, le dernier Inventor II
Series. (Ordre relevé : les 27 machines dans l'ordre alpha du menu.)

Usage :  python tools/harvest_flashprint_ids.py            # veille 5 min
         python tools/harvest_flashprint_ids.py 600        # veille N secondes
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

CONFIG = Path.home() / ".FlashPrint5" / "config"


def read_id() -> str:
    try:
        m = re.search(r"machineId=(\d+)", CONFIG.read_text(encoding="utf-8", errors="ignore"))
        return m.group(1) if m else ""
    except Exception:
        return ""


def main() -> None:
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    if not CONFIG.exists():
        print(f"config introuvable : {CONFIG} (FlashPrint jamais lancé ?)")
        return
    print(f"Veille {dur}s. Dans FlashPrint : bouton machine -> Type Machine -> "
          f"clique chaque machine de haut en bas.\n")
    seq: list[str] = []
    last = read_id()
    print(f"  (machine courante id={last})")
    t0 = time.time()
    while time.time() - t0 < dur:
        time.sleep(0.25)
        cur = read_id()
        if cur and cur != last:
            seq.append(cur)
            print(f"  #{len(seq):2d}  machineId={cur}")
            last = cur
    print(f"\nSéquence ({len(seq)} machines) : {seq}")
    print("Zippe avec l'ordre des noms du sous-menu et mets à jour _MACHINE_IDS.")


if __name__ == "__main__":
    main()
