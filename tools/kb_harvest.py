"""Pilote de recolte : enchaine l'aspiration de tous les wikis Wiki.js des marques.

Chaque site est traite via tools/kb_scrape.scrape() (reprise auto : les pages deja
telechargees sont ignorees). En cas d'echec sur un site, on passe au suivant. On
peut relancer autant de fois que necessaire, ca reprend ou ca s'etait arrete.

Usage :
  python tools/kb_harvest.py                 # tous les sites
  python tools/kb_harvest.py --only creality # un seul
  python tools/kb_harvest.py --limit 5       # test rapide (5 pages/site)
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kb_scrape import scrape

# Sites Wiki.js confirmes (acces GraphQL anonyme). locale = "en" (leur langue source).
SITES = [
    {"key": "creality",   "base": "https://wiki.creality.com",   "out": "creality_wiki",   "locale": "en"},
    {"key": "anycubic",   "base": "https://wiki.anycubic.com",   "out": "anycubic_wiki",   "locale": "en"},
    {"key": "elegoo",     "base": "https://wiki.elegoo.com",     "out": "elegoo_wiki",     "locale": "en"},
    {"key": "snapmaker",  "base": "https://wiki.snapmaker.com",  "out": "snapmaker_wiki",  "locale": "en"},
    {"key": "qidi",       "base": "https://wiki.qidi3d.com",     "out": "qidi_wiki",       "locale": "en"},
    {"key": "flashforge", "base": "https://wiki.flashforge.com", "out": "flashforge_wiki", "locale": "en"},
    {"key": "flsun",      "base": "https://wiki.flsun3d.com",    "out": "flsun_wiki",      "locale": "en"},
    {"key": "twotrees",   "base": "https://wiki.twotrees3d.com", "out": "twotrees_wiki",   "locale": "en"},
    {"key": "ratrig",     "base": "https://wiki.ratrig.com",     "out": "ratrig_wiki",     "locale": "en"},
    {"key": "sovol",      "base": "https://wiki.sovol3d.com",    "out": "sovol_wiki",      "locale": "en"},
    {"key": "artillery",  "base": "https://wiki.artillery3d.com","out": "artillery_wiki",  "locale": "en"},
    {"key": "kingroon",   "base": "https://wiki.kingroon.com",   "out": "kingroon_wiki",   "locale": "en"},
]


def main():
    args = sys.argv[1:]
    only = args[args.index("--only") + 1] if "--only" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    sites = [s for s in SITES if (only is None or s["key"] == only)]
    print(f"Recolte de {len(sites)} site(s) Wiki.js.\n", flush=True)
    summary = []
    for s in sites:
        print(f"===== {s['key'].upper()} ({s['base']}) =====", flush=True)
        try:
            r = scrape(s["base"], s["out"], s["locale"], limit)
            summary.append((s["key"], r))
        except Exception as e:
            print(f"  ECHEC site {s['key']}: {str(e)[:120]}", flush=True)
            summary.append((s["key"], {"fail": "site error"}))
        print("", flush=True)
    print("===== BILAN =====", flush=True)
    for key, r in summary:
        print(f"  {key:12} {r}", flush=True)


if __name__ == "__main__":
    main()
