# -*- coding: utf-8 -*-
"""neoForge : installation, mise à jour et désinstallation depuis GitHub.

neoSlice ne grossit pas tant que neoForge n'est pas installé : le logiciel (code
Python, ~1 Mo) et son noyau de CAO (OpenCascade, 48 Mo à télécharger sur Windows,
63 Mo sur Mac) sont récupérés à la demande depuis la release « neoforge-latest »
du dépôt d'assets.

Sécurité : on exécute du code téléchargé, donc RIEN n'est installé si
  la signature Ed25519 du manifeste ne correspond pas à CLE_PUBLIQUE,
  l'empreinte SHA-256 ou la taille d'un fichier diffère du manifeste,
  le paquet exige une version de neoSlice plus récente.
Installation « tout ou rien » : décompression dans un dossier d'attente, puis
bascule ; en cas d'échec, l'installation précédente reste intacte.

Mise à jour : le code et le noyau sont versionnés séparément ; une nouvelle
version du code ne retélécharge pas le noyau.

La désinstallation ne supprime QUE le logiciel : les projets de l'utilisateur
sont rangés ailleurs (Documents/neoForge).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from loguru import logger

DOSSIER = Path.home() / ".neoslice" / "neoforge"
BASE_URL = "https://github.com/labstral/neoslice-assets/releases/download/neoforge-latest"
MANIFESTE = "neoforge_manifest.json"
SIGNATURE = "neoforge_manifest.sig"
CLE_PUBLIQUE = bytes.fromhex(
    "6723a45ae8e3565934e0adb3afccfc3b990a0ae579eda1e29581223e16d85a68")
TIMEOUT = 60
# Tailles affichées AVANT téléchargement (Mo) : (à télécharger, sur le disque).
# Mesurées sur les roues cadquery-ocp-novtk 8.0.1 (2026-09-11).
TAILLES = {"win-amd64": (48, 175), "mac-arm64": (63, 233)}

# Codes d'erreur (traduits dans modules_dialog)
ERR_RESEAU = "reseau"
ERR_SIGNATURE = "signature"
ERR_EMPREINTE = "empreinte"
ERR_VERSION = "version_neoslice"
ERR_SYSTEME = "systeme"
ERR_EN_COURS = "en_cours"
ERR_ANNULE = "annule"


class ErreurNeoForge(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ── Chemins ────────────────────────────────────────────────────────────────
def chemins(dossier: Path | None = None) -> dict[str, Path]:
    d = Path(dossier or DOSSIER)
    return {"racine": d, "code": d / "code", "noyau": d / "noyau",
            "marqueur": d / "installed.json", "attente": d / ".attente"}


def plateforme() -> str | None:
    """Plateforme du noyau à télécharger, None si le système n'est pas pris en charge."""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win-amd64"
    if sys.platform == "darwin" and machine in ("arm64", "aarch64"):
        return "mac-arm64"
    return None


def _base_url() -> str:
    # Dépôt local de test : sources seulement (jamais dans l'exe distribué).
    if not getattr(sys, "frozen", False) and os.environ.get("NEOSLICE_NEOFORGE_URL"):
        return os.environ["NEOSLICE_NEOFORGE_URL"].rstrip("/")
    return BASE_URL


def _version(v: str) -> tuple:
    out = []
    for morceau in str(v).split("."):
        chiffres = "".join(c for c in morceau if c.isdigit())
        out.append(int(chiffres) if chiffres else 0)
    return tuple(out)


# ── État ───────────────────────────────────────────────────────────────────
def etat(dossier: Path | None = None) -> dict | None:
    c = chemins(dossier)
    try:
        info = json.loads(c["marqueur"].read_text(encoding="utf-8"))
    except Exception:
        return None
    if not (c["code"] / "neoforge" / "__init__.py").is_file() or not (c["noyau"] / "OCP").is_dir():
        return None
    return info


def est_installe(dossier: Path | None = None) -> bool:
    return etat(dossier) is not None


def taille_installee(dossier: Path | None = None) -> int:
    c = chemins(dossier)
    total = 0
    for partie in ("code", "noyau"):
        for p in c[partie].rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total


# ── Réseau ─────────────────────────────────────────────────────────────────
def _lire(url: str) -> bytes:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except Exception as exc:
        raise ErreurNeoForge(ERR_RESEAU, str(exc)) from exc


def lire_manifeste(base_url: str | None = None, cle: bytes | None = None,
                   verifier_version: bool = True) -> dict:
    """Manifeste SIGNÉ, vérifié, compatible avec cette version de neoSlice et ce système.
    verifier_version=False : réservé à l'outil de publication (installation locale
    de test AVANT le passage de neoSlice à la version exigée)."""
    from core.neoforge.signature import verifier
    from version import __version__
    base = (base_url or _base_url()).rstrip("/")
    brut = _lire(f"{base}/{MANIFESTE}")
    try:
        sig = bytes.fromhex(_lire(f"{base}/{SIGNATURE}").decode("ascii").strip())
    except ErreurNeoForge:
        raise
    except Exception as exc:
        raise ErreurNeoForge(ERR_SIGNATURE, "signature illisible") from exc
    if not verifier(cle or CLE_PUBLIQUE, brut, sig):
        raise ErreurNeoForge(ERR_SIGNATURE, "signature invalide")
    m = json.loads(brut.decode("utf-8"))
    if verifier_version and _version(m.get("neoslice_min", "0")) > _version(__version__):
        raise ErreurNeoForge(ERR_VERSION, m.get("neoslice_min", ""))
    plat = plateforme()
    if plat is None or plat not in m.get("noyaux", {}):
        raise ErreurNeoForge(ERR_SYSTEME, plat or platform.machine())
    return m


