"""Installation optionnelle de l'assistant IA (version Pro).

Telecharge et met en place, en local, tout ce dont l'assistant a besoin :
  1. le runtime Ollama (release officielle, URL stable) ;
  2. le modele de discussion + le modele d'embedding (via le registre Ollama,
     donc AUCUN hebergement de notre cote pour ces gros fichiers) ;
  3. la base de connaissances indexee (vecteurs + passages), hebergee par nous
     (ex. une release GitHub).

Tout est reprenable (un fichier deja present et complet est saute) et rapporte sa
progression via un callback `progress(stage_label: str, fraction: float 0..1)` et
un `log(msg)`. Concu pour tourner dans un QThread cote UI.
"""
from __future__ import annotations
import io
import os
import sys
import json
import stat
import zipfile
import tarfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core.assistant.engine import (
    ASSIST_DIR, OLLAMA_DIR, OLLAMA_EXE, MODELS_DIR, BASE, GGUF_PATH, EMBED_GGUF_PATH,
    MODEL_NAME, EMBED_MODEL, CHAT_BASE_MODEL, INSTALL_MARKER, KB_INDEX_DIR, AssistantEngine,
)

# ── Sources : TOUT passe par GitHub (un seul canal) ───────────────────────────
# Une seule release GitHub publique heberge tous les assets de l'assistant. Il
# suffit d'y deposer les fichiers ci-dessous et, au besoin, d'ajuster ces noms.
ASSET_BASE_URL = "https://github.com/labstral/neoslice-assets/releases/download/assistant-latest"

# 1) Runtime Ollama, PAR PLATEFORME (archive officielle mirroir dans NOTRE release
#    pour rester sur un seul canal). Chaque entree : (nom d'asset, format d'archive).
#    -> uploader ces deux fichiers dans la release neoslice-assets.
OLLAMA_RUNTIME: dict[str, tuple[str, str]] = {
    "win32":  ("ollama-windows-amd64.zip", "zip"),
    "darwin": ("ollama-darwin.tgz",        "tgz"),
}

# 2) Modele de discussion (GGUF). Un fichier si <= 2 Go, sinon une liste de parties
#    concatenees (limite d'un asset GitHub = 2 Go).
#    IMPORTANT (2026-07-08) : le modele est passe a Qwen3 8B (voir engine.CHAT_BASE_MODEL).
#    Le GGUF hebergé sous ces noms DOIT etre Qwen3 8B (~5 Go en 3 parties), PAS l'ancien
#    Qwen2.5 7B — sinon l'alias serait cree depuis le mauvais modele. Alternative plus
#    simple : supprimer ces assets et laisser _ensure_model faire `ollama pull qwen3:8b`
#    depuis le registre (l'installateur a deja besoin d'Internet). Decision distribution
#    a trancher.
CHAT_GGUF_ASSET = "model.gguf"
CHAT_GGUF_PARTS: tuple[str, ...] = ("model.gguf.00", "model.gguf.01", "model.gguf.02")

# 3) Modele d'embedding (GGUF). bge-m3 (multilingue, 1024 dim) ~= 1,0 a 1,3 Go selon
#    la quantification, un seul fichier (< 2 Go). Uploader le GGUF bge-m3 sous ce nom.
EMBED_GGUF_ASSET = "embed.gguf"
EMBED_GGUF_PARTS: tuple[str, ...] = ()

# 4) Base de connaissances indexee (3 fichiers). Ecrite dans KB_INDEX_DIR, un
#    dossier INSCRIPTIBLE sous ~/.neoslice (importe depuis engine), jamais dans le
#    dossier d'installation (qui peut etre en lecture seule, ex. Program Files).
KB_INDEX_FILES = ("meta.json", "chunks.jsonl", "vectors.npy")

ProgressCb = Callable[[str, float], None]
LogCb = Callable[[str], None]


def _noop(*_a, **_k):
    pass


def is_installed() -> bool:
    return INSTALL_MARKER.exists()


