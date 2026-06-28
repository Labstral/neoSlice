"""Extracteur du catalogue d'imprimantes PrusaSlicer.

Source = bundles vendor `.ini` de PrusaSlicer (resources/profiles/*.ini). Ces
fichiers contiennent les définitions `[printer:...]` avec chaînes `inherits`
(et templates `*X*`). On les résout pour obtenir, par imprimante FFF :
printer_model, bed_shape (→ aire imprimable), max_print_height, nozzle_diameter,
gcode_flavor, printer_variant.

Sortie : data/prusa_printers.json — index par nom de profil (= preset Prusa).

Usage : python tools/extract_prusa.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

_PRUSA_PROFILES = [
    Path(r"C:\Program Files\Prusa3D\PrusaSlicer\resources\profiles"),
    Path(r"C:\Program Files\PrusaSlicer\resources\profiles"),
]

# Renommage d'affichage des marques (le reste = nom de fichier vendor tel quel)
_BRAND_RENAME = {"PrusaResearch": "Prusa", "QIDITechnology": "Qidi"}


def _parse_ini(path: Path) -> dict[str, dict]:
    """Parse un bundle .ini en {section_name: {key: value}}."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    secs: dict[str, dict] = {}
    for m in re.finditer(r"(?m)^\[([^\]]+)\]\n((?:(?!^\[).*\n?)*)", txt):
        name, body = m.group(1), m.group(2)
        d: dict[str, str] = {}
        for line in body.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
        secs[name] = d
    return secs


def _resolve(secs: dict[str, dict], name: str, seen=None, depth=0) -> dict:
    """Fusionne la chaîne `inherits` (parents → enfant). Gère les templates *X*."""
    seen = seen or set()
    if name in seen or depth > 24:
        return {}
    seen.add(name)
    sec = secs.get(name, {})
    out: dict = {}
    for parent in [p.strip() for p in sec.get("inherits", "").split(";") if p.strip()]:
        cand = "printer:" + parent
        if cand in secs:
            out.update(_resolve(secs, cand, set(seen), depth + 1))
    out.update(sec)
    return out


def _bed_size(bed_shape: str) -> tuple[str, str]:
    """'0x0,250x0,250x210,0x210' → ('250','210')."""
    try:
        xs, ys = [], []
        for pt in bed_shape.split(","):
            x, y = pt.split("x")
            xs.append(float(x)); ys.append(float(y))
        return (str(int(round(max(xs) - min(xs)))), str(int(round(max(ys) - min(ys)))))
    except Exception:
        return ("", "")


def extract() -> dict:
    root = next((d for d in _PRUSA_PROFILES if d.exists()), None)
    if not root:
        print("PrusaSlicer resources/profiles introuvable.", file=sys.stderr)
        sys.exit(1)

    catalog: dict[str, dict] = {}
    for path in sorted(root.glob("*.ini")):
        brand = _BRAND_RENAME.get(path.stem, path.stem)
        secs = _parse_ini(path)
        for name, raw in secs.items():
            if not name.startswith("printer:"):
                continue
            short = name[len("printer:"):]
            if short.startswith("*"):
                continue   # template abstrait
            full = _resolve(secs, name)
            if full.get("printer_technology", "FFF") != "FFF":
                continue   # ignorer SLA
            model = full.get("printer_model", "")
            if not model or not full.get("bed_shape"):
                continue
            w, d = _bed_size(full.get("bed_shape", ""))
            catalog[short] = {
                "marque": brand,
                "name": short,                       # = preset PrusaSlicer
                "printer_model": model,
                "nozzle_diameter": str(full.get("nozzle_diameter", "0.4")).split(",")[0],
                "printer_variant": full.get("printer_variant", "0.4"),
                "bed_shape": full.get("bed_shape", ""),
                "bed_size": f"{w}×{d}" if w else "",
                "max_print_height": str(full.get("max_print_height", "")),
                "gcode_flavor": full.get("gcode_flavor", ""),
                "default_print_profile": full.get("default_print_profile", ""),
                "default_filament_profile": full.get("default_filament_profile", "").strip('"'),
            }
    return catalog


def main():
    catalog = extract()
    out = Path(__file__).resolve().parent.parent / "data" / "prusa_printers.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Catalogue PrusaSlicer écrit : {out}  ({len(catalog)} imprimantes)")
    # Aperçu par marque
    by_brand: dict[str, set] = {}
    for e in catalog.values():
        by_brand.setdefault(e["marque"], set()).add(e["printer_model"])
    for b in sorted(by_brand):
        print(f"  {b:16s} : {len(by_brand[b])} modèles")


if __name__ == "__main__":
    main()
