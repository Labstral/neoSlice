"""Auto-mise-a-jour de la base de connaissances (RAG) d'Oen, SANS rebuild de l'app.

Principe : l'index (vecteurs + passages) est heberge comme asset de release GitHub
(le meme canal que l'installateur) et vit dans un dossier INSCRIPTIBLE
(`~/.neoslice/assistant/kb/index`). Un petit `kb_manifest.json` versionne la base :
Oen le lit au demarrage (en arriere-plan), compare a sa version locale, et propose
de telecharger uniquement ce qui a change.

Garanties (pense pour des milliers d'utilisateurs) :
  - 100% HORS-LIGNE-SAFE : toute erreur reseau => on garde la base actuelle, aucune
    exception ne remonte a l'UI depuis check().
  - INTEGRITE : chaque fichier est verifie par SHA-256 (+ taille) avant d'etre pose.
  - ATOMIQUE + ROLLBACK : telechargement en staging, verification COMPLETE, puis swap
    par os.replace (atomique, meme volume) ; en cas de pepin, restauration du backup.
  - INCREMENTAL : un fichier dont le SHA-256 local correspond deja au manifest n'est
    PAS retelecharge (permet le sharding : n'update que les shards modifies).
  - COMPATIBILITE : refuse un index construit avec un AUTRE modele d'embedding, ou qui
    exige une version d'app plus recente (champ min_app_version).

Format attendu de kb_manifest.json :
{
  "kb_version": "2026-08-01",          // identifiant de version (date ISO conseillee)
  "embed_model": "bge-m3",             // doit matcher EMBED_MODEL de l'app
  "min_app_version": "0.1.7",          // optionnel : app minimale requise
  "notes": "ajout wikis Prusa + Qidi", // optionnel : affiche a l'utilisateur
  "files": [                            // 1..N fichiers OU shards, chacun avec son hash
    {"name": "meta.json",    "sha256": "...", "size": 812},
    {"name": "chunks.jsonl", "sha256": "...", "size": 715000000},
    {"name": "vectors.npy",  "sha256": "...", "size": 1517000000}
  ]
}
Un "url" explicite par fichier est accepte (sinon on prend ASSET_BASE_URL/<name>).
"""
from __future__ import annotations
import os
import json
import hashlib
import shutil
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from core.assistant.engine import KB_INDEX_DIR, EMBED_MODEL

# Meme release GitHub que l'installateur (un seul canal a maintenir).
ASSET_BASE_URL = "https://github.com/labstral/neoslice-assets/releases/download/assistant-latest"
MANIFEST_URL = f"{ASSET_BASE_URL}/kb_manifest.json"

# Fichiers d'index par defaut si le manifest ne liste pas explicitement "files".
DEFAULT_FILES = ("meta.json", "chunks.jsonl", "vectors.npy")

ProgressCb = Callable[[str, float], None]
LogCb = Callable[[str], None]


def _noop(*_a, **_k):
    pass


def _app_version() -> str:
    try:
        from version import __version__
        return str(__version__)
    except Exception:
        return "0.0.0"


def _vtuple(v: str) -> tuple:
    """'0.1.7' -> (0, 1, 7) ; tolerant (parties non numeriques ignorees)."""
    out = []
    for part in str(v).split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out) or (0,)


