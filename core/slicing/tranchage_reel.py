# -*- coding: utf-8 -*-
"""Faire trancher la pièce par le slicer de l'utilisateur, en arrière-plan.

Pourquoi. Le temps d'impression et le poids de filament affichés par neoSlice
sont aujourd'hui CALCULÉS à partir du volume et de quelques règles. Or les
slicers savent tous travailler sans interface, pilotés par une simple ligne de
commande : on peut donc leur demander de trancher pour de vrai, sans que
l'utilisateur voie quoi que ce soit, et lire les valeurs qu'ils écrivent
eux-mêmes dans le gcode.

⚠ Le slicer employé doit être CELUI DE L'UTILISATEUR, avec SES profils. Le
même cube de 30 mm donne 21 min 1 s tranché par OrcaSlicer en profil X1C, et
25 min 19 s tranché par PrusaSlicer en profil par défaut. Afficher le second à
quelqu'un qui imprime sur une X1C serait plus faux que l'estimation actuelle.
C'est la règle qui gouverne tout ce module : mieux vaut ne rien renvoyer que
renvoyer le chiffre d'un autre.

Vérifié sur la machine d'Emmanuel, 2026-09-30 :
  PrusaSlicer  `--export-gcode`  fonctionne tel quel.
  OrcaSlicer   `--slice 0 --load-settings machine;process --load-filaments f`
               fonctionne avec les profils livrés dans OrcaSlicer lui-même.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# Temps maximal accordé à un tranchage. Au delà, on abandonne et on garde
# l'estimation : une pièce très lourde ne doit pas bloquer l'affichage.
DELAI_MAX_S = 180

# Densités usuelles, en g/cm³. Le gcode donne un VOLUME de filament fiable ;
# la masse, elle, dépend du profil de filament chargé et ressort souvent à
# zéro. On la calcule donc nous-mêmes.
DENSITES = {
    "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21,
    "PA": 1.14, "PC": 1.20, "PVA": 1.23, "HIPS": 1.04, "PP": 0.90,
}
DENSITE_PAR_DEFAUT = 1.24


@dataclass(frozen=True)
class Slicer:
    """Un slicer trouvé sur la machine."""
    cle: str          # "prusaslicer", "orcaslicer", "bambustudio"
    nom: str          # nom affichable
    exe: Path
    style: str        # "prusa" ou "orca" : la façon de l'appeler


@dataclass(frozen=True)
class Resultat:
    """Ce que le slicer a réellement calculé."""
    minutes: int
    volume_cm3: float
    grammes: float
    slicer: str
    gcode: Path


# ── Où les trouver ────────────────────────────────────────────────────────
_CANDIDATS = (
    ("prusaslicer", "PrusaSlicer", "prusa", (
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe",
        "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
    )),
    ("orcaslicer", "OrcaSlicer", "orca", (
        r"C:\Program Files\OrcaSlicer\orca-slicer.exe",
        "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer",
    )),
    ("bambustudio", "Bambu Studio", "orca", (
        r"C:\Program Files\Bambu Studio\bambu-studio.exe",
        "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    )),
    ("snapmakerorca", "Snapmaker Orca", "orca", (
        r"C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe",
    )),
)


def slicers_installes() -> list[Slicer]:
    """Les slicers réellement présents sur cette machine."""
    trouves = []
    for cle, nom, style, chemins in _CANDIDATS:
        for c in chemins:
            p = Path(c)
            try:
                if p.is_file():
                    trouves.append(Slicer(cle, nom, p, style))
                    break
            except OSError:
                continue
    return trouves


_CACHE_PROFILS: dict = {}


def profils_orca(slicer: Slicer, imprimante: str, buse: float,
                 hauteur_couche: float, filament: str = "PLA") -> dict | None:
    """Les trois profils à passer à un slicer de la famille Orca.

    Ces slicers refusent de trancher sans profil cohérent : machine, process
    et filament. Ils en livrent une bibliothèque complète, c'est donc là qu'on
    va les chercher plutôt que de les réinventer.

    Renvoie None si l'un des trois manque : sans le bon profil, le chiffre
    obtenu ne vaudrait rien.
    """
    racine = slicer.exe.parent / "resources" / "profiles"
    if not racine.is_dir():
        return None

    # La bibliothèque compte des CENTAINES de fichiers. Les relire à chaque
    # appel coûtait 10 s, ce qui est inacceptable devant un tranchage qui en
    # prend une demie. On garde le résultat, et le contenu des fichiers lus.
    memo = (str(slicer.exe), imprimante.lower(), buse, round(hauteur_couche, 2),
            filament.lower())
    if memo in _CACHE_PROFILS:
        return _CACHE_PROFILS[memo]

    _lus: dict = {}

    def _lire(f: Path) -> dict:
        if f in _lus:
            return _lus[f]
        try:
            import json
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        _lus[f] = d
        return d

    for marque in sorted(d for d in racine.iterdir() if d.is_dir()):
        # 1. La machine : le modèle ET le diamètre de buse doivent coller.
        machine = None
        for f in sorted((marque / "machine").glob("*.json")):
            d = _lire(f)
            if str(d.get("instantiation", "")).lower() != "true":
                continue
            if imprimante.lower() not in str(d.get("printer_model", "")).lower():
                continue
            if f"{buse:g}" not in " ".join(map(str, d.get("nozzle_diameter", []))):
                continue
            machine, nom_machine = f, d.get("name", f.stem)
            break
        if machine is None:
            continue

        # 2. Le process et le filament DOIVENT se déclarer compatibles avec
        # elle. C'est ce qui manquait au premier essai : un process « @BBL A1 »
        # avait été retenu pour une X1 Carbon, et le slicer refusait de
        # travailler. La compatibilité est écrite dans les profils, autant la
        # lire plutôt que la deviner à partir des noms de fichiers.
        def _compatible(dossier: Path, *morceaux: str) -> Path | None:
            besoin = [m.lower() for m in morceaux if m]
            trouves = []
            for f in sorted(dossier.glob("*.json")):
                d = _lire(f)
                if str(d.get("instantiation", "")).lower() != "true":
                    continue
                if nom_machine not in (d.get("compatible_printers") or []):
                    continue
                nom = str(d.get("name", f.stem)).lower()
                if all(b in nom for b in besoin):
                    trouves.append(f)
            # Le nom le plus court est le plus générique, donc le plus sûr.
            return min(trouves, key=lambda f: len(f.name)) if trouves else None

        process = _compatible(marque / "process", f"{hauteur_couche:.2f}mm")
        fil = _compatible(marque / "filament", filament)
        if process is None or fil is None:
            continue
        trouve = {"machine": machine, "process": process, "filament": fil}
        _CACHE_PROFILS[memo] = trouve
        return trouve
    _CACHE_PROFILS[memo] = None
    return None


# ── Lecture du gcode ──────────────────────────────────────────────────────
_RE_TEMPS = (
    # Orca et Bambu : "; model printing time: 14m 27s; total estimated time: 21m 1s"
    re.compile(r"total estimated time:\s*([0-9hms \.]+)", re.I),
    # PrusaSlicer : "; estimated printing time (normal mode) = 25m 19s"
    re.compile(r"estimated printing time[^=]*=\s*([0-9hdms \.]+)", re.I),
)
_RE_VOLUME = re.compile(r"filament used \[cm3\]\s*[=:]\s*([0-9.]+)", re.I)
# Bambu Studio n'écrit PAS le volume, seulement la longueur. Mesuré sur son
# gcode : « ; total filament length [mm] : 2487.06 ». On repasse au volume par
# la section du fil, ce qui donne le même résultat à moins d'un pour cent.
_RE_LONGUEUR = re.compile(
    r"(?:total )?filament (?:used|length) \[mm\]\s*[=:]\s*([0-9.]+)", re.I)
_RE_DIAMETRE = re.compile(r"filament_diameter\s*[=:]\s*([0-9.]+)", re.I)
_RE_MASSE = re.compile(
    r"total filament (?:used|weight) \[g\]\s*[=:]\s*([0-9.]+)", re.I)


def _duree_en_minutes(texte: str) -> int | None:
    """« 1d 2h 21m 1s » → minutes. Les slicers n'écrivent que ce qui est utile."""
    total = 0
    trouve = False
    for valeur, unite in re.findall(r"(\d+)\s*([dhms])", texte.lower()):
        trouve = True
        total += int(valeur) * {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}[unite]
    return int(round(total)) if trouve else None


