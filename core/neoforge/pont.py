# -*- coding: utf-8 -*-
"""Pont entre neoSlice et neoForge, deux programmes séparés (le même exe lancé
deux fois) : un plantage du noyau de CAO ne peut pas emporter le travail en
cours dans neoSlice.

Communication locale en mémoire (QLocalSocket : tube nommé sous Windows,
socket Unix sur Mac), JAMAIS par un fichier sur le disque. Un message =
  4 octets (taille de l'en-tête JSON, gros-boutiste) + en-tête JSON + charge
  binaire de en-tête["octets"] octets.

Messages :
  neoForge → neoSlice  {"type": "piece", "nom", "sommets", "faces"} + float32/int32
                       {"type": "imprimante"}  → {"type": "imprimante", "nom", "plateau", "buse"}
  neoSlice → neoForge  {"type": "montrer"}     (neoForge déjà ouvert : on le ramène devant)
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from shiboken6 import isValid


def _suffixe() -> str:
    """Un nom par utilisateur (deux sessions Windows ne se mélangent pas)."""
    return hashlib.sha1(str(Path.home()).encode("utf-8")).hexdigest()[:10]


NOM_PONT = f"neoslice-pont-{_suffixe()}"
NOM_INSTANCE = f"neoforge-instance-{_suffixe()}"
ARG_NEOFORGE = "--neoforge"


# ── Trames ─────────────────────────────────────────────────────────────────
def emballer(entete: dict, charge: bytes = b"") -> bytes:
    e = dict(entete)
    e["octets"] = len(charge)
    brut = json.dumps(e, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(brut)) + brut + charge


class Lecteur:
    """Reconstitue les messages à partir d'octets arrivés par morceaux."""

    def __init__(self):
        self._tampon = bytearray()

    def ajouter(self, octets: bytes) -> list[tuple[dict, bytes]]:
        self._tampon += octets
        out = []
        while len(self._tampon) >= 4:
            n = struct.unpack(">I", self._tampon[:4])[0]
            if len(self._tampon) < 4 + n:
                break
            entete = json.loads(bytes(self._tampon[4:4 + n]).decode("utf-8"))
            fin = 4 + n + int(entete.get("octets", 0))
            if len(self._tampon) < fin:
                break
            out.append((entete, bytes(self._tampon[4 + n:fin])))
            del self._tampon[:fin]
        return out


def piece_vers_message(nom: str, V: np.ndarray, F: np.ndarray) -> bytes:
    V = np.ascontiguousarray(V, dtype="<f4")
    F = np.ascontiguousarray(F, dtype="<i4")
    return emballer({"type": "piece", "nom": nom, "sommets": len(V), "faces": len(F)},
                    V.tobytes() + F.tobytes())


def piece_depuis_message(entete: dict, charge: bytes) -> tuple[np.ndarray, np.ndarray]:
    nv, nf = int(entete["sommets"]), int(entete["faces"])
    V = np.frombuffer(charge, dtype="<f4", count=nv * 3).reshape(nv, 3).astype(np.float64)
    F = np.frombuffer(charge, dtype="<i4", count=nf * 3, offset=nv * 12).reshape(nf, 3)
    return V, F.astype(np.int64)


# ── Client (appels courts et bloquants) ─────────────────────────────────────
def envoyer(nom_serveur: str, message: bytes, reponse: bool = True,
            delai_ms: int = 3000) -> dict | None:
    """Envoie un message déjà emballé ; renvoie l'en-tête de la réponse, ou None
    si le programme d'en face n'est pas ouvert / ne répond pas."""
    s = QLocalSocket()
    s.connectToServer(nom_serveur)
    if not s.waitForConnected(delai_ms):
        return None
    try:
        s.write(message)
        s.flush()
        while s.bytesToWrite() > 0:
            if not s.waitForBytesWritten(delai_ms):
                return None
        if not reponse:
            return {}
        lecteur = Lecteur()
        while True:
            if not s.waitForReadyRead(delai_ms):
                return None
            recus = lecteur.ajouter(bytes(s.readAll()))
            if recus:
                return recus[0][0]
    finally:
        s.disconnectFromServer()


def en_cours(nom_serveur: str) -> bool:
    s = QLocalSocket()
    s.connectToServer(nom_serveur)
    ok = s.waitForConnected(300)
    s.abort()
    return ok


def neoforge_en_cours() -> bool:
    return en_cours(NOM_INSTANCE)