def uninstall() -> None:
    """Desinstalle l'assistant : arrete le serveur Ollama, libere les fichiers
    verrouilles, puis supprime tout le dossier ~/.neoslice/assistant (runtime,
    modeles, GGUF, marqueur). Reclame l'espace disque (~8 Go)."""
    import sys as _sys
    import time
    import shutil
    import subprocess
    # 1) arreter proprement le serveur lance par le moteur
    try:
        eng = AssistantEngine.instance()
        proc = getattr(eng, "_server_proc", None)
        if proc is not None:
            proc.terminate()
    except Exception:
        pass
    # 2) tuer tout process ollama.exe restant (sinon fichiers verrouilles sous Windows)
    if _sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                           capture_output=True, creationflags=0x08000000)
        except Exception:
            pass
    time.sleep(0.6)
    # 3) supprimer le dossier de l'assistant (contient aussi le marqueur)
    shutil.rmtree(ASSIST_DIR, ignore_errors=True)
    # 4) remettre le moteur a zero
    try:
        eng._model_ready = False
        eng._server_proc = None
    except Exception:
        pass


class AssistantInstaller:
    """Orchestre l'installation. Utiliser install() dans un thread de travail."""

    def __init__(self, progress: Optional[ProgressCb] = None, log: Optional[LogCb] = None):
        self._progress = progress or _noop
        self._log = log or _noop
        self._cancel = False

    def cancel(self):
        self._cancel = True

    # ── Utilitaires ──────────────────────────────────────────────────────────
    def _emit(self, base: float, span: float, frac: float, label: str):
        self._progress(label, base + span * max(0.0, min(1.0, frac)))

    def _check_cancel(self):
        if self._cancel:
            raise RuntimeError("Installation annulee.")

    def _download(self, url: str, dest: Path, base: float, span: float, label: str) -> None:
        """Telecharge `url` -> `dest` en streaming, avec progression. Saute si deja
        present et de taille attendue."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length", 0))
            if dest.exists() and total and dest.stat().st_size == total:
                self._emit(base, span, 1.0, label)
                self._log(f"{dest.name} deja present.")
                return
            tmp = dest.with_suffix(dest.suffix + ".part")
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    self._check_cancel()
                    chunk = r.read(1 << 20)  # 1 Mo
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self._emit(base, span, done / total, label)
            os.replace(tmp, dest)
        self._log(f"{dest.name} telecharge ({done/1e6:.0f} Mo).")

    def _stream_into(self, url: str, out, base: float, span: float, label: str) -> None:
        """Telecharge `url` et l'ecrit dans le flux `out` deja ouvert (pour concatener
        des parties), avec progression basee sur la taille de la partie."""
        req = urllib.request.Request(url, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            while True:
                self._check_cancel()
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    self._emit(base, span, done / total, label)

    def _fetch_asset(self, name: str, parts: tuple, dest: Path,
                     base: float, span: float, label: str) -> None:
        """Recupere un asset : soit un fichier unique, soit plusieurs parties (limite
        de 2 Go par asset GitHub) concatenees dans `dest`."""
        if not parts:
            self._download(f"{ASSET_BASE_URL}/{name}", dest, base, span, label)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        n = len(parts)
        with open(tmp, "wb") as out:
            for i, pname in enumerate(parts):
                self._stream_into(f"{ASSET_BASE_URL}/{pname}", out,
                                  base + span * i / n, span / n, f"{label} ({i+1}/{n})")
        os.replace(tmp, dest)
        self._log(f"{dest.name} assemble depuis {n} parties.")

    # ── Etapes ───────────────────────────────────────────────────────────────
    def _install_ollama(self, base: float, span: float) -> None:
        if OLLAMA_EXE.exists():
            self._emit(base, span, 1.0, "Runtime Ollama déjà installé")
            return
        runtime = OLLAMA_RUNTIME.get(sys.platform)
        if runtime is None:
            raise RuntimeError(
                f"Plateforme non prise en charge pour l'assistant : {sys.platform}.")
        asset, fmt = runtime
        ASSIST_DIR.mkdir(parents=True, exist_ok=True)
        OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
        arc_path = ASSIST_DIR / ("ollama.zip" if fmt == "zip" else "ollama.tgz")
        self._download(f"{ASSET_BASE_URL}/{asset}", arc_path,
                       base, span * 0.85, "Téléchargement du moteur Ollama")
        self._progress("Extraction du moteur Ollama", base + span * 0.9)
        if fmt == "zip":
            with zipfile.ZipFile(arc_path) as z:
                z.extractall(OLLAMA_DIR)
        else:  # .tgz (macOS / Linux)
            with tarfile.open(arc_path, "r:gz") as t:
                t.extractall(OLLAMA_DIR, filter="data")
        arc_path.unlink(missing_ok=True)
        self._finalize_ollama_binary()
        self._emit(base, span, 1.0, "Moteur Ollama installé")

    def _finalize_ollama_binary(self) -> None:
        """Garantit que OLLAMA_EXE est au bon endroit et exécutable (macOS/Linux).
        Si l'archive range le binaire dans un sous-dossier, on remonte TOUT le
        contenu de ce dossier (binaire + éventuelles bibliothèques lib/) d'un
        niveau, pour que le binaire retrouve ses libs à côté de lui."""
        if not OLLAMA_EXE.exists():
            target = OLLAMA_EXE.name  # "ollama.exe" (Windows) ou "ollama" (macOS/Linux)
            found = next((p for p in OLLAMA_DIR.rglob(target) if p.is_file()), None)
            if found is None:
                raise RuntimeError(f"{target} introuvable après extraction.")
            src_dir = found.parent
            if src_dir != OLLAMA_DIR:
                for item in src_dir.iterdir():
                    dest = OLLAMA_DIR / item.name
                    if not dest.exists():
                        item.replace(dest)
        if not OLLAMA_EXE.exists():
            raise RuntimeError(f"{OLLAMA_EXE.name} introuvable après extraction.")
        if sys.platform != "win32":
            m = OLLAMA_EXE.stat().st_mode
            OLLAMA_EXE.chmod(m | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _install_models(self, base: float, span: float) -> None:
        # Modeles tires du REGISTRE Ollama (option B) : RIEN a heberger de notre cote.
        # Changer de modele plus tard = changer engine.CHAT_BASE_MODEL, sans re-uploader
        # de GGUF. L'embedding bge-m3 vient aussi du registre (deja le repli existant).
        eng = AssistantEngine.instance()
        eng._ensure_server()
        # 1) modele de discussion (~5 Go) puis moteur de recherche (~1,2 Go)
        eng.pull_model(CHAT_BASE_MODEL, progress=lambda f: self._emit(
            base, span * 0.70, f, "Téléchargement du modèle de discussion"))
        self._check_cancel()
        eng.pull_model(EMBED_MODEL, progress=lambda f: self._emit(
            base + span * 0.70, span * 0.22, f, "Téléchargement du moteur de recherche"))
        # 2) preparer les modeles (alias neoslice-assistant + embedding)
        self._progress("Préparation des modèles", base + span * 0.94)
        eng._ensure_model()          # cree l'alias neoslice-assistant FROM qwen3:8b
        eng._ensure_embed_model()    # prepare l'embedding (deja pulle ci-dessus)
        self._emit(base, span, 1.0, "Modèles prêts")

    def _install_kb(self, base: float, span: float) -> None:
        n = len(KB_INDEX_FILES)
        for i, fname in enumerate(KB_INDEX_FILES):
            self._download(f"{ASSET_BASE_URL}/{fname}", KB_INDEX_DIR / fname,
                           base + span * (i / n), span / n,
                           f"Base de connaissances ({i+1}/{n})")

    # ── Installation complete ────────────────────────────────────────────────
    def install(self) -> None:
        """Installe tout. Leve une exception en cas d'echec (a attraper cote UI)."""
        self._progress("Préparation...", 0.0)
        self._install_ollama(0.00, 0.40)     # 0 -> 40 %
        self._install_models(0.40, 0.45)     # 40 -> 85 %
        self._install_kb(0.85, 0.15)         # 85 -> 100 %
        INSTALL_MARKER.write_text(
            json.dumps({"model": MODEL_NAME, "embed_model": EMBED_MODEL,
                        "source": "github"}),
            encoding="utf-8")
        self._progress("Assistant IA installé.", 1.0)
        self._log("Installation terminée.")
