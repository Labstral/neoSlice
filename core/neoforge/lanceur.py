# -*- coding: utf-8 -*-
"""Démarre neoForge dans le programme courant (neoSlice lancé avec --neoforge).

Vérifie, dans l'ordre : licence Pro, neoForge pas déjà ouvert (sinon on le
ramène devant), paquet installé et compatible, noyau chargeable. Chaque refus
affiche un message clair et ferme proprement ce second programme : jamais de
fenêtre vide ni de plantage.

En développement (sources, pas l'exe), le dossier neoforge/ du dépôt est
utilisé directement : Emmanuel teste la dernière version via python main.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from PySide6.QtCore import QEventLoop, QThread, Signal

from core.i18n import _
from core.neoforge import installation, pont


class _Prechargement(QThread):
    """Charge le noyau de CAO et l'interface HORS du fil principal.

    Sans ça, la barre de l'écran de chargement se fige : c'est le fil principal
    qui la dessine, et il serait occupé à importer (retour d'Emmanuel)."""
    fini = Signal(str)              # "" si tout va bien, sinon un code d'erreur

    def run(self):
        try:
            import neoforge  # noqa: F401
            from neoforge.noyau import occ  # noqa: F401
            from neoforge.app import creer_fenetre  # noqa: F401
            # L'INTERFACE aussi, et c'est le plus gros morceau : PySide, pyvista
            # et VTK pèsent près d'une seconde. `neoforge.app` est minuscule et
            # ne les tire pas (ses imports sont dans la fonction), si bien que
            # tout ce poids retombait sur le fil principal, à la première ligne
            # de creer_fenetre, écran de chargement figé d'autant.
            # Mesuré : 1038 ms d'imports sur le fil principal avant correction.
            from neoforge.ui import fenetre as _interface  # noqa: F401
            from neoforge.ui import viewer as _vue  # noqa: F401
            self.fini.emit("")
        except ImportError as exc:
            self.fini.emit(str(exc) or "abime")
        except Exception:
            logger.exception("neoForge : préchargement impossible")
            self.fini.emit("abime")


def _source_depot() -> Path | None:
    if getattr(sys, "frozen", False):
        return None
    d = Path(__file__).resolve().parent.parent.parent
    return d if (d / "neoforge" / "__init__.py").is_file() else None


def disponible() -> bool:
    """neoForge peut-il s'ouvrir ? (module installé, ou sources du dépôt en dev)"""
    return _source_depot() is not None or installation.est_installe()


def _message(cle: str, **kw) -> None:
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information(None, "neoForge", _(cle, **kw))


def _version(v: str) -> tuple:
    return installation._version(v)


def demarrer(app, splash=None):
    """Crée et montre la fenêtre neoForge ; None si neoForge ne doit pas s'ouvrir.
    `splash` est fermé avant tout message : jamais une fenêtre de dialogue
    coincée derrière l'écran de chargement."""
    from core import licensing
    from version import __version__

    def _fermer_splash():
        if splash is not None:
            splash.close()

    global _message
    _message_brut = _message

    def _message(cle: str, **kw):            # noqa: F811  (ferme le splash d'abord)
        _fermer_splash()
        _message_brut(cle, **kw)

    if not licensing.est_pro():
        _message("neoforge.lance_pro")
        return None
    if pont.neoforge_en_cours():
        pont.envoyer(pont.NOM_INSTANCE, pont.emballer({"type": "montrer"}), reponse=False)
        return None

    depot = _source_depot()
    if depot is not None:
        if str(depot) not in sys.path:
            sys.path.insert(0, str(depot))
    else:
        if not installation.est_installe():
            _message("neoforge.lance_absent")
            return None
        code = str(installation.chemins()["code"])
        if code not in sys.path:
            sys.path.insert(0, code)

    try:
        import neoforge
        if depot is None and _version(neoforge.NEOSLICE_MIN) > _version(__version__):
            _message("neoforge.lance_maj_neoslice", v=neoforge.NEOSLICE_MIN)
            return None
    except Exception:
        logger.exception("neoForge : paquet illisible")
        _message("neoforge.lance_abime")
        return None

    # Chargement dans un fil : l'écran de chargement reste vivant (sa barre
    # défile) pendant l'import du noyau et de l'interface.
    fil = _Prechargement()
    resultat: dict[str, str] = {}
    boucle = QEventLoop()
    fil.fini.connect(lambda code: (resultat.setdefault("code", code), boucle.quit()))
    fil.start()
    boucle.exec()
    fil.wait(3000)
    code = resultat.get("code", "abime")
    if code:
        # occ lève un code : le message doit dire la VRAIE raison, pas
        # « réinstallez » quand le noyau est là mais pas fait pour ce Python.
        cle = {"python": "neoforge.lance_python",
               "absent": "neoforge.lance_absent"}.get(code, "neoforge.lance_abime")
        logger.error(f"neoForge : démarrage impossible ({code})")
        _message(cle, v=f"{sys.version_info.major}.{sys.version_info.minor}")
        return None

    from neoforge.app import creer_fenetre
    fen = creer_fenetre(app)
    serveur = pont.Serveur(pont.NOM_INSTANCE, parent=fen)

    def _recu(entete, _charge):
        if entete.get("type") == "montrer":
            # On sort de la barre des tâches SANS défaire le plein écran :
            # `showNormal()` aurait rendu la fenêtre à sa taille de secours.
            from PySide6.QtCore import Qt as _Qt
            fen.setWindowState((fen.windowState() & ~_Qt.WindowMinimized)
                               | _Qt.WindowActive)
            fen.show()
            fen.raise_()
            fen.activateWindow()
    serveur.message.connect(_recu)
    serveur.demarrer()
    fen._serveur_instance = serveur          # anti-GC
    # La fenêtre D'ABORD, l'écran de chargement ensuite : en fermant le splash
    # avant, on laissait l'utilisateur devant un bureau vide le temps que la
    # fenêtre se dessine (environ 200 ms mesurées).
    # Plein écran d'entrée de jeu (demande d'Emmanuel) : on modélise avec la
    # vue 3D la plus grande possible, et les trois colonnes ont enfin la place
    # de respirer. Fenêtre AGRANDIE et non « plein écran » au sens strict : la
    # barre de titre reste, donc la croix de fermeture et le passage aux autres
    # fenêtres restent à portée de souris.
    fen.showMaximized()
    _fermer_splash()
    logger.info(f"neoForge {neoforge.VERSION} prêt")
    return fen
