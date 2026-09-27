# -*- coding: utf-8 -*-
"""Accès UNIQUE au noyau OpenCascade (OCP).

Le noyau est téléchargé avec le module (≈ 175 Mo installé) dans
~/.neoslice/neoforge/noyau. Tout le reste de neoForge importe OCP par ce
module, jamais directement : un seul endroit sait où le trouver et gère les
différences de nommage entre versions d'OCP (méthodes statiques suffixées
« _s » sur les classes, fonctions sans suffixe sur les espaces de noms).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DOSSIER_NOYAU = Path.home() / ".neoslice" / "neoforge" / "noyau"


PYTHON_NOYAU = (3, 12)      # version pour laquelle le noyau est compilé


def diagnostic(dossier: str | Path | None = None) -> str:
    """Rend OCP importable et dit ce qui manque, le cas échéant :
      « »        le noyau est chargeable ;
      « absent » le noyau n'est pas installé ;
      « python » il est là mais compilé pour une autre version de Python
                 (arrive seulement en développement : l'application distribuée
                 embarque toujours Python 3.12) ;
      « abime »  autre problème, le détail part dans le journal.
    Le paquet OCP enregistre lui-même le dossier de ses DLL."""
    d = Path(dossier or os.environ.get("NEOFORGE_NOYAU") or DOSSIER_NOYAU)
    if not (d / "OCP").is_dir():
        return "absent"
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    try:
        import OCP  # noqa: F401
        return ""
    except Exception as exc:
        try:
            from loguru import logger
            logger.debug(f"neoForge noyau : {type(exc).__name__} : {exc}")
        except Exception:
            pass
        return "python" if sys.version_info[:2] != PYTHON_NOYAU else "abime"


def preparer_chemin(dossier: str | Path | None = None) -> bool:
    return diagnostic(dossier) == ""


_etat = diagnostic()
if _etat:
    raise ImportError(_etat)

from OCP.gp import (gp_Pnt, gp_Dir, gp_Vec, gp_Ax1, gp_Ax2, gp_Trsf,  # noqa: E402
                    gp_Elips)
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Compound  # noqa: E402
from OCP.BRep import BRep_Builder  # noqa: E402
from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID,  # noqa: E402
                        TopAbs_REVERSED)
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopLoc import TopLoc_Location  # noqa: E402
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere,  # noqa: E402
                             BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone,
                             BRepPrimAPI_MakeTorus, BRepPrimAPI_MakePrism)
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeVertex,  # noqa: E402
                                BRepBuilderAPI_Transform,
                                BRepBuilderAPI_MakePolygon,
                                BRepBuilderAPI_MakeEdge,
                                BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_MakeFace)
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.BRepAlgoAPI import (BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut,  # noqa: E402
                             BRepAlgoAPI_Common)
from OCP.BRepFilletAPI import (BRepFilletAPI_MakeFillet,  # noqa: E402
                               BRepFilletAPI_MakeChamfer)
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: E402
from OCP.BRepTools import BRepTools  # noqa: E402
from OCP.BRepCheck import BRepCheck_Analyzer  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402
from OCP.Bnd import Bnd_Box  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: E402
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle, GeomAbs_C0  # noqa: E402
from OCP.BRepLib import BRepLib  # noqa: E402
from OCP.Geom import Geom_CylindricalSurface  # noqa: E402
from OCP.Geom2d import Geom2d_Line  # noqa: E402
from OCP.gp import gp_Ax3, gp_Pnt2d, gp_Dir2d, gp_Lin2d  # noqa: E402
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell  # noqa: E402
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain  # noqa: E402


def _f(classe, nom: str):
    """Méthode statique quel que soit le nommage (« Nom_s » ou « Nom »)."""
    return getattr(classe, nom + "_s", None) or getattr(classe, nom)


def arete(s):
    return _f(TopoDS, "Edge")(s)


def face(s):
    return _f(TopoDS, "Face")(s)


def triangulation(f, loc):
    return _f(BRep_Tool, "Triangulation")(f, loc)


def _chercher(table: dict, s):
    """Entrée de `table` (hash → [[forme, …], …]) correspondant à la même
    sous-forme que `s` (IsSame : même géométrie, orientation ignorée)."""
    for ent in table.get(hash(s), ()):
        if ent[0].IsSame(s):
            return ent
    return None


def sous_formes(forme, genre) -> list:
    """Sous-formes UNIQUES de `forme` (une arête partagée par deux faces n'est
    rendue qu'une fois), dans un ordre stable. Sans les conteneurs NCollection
    d'OpenCascade, dont les noms changent d'une version d'OCP à l'autre."""
    table, out = {}, []
    ex = TopExp_Explorer(forme, genre)
    while ex.More():
        s = ex.Current()
        if _chercher(table, s) is None:
            table.setdefault(hash(s), []).append([s])
            out.append(s)
        ex.Next()
    return out


def aretes_et_faces(forme) -> list[tuple]:
    """[(arête, [faces voisines distinctes])] pour chaque arête unique."""
    table, ordre = {}, []
    exf = TopExp_Explorer(forme, TopAbs_FACE)
    while exf.More():
        f = exf.Current()
        exe = TopExp_Explorer(f, TopAbs_EDGE)
        while exe.More():
            e = exe.Current()
            ent = _chercher(table, e)
            if ent is None:
                ent = [e, []]
                table.setdefault(hash(e), []).append(ent)
                ordre.append(ent)
            if not any(f.IsSame(g) for g in ent[1]):
                ent[1].append(f)
            exe.Next()
        exf.Next()
    return [(arete(e), [face(x) for x in fs]) for e, fs in ordre]


def continuite(e, f1, f2):
    return _f(BRep_Tool, "Continuity")(e, f1, f2)


def degeneree(e) -> bool:
    return bool(_f(BRep_Tool, "Degenerated")(e))


def encoder_regularite(forme) -> None:
    """Marque les arêtes lisses (tangentes) : sans ça, Continuity() répond C0
    même entre un congé et sa face voisine."""
    try:
        _f(BRepLib, "EncodeRegularity")(forme, 1e-3)
    except Exception:
        pass


def nettoyer_maillage(forme) -> None:
    try:
        _f(BRepTools, "Clean")(forme)
    except Exception:
        pass


def volume(forme) -> float:
    p = GProp_GProps()
    _f(BRepGProp, "VolumeProperties")(forme, p)
    return float(p.Mass())


def longueur(e) -> float:
    p = GProp_GProps()
    _f(BRepGProp, "LinearProperties")(e, p)
    return float(p.Mass())


def boite(forme) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Boîte englobante EXACTE (la version rapide d'OpenCascade peut déborder
    sur les surfaces courbes : le « haut » de la pièce serait faux)."""
    b = Bnd_Box()
    try:
        _f(BRepBndLib, "AddOptimal")(forme, b, False, False)
    except Exception:
        _f(BRepBndLib, "Add")(forme, b)
    try:
        # OCP 8 : Get() renvoie une structure C++ que Python ne sait pas lire.
        lo, hi = b.CornerMin(), b.CornerMax()
        return (lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())
    except Exception:
        x0, y0, z0, x1, y1, z1 = b.Get()
        return (x0, y0, z0), (x1, y1, z1)


def valide(forme) -> bool:
    try:
        return forme is not None and not forme.IsNull() and BRepCheck_Analyzer(forme).IsValid()
    except Exception:
        return False


def unifier(forme):
    """Fusionne les faces coplanaires laissées par les booléens (deux cubes
    empilés de même largeur ne doivent pas garder d'arête de couture)."""
    try:
        u = ShapeUpgrade_UnifySameDomain(forme, True, True, False)
        u.Build()
        r = u.Shape()
        return r if not r.IsNull() else forme
    except Exception:
        return forme