def lire_gcode(texte: str, densite: float = DENSITE_PAR_DEFAUT) -> tuple | None:
    """(minutes, volume_cm3, grammes) lus dans l'en-tête du gcode.

    La masse écrite par le slicer vaut souvent zéro, parce qu'elle dépend d'une
    densité renseignée dans son profil de filament. Le VOLUME, lui, est
    toujours juste : on préfère donc le convertir nous-mêmes, et on ne retient
    la masse du slicer que si elle est crédible.
    """
    minutes = None
    for motif in _RE_TEMPS:
        m = motif.search(texte)
        if m:
            minutes = _duree_en_minutes(m.group(1))
            if minutes:
                break
    if minutes is None:
        return None
    mv = _RE_VOLUME.search(texte)
    if mv:
        volume = float(mv.group(1))
    else:
        ml = _RE_LONGUEUR.search(texte)
        if not ml:
            return None
        md = _RE_DIAMETRE.search(texte)
        diametre = float(md.group(1)) if md else 1.75
        if not 1.0 < diametre < 4.0:
            diametre = 1.75
        # longueur (mm) × section (mm²) → mm³, puis en cm³
        volume = float(ml.group(1)) * 3.141592653589793 * (diametre / 2.0) ** 2 / 1000.0
    mm = _RE_MASSE.search(texte)
    masse = float(mm.group(1)) if mm else 0.0
    if masse <= 0.01:
        masse = volume * max(0.5, densite)
    return minutes, volume, masse


