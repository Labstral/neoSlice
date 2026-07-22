# -*- coding: utf-8 -*-
"""Extraction du catalogue FlashPrint 5 (FlashForge) → data/flashprint_printers.json.

FlashPrint 5 embarque TOUTES ses machines et TOUS ses profils de tranchage dans
un conteneur propriétaire `profile.dat` (magic « fprofile ») :

    fprofile + 8 octets nuls
    u32 nb_entrées
    puis par entrée : u32 len_nom, u32 len_données, nom, données

Les noms forment une arborescence « <Machine>-<buse>/<Matériau>-<diam>/<Qualité> » :
    FlashForge Adventurer 5M-0.4/.info                 → liste des matériaux
    FlashForge Adventurer 5M-0.4/PLA-1.75/.info        → qualités dispo (["Standard",…])
    FlashForge Adventurer 5M-0.4/PLA-1.75/Standard     → profil INI [General] (~200 clés)

On n'extrait QUE les profils « Standard » mono-matériau (les combos bi-extrudeur
« A{+}B » et les qualités Fine/Fast sont ignorés : le moteur neoSlice calcule ses
propres hauteurs de couche/vitesses et surcharge le profil de base).

Dimensions plateau : profile.dat ne les contient PAS (FlashPrint les code en dur
dans l'exe et les passe au moteur au moment du slice). On les fournit ici depuis
les specs officielles FlashForge, croisées avec data/printers_catalog.json (extrait
d'OrcaSlicer) pour les modèles communs.

Usage :  python tools/extract_flashprint_printers.py
         (relire profile.dat après une mise à jour de FlashPrint)
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

PROFILE_DAT = Path(r"C:\Program Files\FlashForge\FlashPrint 5\profile.dat")
OUT = Path(__file__).parent.parent / "data" / "flashprint_printers.json"

# Dimensions plateau (mm) — specs officielles FlashForge. Pour les modèles aussi
# présents dans printers_catalog.json (source OrcaSlicer), les valeurs concordent.
_DIMS: dict[str, tuple[int, int, int]] = {
    "FlashForge Adventurer 3 Series":  (150, 150, 150),
    "FlashForge Adventurer 3 Pro 2":   (150, 150, 150),
    "FlashForge Adventurer 4 Series":  (220, 200, 250),
    "FlashForge Adventurer 4 Pro":     (220, 200, 250),
    "FlashForge Adventurer 5M":        (220, 220, 220),
    "FlashForge Adventurer 5M Pro":    (220, 220, 220),
    "FlashForge Artemis":              (190, 195, 200),
    "FlashForge Creator 3":            (300, 250, 200),
    "FlashForge Creator 3 Pro":        (300, 250, 200),
    "FlashForge Creator 4":            (400, 350, 500),
    "FlashForge Creator Max":          (227, 148, 150),
    "FlashForge Creator Max 2":        (200, 148, 150),
    "FlashForge Creator Pro":          (227, 148, 150),
    "FlashForge Creator Pro 2":        (200, 148, 150),
    "FlashForge Creator Pro T":        (227, 148, 150),
    "FlashForge Dreamer":              (230, 150, 140),
    "FlashForge Dreamer NX":           (230, 150, 140),
    "FlashForge Finder":               (140, 140, 140),
    "FlashForge Finder 3":             (190, 195, 200),
    "FlashForge Guider":               (280, 250, 300),
    "FlashForge Guider II":            (280, 250, 300),
    "FlashForge Guider II S Series":   (280, 250, 300),
    "FlashForge Guider 3":             (300, 250, 340),
    "FlashForge Guider 3 Plus":        (350, 350, 600),
    "FlashForge Guider 3 Ultra":       (330, 330, 600),
    "FlashForge Inventor Series":      (230, 150, 160),
    "FlashForge Inventor II Series":   (150, 140, 140),
}

# machineId interne de FlashPrint (nécessaire au dépôt de profils utilisateur :
# fichier ~/.FlashPrint5/slice_profile/<machineId>_<buse>_<nom>.cfg + clé machineId
# dans le profil). Ces ids NE SONT PAS dans profile.dat ni extractibles du binaire :
# RELEVÉS le 2026-07-20 en pilotant FlashPrint 5.8.7 (chaque sélection de machine
# écrit son machineId dans ~/.FlashPrint5/config). Validés bout-en-bout
# (Adventurer 3 Pro 2=30, 3 Series=9, 4 Pro=29 … Inventor II Series=8).
# Pour rafraîchir après une MAJ FlashPrint : voir tools/harvest_flashprint_ids
# (veilleur config + clic de chaque machine dans « Type Machine »).
_MACHINE_IDS: dict[str, int] = {
    "FlashForge Adventurer 3 Pro 2":  30,
    "FlashForge Adventurer 3 Series":  9,
    "FlashForge Adventurer 4 Pro":    29,
    "FlashForge Adventurer 4 Series": 21,
    "FlashForge Adventurer 5M":       33,
    "FlashForge Adventurer 5M Pro":   34,
    "FlashForge Artemis":             25,
    "FlashForge Creator 3":           12,
    "FlashForge Creator 3 Pro":       22,
    "FlashForge Creator 4":           19,
    "FlashForge Creator Max":         16,
    "FlashForge Creator Max 2":       20,
    "FlashForge Creator Pro":          5,
    "FlashForge Creator Pro 2":       17,
    "FlashForge Creator Pro T":       23,
    "FlashForge Dreamer":              0,
    "FlashForge Dreamer NX":          11,
    "FlashForge Finder":               2,
    "FlashForge Finder 3":            24,
    "FlashForge Guider":               3,
    "FlashForge Guider II":            6,
    "FlashForge Guider II S Series":  10,
    "FlashForge Guider 3":            27,
    "FlashForge Guider 3 Plus":       26,
    "FlashForge Guider 3 Ultra":      28,
    "FlashForge Inventor Series":      7,
    "FlashForge Inventor II Series":   8,
}

# Machines bi-extrudeur (v1 neoSlice : extrudeur droit T0 uniquement, mais le
# drapeau est stocké pour l'UI/les notes et une éventuelle v2).
_DUAL = {
    "FlashForge Creator 3", "FlashForge Creator 3 Pro", "FlashForge Creator 4",
    "FlashForge Creator Max", "FlashForge Creator Max 2", "FlashForge Creator Pro",
    "FlashForge Creator Pro 2", "FlashForge Creator Pro T", "FlashForge Dreamer",
    "FlashForge Dreamer NX", "FlashForge Inventor Series",
}


def parse_container(path: Path) -> list[tuple[str, bytes]]:
    raw = path.read_bytes()
    if raw[:8] != b"fprofile":
        raise SystemExit(f"magic inattendu dans {path} : {raw[:8]!r}")
    off = 16
    (count,) = struct.unpack_from("<I", raw, off)
    off += 4
    entries = []
    for _ in range(count):
        nlen, dlen = struct.unpack_from("<II", raw, off)
        off += 8
        name = raw[off:off + nlen].decode("utf-8", "replace")
        off += nlen
        entries.append((name, raw[off:off + dlen]))
        off += dlen
    if off != len(raw):
        raise SystemExit(f"conteneur mal parsé : offset final {off} ≠ taille {len(raw)}")
    return entries


def parse_ini(data: bytes) -> dict[str, str]:
    """Profil FlashPrint = INI à section unique [General] ; on aplatit en dict."""
    out: dict[str, str] = {}
    for line in data.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "[")):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else PROFILE_DAT
    entries = parse_container(src)

    machines: dict[str, dict] = {}
    profiles: dict[str, dict[str, dict[str, str]]] = {}

    for name, data in entries:
        parts = name.split("/")
        machine_nozzle = parts[0]                       # « FlashForge Adventurer 5M-0.4 »
        model, _, nozzle = machine_nozzle.rpartition("-")
        try:
            nozzle_f = float(nozzle)
        except ValueError:
            continue                                    # entrée inattendue → ignorer
        m = machines.setdefault(model, {
            # « Flashforge » (casse du reste du catalogue neoSlice / POPULAR_BRANDS),
            # les CLÉS machine gardent la casse exacte de FlashPrint (« FlashForge … »)
            "brand": "Flashforge",
            "nozzles": [],
            "materials": {},
            "dual_extruder": model in _DUAL,
        })
        if nozzle_f not in m["nozzles"]:
            m["nozzles"].append(nozzle_f)

        if len(parts) == 3 and parts[2] == "Standard" and "{+}" not in parts[1]:
            # matériaux stockés par RÉPERTOIRE FlashPrint exact (« PLA-1.75 ») :
            # nécessaire pour déposer nos profils dans ~/.FlashPrint5/slice_profile/
            # au chemin que FlashPrint attend (nom affiché = partie avant le « -1.75 »)
            mat_dir = parts[1]
            m["materials"].setdefault(nozzle, []).append(mat_dir)
            profiles.setdefault(machine_nozzle, {})[mat_dir] = parse_ini(data)

    for model, m in machines.items():
        m["nozzles"] = sorted(m["nozzles"])
        dims = _DIMS.get(model)
        if dims is None:
            print(f"[!] dimensions inconnues pour {model} - a completer dans _DIMS")
            dims = (200, 200, 200)
        m["bed_size"] = f"{dims[0]}x{dims[1]}"
        m["printable_height"] = dims[2]
        mid = _MACHINE_IDS.get(model)
        if mid is None:
            print(f"[!] machineId inconnu pour {model} - depot de profil impossible")
        m["machine_id"] = mid if mid is not None else -1

    out = {
        "_source": f"FlashPrint 5 profile.dat ({src})",
        "machines": dict(sorted(machines.items())),
        "profiles": dict(sorted(profiles.items())),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n_prof = sum(len(v) for v in profiles.values())
    print(f"{len(machines)} machines, {n_prof} profils Standard -> {OUT}")


if __name__ == "__main__":
    main()
