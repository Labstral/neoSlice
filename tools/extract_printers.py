"""Extracteur de catalogue d'imprimantes depuis les profils officiels.

Source = profils machine de Bambu Studio ET OrcaSlicer (identiques pour les
marques partagées ; l'union ajoute Flashforge, présent seulement dans Orca).
Ces profils SONT la source officielle des specs : volume, vitesses/accélérations
max, diamètres de buse, type de g-code, identité machine. Les extraire garantit
que le 3MF chargera la bonne imprimante dans le slicer.

Sortie : data/printers_catalog.json — embarqué dans neoSlice (marche hors-ligne).

Usage : python tools/extract_printers.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Dossiers d'install par slicer (Windows). Chaque imprimante est taguée avec le(s)
# slicer(s) qui la supporte(nt) : Bambu Studio en supporte moins qu'OrcaSlicer.
_PROFILE_DIRS_BY_SLICER = {
    "bambu": [
        Path(r"C:\Program Files\Bambu Studio\resources\profiles"),
        Path(r"C:\Program Files (x86)\Bambu Studio\resources\profiles"),
    ],
    "orca": [
        Path(r"C:\Program Files\OrcaSlicer\resources\profiles"),
        Path(r"C:\Program Files (x86)\OrcaSlicer\resources\profiles"),
        Path.home() / "AppData/Local/Programs/OrcaSlicer/resources/profiles",
    ],
    # CrealityPrint 5+/6+ = fork OrcaSlicer (même format de profils). Dossier
    # versionné (« Creality Print 6.3 ») → on globe pour rester robuste aux MAJ.
    "creality": [
        *sorted(Path(r"C:\Program Files\Creality").glob("Creality Print*/resources/profiles")),
        *sorted(Path(r"C:\Program Files (x86)\Creality").glob("Creality Print*/resources/profiles")),
    ],
    # ElegooSlicer = fork OrcaSlicer (profils en SOUS-DOSSIERS EC/ECC2… → scan récursif).
    "elegoo": [
        Path(r"C:\Program Files\ElegooSlicer\resources\profiles"),
        Path(r"C:\Program Files (x86)\ElegooSlicer\resources\profiles"),
    ],
}

# Bambu Lab (BBL) géré à part via PRINTERS (catalogue enrichi). On l'exclut ici.
_SKIP_VENDORS = {"BBL", "Custom"}


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve(profile: dict, by_name: dict[str, dict], depth: int = 0) -> dict:
    """Fusionne la chaîne d'héritage `inherits` (parent → enfant)."""
    if depth > 12:
        return dict(profile)
    parent_name = profile.get("inherits")
    if parent_name and parent_name in by_name:
        merged = _resolve(by_name[parent_name], by_name, depth + 1)
        merged.update(profile)
        return merged
    return dict(profile)


def _first(v, default=None):
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _num(v, default):
    """Numérique robuste : liste → 1er élément ; chaîne « 500,500 » (klipper,
    CrealityPrint) → 1er token ; sinon valeur. Repli sur `default` si invalide."""
    if isinstance(v, list):
        v = v[0] if v else default
    if isinstance(v, str) and "," in v:
        v = v.split(",")[0]
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _bed_size(printable_area) -> str:
    """'0x0','220x0','220x220','0x220' → '220×220 mm'."""
    try:
        xs, ys = [], []
        for pt in printable_area:
            x, y = pt.split("x")
            xs.append(float(x)); ys.append(float(y))
        w = int(round(max(xs) - min(xs)))
        d = int(round(max(ys) - min(ys)))
        return f"{w}×{d}"
    except Exception:
        return ""


# Clés de métadonnées de hiérarchie à retirer du dump machine final
_MACHINE_SKIP = {"type", "from", "setting_id", "instantiation", "inherits",
                 "default_print_profile", "name"}


def _scan_vendor(mdir: Path, vendor_root: Path) -> dict[str, dict]:
    """Indexe les profils machine d'un vendor par 'name' (pour résoudre inherits).
    Récursif : ElegooSlicer range ses profils dans des sous-dossiers (EC, ECC2…)."""
    by_name: dict[str, dict] = {}
    for f in mdir.rglob("*.json"):
        d = _load(f)
        nm = d.get("name")
        if nm:
            by_name[nm] = d
    for f in vendor_root.glob("*.json"):   # communs fdm_*_common
        d = _load(f)
        nm = d.get("name")
        if nm and nm not in by_name:
            by_name[nm] = d
    return by_name


