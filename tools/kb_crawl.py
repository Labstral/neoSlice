"""Crawler generique (via sitemap) pour les sites de doc non-Wiki.js.

Pour les plateformes qui exposent un sitemap.xml (MkDocs, Zendesk, Shopify, Prusa,
MediaWiki...), on enumere les URLs, on rend chaque page (Playwright) et on extrait
le bloc de contenu principal (heuristique multi-selecteurs : on garde le conteneur
qui a le plus de texte), converti en Markdown propre.

Usage :
  python tools/kb_crawl.py --only prusa --limit 5
  python tools/kb_crawl.py                # tous les sites phase 2 sitemap

Reprise auto (pages deja telechargees ignorees). Sortie : data/kb/<out>/<...>.md
"""
from __future__ import annotations
import sys
import re
import ssl
import time
import hashlib
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from markdownify import markdownify as _md

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
KB_ROOT = ROOT / "data" / "kb"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_CTX = ssl.create_default_context()

# Conteneurs de contenu principal, par ordre de preference (on garde le + long).
MAIN_SELECTORS = [
    "article", "main", '[role="main"]', ".md-content", ".markdown-body",
    ".article-body", ".article__body", ".kb-article-body", ".content__body",
    ".knowledge-article", "#main-content", "#content", ".content", ".post-content",
    ".entry-content", ".page-content",
]

# Sites phase 2 disposant d'un sitemap.xml (valide par sondage).
SITES = [
    {"key": "prusa",      "out": "prusa_help",   "sitemap": "https://help.prusa3d.com/sitemap.xml",
     "host": "help.prusa3d.com",   "must": ["/article/", "/en/"]},
    {"key": "voronwiki",  "out": "voron_wiki",   "sitemap": "https://voron3d.wiki/sitemap.xml",
     "host": "voron3d.wiki",       "must": []},
    {"key": "btt",        "out": "btt_wiki",     "sitemap": "https://global.bttwiki.com/sitemap.xml",
     "host": "global.bttwiki.com", "must": []},
    {"key": "printedboats", "out": "printedboats_wiki", "sitemap": "https://wiki.printed.boats/sitemap.xml",
     "host": "wiki.printed.boats", "must": []},
    {"key": "tronxy",     "out": "tronxy_support", "sitemap": "https://www.tronxy3d.com/sitemap.xml",
     "host": "www.tronxy3d.com",   "must": ["/blogs/", "/pages/", "/apps/help"]},
    {"key": "eryone",     "out": "eryone_support", "sitemap": "https://www.eryone.com/sitemap.xml",
     "host": "www.eryone.com",     "must": ["/news/", "/product/"]},
    {"key": "longer",     "out": "longer_support", "sitemap": "https://www.longer3d.com/sitemap.xml",
     "host": "www.longer3d.com",   "must": ["/blogs/", "/pages/"]},
]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=40, context=_CTX).read()


def collect_urls(sitemap: str, host: str, must: list[str], seen=None, depth=0) -> list[str]:
    """Enumere les URLs d'un sitemap (suit les sitemapindex). Filtre par host et,
    si `must` est non vide, ne garde que les URLs contenant un de ces fragments."""
    if seen is None:
        seen = set()
    if sitemap in seen or depth > 4:
        return []
    seen.add(sitemap)
    try:
        xml = _fetch(sitemap).decode("utf-8", "replace")
    except Exception as e:
        print(f"  sitemap KO {sitemap}: {str(e)[:70]}", flush=True)
        return []
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.IGNORECASE | re.DOTALL)
    urls = []
    for loc in locs:
        loc = loc.strip()
        if loc.endswith(".xml") or "sitemap" in loc.lower().rsplit("/", 1)[-1]:
            urls += collect_urls(loc, host, must, seen, depth + 1)
        else:
            if host in loc and (not must or any(m in loc for m in must)):
                urls.append(loc)
    return urls


def _safe_path(out_root: Path, url: str) -> Path:
    p = re.sub(r"^https?://", "", url).split("?")[0].split("#")[0]
    parts = [seg for seg in p.split("/") if seg not in ("", ".", "..")]
    parts = [re.sub(r"[^\w\-.]", "-", seg)[:80] for seg in parts] or ["index"]
    rel = Path(*parts)
    if not rel.suffix or rel.suffix.lower() not in (".md",):
        rel = rel.with_suffix(rel.suffix + ".md") if rel.suffix else Path(str(rel) + ".md")
    # Chemin trop long -> hash
    if len(rel.as_posix()) > 180:
        h = hashlib.md5(url.encode()).hexdigest()[:10]
        rel = Path(parts[0]) / f"{h}.md"
    return out_root / rel


def extract_main_html(page) -> str:
    best_html, best_len = "", 0
    for sel in MAIN_SELECTORS:
        try:
            el = page.query_selector(sel)
        except Exception:
            el = None
        if not el:
            continue
        try:
            t = el.inner_text()
        except Exception:
            continue
        if len(t) > best_len:
            best_len = len(t)
            best_html = el.inner_html()
    if best_len < 200:
        el = page.query_selector("body")
        best_html = el.inner_html() if el else best_html
    return best_html


def crawl(site: dict, limit: int | None = None) -> dict:
    out_root = KB_ROOT / site["out"]
    print(f"[{site['key']}] enumeration du sitemap...", flush=True)
    urls = collect_urls(site["sitemap"], site["host"], site.get("must", []))
    # dedup en gardant l'ordre
    urls = list(dict.fromkeys(urls))
    if limit:
        urls = urls[:limit]
    total = len(urls)
    print(f"[{site['key']}] {total} URLs a traiter (reprise auto).", flush=True)
    done = skipped = failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        page.set_default_timeout(35000)
        for i, url in enumerate(urls):
            out_file = _safe_path(out_root, url)
            if out_file.exists():
                skipped += 1
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=35000)
                time.sleep(0.4)
                title = (page.title() or "").strip()
                html = extract_main_html(page)
                body = _md(html, heading_style="ATX", strip=["script", "style"]).strip() if html else ""
                body = re.sub(r"\n{3,}", "\n\n", body)
                if len(body) < 80:
                    failed += 1
                    continue
                out_file.parent.mkdir(parents=True, exist_ok=True)
                front = f"---\nurl: {url}\ntitle: {title.replace(chr(10),' ')}\n---\n\n# {title}\n\n"
                out_file.write_text(front + body + "\n", encoding="utf-8")
                done += 1
            except Exception as e:
                failed += 1
                print(f"  FAIL {url[:80]}: {str(e)[:60]}", flush=True)
            if (i + 1) % 25 == 0 or (i + 1) == total:
                print(f"  [{site['key']} {i+1}/{total}] ok={done} skip={skipped} fail={failed}", flush=True)
            time.sleep(0.2)
        browser.close()
    print(f"TERMINE [{site['key']}]: ok={done} skip={skipped} fail={failed} / {total}", flush=True)
    return {"key": site["key"], "total": total, "ok": done, "skip": skipped, "fail": failed}


def main():
    args = sys.argv[1:]
    only = args[args.index("--only") + 1] if "--only" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    sites = [s for s in SITES if (only is None or s["key"] == only)]
    summary = []
    for s in sites:
        print(f"===== {s['key'].upper()} =====", flush=True)
        try:
            summary.append(crawl(s, limit))
        except Exception as e:
            print(f"  ECHEC {s['key']}: {str(e)[:100]}", flush=True)
    print("===== BILAN =====", flush=True)
    for r in summary:
        print(f"  {r}", flush=True)


if __name__ == "__main__":
    main()