def _telecharger(url: str, dest: Path, attendu: dict, progress, part: float,
                 poids: float, annule) -> None:
    """Téléchargement en flux vers `dest`, empreinte SHA-256 et taille vérifiées."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    recu = 0
    total = int(attendu.get("taille", 0)) or 1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(dest, "wb") as f:
            while True:
                if annule():
                    raise ErreurNeoForge(ERR_ANNULE)
                bloc = r.read(1 << 20)
                if not bloc:
                    break
                f.write(bloc)
                h.update(bloc)
                recu += len(bloc)
                if progress:
                    progress("telechargement", part + poids * min(1.0, recu / total))
    except ErreurNeoForge:
        raise
    except Exception as exc:
        raise ErreurNeoForge(ERR_RESEAU, str(exc)) from exc
    if recu != int(attendu.get("taille", -1)) or h.hexdigest() != attendu.get("sha256"):
        raise ErreurNeoForge(ERR_EMPREINTE, dest.name)


def _extraire(archive: Path, dest: Path) -> None:
    """Décompression sûre : aucun chemin ne peut sortir de `dest`."""
    racine = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        for nom in z.namelist():
            cible = (dest / nom).resolve()
            if racine not in cible.parents and cible != racine:
                raise ErreurNeoForge(ERR_EMPREINTE, f"chemin refusé : {nom}")
        z.extractall(dest)


# ── Installation / mise à jour ─────────────────────────────────────────────
def verifier_maj(dossier: Path | None = None, base_url: str | None = None,
                 cle: bytes | None = None) -> dict | None:
    """Manifeste si une version plus récente existe (installé seulement).
    Jamais d'exception : hors ligne, on répond « pas de mise à jour »."""
    info = etat(dossier)
    if info is None:
        return None
    try:
        m = lire_manifeste(base_url, cle)
    except Exception as exc:
        logger.debug(f"neoForge maj : {exc}")
        return None
    noyau = m["noyaux"][plateforme()]
    if (_version(m["version"]) > _version(info.get("version", "0"))
            or noyau.get("version") != info.get("noyau_version")):
        return m
    return None


def installer(progress=None, annule=lambda: False, dossier: Path | None = None,
              base_url: str | None = None, cle: bytes | None = None,
              verifier_version: bool = True) -> dict:
    """Installe ou met à jour neoForge (bloquant : appeler depuis un QThread).
    progress(etape, fraction 0..1) ; etape ∈ {manifeste, telechargement, installation}."""
    c = chemins(dossier)
    base = (base_url or _base_url()).rstrip("/")
    if progress:
        progress("manifeste", 0.0)
    m = lire_manifeste(base, cle, verifier_version)
    plat = plateforme()
    noyau = m["noyaux"][plat]
    avant = etat(dossier) or {}
    besoin_noyau = (noyau.get("version") != avant.get("noyau_version")
                    or not (c["noyau"] / "OCP").is_dir())

    shutil.rmtree(c["attente"], ignore_errors=True)
    c["attente"].mkdir(parents=True, exist_ok=True)
    try:
        parts = [("code", m["code"])] + ([("noyau", noyau)] if besoin_noyau else [])
        poids_total = sum(max(1, int(p[1].get("taille", 1))) for p in parts)
        fait = 0.0
        for nom, fichier in parts:
            poids = max(1, int(fichier.get("taille", 1))) / poids_total * 0.9
            archive = c["attente"] / fichier["fichier"]
            _telecharger(f"{base}/{fichier['fichier']}", archive, fichier,
                         progress, fait, poids, annule)
            _extraire(archive, c["attente"] / nom)
            archive.unlink()
            fait += poids
        if progress:
            progress("installation", 0.95)
        _basculer(c, [nom for nom, _f in parts])
    finally:
        shutil.rmtree(c["attente"], ignore_errors=True)

    info = {"version": m["version"],
            "noyau_version": noyau.get("version") if besoin_noyau else avant.get("noyau_version"),
            "plateforme": plat}
    c["marqueur"].write_text(json.dumps(info, indent=1), encoding="utf-8")
    if progress:
        progress("installation", 1.0)
    logger.info(f"neoForge {info['version']} installé (noyau {info['noyau_version']})")
    return info


def _basculer(c: dict, parties: list[str]) -> None:
    """Remplace code/noyau par leur version en attente, avec retour arrière."""
    anciens = []
    try:
        for nom in parties:
            actuel, ancien = c[nom], c["racine"] / f".{nom}.ancien"
            shutil.rmtree(ancien, ignore_errors=True)
            if actuel.exists():
                os.replace(actuel, ancien)          # échoue si neoForge est ouvert (DLL)
                anciens.append((actuel, ancien))
            os.replace(c["attente"] / nom, actuel)
    except PermissionError as exc:
        for actuel, ancien in reversed(anciens):
            shutil.rmtree(actuel, ignore_errors=True)
            os.replace(ancien, actuel)
        raise ErreurNeoForge(ERR_EN_COURS, str(exc)) from exc
    for _actuel, ancien in anciens:
        shutil.rmtree(ancien, ignore_errors=True)


def desinstaller(dossier: Path | None = None) -> None:
    """Supprime le logiciel et son noyau (les projets, rangés ailleurs, restent)."""
    c = chemins(dossier)
    for nom in ("code", "noyau", "attente"):
        shutil.rmtree(c[nom], ignore_errors=True)
    try:
        c["marqueur"].unlink()
    except FileNotFoundError:
        pass
    for p in c["racine"].glob(".*.ancien"):
        shutil.rmtree(p, ignore_errors=True)
    if (c["noyau"]).exists():
        raise ErreurNeoForge(ERR_EN_COURS, "noyau encore utilisé")