def extract() -> tuple[dict, dict]:
    catalog: dict[str, dict] = {}    # clé = name ; specs (léger, pour UI) + slicers
    machines: dict[str, dict] = {}   # clé = name ; config machine COMPLÈTE (pour 3MF)
    found_any = False

    for slicer, dirs in _PROFILE_DIRS_BY_SLICER.items():
        for root in dirs:
            if not root.exists():
                continue
            found_any = True
            # Toutes les marques (sauf BBL/Custom) présentes dans ce slicer
            for vendor_root in sorted(p for p in root.iterdir() if p.is_dir()):
                brand = vendor_root.name
                if brand in _SKIP_VENDORS:
                    continue
                mdir = vendor_root / "machine"
                if not mdir.exists():
                    continue
                by_name = _scan_vendor(mdir, vendor_root)
                for nm, raw in by_name.items():
                    if raw.get("instantiation") != "true" or raw.get("type") != "machine":
                        continue
                    if nm in catalog:                       # déjà vu dans l'autre slicer
                        if slicer not in catalog[nm]["slicers"]:
                            catalog[nm]["slicers"].append(slicer)
                        continue
                    full = _resolve(raw, by_name)
                    if full.get("printer_technology", "FFF") != "FFF":
                        continue
                    nozzle = _first(full.get("nozzle_diameter"), "0.4")
                    catalog[nm] = {
                        "marque": brand,
                        "name": nm,
                        "printer_model": full.get("printer_model", ""),
                        "printer_settings_id": full.get("printer_settings_id", brand),
                        "nozzle_diameter": str(nozzle),
                        "printer_variant": full.get("printer_variant", str(nozzle)),
                        "bed_size": _bed_size(full.get("printable_area", [])),
                        "printable_height": str(full.get("printable_height", "")),
                        "max_speed_mms": int(_num(full.get("machine_max_speed_x"), 500)),
                        "max_accel_mms2": int(_num(full.get("machine_max_acceleration_extruding"),
                                                   _num(full.get("machine_max_acceleration_x"), 10000))),
                        "gcode_flavor": full.get("gcode_flavor", ""),
                        "default_print_profile": full.get("default_print_profile", ""),
                        "default_filament_profile": _first(full.get("default_filament_profile"), ""),
                        "slicers": [slicer],
                    }
                    machines[nm] = {k: v for k, v in full.items() if k not in _MACHINE_SKIP}

    if not found_any:
        print("Aucun dossier de profils trouvé (Bambu Studio / OrcaSlicer).", file=sys.stderr)
        sys.exit(1)
    return catalog, machines


# Slicers-forks « stricts » (CrealityPrint, ElegooSlicer) pour lesquels on génère
# le vocabulaire de clés valides → sert au filtrage 3MF (tmf_builder).
_STRICT_SLICERS = ("creality", "elegoo")
# Métadonnées de hiérarchie à NE PAS compter comme clés de réglage.
_VOCAB_SKIP = {"type", "name", "inherits", "from", "instantiation", "setting_id",
               "version", "url", "filament_id", "is_custom_defined"}


def dump_slicer_vocab(data_dir: Path) -> None:
    """Écrit data/<slicer>_keys.json = union de TOUTES les clés des profils du
    slicer (process+machine+filament+commons). Permet à l'export de retirer du 3MF
    les clés Bambu-only que ce slicer ne connaît pas. Régénéré à chaque extraction."""
    for slicer in _STRICT_SLICERS:
        keys: set[str] = set()
        nfiles = 0
        for root in _PROFILE_DIRS_BY_SLICER.get(slicer, []):
            if not root.exists():
                continue
            for f in root.rglob("*.json"):
                d = _load(f)
                if not isinstance(d, dict):
                    continue
                nfiles += 1
                keys |= {k for k in d.keys() if k not in _VOCAB_SKIP}
        if keys:
            out = data_dir / f"{slicer}_keys.json"
            out.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=0),
                           encoding="utf-8")
            print(f"Vocabulaire {slicer:8}: {out}  ({len(keys)} clés, {nfiles} fichiers)")


def dump_slicer_presets(data_dir: Path) -> None:
    """Écrit data/<slicer>_presets.json = {"machines":[…], "filaments":[…]} = noms
    EXACTS des préréglages SYSTÈME installés (instantiation=true) de ce fork. Sert à
    l'export à aligner printer_settings_id/filament_settings_id sur de vrais
    préréglages → le fork les reconnaît comme « système » et n'affiche plus
    « préréglage personnalisé / confirmez le G-code »."""
    for slicer in _STRICT_SLICERS:
        machines_n: set[str] = set()
        filaments_n: set[str] = set()
        for root in _PROFILE_DIRS_BY_SLICER.get(slicer, []):
            if not root.exists():
                continue
            for f in root.rglob("*.json"):
                d = _load(f)
                if not isinstance(d, dict):
                    continue
                nm = d.get("name")
                # Seuls les préréglages réellement sélectionnables comptent.
                if not nm or str(d.get("instantiation", "")).lower() != "true":
                    continue
                low = str(f).lower()
                if "machine" in low:
                    machines_n.add(nm)
                elif "filament" in low:
                    filaments_n.add(nm)
        if machines_n or filaments_n:
            out = data_dir / f"{slicer}_presets.json"
            out.write_text(json.dumps(
                {"machines": sorted(machines_n), "filaments": sorted(filaments_n)},
                ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"Préréglages {slicer:8}: {out}  "
                  f"({len(machines_n)} machines, {len(filaments_n)} filaments)")


def main():
    catalog, machines = extract()
    data = Path(__file__).resolve().parent.parent / "data"
    out_cat = data / "printers_catalog.json"
    out_mac = data / "printer_machines.json"
    out_cat.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    out_mac.write_text(json.dumps(machines, ensure_ascii=False, indent=1), encoding="utf-8")
    dump_slicer_vocab(data)     # régénère creality_keys.json / elegoo_keys.json
    dump_slicer_presets(data)   # régénère creality_presets.json / elegoo_presets.json

    # Résumé console
    nb_bambu = sum(1 for e in catalog.values() if "bambu" in e["slicers"])
    nb_orca = sum(1 for e in catalog.values() if "orca" in e["slicers"])
    brands = sorted({e["marque"] for e in catalog.values()})
    print(f"Catalogue (UI)     : {out_cat}  ({len(catalog)} imprimantes, {len(brands)} marques)")
    print(f"Machines (3MF)     : {out_mac}  ({len(machines)} profils)")
    print(f"  Supportées Bambu Studio : {nb_bambu}")
    print(f"  Supportées OrcaSlicer   : {nb_orca}")
    print(f"  Marques : {', '.join(brands)}")


if __name__ == "__main__":
    main()
