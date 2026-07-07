"""Aspirateur de wikis Wiki.js (build-time) pour la base de connaissances de l'IA.

Wiki.js rend le contenu cote client et verrouille son API de contenu (pages.single),
mais pages.list est accessible anonymement. On liste donc les pages via GraphQL, puis
on rend chacune dans un navigateur headless (Playwright) et on extrait le conteneur
.contents converti en Markdown propre. Fonctionne pour tout site Wiki.js (Bambu,
Creality, Anycubic, Elegoo, Qidi, Snapmaker, Flashforge, FLSun, TwoTrees, RatRig,
Sovol, Artillery, Kingroon...).

Usage :
  python tools/kb_scrape.py                                   # Bambu FR (defaut)
  python tools/kb_scrape.py --base https://wiki.creality.com --out creality_wiki --locale en
  python tools/kb_scrape.py --limit 5                         # test rapide

Reprise automatique : les pages deja telechargees sont ignorees. Relancable.
Sortie : data/kb/<out>/<locale>/<chemin>.md (front-matter url/path/title).
"""
from __future__ import annotations
import sys
import re
import json
import time
import ssl
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from markdownify import markdownify as _md

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DEFAULT_BASE = "https://wiki.bambulab.com"
DEFAULT_OUT = "bambu_wiki"
KB_ROOT = Path(__file__).resolve().parent.parent / "data" / "kb"


def get_page_list(base: str, locale: str) -> list[dict]:
    """Liste complete des pages (path, title) via l'API GraphQL publique Wiki.js."""
    q = '{pages{list(locale:"%s"){path title}}}' % locale
    req = urllib.request.Request(
        f"{base}/graphql", data=json.dumps({"query": q}).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/json",
                 "Accept": "application/json"})
    data = json.loads(urllib.request.urlopen(
        req, timeout=40, context=ssl.create_default_context()).read())
    return data["data"]["pages"]["list"]


def _safe_path(out_root: Path, locale: str, path: str) -> Path:
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    parts = [p.replace(":", "-") for p in parts] or ["index"]
    return out_root / locale / (Path(*parts).as_posix() + ".md")


def scrape(base: str = DEFAULT_BASE, out: str = DEFAULT_OUT,
           locale: str = "fr", limit: int | None = None) -> dict:
    out_root = KB_ROOT / out
    pages = get_page_list(base, locale)
    if limit:
        pages = pages[:limit]
    total = len(pages)
    print(f"[{out}] {total} pages {locale.upper()} a traiter (reprise auto).", flush=True)

    done = skipped = failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        page.set_default_timeout(40000)
        for i, p in enumerate(pages):
            path = p.get("path", "")
            title = (p.get("title") or "").strip()
            out_file = _safe_path(out_root, locale, path)
            if out_file.exists():
                skipped += 1
                continue
            url = f"{base}/{locale}/{path}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_selector(".contents", timeout=12000)
                el = page.query_selector(".contents")
                html = el.inner_html() if el else ""
                body = _md(html, heading_style="ATX",
                           strip=["script", "style"]).strip() if html else ""
                body = re.sub(r"\[¶\]\(#[^)]*\)\s*", "", body)
                body = re.sub(r"\n{3,}", "\n\n", body)
                out_file.parent.mkdir(parents=True, exist_ok=True)
                front = (f"---\nurl: {url}\npath: {path}\n"
                         f"title: {title.replace(chr(10), ' ')}\n---\n\n# {title}\n\n")
                out_file.write_text(front + body + "\n", encoding="utf-8")
                done += 1
            except Exception as e:
                failed += 1
                print(f"  FAIL {path}: {str(e)[:90]}", flush=True)
            if (i + 1) % 25 == 0 or (i + 1) == total:
                print(f"  [{out} {i+1}/{total}] ok={done} skip={skipped} fail={failed}", flush=True)
            time.sleep(0.2)
        browser.close()
    print(f"TERMINE [{out}] {locale}: ok={done} skip={skipped} fail={failed} / {total}", flush=True)
    return {"out": out, "total": total, "ok": done, "skip": skipped, "fail": failed}


def main():
    args = sys.argv[1:]
    base, out, locale, limit = DEFAULT_BASE, DEFAULT_OUT, "fr", None
    if "--base" in args:
        base = args[args.index("--base") + 1]
    if "--out" in args:
        out = args[args.index("--out") + 1]
    if "--locale" in args:
        locale = args[args.index("--locale") + 1]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    scrape(base, out, locale, limit)


if __name__ == "__main__":
    main()
