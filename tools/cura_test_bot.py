"""BOT de test AUTOMATIQUE neoSlice → UltiMaker Cura (boucle fermée complète).

Pour chaque cas d'une matrice (imprimantes × buses × filaments × réglages ×
pièces avec surplombs) :
  1. génère la pièce (dont formes à SURPLOMBS : T, demi-sphère) ;
  2. exporte le 3MF projet via CuraThreeMFBuilder (le vrai code de l'app) ;
  3. valide la STRUCTURE avec le simulateur preRead (tests/test_cura_3mf.py) ;
  4. [--cura] ouvre le fichier dans le VRAI Cura installé et vérifie :
     - son cura.log : marqueurs d'échec internes (« not a valid workspace »,
       « Could not find quality_changes », machine inconnue…) et de succès
       (« Loading custom profile ») ;
     - les VALEURS RÉELLEMENT APPLIQUÉES : Cura auto-sauvegarde les conteneurs
       dans %APPDATA%/cura/5.6/quality_changes/ → le bot les relit et les
       compare clé par clé à ce que neoSlice a exporté (c'est exactement ce
       qui aurait détecté le bug « infill 20 % au lieu de 80 % », invisible
       dans les logs).

Sécurité : la config Cura de l'utilisateur est SAUVEGARDÉE avant et RESTAURÉE
après (et entre chaque cas → état propre, pas de sentinelle de crash, pas de
pollution par les profils de test). Le bot REFUSE de démarrer si Cura est déjà
ouvert (travail non sauvegardé).

Usage :
  python tools/cura_test_bot.py                 # structurel seul (rapide, sans GUI)
  python tools/cura_test_bot.py --cura          # + vrais lancements de Cura (~2 min/cas)
  python tools/cura_test_bot.py --cura --cases s5_extrafine
Rapport : _calib/cura_bot_report.json + tableau console.
"""
from __future__ import annotations

import argparse
import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import trimesh

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests"))

from core.export.cura_3mf_builder import CuraThreeMFBuilder, _config_to_cura  # noqa: E402
from core.parameters.print_config import PrintConfig                          # noqa: E402

_CURA_CFG_DIR = Path(os.environ.get("APPDATA", "")) / "cura" / "5.6"
_CURA_EXES = [p for base in (r"C:\Program Files", r"C:\Program Files (x86)")
              for p in sorted(Path(base).glob("UltiMaker Cura*/UltiMaker-Cura.exe"))]
_REPORT = _REPO / "_calib" / "cura_bot_report.json"

# Clés comparées entre « exporté par neoSlice » et « appliqué par Cura »
_KEYS_VERIFIEES = [
    "layer_height", "layer_height_0", "infill_sparse_density", "infill_pattern",
    "support_enable", "support_structure", "adhesion_type",
    "material_print_temperature", "material_bed_temperature", "speed_wall_0",
]

_MARQUEURS_ECHEC = [
    "is not a valid workspace", "No global stack file found",
    "Could not find quality_changes", "contains an unknown machine type",
    "Failed to deserialize", "doesn't seem to be valid stack file",
]
_MARQUEUR_SUCCES = "Loading custom profile ["


# ── Pièces de test (dont surplombs) ──────────────────────────────────────────
def _piece_t_surplomb() -> trimesh.Trimesh:
    """T inversé : barre horizontale en porte-à-faux des deux côtés (surplombs
    francs à 90° → supports indispensables)."""
    pied = trimesh.creation.box((10, 10, 30))
    pied.apply_translation((0, 0, 15))
    barre = trimesh.creation.box((50, 10, 8))
    barre.apply_translation((0, 0, 34))
    return trimesh.util.concatenate([pied, barre])


def _piece_demi_sphere() -> trimesh.Trimesh:
    """Demi-sphère coupole (surplombs progressifs sur tout le pourtour)."""
    s = trimesh.creation.icosphere(subdivisions=3, radius=20)
    s.apply_translation((0, 0, 0))
    boite = trimesh.creation.box((50, 50, 25))
    boite.apply_translation((0, 0, 12.5))
    demi = s.slice_plane((0, 0, 0), (0, 0, 1), cap=True)
    demi.apply_translation((0, 0, 0.0))
    return demi if demi is not None and len(demi.faces) else s