def neoslice_en_cours() -> bool:
    return en_cours(NOM_PONT)


# ── Serveur (chaque programme en ouvre un) ───────────────────────────────────
class Serveur(QObject):
    """Écoute un nom local ; `repondre(entete, charge) -> bytes | None` produit la
    réponse (message emballé) à chaque message reçu."""
    message = Signal(dict, bytes)

    def __init__(self, nom: str, repondre=None, parent=None):
        super().__init__(parent)
        self._nom = nom
        self._repondre = repondre
        self._serveur = QLocalServer(self)
        self._serveur.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._serveur.newConnection.connect(self._nouvelle)
        self._lecteurs: dict = {}

    def demarrer(self) -> bool:
        if self._serveur.listen(self._nom):
            return True
        # Nom resté pris après un plantage (socket Unix orpheline) : on le libère
        # SEULEMENT si personne ne répond derrière.
        if not en_cours(self._nom):
            QLocalServer.removeServer(self._nom)
            return self._serveur.listen(self._nom)
        return False

    def fermer(self) -> None:
        """Ferme le serveur et ses connexions, puis laisse Qt terminer ses
        suppressions différées : détruire ces objets pendant qu'il reste des
        événements en attente fait planter le processus."""
        from PySide6.QtCore import QCoreApplication, QEvent
        for s in list(self._lecteurs):
            if isValid(s):
                s.abort()
        self._lecteurs.clear()
        self._serveur.close()
        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _nouvelle(self):
        while self._serveur.hasPendingConnections():
            s = self._serveur.nextPendingConnection()
            self._lecteurs[s] = Lecteur()
            s.readyRead.connect(lambda s=s: self._lire(s))
            s.disconnected.connect(lambda s=s: self._fermer(s))
            # Données arrivées AVANT le branchement de readyRead : sans cette
            # lecture immédiate, le premier message était perdu (vu au test).
            if s.bytesAvailable():
                self._lire(s)

    def _fermer(self, s):
        self._lecteurs.pop(s, None)
        if isValid(s):
            s.deleteLater()

    def _lire(self, s):
        lecteur = self._lecteurs.get(s)
        if lecteur is None or not isValid(s):
            return
        for entete, charge in lecteur.ajouter(bytes(s.readAll())):
            rep = None
            if self._repondre is not None:
                try:
                    rep = self._repondre(entete, charge)
                except Exception as exc:
                    rep = emballer({"type": "erreur", "detail": str(exc)[:200]})
            if isValid(s):
                s.write(rep or emballer({"type": "ok"}))
                s.flush()
            self.message.emit(entete, charge)


# ── Lancement des programmes ────────────────────────────────────────────────
PYTHON_NOYAU = (3, 12)          # version pour laquelle le noyau de CAO est compilé


def interpreteur_neoforge(version: tuple | None = None) -> str:
    """Python à utiliser pour neoForge.

    L'application distribuée embarque Python 3.12 : rien à choisir. Depuis les
    SOURCES en revanche, neoSlice peut tourner sous une autre version, avec
    laquelle le noyau de CAO (compilé pour 3.12) ne se charge pas. On prend
    alors automatiquement le Python 3.12 du projet, sans rien demander."""
    if getattr(sys, "frozen", False) or (version or sys.version_info[:2]) == PYTHON_NOYAU:
        return sys.executable
    racine = Path(__file__).resolve().parent.parent.parent
    for candidat in (racine / ".venv312" / "Scripts" / "python.exe",
                     racine / ".venv312" / "bin" / "python"):
        if candidat.exists():
            return str(candidat)
    return sys.executable


def _commande(args: list[str], python: str | None = None) -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        return sys.executable, args
    main_py = Path(__file__).resolve().parent.parent.parent / "main.py"
    return (python or sys.executable), [str(main_py), *args]


def lancer_neoforge() -> bool:
    """Ouvre neoForge dans son propre programme, ou le ramène devant s'il l'est déjà."""
    if neoforge_en_cours():
        envoyer(NOM_INSTANCE, emballer({"type": "montrer"}), reponse=False)
        return True
    prog, args = _commande([ARG_NEOFORGE], interpreteur_neoforge())
    ok = QProcess.startDetached(prog, args)
    return bool(ok[0] if isinstance(ok, tuple) else ok)


def lancer_neoslice() -> bool:
    prog, args = _commande([])
    ok = QProcess.startDetached(prog, args)
    return bool(ok[0] if isinstance(ok, tuple) else ok)
