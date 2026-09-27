# -*- coding: utf-8 -*-
"""Pont neoForge ↔ neoSlice : trames reçues par morceaux, pièce transmise sans
perte, et vrai échange entre DEUX PROGRAMMES (comme en vrai : neoForge tourne
dans son propre processus).

Note : on ne teste pas un client bloquant contre un serveur du MÊME processus.
Pendant l'attente bloquante d'un socket Qt, le fil principal ne peut plus
exécuter de Python, donc le serveur n'accepterait la connexion qu'après
l'abandon du client (diagnostiqué le 2026-09-12). Ce cas n'existe pas en
production, où les deux bouts sont deux programmes distincts."""
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtNetwork import QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.neoforge import pont as P  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
# L'application Qt est gardée pour TOUT le module : dans une variable locale,
# elle serait détruite à la fin du test et le test d'interface suivant
# s'arrêterait net (« Fatal Python error: Aborted », vu sur la suite complète).
APP = QApplication.instance() or QApplication([])
_GARDE: list = []          # objets Qt gardés en vie jusqu'à la fin du module
V = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10.5]], float)
F = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]], np.int64)


def test_trames_recues_par_petits_morceaux():
    flux = P.emballer({"type": "montrer"}) + P.piece_vers_message("cale", V, F)
    lecteur, recus = P.Lecteur(), []
    for i in range(0, len(flux), 7):
        recus += lecteur.ajouter(flux[i:i + 7])
    assert [e["type"] for e, _c in recus] == ["montrer", "piece"]
    e, c = recus[1]
    assert e["nom"] == "cale"
    V2, F2 = P.piece_depuis_message(e, c)
    assert np.allclose(V2, V) and np.array_equal(F2, F)


def test_serveur_recoit_et_repond(tmp_path):
    """Serveur réel, client piloté par la boucle d'événements (sans attente
    bloquante) : c'est le chemin utilisé côté neoSlice."""
    nom = f"neoforge-test-{os.getpid()}"
    recus = []

    def repondre(e, _c):
        recus.append(e["type"])
        if e["type"] == "imprimante":
            return P.emballer({"type": "imprimante", "plateau": [256, 256, 256]})
        return None

    srv = P.Serveur(nom, repondre)
    assert srv.demarrer()
    boucle, reponses, lecteur = QEventLoop(), [], P.Lecteur()
    s = QLocalSocket()

    def envoyer():
        s.write(P.emballer({"type": "imprimante"}))
        s.write(P.piece_vers_message("cale", V, F))

    def lire():
        for entete, _c in lecteur.ajouter(bytes(s.readAll())):
            reponses.append(entete)
            if len(reponses) == 2:
                boucle.quit()

    s.connected.connect(envoyer)
    s.readyRead.connect(lire)
    s.connectToServer(nom)
    QTimer.singleShot(8000, boucle.quit)
    boucle.exec()
    try:
        assert recus == ["imprimante", "piece"]
        assert reponses[0]["plateau"] == [256, 256, 256]
        assert reponses[1]["type"] == "ok"
    finally:
        # Fermeture ORDONNÉE, puis on garde les objets en vie : détruits par
        # Python alors que Qt a encore des événements pour eux, le test suivant
        # qui crée un widget plantait le processus (« access violation »).
        s.abort()
        srv.fermer()
        _GARDE.extend([s, srv])
        APP.processEvents()


def test_echange_entre_deux_programmes(tmp_path):
    """Le vrai cas : le serveur est dans un AUTRE programme, le client attend sa
    réponse (c'est ce que fait neoForge en envoyant sa pièce)."""
    nom = f"neoforge-proc-{os.getpid()}"
    script = tmp_path / "serveur.py"
    script.write_text(textwrap.dedent(f"""
        import sys
        sys.path.insert(0, r"{RACINE}")
        from PySide6.QtWidgets import QApplication
        from core.neoforge import pont as P
        app = QApplication([])
        recu = []
        def repondre(e, c):
            if e["type"] == "piece":
                V, F = P.piece_depuis_message(e, c)
                return P.emballer({{"type": "recu", "sommets": len(V), "faces": len(F),
                                   "z_max": float(V[:, 2].max())}})
            return None
        srv = P.Serveur("{nom}", repondre)
        assert srv.demarrer()
        print("pret", flush=True)
        app.exec()
    """), encoding="utf-8")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE,
                            text=True, env=env)
    try:
        assert proc.stdout.readline().strip() == "pret"
        fin = time.time() + 10
        rep = None
        while rep is None and time.time() < fin:
            rep = P.envoyer(nom, P.piece_vers_message("cale", V, F), delai_ms=2000)
        assert rep is not None, "le second programme n'a pas répondu"
        assert (rep["sommets"], rep["faces"]) == (len(V), len(F))
        assert rep["z_max"] == 10.5                      # géométrie intacte
        assert P.en_cours(nom) and not P.en_cours(nom + "-absent")
    finally:
        proc.terminate()
        proc.wait(10)