# ── Matrice de cas ───────────────────────────────────────────────────────────
def _cases() -> dict[str, dict]:
    return {
        # LE cas du testeur : S5, extra-fin + ultra-solide
        "s5_extrafine": dict(
            machine="ultimaker_s5", nozzle=0.4, filament="PLA",
            mesh=trimesh.creation.box((30, 30, 15)),
            config=PrintConfig(layer_height=0.06, first_layer_height=0.2,
                               infill_density=80, infill_pattern="gyroid")),
        # surplombs francs → supports arbre
        "ender3_tree_surplomb": dict(
            machine="creality_ender3", nozzle=0.4, filament="PLA",
            mesh=_piece_t_surplomb(),
            config=PrintConfig(layer_height=0.16, support_type="tree(auto)",
                               infill_density=30, infill_pattern="cubic")),
        # coupole + supports classiques + brim
        "ender3_dome_brim": dict(
            machine="creality_ender3", nozzle=0.6, filament="PETG",
            mesh=_piece_demi_sphere(),
            config=PrintConfig(layer_height=0.28, support_type="normal(auto)",
                               brim_type="outer_only", brim_width=8.0,
                               nozzle_temperature=245, bed_temperature=80)),
        # machine SANS variants (buse via definition_changes) + TPU lent
        "kobra_max_tpu": dict(
            machine="anycubic_kobra_max", nozzle=0.4, filament="TPU",
            mesh=trimesh.creation.box((25, 25, 12)),
            config=PrintConfig(layer_height=0.2, outer_wall_speed=25,
                               inner_wall_speed=35, infill_speed=40,
                               nozzle_temperature=225, bed_temperature=45)),
        # petite buse 0.2 + fin
        "cr10_fine02": dict(
            machine="creality_cr10", nozzle=0.2, filament="PLA",
            mesh=trimesh.creation.box((20, 20, 10)),
            config=PrintConfig(layer_height=0.08, infill_density=15,
                               infill_pattern="grid")),
    }


# ── Phase 1 : structurel (simulateur preRead) ────────────────────────────────
def _structurel(path: Path) -> tuple[bool, str]:
    try:
        try:
            import pytest  # noqa: F401  (le module de test l'importe)
        except ImportError:
            import types
            stub = types.ModuleType("pytest")
            stub.mark = types.SimpleNamespace(
                parametrize=lambda *a, **k: (lambda f: f))
            stub.raises = None
            sys.modules["pytest"] = stub
        import test_cura_3mf as sim
        info = sim._pre_read_simulation(path)
        return True, f"OK ({info['machine_def_id']}, {info['n_extruders']} extr.)"
    except AssertionError as e:
        return False, f"SIMULATEUR: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ── Phase 2 : vrai Cura ──────────────────────────────────────────────────────
def _cura_tourne() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UltiMaker-Cura.exe"],
                         capture_output=True, text=True)
    return "UltiMaker-Cura.exe" in out.stdout


def _tuer_cura() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "UltiMaker-Cura.exe"],
                   capture_output=True)
    time.sleep(3)


def _restaurer_config(backup: Path) -> None:
    if _CURA_CFG_DIR.exists():
        shutil.rmtree(_CURA_CFG_DIR, ignore_errors=True)
    shutil.copytree(backup, _CURA_CFG_DIR)


def _forcer_ouverture_projet() -> None:
    """cura.cfg : choice_on_open_project=open_as_project → pas de dialogue bloquant."""
    cfg = _CURA_CFG_DIR / "cura.cfg"
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(cfg, encoding="utf-8")
    if not cp.has_section("cura"):
        cp.add_section("cura")
    cp.set("cura", "choice_on_open_project", "open_as_project")
    with open(cfg, "w", encoding="utf-8") as f:
        cp.write(f)


_PLUGIN_JSON = json.dumps({
    "name": "NeoSlice Auto Accept",
    "author": "neoSlice test bot",
    "version": "1.0.0",
    "description": "Auto-accepte le WorkspaceDialog (bot de test uniquement).",
    "api": 8,
    "supported_sdk_versions": ["8.6.0"],
}, indent=1)

