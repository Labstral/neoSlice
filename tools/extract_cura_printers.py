"""Extracteur de catalogue d'imprimantes depuis les définitions officielles UltiMaker
Cura (share/cura/resources/definitions/*.def.json), résolues via leur chaîne
`inherits` — comme tools/extract_printers.py pour Bambu/Orca/Creality/Elegoo.

Cura structure ses profils très différemment de la famille Bambu/Orca :
  - une définition MACHINE (.def.json) hérite (inherits) d'une définition parente
    (souvent une famille "<marque>_base", elle-même héritant de fdmprinter) ;
  - les dimensions/gcode/extrudeur(s) sont dans `overrides` (résolu par héritage) ;
  - les BUSES sont des fichiers "variant" séparés (resources/variants/**/*.inst.cfg),
    rattachés à la machine par le champ `[general] definition` À L'INTÉRIEUR du
    fichier (PAS par le nom du dossier/fichier — vérifié, contre-intuitif) ;
  - le DIAMÈTRE de filament vit dans la définition d'EXTRUDEUR
    (resources/extruders/<id>.def.json, hérite de fdmextruder, défaut 2.85) ;
  - un projet 3MF valide doit EMBARQUER ces conteneurs (def.json machine,
    variant .inst.cfg, matériau .xml.fdm_material) — exigences relevées dans
    ThreeMFWorkspaceReader.preRead (machine_definition_container_count == 1,
    KeyError si variant/matériau référencé absent de l'archive).

Sorties :
  - data/cura_printers.json  — catalogue machines (specs + variants bruts + méta)
  - data/cura_materials.json — matériaux génériques bruts (generic_*.xml.fdm_material)

Usage : python tools/extract_cura_printers.py
"""
from __future__ import annotations
import configparser
import json
from pathlib import Path

_CURA_ROOTS = [
    Path(r"C:\Program Files\UltiMaker Cura 5.6.0\share\cura\resources"),
]
for _p in sorted(Path(r"C:\Program Files").glob("*Cura*")):
    _r = _p / "share" / "cura" / "resources"
    if _r.exists() and _r not in _CURA_ROOTS:
        _CURA_ROOTS.append(_r)

_DATA = Path(__file__).resolve().parent.parent / "data"
_OUT_PRINTERS = _DATA / "cura_printers.json"
_OUT_MATERIALS = _DATA / "cura_materials.json"


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


def _build_variant_index(resources: Path) -> dict[str, dict[str, list]]:
    """Index GLOBAL des variants BUSE : {definition_id: {nozzle: [{id, name, cfg}…]}}.
    On garde le CONTENU BRUT du .inst.cfg : il doit être embarqué tel quel dans
    le 3MF projet (le lecteur Cura exige la présence du conteneur variant dans
    l'archive quand la pile y fait référence — sinon KeyError dans preRead).
    Filtres appris à la dure : hardware_type doit être « nozzle » (les variants
    PLATEAU comme « ultimaker_s5_glass » polluaient l'index) et machine_nozzle_size
    doit être EXPLICITE (pas de 0.4 par défaut inventé). Plusieurs variants
    peuvent partager une buse (AA/BB/CC chez UltiMaker) → liste, départagée par
    machine via preferred_variant_name."""
    index: dict[str, dict[str, list]] = {}
    vdir = resources / "variants"
    if not vdir.exists():
        return index
    for f in vdir.rglob("*.inst.cfg"):
        cp = configparser.ConfigParser(interpolation=None)
        try:
            raw = f.read_text(encoding="utf-8")
            cp.read_string(raw)
        except Exception:
            continue
        definition = cp.get("general", "definition", fallback=None)
        if not definition:
            continue
        if cp.get("metadata", "hardware_type", fallback="nozzle") != "nozzle":
            continue                                    # plateau/verre… pas une buse
        vid = f.name[: -len(".inst.cfg")]
        vname = cp.get("general", "name", fallback=vid)
        size = cp.get("values", "machine_nozzle_size", fallback=None)
        if size is None:
            # Les variants UltiMaker (AA 0.4, BB 0.8…) n'ont PAS machine_nozzle_size :
            # la buse est encodée dans le NOM. Repli : dernier nombre du nom.
            import re as _re
            m = _re.search(r"(\d+(?:\.\d+)?)\s*$", vname)
            if not m:
                continue
            size = m.group(1)
        try:
            nz = f"{float(size):g}"
        except ValueError:
            continue
        index.setdefault(definition, {}).setdefault(nz, []).append(
            {"id": vid, "name": vname, "cfg": raw})
    return index


def _choisir_variants(candidats: dict[str, list], preferred_name: str) -> dict[str, dict]:
    """{nozzle: [candidats]} -> {nozzle: {id, name, cfg}} : le variant préféré de
    la machine (preferred_variant_name, ex. « AA 0.4 ») gagne sa buse ; sinon le
    1er par ordre alphabétique (stable, AA avant BB/CC)."""
    out: dict[str, dict] = {}
    for nz, lst in candidats.items():
        lst = sorted(lst, key=lambda v: (v["name"] != preferred_name, v["name"]))
        out[nz] = lst[0]
    return out