# ── Le tranchage lui-même ─────────────────────────────────────────────────
def trancher(modele, slicer: Slicer, profils: dict | None = None,
             densite: float = DENSITE_PAR_DEFAUT,
             delai_s: int = DELAI_MAX_S) -> Resultat | None:
    """Tranche `modele` (chemin de fichier) avec `slicer`, sans interface.

    `profils` est obligatoire pour la famille Orca, qui refuse de travailler
    sans machine, process et filament cohérents.

    Ne lève jamais : renvoie None si le tranchage n'aboutit pas, et l'appelant
    garde alors son estimation. Un chiffre faux serait pire que pas de chiffre.
    """
    source = Path(modele)
    if not source.is_file():
        return None
    if slicer.style == "orca" and not profils:
        logger.debug("tranchage : profils manquants pour %s", slicer.nom)
        return None

    with tempfile.TemporaryDirectory(prefix="neoslice_tranche_") as tmp:
        sortie = Path(tmp)
        if slicer.style == "prusa":
            gcode = sortie / "piece.gcode"
            cmd = [str(slicer.exe), "--export-gcode", "--output", str(gcode),
                   str(source)]
        else:
            reglages = f"{profils['machine']};{profils['process']}"
            cmd = [str(slicer.exe), "--slice", "0",
                   "--load-settings", reglages,
                   "--load-filaments", str(profils["filament"]),
                   "--outputdir", str(sortie), str(source)]
            gcode = None

        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=delai_s,
                                  creationflags=_sans_fenetre())
        except subprocess.TimeoutExpired:
            logger.info("tranchage abandonné : %s a dépassé %ss", slicer.nom, delai_s)
            return None
        except OSError as e:
            logger.debug("tranchage impossible (%s) : %s", slicer.nom, e)
            return None

        if gcode is None or not gcode.is_file():
            produits = sorted(sortie.glob("*.gcode"))
            if not produits:
                logger.debug("tranchage : aucun gcode produit par %s (code %s)",
                             slicer.nom, proc.returncode)
                return None
            gcode = produits[0]

        try:
            # Les deux BOUTS, recollés. Inutile de lire 700 Ko de trajets, mais
            # il faut bien prendre les deux extrémités : Orca écrit le temps en
            # tête de fichier et le volume de filament tout à la fin, si bien
            # qu'aucun des deux morceaux ne contient les deux valeurs.
            entier = gcode.read_text(encoding="utf-8", errors="ignore")
            extrait = (entier[:40_000] + "\n" + entier[-40_000:]
                       if len(entier) > 80_000 else entier)
        except OSError:
            return None
        lu = lire_gcode(extrait, densite)
        if lu is None:
            logger.debug("tranchage : gcode de %s illisible", slicer.nom)
            return None

        minutes, volume, masse = lu
        garde = Path(tempfile.gettempdir()) / f"neoslice_{gcode.name}"
        try:
            garde.write_bytes(gcode.read_bytes())
        except OSError:
            garde = gcode
        return Resultat(minutes=minutes, volume_cm3=volume, grammes=round(masse, 1),
                        slicer=slicer.nom, gcode=garde)


def _sans_fenetre() -> int:
    """Empêche la console noire de clignoter sous Windows."""
    try:
        return subprocess.CREATE_NO_WINDOW
    except AttributeError:
        return 0