_PLUGIN_INIT = '''# Bot neoSlice : auto-accepte le dialogue projet (strategies par defaut,
# equivalent au clic sur « Ouvrir »). Installe UNIQUEMENT dans la config
# sandbox du bot — jamais dans la config utilisateur (restauree apres).
# register() DOIT renvoyer un objet plugin (une Extension vide suffit), sinon
# Cura affiche « could not be loaded / Remove plugin » (vecu).
from UM.Extension import Extension
from UM.Logger import Logger


def _patch():
    import sys
    m = sys.modules.get("3MFReader.WorkspaceDialog")
    if m is None:
        Logger.log("w", "NeoSliceAutoAccept: module WorkspaceDialog absent")
        return
    D = m.WorkspaceDialog
    D.show = lambda self: Logger.log(
        "i", "NeoSliceAutoAccept: dialogue auto-accepte")
    D.waitForClose = lambda self: None
    Logger.log("i", "NeoSliceAutoAccept: patch actif")


class NeoSliceAutoAccept(Extension):
    def __init__(self, app):
        super().__init__()
        try:
            app.callLater(_patch)
        except Exception:
            _patch()


def getMetaData():
    return {}


def register(app):
    return {"extension": NeoSliceAutoAccept(app)}
'''


def _installer_plugin_auto() -> None:
    """Dépose le plugin auto-accepteur dans la config RESTAURÉE (sandbox du bot).
    Le WorkspaceDialog (résumé/conflits) s'affiche TOUJOURS pendant la lecture
    d'un projet (preRead ligne 620) — la préférence open_as_project ne saute que
    le premier choix « projet ou modèles ». Sans ce patch, waitForClose() bloque
    et le bot ne peut pas être full-auto."""
    d = _CURA_CFG_DIR / "plugins" / "NeoSliceAutoAccept" / "NeoSliceAutoAccept"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(_PLUGIN_JSON, encoding="utf-8")
    (d / "__init__.py").write_text(_PLUGIN_INIT, encoding="utf-8")


def self_save_log(case_name: str, txt: str) -> None:
    """Copie le cura.log capturé dans _calib/ AVANT restauration (diagnostic)."""
    try:
        out = _REPO / "_calib" / f"cura_bot_log_{case_name}.log"
        out.parent.mkdir(exist_ok=True)
        out.write_text(txt, encoding="utf-8")
    except Exception:
        pass


def _valeurs_appliquees(nom_profil: str) -> dict[str, str]:
    """Relit les [values] des quality_changes 'neoSlice <machine>' auto-sauvegardés
    par Cura (global + extrudeurs fusionnés) — les valeurs RÉELLEMENT appliquées."""
    vals: dict[str, str] = {}
    qdir = _CURA_CFG_DIR / "quality_changes"
    if not qdir.exists():
        return vals
    for f in qdir.glob("*.inst.cfg"):
        cp = configparser.ConfigParser(interpolation=None, comment_prefixes=())
        try:
            cp.read(f, encoding="utf-8")
        except Exception:
            continue
        if cp.get("general", "name", fallback="") != nom_profil:
            continue
        if cp.has_section("values"):
            vals.update(dict(cp.items("values")))
    return vals


def _test_reel_cura(path: Path, machine_display: str, attendu: dict,
                    backup: Path, case_name: str,
                    timeout: int = 300) -> tuple[bool, str, dict]:
    exe = str(_CURA_EXES[0])
    _restaurer_config(backup)
    _forcer_ouverture_projet()
    _installer_plugin_auto()
    log = _CURA_CFG_DIR / "cura.log"
    log.unlink(missing_ok=True)

    shutil.copy(_CURA_CFG_DIR / "cura.cfg",
                _REPO / "_calib" / f"cura_bot_cfg_{case_name}_avant.cfg")
    proc = subprocess.Popen([exe, str(path)])
    marqueur, t0, txt = None, time.time(), ""
    demarre = False
    try:
        while time.time() - t0 < timeout:
            time.sleep(5)
            if proc.poll() is not None and not log.exists():
                return False, f"Cura s'est terminé immédiatement (code {proc.returncode})", {}
            txt = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
            if not demarre and ("Booting Cura took" in txt or "Loading UI" in txt):
                demarre = True
            for m in _MARQUEURS_ECHEC:
                if m in txt:
                    self_save_log(case_name, txt)
                    return False, f"CURA LOG: « {m} »", {}
            if _MARQUEUR_SUCCES in txt:
                marqueur = "charge"
                break
        self_save_log(case_name, txt)
        try:                                   # cura.cfg vu par Cura (post-autosave)
            shutil.copy(_CURA_CFG_DIR / "cura.cfg",
                        _REPO / "_calib" / f"cura_bot_cfg_{case_name}_apres.cfg")
        except Exception:
            pass
        if marqueur is None:
            etat = "démarré mais projet non chargé" if demarre else "Cura pas (encore) démarré"
            return False, f"timeout {timeout}s — {etat} (log: _calib/cura_bot_log_{case_name}.log)", {}

        time.sleep(45)                     # AutoSave écrit les conteneurs appliqués
        nom_profil = f"neoSlice {machine_display}"
        vals = _valeurs_appliquees(nom_profil)
        if not vals:
            return False, f"profil « {nom_profil} » introuvable dans la config auto-sauvée", {}

        diffs = {}
        for k in _KEYS_VERIFIEES:
            if k not in attendu:
                continue
            a, b = str(attendu[k]), str(vals.get(k, "(absent)"))
            try:
                same = abs(float(a) - float(b)) < 1e-6
            except ValueError:
                same = a == b
            if not same:
                diffs[k] = {"exporté": a, "appliqué": b}
        if diffs:
            return False, f"{len(diffs)} valeur(s) non appliquée(s)", diffs
        return True, f"profil appliqué, {len([k for k in _KEYS_VERIFIEES if k in attendu])} clés vérifiées", {}
    finally:
        _tuer_cura()


