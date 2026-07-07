"""Orchestrateur autonome de la base de connaissances (a lancer et laisser tourner).

Fait TOUTE la chaine en sequence, dans un seul processus (aucune intervention) :
  1. Recolte phase 1 : les 12 wikis Wiki.js des marques (reprise auto).
  2. Indexation : vectorise tout data/kb (Bambu deja fait + nouvelles marques).
  3. Recolte phase 2 : sites a sitemap (Prusa, Voron, BTT, printed.boats, Tronxy,
     Eryone, Longer).
  4. Indexation finale : ajoute les pages de la phase 2.

Chaque etape est tolerante aux erreurs (un site qui echoue n'arrete pas le reste)
et reprenable (les pages/passages deja faits sont ignores). On peut relancer ce
script autant de fois qu'on veut : il repart la ou il s'etait arrete.

Usage : python tools/kb_run_all.py
"""
from __future__ import annotations
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kb_scrape import scrape
from tools.kb_harvest import SITES as WIKIJS_SITES
from tools.kb_crawl import crawl, SITES as CRAWL_SITES
from tools.kb_index import build as index_build, KB_ROOT


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def step_harvest_wikijs() -> None:
    log(f"=== PHASE 1 : recolte de {len(WIKIJS_SITES)} wikis Wiki.js ===")
    for s in WIKIJS_SITES:
        try:
            scrape(s["base"], s["out"], s["locale"])
        except Exception as e:
            log(f"  ECHEC {s['key']}: {str(e)[:120]}")


def step_crawl_sitemaps() -> None:
    log(f"=== PHASE 2 : crawl de {len(CRAWL_SITES)} sites a sitemap ===")
    for s in CRAWL_SITES:
        try:
            crawl(s)
        except Exception as e:
            log(f"  ECHEC {s['key']}: {str(e)[:120]}")


def step_index(tag: str) -> None:
    log(f"=== INDEXATION ({tag}) : vectorisation de tout data/kb ===")
    try:
        index_build(KB_ROOT)
    except Exception:
        log("  ECHEC indexation:\n" + traceback.format_exc()[:600])


def main() -> None:
    t0 = time.time()
    log("########## DEBUT recolte + indexation complete ##########")
    step_harvest_wikijs()
    step_index("apres phase 1")
    step_crawl_sitemaps()
    step_index("finale, apres phase 2")
    log(f"########## TERMINE en {(time.time()-t0)/3600:.1f} h ##########")


if __name__ == "__main__":
    main()