def _extruder_diameter(resources: Path, ext_def_id: str, cache: dict) -> float:
    """material_diameter de la définition d'extrudeur (chaîne inherits jusqu'à
    fdmextruder, défaut 2.85). Les machines 1.75 mm l'overrident ici."""
    if ext_def_id in cache:
        return cache[ext_def_id]
    d = 2.85
    f = resources / "extruders" / f"{ext_def_id}.def.json"
    raw = _load(f)
    ov = raw.get("overrides", {})
    v = ov.get("material_diameter", {})
    if isinstance(v, dict) and "default_value" in v:
        d = float(v["default_value"])
    elif raw.get("inherits") and raw["inherits"] != "fdmextruder":
        d = _extruder_diameter(resources, raw["inherits"], cache)
    cache[ext_def_id] = d
    return d


def _extract_materials(resources: Path) -> None:
    """Matériaux génériques bruts (embarqués dans le 3MF projet : le lecteur exige
    le .xml.fdm_material dans l'archive pour tout matériau non-« empty »)."""
    out: dict[str, str] = {}
    mdir = resources / "materials"
    if mdir.exists():
        for f in sorted(mdir.glob("generic_*.xml.fdm_material")):
            stem = f.name[: -len(".xml.fdm_material")]
            try:
                out[stem] = f.read_text(encoding="utf-8")
            except Exception:
                continue
    _OUT_MATERIALS.write_text(json.dumps(out, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"{len(out)} matériaux génériques -> {_OUT_MATERIALS} "
          f"({_OUT_MATERIALS.stat().st_size // 1024} KB)")


def main() -> None:
    root = _find_root()
    if root is None:
        print("UltiMaker Cura introuvable — rien à extraire.")
        return
    defs_dir = root / "definitions"
    cache: dict[str, dict] = {}
    ext_diam_cache: dict[str, float] = {}
    catalogue: dict[str, dict] = {}
    variant_index = _build_variant_index(root)

    def_files = sorted(defs_dir.glob("*.def.json"))
    print(f"{len(def_files)} définitions trouvées sous {defs_dir}")
    print(f"{len(variant_index)} machines avec buses indexées (variants)")

    extruder_def_raws: dict[str, str] = {}             # dédupliqués (familles partagées)
    for f in def_files:
        machine_id = f.name[: -len(".def.json")]
        resolved = _resolve_chain(defs_dir, machine_id, cache)
        meta = resolved["metadata"]
        if meta.get("visible") is False:
            continue                                   # définition abstraite (famille/parent)
        overrides = resolved["overrides"]
        name = _ov_val(overrides, "machine_name", resolved.get("name", machine_id))
        extruder_count = int(_ov_val(overrides, "machine_extruder_count", 1))
        trains = meta.get("machine_extruder_trains", {}) or {}
        extruder_defs = [trains.get(str(i), f"{machine_id}_extruder_{i}")
                         for i in range(extruder_count)]

        variants = _choisir_variants(variant_index.get(machine_id, {}),
                                     meta.get("preferred_variant_name", ""))
        nozzles = sorted(float(k) for k in variants) if variants else []
        if not nozzles:
            single = _ov_val(overrides, "machine_nozzle_size", None)
            nozzles = [float(single)] if single is not None else [0.4]

        catalogue[machine_id] = {
            "name": name,
            "manufacturer": meta.get("manufacturer", "Autre"),
            "quality_definition": meta.get("quality_definition", machine_id),
            "width": float(_ov_val(overrides, "machine_width", 200.0)),
            "depth": float(_ov_val(overrides, "machine_depth", 200.0)),
            "height": float(_ov_val(overrides, "machine_height", 200.0)),
            "center_is_zero": bool(_ov_val(overrides, "machine_center_is_zero", False)),
            "extruder_count": extruder_count,
            "heated_bed": bool(_ov_val(overrides, "machine_heated_bed", False)),
            "gcode_flavor": _ov_val(overrides, "machine_gcode_flavor",
                                    "RepRap (Marlin/Sprinter)"),
            "nozzles": nozzles,
            "extruder_defs": extruder_defs,
            # ── champs 3MF projet (exigences ThreeMFWorkspaceReader) ────────
            "variants": variants,                       # {nozzle: {id, cfg brut}}
            "variants_name": meta.get("variants_name", "Nozzle"),
            "has_variants": bool(meta.get("has_variants", False)),
            "has_materials": bool(meta.get("has_materials", True)),
            "preferred_material": meta.get("preferred_material", "generic_pla"),
            "preferred_quality_type": meta.get("preferred_quality_type", "normal"),
            "material_diameter": _extruder_diameter(root, extruder_defs[0],
                                                    ext_diam_cache),
            # def.json COMPLET (le writer officiel embarque l'original ; un def
            # minimal synthétisé est un risque inutile)
            "def_raw": f.read_text(encoding="utf-8"),
        }
        for ed in extruder_defs:
            if ed not in extruder_def_raws:
                ef = root / "extruders" / f"{ed}.def.json"
                if ef.exists():
                    extruder_def_raws[ed] = ef.read_text(encoding="utf-8")

    # Clé réservée (préfixe __) : dictionnaire dédupliqué des def.json d'extrudeur.
    catalogue["__extruder_defs__"] = extruder_def_raws

    _OUT_PRINTERS.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PRINTERS.write_text(json.dumps(catalogue, indent=1, ensure_ascii=False),
                             encoding="utf-8")
    brands = sorted({v["manufacturer"] for k, v in catalogue.items()
                     if not k.startswith("__")})
    n_machines = sum(1 for k in catalogue if not k.startswith("__"))
    print(f"{n_machines} imprimantes Cura ({len(extruder_def_raws)} defs extrudeur) "
          f"-> {_OUT_PRINTERS} ({_OUT_PRINTERS.stat().st_size // 1024} KB, "
          f"{len(brands)} marques)")

    _extract_materials(root)


if __name__ == "__main__":
    main()
