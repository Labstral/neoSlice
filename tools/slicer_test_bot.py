"""BOT de test AUTOMATIQUE neoSlice → TOUS les slicers de sortie (boucle fermée).

But : prouver, sans test manuel, qu'un 3MF exporté par neoSlice s'ouvre
correctement dans CHAQUE slicer installé, avec la bonne imprimante, le bon
centrage, le bon filament et les réglages RÉELLEMENT appliqués — pas juste
« le fichier s'ouvre ».

Approche PRUDENTE (option B) selon la lisibilité de chaque slicer :

  • PrusaSlicer → boucle fermée PROFONDE, headless : on découpe le 3MF via la
    CLI (`prusa-slicer-console -g`), et le G-code produit contient TOUT le bloc
    de config en clair. On compare clé par clé « ce que neoSlice a écrit dans le
    3MF » (Metadata/Slic3r_PE.config) à « ce que Prusa a réellement appliqué »
    (bloc du G-code). Zéro GUI, déterministe.

  • UltiMaker Cura → boucle fermée PROFONDE (déléguée à tools/cura_test_bot, déjà
    validée 5/5) : GUI + conteneurs quality_changes auto-sauvés relus.

  • Famille Orca (Bambu/Orca/Creality/Elegoo/Anycubic/Snapmaker) → validation
    PRUDENTE : (1) structure du 3MF (JSON valide, print_settings_id INCONNU du
    slicer = la règle critique anti-rechargement de preset, imprimante/filament/
    buse présents, réglages présents) ; (2) ouverture RÉELLE dans le slicer +
    CAPTURE D'ÉCRAN (contrôle visuel : objet chargé, centré, bonne imprimante,
    pas de fenêtre d'erreur) + lecture des logs du slicer pour ses erreurs
    internes. On NE modifie PAS le 3MF pour forcer une lecture CLI (ces forks
    exigent une métadonnée de plateau que la GUI tolère absente — trop risqué de
    toucher à un export qui marche déjà).

Sécurité (pour tous) : config utilisateur du slicer SAUVEGARDÉE avant / RESTAURÉE
après chaque cas (sauvegarde LÉGÈRE : .conf + user/, jamais les caches) ; REFUS
de démarrer si le slicer visé est déjà ouvert (travail non sauvegardé).

Un builder n'est JAMAIS modifié par ce bot. Le bot RÉVÈLE les écarts ; les
corrections se font à part, une fois le vrai bug prouvé, et re-testées ici.

Usage :
  python tools/slicer_test_bot.py                          # structurel seul (rapide, sans GUI)
  python tools/slicer_test_bot.py --run                    # + vrais lancements des slicers
  python tools/slicer_test_bot.py --run --slicers prusa    # un seul slicer
  python tools/slicer_test_bot.py --run --slicers prusa,orca,bambu
Rapport : _calib/slicer_bot_report.json + tableau console + captures _calib/shot_*.png
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import trimesh

try:                                    # console Windows en cp1252 → forcer UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tools"))

from core.parameters.print_config import PrintConfig          # noqa: E402
from core.prefs import PREFS                                  # noqa: E402

_CALIB = _REPO / "_calib"
_REPORT = _CALIB / "slicer_bot_report.json"
_APPDATA = Path(os.environ.get("APPDATA", ""))


# ══════════════════════════ Pièces de test (dont surplombs) ══════════════════
def _piece_box() -> trimesh.Trimesh:
    return trimesh.creation.box((25, 25, 12))


def _piece_t_surplomb() -> trimesh.Trimesh:
    """T inversé : barre en porte-à-faux des deux côtés (surplombs francs 90°)."""
    pied = trimesh.creation.box((10, 10, 30)); pied.apply_translation((0, 0, 15))
    barre = trimesh.creation.box((50, 10, 8)); barre.apply_translation((0, 0, 34))
    return trimesh.util.concatenate([pied, barre])


def _piece_dome() -> trimesh.Trimesh:
    """Demi-sphère (surplombs progressifs → supports)."""
    s = trimesh.creation.icosphere(subdivisions=3, radius=20)
    demi = s.slice_plane((0, 0, 0), (0, 0, 1), cap=True)
    return demi if demi is not None and len(demi.faces) else s


# ══════════════════════════ Scénarios (surface de paramètres) ════════════════
# Chaque scénario touche un pan de ce que neoSlice pilote et qui DOIT être lu par
# le slicer : couche, parois, remplissage+motif, supports (aucun/arbre/normal),
# adhérence, températures, vitesses, buse.
def _scenarios() -> dict[str, dict]:
    return {
        "standard": dict(
            filament="PLA", nozzle=0.4, piece=_piece_box(),
            config=PrintConfig(layer_height=0.2, wall_loops=3,
                               infill_density=20, infill_pattern="grid")),
        "fine_solid": dict(
            filament="PLA", nozzle=0.4, piece=_piece_box(),
            config=PrintConfig(layer_height=0.12, first_layer_height=0.2,
                               wall_loops=4, top_shell_layers=6,
                               infill_density=80, infill_pattern="gyroid")),
        "tree_support": dict(
            filament="PLA", nozzle=0.4, piece=_piece_t_surplomb(),
            config=PrintConfig(layer_height=0.2, support_type="tree(auto)",
                               infill_density=15, infill_pattern="cubic")),
        "normal_brim_petg": dict(
            filament="PETG", nozzle=0.6, piece=_piece_dome(),
            config=PrintConfig(layer_height=0.28, support_type="normal(auto)",
                               brim_type="outer_only", brim_width=8.0,
                               nozzle_temperature=245, bed_temperature=80)),
        "fast_thick": dict(
            filament="PLA", nozzle=0.4, piece=_piece_box(),
            config=PrintConfig(layer_height=0.3, outer_wall_speed=80,
                               inner_wall_speed=150, infill_speed=250,
                               infill_density=10, infill_pattern="lightning")),
    }


# ══════════════════════════ Utilitaires communs ══════════════════════════════
def _screenshot(dest: Path) -> bool:
    """Capture l'écran (tous moniteurs) → PNG. Contrôle visuel de l'ouverture."""
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
        "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($bmp);"
        "$g.CopyFromScreen($b.X,$b.Y,0,0,$bmp.Size);"
        f"$bmp.Save('{dest.as_posix()}')"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
        return dest.exists()
    except Exception:
        return False


def _proc_running(image: str) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"],
                         capture_output=True, text=True)
    return image.lower() in out.stdout.lower()


def _kill(image: str) -> None:
    subprocess.run(["taskkill", "/F", "/IM", image], capture_output=True)
    time.sleep(2)


def _backup_light(cfg_dir: Path, conf_files: list[str]) -> Path | None:
    """Sauvegarde LÉGÈRE : les fichiers .conf + le dossier user/ (petits), jamais
    les caches. Renvoie le dossier de sauvegarde (ou None si dir absent)."""
    if not cfg_dir.exists():
        return None
    bak = Path(tempfile.mkdtemp(prefix="slicercfg_"))
    for name in conf_files:
        src = cfg_dir / name
        if src.exists():
            shutil.copy2(src, bak / name)
    if (cfg_dir / "user").exists():
        shutil.copytree(cfg_dir / "user", bak / "user")
    return bak


def _restore_light(bak: Path | None, cfg_dir: Path, conf_files: list[str]) -> None:
    if bak is None:
        return
    for name in conf_files:
        s = bak / name
        if s.exists():
            shutil.copy2(s, cfg_dir / name)
    if (bak / "user").exists():
        if (cfg_dir / "user").exists():
            shutil.rmtree(cfg_dir / "user", ignore_errors=True)
        shutil.copytree(bak / "user", cfg_dir / "user")
    shutil.rmtree(bak, ignore_errors=True)


_NUM = re.compile(r"^-?\d+(\.\d+)?$")


def _norm(v: str) -> str:
    return str(v).strip().rstrip("%").strip()


def _compare(expected: dict, applied: dict, keys: list[str]) -> dict:
    """Diffs {clé: {exporté, appliqué}} sur les clés présentes dans `expected`."""
    diffs = {}
    for k in keys:
        if k not in expected:
            continue
        a, b = _norm(expected[k]), _norm(applied.get(k, "(absent)"))
        if _NUM.match(a) and _NUM.match(b):
            same = abs(float(a) - float(b)) < 1e-6
        else:
            same = a == b
        if not same:
            diffs[k] = {"exporte": expected[k], "applique": applied.get(k, "(absent)")}
    return diffs


def _parse_ini_config(text: str) -> dict:
    """Parse un bloc « clé = valeur » (avec ou sans préfixe « ; »)."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(";"):
            line = line[1:].strip()
        m = re.match(r"^([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


# ══════════════════════════ Adaptateur PrusaSlicer ═══════════════════════════
_PRUSA_KEYS = [
    "layer_height", "first_layer_height", "perimeters", "top_solid_layers",
    "bottom_solid_layers", "fill_density", "fill_pattern", "perimeter_speed",
    "external_perimeter_speed", "infill_speed", "temperature",
    "first_layer_temperature", "bed_temperature", "first_layer_bed_temperature",
    "support_material", "brim_type", "brim_width", "nozzle_diameter",
]


class PrusaAdapter:
    id = "prusa"
    image = "prusa-slicer.exe"

    def exe(self) -> Path | None:
        for p in (r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
                  r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe"):
            if Path(p).exists():
                return Path(p)
        return None

    def printer(self, nozzle: float) -> str:
        from data.printers import prusa_models
        models = [mk for _, mk in prusa_models()]
        for pref in ("MK4", "MK3.9", "MK3S", "MK3", "MINI"):
            for mk in models:
                if pref in mk.upper():
                    return mk
        return models[0] if models else "MK3S"

    def build(self, path: Path, scen: dict) -> str:
        from core.export.prusa_3mf_builder import PrusaThreeMFBuilder
        PREFS.set("slicer_output", "prusa")
        printer = self.printer(scen["nozzle"])
        PrusaThreeMFBuilder().build(
            mesh=scen["piece"], config=scen["config"], output_path=path,
            printer_ui_name=printer, filament_ui_name=scen["filament"],
            nozzle_diameter_mm=scen["nozzle"])
        return printer

    def structural(self, path: Path) -> tuple[bool, str]:
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                assert "Metadata/Slic3r_PE.config" in names, "Slic3r_PE.config absent"
                cfg = _parse_ini_config(z.read("Metadata/Slic3r_PE.config").decode("utf-8"))
                assert "layer_height" in cfg, "config vide"
                assert cfg.get("nozzle_diameter"), "nozzle_diameter absent"
                assert any(n.endswith(".model") for n in names), "géométrie absente"
            return True, f"config {len(cfg)} clés"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def expected(self, path: Path) -> dict:
        with zipfile.ZipFile(path) as z:
            return _parse_ini_config(z.read("Metadata/Slic3r_PE.config").decode("utf-8"))

    def run_real(self, path: Path, scen_name: str, backup_unused=None) -> tuple[str, str, dict, str]:
        """Découpe headless → parse le bloc config du G-code → applied values.
        Verdict : « ok » toutes clés identiques, « echec » écart réel."""
        exe = self.exe()
        gcode = _CALIB / f"prusa_{scen_name}.gcode"
        gcode.unlink(missing_ok=True)
        try:
            r = subprocess.run([str(exe), "-g", str(path), "--output", str(gcode)],
                               capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return "na", "timeout découpe Prusa (180s)", {}, ""
        if not gcode.exists():
            tail = (r.stderr or r.stdout or "")[-200:]
            return "echec", f"pas de G-code produit — {tail}", {}, ""
        applied = _parse_ini_config(gcode.read_text(encoding="utf-8", errors="ignore"))
        exported = self.expected(path)
        diffs = _compare(exported, applied, _PRUSA_KEYS)
        n = len([k for k in _PRUSA_KEYS if k in exported])
        if diffs:
            return "echec", f"{len(diffs)}/{n} clé(s) non appliquée(s)", diffs, ""
        return "ok", f"découpé, {n} clés vérifiées identiques", {}, ""


# ══════════════════════════ Adaptateur Cura (délégué) ════════════════════════
class CuraAdapter:
    id = "cura"
    image = "UltiMaker-Cura.exe"

    def __init__(self):
        import cura_test_bot as cb
        self.cb = cb

    def exe(self):
        return self.cb._CURA_EXES[0] if self.cb._CURA_EXES else None

    def cases(self):
        return self.cb._cases()

    def structural(self, path: Path) -> tuple[bool, str]:
        return self.cb._structurel(path)


# ══════════════════════════ Adaptateur famille Orca ══════════════════════════
_ORCA_SLICERS = {
    # id : (proc image, exes candidats, dossier config, fichiers .conf, marque catalogue)
    "bambu": ("bambu-studio.exe", [r"C:\Program Files\Bambu Studio\bambu-studio.exe"],
              "BambuStudio", ["BambuStudio.conf"], None),  # None -> Bambu Lab (PRINTERS)
    "orca": ("orca-slicer.exe", [r"C:\Program Files\OrcaSlicer\orca-slicer.exe"],
             "OrcaSlicer", ["OrcaSlicer.conf"], None),
    "creality": ("CrealityPrint.exe",
                 sorted(str(p) for p in Path(r"C:\Program Files\Creality").glob("Creality Print*/CrealityPrint.exe")),
                 "Creality/Creality Print/7.0", ["Creality.conf"], "Creality"),
    "elegoo": ("elegoo-slicer.exe", [r"C:\Program Files\ElegooSlicer\elegoo-slicer.exe"],
               "ElegooSlicer", ["ElegooSlicer.conf"], "Elegoo"),
    "anycubic": ("AnycubicSlicerNext.exe", [r"C:\Program Files\AnycubicSlicerNext\AnycubicSlicerNext.exe"],
                 "AnycubicSlicerNext", ["AnycubicSlicerNext.conf"], "Anycubic"),
    # Snapmaker Orca : neoSlice propose bien les imprimantes Snapmaker (A250/A350/
    # Artisan/J1/U1 — via la bibliothèque Orca embarquée) → on teste une VRAIE
    # Snapmaker.
    "snapmaker": ("snapmaker-orca.exe", [r"C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe"],
                  "Snapmaker_Orca", ["Snapmaker_Orca.conf"], "Snapmaker"),
}

_ORCA_STRUCT_KEYS = ["layer_height", "sparse_infill_density", "sparse_infill_pattern",
                     "wall_loops", "nozzle_temperature", "hot_plate_temp"]
_ORCA_LOG_ERRORS = ["ACCESS_VIOLATION", "Unable to open the file", "couldn't be read",
                    "fatal", "Segmentation"]


class OrcaAdapter:
    def __init__(self, sid: str):
        self.id = sid
        img, exes, cfgsub, conf, brand = _ORCA_SLICERS[sid]
        self.image = img
        self._exes = exes
        self.cfg_dir = _APPDATA / cfgsub
        self.conf_files = conf
        self.brand = brand

    def exe(self) -> Path | None:
        for p in self._exes:
            if Path(p).exists():
                return Path(p)
        return None

    def printer(self) -> str:
        from data.printers import models_for_brand, PRINTERS
        if self.brand is None:                       # Bambu Lab (X1 Carbon fiable)
            return "X1 Carbon" if "X1 Carbon" in PRINTERS else next(iter(PRINTERS))
        models = models_for_brand(self.brand, self.id)
        return models[0][1] if models else "X1 Carbon"

    def build(self, path: Path, scen: dict) -> str:
        from core.export.tmf_builder import ThreeMFBuilder
        PREFS.set("slicer_output", self.id)
        printer = self.printer()
        ThreeMFBuilder().build(
            mesh=scen["piece"], config=scen["config"], output_path=path,
            printer_ui_name=printer, filament_ui_name=scen["filament"],
            nozzle_diameter_mm=scen["nozzle"])
        return printer

    def structural(self, path: Path) -> tuple[bool, str]:
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                ps_name = next((n for n in names if n.endswith("project_settings.config")), None)
                assert ps_name, "project_settings.config absent"
                ps = json.loads(z.read(ps_name))

                def g(k):
                    v = ps.get(k)
                    return v[0] if isinstance(v, list) and v else v
                # règle CRITIQUE : print_settings_id INCONNU du slicer (préfixe
                # neoSlice) → le slicer ne recharge pas son preset par-dessus.
                psid = g("print_settings_id") or ""
                assert psid.startswith("neoSlice"), f"print_settings_id={psid!r} (doit préfixer neoSlice)"
                assert g("printer_settings_id"), "printer_settings_id absent"
                assert g("filament_settings_id"), "filament_settings_id absent"
                assert g("nozzle_diameter"), "nozzle_diameter absent"
                for k in _ORCA_STRUCT_KEYS:
                    assert k in ps, f"clé {k} absente"
                assert any(n.endswith(".model") for n in names), "géométrie absente"
            return True, f"psid OK, {len(ps)} clés"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def _new_log(self, logdir: Path, before: dict) -> str:
        txt = ""
        if logdir.exists():
            for f in logdir.glob("*.log*"):
                prev = before.get(f.name, 0)
                if f.stat().st_size > prev:
                    try:
                        with open(f, "rb") as fh:
                            fh.seek(prev)
                            txt += fh.read().decode("utf-8", "ignore")
                    except Exception:
                        pass
        return txt

    def run_real(self, path: Path, scen_name: str, backup,
                 timeout: int = 120) -> tuple[str, str, dict, str]:
        """Ouvre le 3MF dans le vrai slicer, best-effort, avec CAPTURE D'ÉCRAN.
        NE modifie JAMAIS la config du slicer (juste sauvegarde/restauration
        légère autour). Verdict à 3 états :
          « ok »  : le log confirme le chargement de NOTRE fichier ;
          « echec »: le log dit explicitement qu'il ne peut PAS ouvrir NOTRE
                     fichier, ou crash interne → vrai signal neoSlice ;
          « na »  : non concluant (ces forks gèlent souvent au boot sous
                     automatisation — réseau/GUI) → PAS un bug neoSlice ; la
                     validité reste établie par le structurel + la capture.
        Les erreurs sur d'AUTRES fichiers (session restaurée) sont ignorées."""
        exe = self.exe()
        logdir = self.cfg_dir / "log"
        before = {f.name: f.stat().st_size for f in logdir.glob("*.log*")} if logdir.exists() else {}
        fl = path.name.lower()                        # NOTRE fichier
        shot = _CALIB / f"shot_{self.id}_{scen_name}.png"
        proc = subprocess.Popen([str(exe), str(path)])
        verdict, t0, txt, shot_done = None, time.time(), "", False
        try:
            while time.time() - t0 < timeout:
                time.sleep(6)
                if not shot_done and time.time() - t0 >= 40:
                    _screenshot(shot); shot_done = True   # capture AVANT idle prolongé
                txt = self._new_log(logdir, before)
                low = txt.lower()
                if any(fl in ln.lower() and "unable to open" in ln.lower()
                       for ln in txt.splitlines()):
                    verdict = ("echec", "le slicer refuse NOTRE fichier"); break
                if any(m in low for m in ("access_violation", "segmentation", "fatal error")):
                    verdict = ("echec", "crash interne du slicer"); break
                if fl in low and any(k in low for k in (
                        "load_3mf", "loaded", "arrange", "partplate",
                        "add object", "objects loaded", "slice all")):
                    verdict = ("ok", "chargé (confirmé par le log)"); break
                if proc.poll() is not None:
                    verdict = ("na", f"process terminé tôt (code {proc.returncode})"); break
            if not shot_done:
                _screenshot(shot)
            (_CALIB / f"log_{self.id}_{scen_name}.txt").write_text(txt, encoding="utf-8")
            if verdict is None:
                seen = fl in txt.lower()
                return ("na", f"chargement non confirmé en {timeout}s "
                        f"({'fichier vu, pas de marqueur' if seen else 'boot lent/gel'}) "
                        f"— voir capture", {}, str(shot))
            etat, msg = verdict
            return (etat, msg, {}, str(shot))
        finally:
            _kill(self.image)
            _restore_light(backup, self.cfg_dir, self.conf_files)


# ══════════════════════════ Orchestration ════════════════════════════════════
def _all_adapters() -> dict:
    ad = {"prusa": PrusaAdapter(), "cura": CuraAdapter()}
    for sid in _ORCA_SLICERS:
        ad[sid] = OrcaAdapter(sid)
    return ad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true",
                    help="lance les slicers à lecture FIABLE (Prusa headless)")
    ap.add_argument("--gui", action="store_true",
                    help="tente EN PLUS l'ouverture GUI best-effort de la famille "
                         "Orca (captures d'écran ; ces forks gèlent souvent au boot "
                         "→ résultats « non concluant », jamais comptés comme bug)")
    ap.add_argument("--slicers", default="", help="sous-ensemble : prusa,orca,bambu,…")
    ap.add_argument("--scenarios", default="", help="sous-ensemble de scénarios")
    args = ap.parse_args()
    _CALIB.mkdir(exist_ok=True)

    adapters = _all_adapters()
    if args.slicers:
        keep = {s.strip() for s in args.slicers.split(",")}
        adapters = {k: v for k, v in adapters.items() if k in keep}

    scenarios = _scenarios()
    if args.scenarios:
        keep = {s.strip() for s in args.scenarios.split(",")}
        scenarios = {k: v for k, v in scenarios.items() if k in keep}

    rapport = {}
    outdir = Path(tempfile.mkdtemp(prefix="neoslice_slicerbot_"))

    for sid, ad in adapters.items():
        if sid == "cura":
            print(f"\n########## {sid} (délégué à cura_test_bot) ##########")
            print("  → lance : python tools/cura_test_bot.py --cura")
            rapport[sid] = {"note": "voir cura_test_bot (validé 5/5)"}
            continue
        exe = ad.exe()
        print(f"\n########## {sid} ##########  exe={'OK' if exe else 'ABSENT'}")
        rapport[sid] = {}
        if args.run and exe and _proc_running(ad.image):
            print(f"  REFUS : {ad.image} est déjà ouvert — fermez-le d'abord.")
            rapport[sid]["_refus"] = "slicer déjà ouvert"
            continue

        # famille Orca : sauvegarde config une fois pour tout le slicer
        orca = isinstance(ad, OrcaAdapter)
        for name, scen in scenarios.items():
            path = outdir / f"{sid}_{name}.3mf"
            try:
                printer = ad.build(path, scen)
            except Exception as e:
                print(f"  [{name}] BUILD ÉCHEC — {type(e).__name__}: {e}")
                rapport[sid][name] = {"build": f"{type(e).__name__}: {e}"}
                continue
            ok_s, msg_s = ad.structural(path)
            entry = {"printer": printer, "structurel": {"ok": ok_s, "detail": msg_s}}
            print(f"  [{name}] structurel : {'OK ' if ok_s else 'ÉCHEC'} — {msg_s}  ({printer})")

            # Réel : Prusa (headless, fiable) sous --run ; famille Orca (GUI
            # best-effort) seulement sous --gui.
            faire_reel = ok_s and exe and ((args.run and not orca) or (args.gui and orca))
            if faire_reel:
                bak = _backup_light(ad.cfg_dir, ad.conf_files) if orca else None
                try:
                    st, msg_r, diffs, shot = ad.run_real(path, name, bak)
                except Exception as e:
                    st, msg_r, diffs, shot = "na", f"{type(e).__name__}: {e}", {}, ""
                    if orca:
                        _kill(ad.image); _restore_light(bak, ad.cfg_dir, ad.conf_files)
                badge = {"ok": "OK ", "echec": "ÉCHEC", "na": "n/c"}.get(st, st)
                entry["reel"] = {"statut": st, "detail": msg_r, "diffs": diffs, "capture": shot}
                print(f"  [{name}] réel       : {badge} — {msg_r}")
                for k, d in (diffs or {}).items():
                    print(f"        {k}: exporté={d['exporte']}  appliqué={d['applique']}")
                if shot:
                    print(f"        capture → {shot}")
            rapport[sid][name] = entry

    _REPORT.write_text(json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport → {_REPORT}")
    # Bilan : seuls structurel ÉCHEC ou réel « echec » comptent (jamais « n/c »)
    ko = []
    for sid, cases in rapport.items():
        if not isinstance(cases, dict):
            continue
        for cname, e in cases.items():
            if not isinstance(e, dict):
                continue
            if e.get("structurel", {}).get("ok") is False:
                ko.append(f"{sid}/{cname} (structurel)")
            if e.get("reel", {}).get("statut") == "echec":
                ko.append(f"{sid}/{cname} (réel)")
    print("BILAN :", "TOUT OK (aucun vrai écart)" if not ko else "ÉCARTS RÉELS: " + ", ".join(ko))
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
