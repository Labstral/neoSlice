# -*- coding: utf-8 -*-
"""Vérification d'imprimabilité et export (STL, 3MF, STEP).

Règle neoForge : on ne peut pas exporter une pièce non imprimable sans un
avertissement CLAIR. verifier() dit ce qui ne va pas, l'interface décide
(bloquant avec « exporter quand même », ou simple information)."""
from __future__ import annotations

import datetime
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from neoforge.noyau import occ as O

# Gravité : « bloquant » = l'imprimante produira une pièce ratée ;
#           « attention » = probablement voulu, mais à savoir.
BLOQUANT, ATTENTION = "bloquant", "attention"


@dataclass
class Constat:
    code: str                 # traduit par l'interface
    gravite: str
    detail: dict = field(default_factory=dict)


def verifier(V: np.ndarray, F: np.ndarray, plateau: tuple | None = None) -> list[Constat]:
    """Constats sur le maillage final. plateau = (largeur, profondeur, hauteur) mm."""
    import trimesh
    out: list[Constat] = []
    if len(F) == 0:
        return [Constat("vide", BLOQUANT)]
    m = trimesh.Trimesh(V, F, process=False)
    if not (m.is_watertight and m.is_winding_consistent):
        out.append(Constat("ouverte", BLOQUANT))
    taille = V.max(0) - V.min(0)
    if plateau:
        depasse = [float(t) for t, p in zip(taille, plateau) if p and t > p + 1e-6]
        if depasse:
            out.append(Constat("trop_grande", BLOQUANT,
                               {"taille": [round(float(t), 1) for t in taille],
                                "plateau": [round(float(p), 1) for p in plateau]}))
    try:
        n = int(trimesh.graph.connected_component_labels(m.face_adjacency,
                                                         node_count=len(F)).max()) + 1
    except Exception:
        n = 1
    if n > 1:
        out.append(Constat("morceaux", ATTENTION, {"n": n}))
    if float(taille.min()) < 0.8:
        out.append(Constat("trop_fine", ATTENTION, {"mm": round(float(taille.min()), 2)}))
    return out


def poser_au_sol(V: np.ndarray) -> np.ndarray:
    """Le point le plus bas à z = 0 (ce que fera de toute façon le slicer)."""
    W = V.copy()
    W[:, 2] -= W[:, 2].min()
    return W


def exporter_stl(V: np.ndarray, F: np.ndarray, chemin: str | Path) -> Path:
    chemin = Path(chemin)
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lg = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, lg, out=np.zeros_like(n), where=lg > 1e-12)
    rec = np.zeros(len(F), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    entete = f"neoForge {datetime.date.today().isoformat()}".encode("ascii")
    with open(chemin, "wb") as f:
        f.write(entete.ljust(80, b"\0")[:80])
        f.write(struct.pack("<I", len(F)))
        f.write(rec.tobytes())
    return chemin


def exporter_3mf(V: np.ndarray, F: np.ndarray, chemin: str | Path, nom: str = "neoForge") -> Path:
    import trimesh
    chemin = Path(chemin)
    m = trimesh.Trimesh(V, F, process=False)
    m.metadata["name"] = nom
    # Export générique (le nom de la fonction dédiée varie selon la version de trimesh)
    chemin.write_bytes(m.export(file_type="3mf"))
    return chemin


def exporter_step(forme, chemin: str | Path) -> Path:
    """STEP : le format d'échange des logiciels de CAO (FreeCAD, Fusion…),
    géométrie EXACTE (vrais cercles, vrais congés), pas des triangles."""
    from OCP.STEPControl import STEPControl_Writer
    import OCP.STEPControl as SC
    import OCP.IFSelect as IF
    chemin = Path(chemin)
    tel_quel = getattr(SC, "STEPControl_AsIs", None)
    if tel_quel is None:
        tel_quel = SC.STEPControl_StepModelType.STEPControl_AsIs
    ok = getattr(IF, "IFSelect_RetDone", None)
    if ok is None:
        ok = IF.IFSelect_ReturnStatus.IFSelect_RetDone
    w = STEPControl_Writer()
    if w.Transfer(forme, tel_quel) != ok or w.Write(str(chemin)) != ok:
        raise RuntimeError("export STEP impossible")
    return chemin