# ── Orchestration ────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cura", action="store_true",
                    help="lance le VRAI Cura pour chaque cas (sinon structurel seul)")
    ap.add_argument("--cases", default="", help="liste de cas séparés par des virgules")
    args = ap.parse_args()

    if not _CURA_EXES and args.cura:
        print("UltiMaker Cura introuvable — mode structurel seul.")
        args.cura = False
    if args.cura and _cura_tourne():
        print("REFUS : UltiMaker Cura est déjà ouvert (fermez-le d'abord — "
              "le bot restaure la config entre chaque cas).")
        return 2

    cases = _cases()
    if args.cases:
        keep = {c.strip() for c in args.cases.split(",")}
        cases = {k: v for k, v in cases.items() if k in keep}

    outdir = Path(tempfile.mkdtemp(prefix="neoslice_cura_bot_"))
    backup = None
    if args.cura:
        backup = Path(tempfile.mkdtemp(prefix="cura_cfg_backup_")) / "5.6"
        shutil.copytree(_CURA_CFG_DIR, backup)
        print(f"Config Cura sauvegardée -> {backup}")

    from data.printers import cura_machine_for
    rapport = {}
    try:
        for nom, c in cases.items():
            path = outdir / f"{nom}.3mf"
            CuraThreeMFBuilder().build(c["mesh"], c["config"], path,
                                       object_name=nom, printer_ui_name=c["machine"],
                                       filament_ui_name=c["filament"],
                                       nozzle_diameter_mm=c["nozzle"])
            ok_s, msg_s = _structurel(path)
            entry = {"fichier": str(path), "structurel": {"ok": ok_s, "detail": msg_s}}
            print(f"[{nom}] structurel : {'OK ' if ok_s else 'ÉCHEC'} — {msg_s}")

            if args.cura and ok_s:
                attendu = _config_to_cura(c["config"], c["filament"])
                display = cura_machine_for(c["machine"]).get("name", c["machine"])
                ok_r, msg_r, diffs = _test_reel_cura(path, display, attendu, backup, nom)
                entry["cura_reel"] = {"ok": ok_r, "detail": msg_r, "diffs": diffs}
                print(f"[{nom}] Cura réel  : {'OK ' if ok_r else 'ÉCHEC'} — {msg_r}")
                if diffs:
                    for k, d in diffs.items():
                        print(f"      {k}: exporté={d['exporté']}  appliqué={d['appliqué']}")
            rapport[nom] = entry
    finally:
        if backup is not None:
            _tuer_cura()
            _restaurer_config(backup)
            shutil.rmtree(backup.parent, ignore_errors=True)
            print("Config Cura restaurée.")

    _REPORT.parent.mkdir(exist_ok=True)
    _REPORT.write_text(json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport -> {_REPORT}")
    ko = [n for n, e in rapport.items()
          if not e["structurel"]["ok"] or not e.get("cura_reel", {}).get("ok", True)]
    print("BILAN :", "TOUT OK" if not ko else f"ÉCHECS: {', '.join(ko)}")
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
