"""Extracteur de catalogue d'imprimantes depuis les définitions officielles UltiMaker
Cura (share/cura/resources/definitions/*.def.json), résolues via leur chaîne
`inherits` — comme tools/extract_printers.py pour Bambu/Orca/Creality/Elegoo.

Cura structure ses profils très différemment de la famille Bambu/Orca :
  - une définition MACHINE (.def.json) hérite (inherits) d'une définition parente
    (souvent une famille "<marque>_base", elle-même héritant de fdmprinter) ;
  - les dimensions/gcode/extrudeur(s) sont dans `overrides` (résolu par héritage) ;
  - les BUSES disponibles sont des fichiers "variant" séparés
    (resources/variants/<quality_definition>/<id>_<buse>.inst.cfg) ;
  - les profils QUALITÉ (couche/vitesse) sont dans resources/quality/<quality_definition>/.
  - `metadata.visible = false` marque une définition ABSTRAITE (famille/parent),
    jamais une vraie imprimante sélectionnable → exclue du catalogue.

Sortie : data/cura_printers.json — {machine_id: {name, manufacturer, quality_definition,
width, depth, height, center_is_zero, extruder_count, heated_bed, gcode_flavor,
nozzles: [0.2, 0.4, ...], extruder_defs: [...]}}

Usage : python tools/extract_cura_printers.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

_CURA_ROOTS = [
    Path(r"C:\Program Files\UltiMaker Cura 5.6.0\share\cura\resources"),
]
for _p in sorted(Path(r"C:\Program Files").glob("*Cura*")):
    _r = _p / "share" / "cura" / "resources"
    if _r.exists() and _r not in _CURA_ROOTS:
        _CURA_ROOTS.append(_r)

_OUT = Path(__file__).resolve().parent.parent / "data" / "cura_printers.json"


def _find_root() -> Path | None:
    for r in _CURA_ROOTS:
        if (r / "definitions").exists():
            return r
    return None


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_chain(defs_dir: Path, def_id: str, cache: dict, depth: int = 0) -> dict:
    """Fusionne la chaîne d'héritage complète (parent -> enfant), en accumulant
    metadata + overrides (l'enfant écrase le parent)."""
    if def_id in cache:
        return cache[def_id]
    if depth > 15:
        return {"metadata": {}, "overrides": {}, "name": def_id}
    raw = _load(defs_dir / f"{def_id}.def.json")
    parent_id = raw.get("inherits")
    if parent_id:
        parent = _resolve_chain(defs_dir, parent_id, cache, depth + 1)
        merged_meta = dict(parent.get("metadata", {}))
        merged_meta.update(raw.get("metadata", {}))
        merged_ov = dict(parent.get("overrides", {}))
        merged_ov.update(raw.get("overrides", {}))
        merged = {
            "metadata": merged_meta,
            "overrides": merged_ov,
            "name": raw.get("name", parent.get("name", def_id)),
        }
    else:
        merged = {
            "metadata": dict(raw.get("metadata", {})),
            "overrides": dict(raw.get("overrides", {})),
            "name": raw.get("name", def_id),
        }
    cache[def_id] = merged
    return merged


def _ov_val(overrides: dict, key: str, default):
    v = overrides.get(key, {})
    if isinstance(v, dict) and "default_value" in v:
        return v["default_value"]
    return default


def _build_variant_index(resources: Path) -> dict[str, list[float]]:
    """Index GLOBAL des buses : les fichiers variant sont organisés en dossiers
    par MARQUE sur le disque, mais Cura les résout par le champ `[general]
    definition = <machine_id>` À L'INTÉRIEUR du fichier (constaté : le nom du
    dossier ne correspond ni à l'id machine ni à quality_definition). On scanne
    donc tous les .inst.cfg récursivement et on groupe par ce champ, pas par
    chemin ni par nom de fichier."""
    import configparser
    index: dict[str, list[float]] = {}
    vdir = resources / "variants"
    if not vdir.exists():
        return index
    for f in vdir.rglob("*.inst.cfg"):
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(f, encoding="utf-8")
        except Exception:
            continue
        definition = cp.get("general", "definition", fallback=None)
        if not definition:
            continue
        try:
            nz = float(cp.get("values", "machine_nozzle_size", fallback="0.4"))
        except ValueError:
            continue
        index.setdefault(definition, []).append(nz)
    return {k: sorted(set(v)) for k, v in index.items()}


def main() -> None:
    root = _find_root()
    if root is None:
        print("UltiMaker Cura introuvable — rien à extraire.")
        return
    defs_dir = root / "definitions"
    cache: dict[str, dict] = {}
    catalogue: dict[str, dict] = {}
    variant_index = _build_variant_index(root)

    def_files = sorted(defs_dir.glob("*.def.json"))
    print(f"{len(def_files)} définitions trouvées sous {defs_dir}")
    print(f"{len(variant_index)} machines avec buses indexées (variants)")

    for f in def_files:
        machine_id = f.name[: -len(".def.json")]
        resolved = _resolve_chain(defs_dir, machine_id, cache)
        meta = resolved["metadata"]
        if meta.get("visible") is False:
            continue                                   # définition abstraite (famille/parent)
        if not meta.get("has_machine_quality", True) and "quality_definition" not in meta:
            pass                                        # certaines n'ont pas de profil qualité dédié, on garde quand même
        overrides = resolved["overrides"]
        name = _ov_val(overrides, "machine_name", resolved.get("name", machine_id))
        width = _ov_val(overrides, "machine_width", 200.0)
        depth = _ov_val(overrides, "machine_depth", 200.0)
        height = _ov_val(overrides, "machine_height", 200.0)
        center0 = _ov_val(overrides, "machine_center_is_zero", False)
        extruder_count = int(_ov_val(overrides, "machine_extruder_count", 1))
        heated_bed = bool(_ov_val(overrides, "machine_heated_bed", False))
        gcode_flavor = _ov_val(overrides, "machine_gcode_flavor", "RepRap (Marlin/Sprinter)")
        quality_def = meta.get("quality_definition", machine_id)
        manufacturer = meta.get("manufacturer", "Autre")
        nozzle_single = _ov_val(overrides, "machine_nozzle_size", None)

        nozzles = variant_index.get(machine_id, [])
        if not nozzles:
            nozzles = [float(nozzle_single)] if nozzle_single is not None else [0.4]

        # ids des définitions d'extrudeur (pour construire un 3MF projet fidèle) :
        trains = meta.get("machine_extruder_trains", {}) or {}
        extruder_defs = [trains.get(str(i), f"{machine_id}_extruder_{i}")
                         for i in range(extruder_count)]

        catalogue[machine_id] = {
            "name": name,
            "manufacturer": manufacturer,
            "quality_definition": quality_def,
            "width": float(width) if isinstance(width, (int, float)) else 200.0,
            "depth": float(depth) if isinstance(depth, (int, float)) else 200.0,
            "height": float(height) if isinstance(height, (int, float)) else 200.0,
            "center_is_zero": bool(center0),
            "extruder_count": extruder_count,
            "heated_bed": heated_bed,
            "gcode_flavor": gcode_flavor,
            "nozzles": nozzles,
            "extruder_defs": extruder_defs,
        }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(catalogue, indent=1, ensure_ascii=False), encoding="utf-8")
    brands = sorted({v["manufacturer"] for v in catalogue.values()})
    print(f"{len(catalogue)} imprimantes Cura -> {_OUT} ({len(brands)} marques)")


if __name__ == "__main__":
    main()
