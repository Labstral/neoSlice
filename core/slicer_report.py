# -*- coding: utf-8 -*-
"""Lecture des CHIFFRES EXACTS d'un fichier découpé par un slicer.

L'Espace Pro (devis, stock, commandes) travaillait sur des ESTIMATIONS, avec
une note orange invitant à reporter les chiffres du slicer à la main. Ce module
ferme la boucle : on lit directement le fichier produit par la découpe.

Formats couverts :
  - .gcode.3mf  Bambu Studio / OrcaSlicer (et forks) : Metadata/slice_info.config
                → poids et durée EXACTS, et le détail PAR FILAMENT (multicouleur) ;
  - .gcode      PrusaSlicer : « ; filament used [g] = » + « estimated printing time » ;
  - .gcode      Bambu/Orca export G-code brut : « total filament weight [g] » ;
  - .gcode      Cura : « ;TIME: » (s) + « ;Filament used: …m » → poids APPROXIMATIF
                (longueur × ~2,98 g/m, PLA 1,75 mm — signalé par exact=False).

Retour : dict {poids_g, duree_s, par_filament: [{id, type, couleur, grams}],
               source, exact} — ValueError si le fichier n'est pas exploitable.
100 % local, lecture seule.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from loguru import logger

# PLA 1,75 mm : section 0,02405 cm² × 100 cm × 1,24 g/cm³ ≈ 2,98 g par mètre.
_G_PAR_METRE_PLA = 2.98


def _parse_duree(texte: str) -> int:
    """« 1h 32m 10s », « 2d 1h 3m », « 45m », « 90s » → secondes."""
    total = 0
    for val, unit in re.findall(r"(\d+)\s*([dhms])", texte.lower()):
        total += int(val) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return total


def _lire_slice_info(path: Path) -> dict:
    """Bambu/Orca .gcode.3mf : Metadata/slice_info.config (XML), toutes plates
    agrégées (un fichier multi-plateaux additionne poids et durées)."""
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read("Metadata/slice_info.config")
        except KeyError:
            raise ValueError("slice_info.config absent — fichier non découpé ?")
    root = ElementTree.fromstring(xml)
    poids, duree = 0.0, 0
    par_fil: dict[str, dict] = {}
    n_plates = 0
    for plate in root.iter("plate"):
        n_plates += 1
        for md in plate.iter("metadata"):
            k, v = md.get("key"), md.get("value") or ""
            if k == "weight":
                poids += float(v or 0)
            elif k == "prediction":
                duree += int(float(v or 0))
        for fil in plate.iter("filament"):
            fid = fil.get("id") or "1"
            g = float(fil.get("used_g") or 0)
            acc = par_fil.setdefault(fid, {
                "id": int(fid), "type": fil.get("type") or "",
                "couleur": fil.get("color") or "", "grams": 0.0})
            acc["grams"] += g
    if poids <= 0 and par_fil:
        poids = sum(f["grams"] for f in par_fil.values())
    if poids <= 0 and duree <= 0:
        raise ValueError("slice_info.config sans poids ni durée")
    logger.info(f"Fichier découpé Bambu/Orca lu : {poids:.1f} g, {duree} s, "
                f"{len(par_fil)} filament(s), {n_plates} plateau(x)")
    return {"poids_g": round(poids, 2), "duree_s": duree,
            "par_filament": sorted(par_fil.values(), key=lambda f: f["id"]),
            "source": "bambu", "exact": True}


def _lire_gcode(path: Path) -> dict:
    """G-code texte : Prusa, Bambu/Orca brut, Cura — on lit têtes et queues
    (les commentaires y vivent), jamais le corps entier d'un fichier de 200 MB."""
    taille = path.stat().st_size
    with open(path, "rb") as f:
        tete = f.read(65536)
        if taille > 131072:
            f.seek(-65536, 2)
            queue = f.read()
        else:
            queue = b""
    texte = (tete + b"\n" + queue).decode("utf-8", errors="replace")

    poids, duree, exact = 0.0, 0, True
    # Prusa : "; filament used [g] = 12.34" — Bambu brut : "; total filament weight [g] : 42.5,1.2"
    m = re.search(r";\s*(?:total\s+)?filament\s+(?:used|weight)\s*\[g\]\s*[:=]\s*([\d., ]+)", texte, re.I)
    if m:
        poids = sum(float(x) for x in re.split(r"[;,]", m.group(1)) if x.strip())
    # Prusa : "; estimated printing time (normal mode) = 1h32m10s"
    m = re.search(r";\s*(?:total\s+)?estimated\s+(?:printing\s+)?time.*?[:=]\s*([\dhdms ]+)", texte, re.I)
    if m:
        duree = _parse_duree(m.group(1))
    if duree <= 0:
        m = re.search(r";\s*model printing time\s*[:=]\s*([\dhdms ]+)", texte, re.I)
        if m:
            duree = _parse_duree(m.group(1))
    # Cura : ";TIME:5581" + ";Filament used: 1.234m" (→ poids approx densité PLA)
    if duree <= 0:
        m = re.search(r";TIME:(\d+)", texte)
        if m:
            duree = int(m.group(1))
    if poids <= 0:
        m = re.search(r";Filament used:\s*([\d.]+)\s*m", texte, re.I)
        if m:
            poids = float(m.group(1)) * _G_PAR_METRE_PLA
            exact = False                       # approximation par densité PLA
    if poids <= 0 and duree <= 0:
        raise ValueError("aucun poids ni durée trouvé dans les commentaires G-code")
    logger.info(f"G-code lu : {poids:.1f} g ({'exact' if exact else 'approx'}), {duree} s")
    return {"poids_g": round(poids, 2), "duree_s": duree, "par_filament": [],
            "source": "gcode", "exact": exact}


def lire_fichier_tranche(path) -> dict:
    """Point d'entrée : accepte .gcode.3mf, .3mf découpé, .gcode."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Fichier introuvable : {path.name}")
    if path.suffix.lower() == ".3mf":           # couvre aussi « .gcode.3mf »
        return _lire_slice_info(path)
    if path.suffix.lower() == ".gcode":
        return _lire_gcode(path)
    raise ValueError(f"Format non pris en charge : {path.suffix}")