def _sha256(path: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _files_of(manifest: dict) -> list[dict]:
    fs = manifest.get("files")
    if isinstance(fs, list) and fs:
        return fs
    return [{"name": n} for n in DEFAULT_FILES]


class KBUpdater:
    """Verifie et applique une mise a jour de la base d'Oen. Concu pour tourner dans
    un QThread (progress/log = callbacks). `index_dir` et `manifest_url` sont
    injectables pour les tests."""

    def __init__(self, progress: Optional[ProgressCb] = None, log: Optional[LogCb] = None,
                 index_dir: Optional[Path] = None, manifest_url: str = MANIFEST_URL,
                 base_url: str = ASSET_BASE_URL):
        self._progress = progress or _noop
        self._log = log or _noop
        self._index_dir = Path(index_dir) if index_dir else KB_INDEX_DIR
        self._manifest_url = manifest_url
        self._base_url = base_url
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _raise_if_cancel(self):
        if self._cancel:
            raise RuntimeError("Mise a jour annulee.")

    @property
    def _version_file(self) -> Path:
        return self._index_dir / "kb_version.json"

    # ── Lecture des versions ─────────────────────────────────────────────────
    def local_version(self) -> str:
        """Version de la base actuellement installee ('' si inconnue)."""
        for p, key in ((self._version_file, "kb_version"),
                       (self._index_dir / "meta.json", "kb_version")):
            try:
                if p.exists():
                    v = json.loads(p.read_text(encoding="utf-8")).get(key, "")
                    if v:
                        return str(v)
            except Exception:
                pass
        return ""

    def fetch_manifest(self, timeout: int = 15) -> Optional[dict]:
        """Recupere le manifest distant. None si indisponible (aucune exception)."""
        try:
            req = urllib.request.Request(self._manifest_url, headers={"User-Agent": "neoSlice"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            logger.info(f"[KB] manifest indisponible ({e}) -> base actuelle conservee")
            return None

    # ── Decision ──────────────────────────────────────────────────────────────
    def check(self) -> Optional[dict]:
        """Renvoie un descripteur de MAJ si une version compatible et plus recente
        existe, sinon None. HORS-LIGNE-SAFE (jamais d'exception)."""
        man = self.fetch_manifest()
        if not man:
            return None
        remote_v = str(man.get("kb_version", "")).strip()
        if not remote_v:
            return None
        local_v = self.local_version()
        if remote_v == local_v:
            self._log("Base d'Oen deja a jour.")
            return None
        # On ne "downgrade" jamais : si les deux versions se comparent, exiger remote > local.
        if local_v and _vtuple(remote_v) < _vtuple(local_v):
            return None
        # Compatibilite modele d'embedding : un index d'un autre modele est inutilisable.
        man_embed = man.get("embed_model", EMBED_MODEL)
        if man_embed != EMBED_MODEL:
            logger.warning(f"[KB] MAJ ignoree : index '{man_embed}' != app '{EMBED_MODEL}'")
            return None
        # Compatibilite version d'app.
        min_app = man.get("min_app_version")
        if min_app and _vtuple(_app_version()) < _vtuple(min_app):
            logger.warning(f"[KB] MAJ {remote_v} requiert l'app >= {min_app}")
            return {"incompatible_app": True, "min_app_version": min_app,
                    "kb_version": remote_v, "manifest": man}
        files = _files_of(man)
        total_size = sum(int(f.get("size", 0) or 0) for f in files)
        # Estimation de ce qui reste vraiment a telecharger (incremental).
        to_dl = 0
        for f in files:
            dest = self._index_dir / f["name"]
            want = f.get("sha256")
            if want and dest.exists():
                try:
                    if _sha256(dest) == want:
                        continue
                except Exception:
                    pass
            to_dl += int(f.get("size", 0) or 0)
        return {"kb_version": remote_v, "local_version": local_v, "manifest": man,
                "notes": man.get("notes", ""), "total_size": total_size,
                "download_size": to_dl}

    # ── Application ─────────────────────────────────────────────────────────────
    def _download(self, url: str, dest: Path, idx: int, n: int, name: str) -> str:
        """Telecharge url -> dest en streaming, renvoie le SHA-256 calcule a la volee."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        req = urllib.request.Request(url, headers={"User-Agent": "neoSlice"})
        with urllib.request.urlopen(req, timeout=120) as r:
            total = int(r.headers.get("Content-Length", 0) or 0)
            done = 0
            with open(dest, "wb") as fout:
                while True:
                    self._raise_if_cancel()
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fout.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    frac = (idx + (done / total if total else 0.5)) / n
                    self._progress(f"Telechargement de la base d'Oen ({idx+1}/{n})", frac)
        return h.hexdigest()

    def _commit(self, staged: dict[str, Optional[Path]]) -> None:
        """Remplace les fichiers d'index par ceux stages (os.replace atomique, meme
        volume). Sauvegarde l'ancien dans .backup et restaure en cas d'echec."""
        backup = self._index_dir / ".backup"
        shutil.rmtree(backup, ignore_errors=True)
        backup.mkdir(parents=True, exist_ok=True)
        replaced: list[str] = []
        try:
            for name, tmp in staged.items():
                if tmp is None:        # inchange -> rien a faire
                    continue
                dest = self._index_dir / name
                if dest.exists():
                    shutil.move(str(dest), str(backup / name))
                os.replace(str(tmp), str(dest))
                replaced.append(name)
            shutil.rmtree(backup, ignore_errors=True)
        except Exception:
            # Rollback : on remet les fichiers sauvegardes.
            for name in replaced:
                b = backup / name
                if b.exists():
                    os.replace(str(b), str(self._index_dir / name))
            shutil.rmtree(backup, ignore_errors=True)
            raise

    def update(self, info: dict) -> bool:
        """Applique la MAJ decrite par check(). Renvoie True si appliquee. En cas
        d'echec, l'index existant est CONSERVE intact (exception relayee a l'UI)."""
        if info.get("incompatible_app"):
            raise RuntimeError(
                f"Cette base necessite neoSlice >= {info.get('min_app_version')}. "
                f"Mets d'abord l'application a jour.")
        man = info["manifest"]
        files = _files_of(man)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        staging = self._index_dir / ".staging"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        n = len(files)
        staged: dict[str, Optional[Path]] = {}
        try:
            for i, f in enumerate(files):
                self._raise_if_cancel()
                name = f["name"]
                dest = self._index_dir / name
                want_sha = f.get("sha256")
                want_size = int(f.get("size", 0) or 0)
                # Incremental : fichier local deja conforme -> on le garde.
                if want_sha and dest.exists():
                    try:
                        if _sha256(dest) == want_sha:
                            staged[name] = None
                            self._log(f"{name} : inchange (saute).")
                            self._progress(f"Base d'Oen ({i+1}/{n})", (i + 1) / n)
                            continue
                    except Exception:
                        pass
                url = f.get("url") or f"{self._base_url}/{name}"
                tmp = staging / name
                got_sha = self._download(url, tmp, i, n, name)
                if want_sha and got_sha != want_sha:
                    raise RuntimeError(f"Integrite invalide pour {name} (SHA-256).")
                if want_size and tmp.stat().st_size != want_size:
                    raise RuntimeError(f"Taille invalide pour {name}.")
                staged[name] = tmp
                self._log(f"{name} : telecharge et verifie.")
            # Tout est verifie -> swap atomique.
            self._raise_if_cancel()
            self._progress("Installation de la nouvelle base...", 0.98)
            self._commit(staged)
            self._version_file.write_text(
                json.dumps({"kb_version": info["kb_version"], "embed_model": EMBED_MODEL},
                           ensure_ascii=False), encoding="utf-8")
            self._invalidate_rag()
            shutil.rmtree(staging, ignore_errors=True)
            self._progress("Base d'Oen mise a jour.", 1.0)
            self._log(f"Base de connaissances a jour (version {info['kb_version']}).")
            return True
        except Exception as e:
            shutil.rmtree(staging, ignore_errors=True)
            logger.error(f"[KB] mise a jour echouee, base actuelle conservee : {e}")
            raise

    @staticmethod
    def _invalidate_rag() -> None:
        """Vide le cache en memoire du RAG pour que le nouvel index soit relu."""
        try:
            from core.assistant import rag
            rag._loaded = False
            rag._shards = None
            rag._chunks = None
            rag._meta_cache = None
        except Exception:
            pass


def available_update() -> Optional[dict]:
    """Helper simple : renvoie le descripteur de MAJ dispo, ou None. Hors-ligne-safe.
    A appeler en arriere-plan (jamais sur le thread UI : fait un appel reseau)."""
    try:
        return KBUpdater().check()
    except Exception:
        return None
