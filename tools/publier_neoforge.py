# -*- coding: utf-8 -*-
"""Construit, SIGNE et (sur demande) publie les paquets de neoForge.

    python tools/publier_neoforge.py              construit dans tools/out/neoforge/
    python tools/publier_neoforge.py --local      + installe sur CETTE machine par le
                                                  vrai chemin d'installation (file://)
    python tools/publier_neoforge.py --publier    + téléverse sur GitHub (release
                                                  « neoforge-latest » de neoslice-assets)

⚠ --publier UNIQUEMENT après le « publie » d'Emmanuel.

Paquets produits :
  neoforge_code_<version>.zip          le dossier neoforge/ du dépôt (sans caches)
  neoforge_noyau_<plateforme>.zip      le contenu de la roue cadquery-ocp-novtk
  neoforge_manifest.json / .sig        versions, empreintes, signature Ed25519

La clé privée est lue dans ~/.neoslice/neoforge_signature.key : elle ne doit
JAMAIS entrer dans le dépôt. Sans elle, plus aucune mise à jour publiable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from core.neoforge import installation as I  # noqa: E402
from core.neoforge.signature import cle_publique, signer  # noqa: E402

SORTIE = RACINE / "tools" / "out" / "neoforge"
ROUES = SORTIE / "roues"
CLE = Path.home() / ".neoslice" / "neoforge_signature.key"
OCP_PAQUET, OCP_VERSION = "cadquery-ocp-novtk", "8.0.1.0.0"
PLATEFORMES = {"win-amd64": "win_amd64", "mac-arm64": "macosx_11_0_arm64"}
DEPOT, TAG = "Labstral/neoslice-assets", "neoforge-latest"
DATE_FIXE = (2026, 1, 1, 0, 0, 0)          # archives reproductibles


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _ajouter(z: zipfile.ZipFile, nom: str, donnees: bytes) -> None:
    info = zipfile.ZipInfo(nom, DATE_FIXE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    z.writestr(info, donnees)


def paquet_code(version: str) -> Path:
    sortie = SORTIE / f"neoforge_code_{version}.zip"
    src = RACINE / "neoforge"
    with zipfile.ZipFile(sortie, "w") as z:
        for p in sorted(src.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                _ajouter(z, p.relative_to(RACINE).as_posix(), p.read_bytes())
    return sortie


def roue(plateforme: str) -> Path:
    ROUES.mkdir(parents=True, exist_ok=True)
    tag = PLATEFORMES[plateforme]
    motif = f"cadquery_ocp_novtk-{OCP_VERSION}-cp312-cp312-{tag}.whl"
    if not (ROUES / motif).exists():
        subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps",
                        "--only-binary=:all:", "--platform", tag, "--python-version",
                        "3.12", f"{OCP_PAQUET}=={OCP_VERSION}", "-d", str(ROUES), "-q"],
                       check=True)
    return ROUES / motif


def paquet_noyau(plateforme: str) -> tuple[Path, int]:
    """Le contenu de la roue tel que pip l'installerait, sans ses métadonnées."""
    sortie = SORTIE / f"neoforge_noyau_{plateforme}.zip"
    installe = 0
    with zipfile.ZipFile(roue(plateforme)) as src, zipfile.ZipFile(sortie, "w") as z:
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            if info.is_dir() or ".dist-info/" in info.filename or "__pycache__" in info.filename:
                continue
            _ajouter(z, info.filename, src.read(info))
            installe += info.file_size
    return sortie, installe


def construire(notes: str) -> Path:
    from neoforge import NEOSLICE_MIN, VERSION
    SORTIE.mkdir(parents=True, exist_ok=True)
    code = paquet_code(VERSION)
    manifeste = {"version": VERSION, "neoslice_min": NEOSLICE_MIN, "notes": notes,
                 "code": {"fichier": code.name, "sha256": _sha(code),
                          "taille": code.stat().st_size},
                 "noyaux": {}}
    for plat in PLATEFORMES:
        z, installe = paquet_noyau(plat)
        manifeste["noyaux"][plat] = {"version": f"ocp-{OCP_VERSION}", "fichier": z.name,
                                     "sha256": _sha(z), "taille": z.stat().st_size,
                                     "taille_installee": installe}
    brut = json.dumps(manifeste, ensure_ascii=False, indent=1).encode("utf-8")
    secret = bytes.fromhex(CLE.read_text(encoding="ascii").strip())
    if cle_publique(secret) != I.CLE_PUBLIQUE:
        raise SystemExit("La clé privée ne correspond pas à CLE_PUBLIQUE : rien n'est signé.")
    (SORTIE / I.MANIFESTE).write_bytes(brut)
    (SORTIE / I.SIGNATURE).write_text(signer(secret, brut).hex() + "\n", encoding="ascii")
    print(f"neoForge {VERSION} construit dans {SORTIE}")
    for p in sorted(SORTIE.glob("*.zip")):
        print(f"  {p.name:42} {p.stat().st_size / 1e6:7.1f} Mo")
    return SORTIE


def publier() -> None:
    fichiers = [str(p) for p in sorted(SORTIE.glob("neoforge_*.zip"))]
    fichiers += [str(SORTIE / I.MANIFESTE), str(SORTIE / I.SIGNATURE)]
    existe = subprocess.run(["gh", "release", "view", TAG, "--repo", DEPOT],
                            capture_output=True).returncode == 0
    if not existe:
        subprocess.run(["gh", "release", "create", TAG, "--repo", DEPOT, "--title",
                        "neoForge", "--notes", "Paquets du module neoForge (signés)."],
                       check=True)
    subprocess.run(["gh", "release", "upload", TAG, "--repo", DEPOT, "--clobber", *fichiers],
                   check=True)
    print("Publié sur", DEPOT, TAG)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--notes", default="")
    a.add_argument("--local", action="store_true")
    a.add_argument("--publier", action="store_true")
    args = a.parse_args()
    sortie = construire(args.notes)
    if args.local:
        # Signature et empreintes vérifiées comme chez l'utilisateur ; seule la
        # version minimale de neoSlice est ignorée (le dépôt la précède).
        info = I.installer(base_url=sortie.as_uri(), verifier_version=False,
                           progress=lambda e, f: print(f"  {e:15} {f * 100:5.1f} %", end="\r"))
        print(f"\nInstallé localement : {info}")
    if args.publier:
        publier()
