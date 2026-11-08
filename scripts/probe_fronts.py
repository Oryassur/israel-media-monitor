#!/usr/bin/env python3
"""Probe candidate homepages with the pipeline's own fetcher and extractor.

    python scripts/probe_fronts.py URL [URL ...]           # plain HTTP, like the hourly run
    python scripts/probe_fronts.py --render URL [URL ...]  # headless Chromium (pipeline/render.py)
    python scripts/probe_fronts.py --sources NAME [NAME ...]   # entries of config/sources.yaml

Prints one line per front: HTTP status, whether it looks walled, bytes, the number
of headlines extract_items finds, and the first three. Run it from a GitHub Actions
runner (workflow "probe-fronts") before a new source enters aggregates: runner IPs
are refused more often than residential ones.
"""
import argparse
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from pipeline.common import load_sources  # noqa: E402
from pipeline.extract import UA, UA_MOBILE, extract_items  # noqa: E402

WALL = re.compile(r"just a moment|enable javascript and cookies|access denied|datadome|captcha|"
                  r"verify you are human|attention required|verifying device|security verification", re.I)


def probe(url, render=False, selector=None, skip=None, lead=None, site=None, headline=None, ua=None):
    if render:
        from pipeline import render as rnd
        try:
            html = rnd.render_html(url)
            status = 200
        except rnd.RobotsDisallowed:
            return f"{url[:48]:48} ROBOTS-DISALLOW"
        except Exception as e:  # noqa: BLE001
            return f"{url[:48]:48} ERR {type(e).__name__} {str(e)[:60]}"
    else:
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": UA_MOBILE if ua == "mobile" else UA,
                                                       "Accept": "text/html,application/xhtml+xml"})
        except requests.RequestException as e:
            return f"{url[:48]:48} ERR {type(e).__name__}"
        status, html = r.status_code, r.text
    wall = "WALL?" if status in (401, 402, 403, 429, 503) or (WALL.search(html[:20000]) and len(html) < 80000) else ""
    items = extract_items(html, url, selector, skip, lead, site, headline) if status == 200 else []
    sample = " || ".join(it["headline"][:50] for it in items[:3])
    return f"{url[:48]:48} {status} {wall:5} {len(html):>8}b {len(items):>3} headlines  {sample}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+", help="URLs, or source names with --sources")
    ap.add_argument("--render", action="store_true", help="load with headless Chromium")
    ap.add_argument("--sources", action="store_true", help="targets are names from config/sources.yaml")
    a = ap.parse_args()
    if a.sources:
        by_name = {s["name"]: s for s in load_sources()}
        for n in a.targets:
            s = by_name[n]
            print(probe(s["url"], a.render or s.get("render") == "browser", s.get("selector"), s.get("skip"),
                        s.get("lead"), s.get("site_hook"), s.get("headline"), s.get("ua")), flush=True)
    else:
        for u in a.targets:
            print(probe(u, a.render), flush=True)
    if a.render:
        from pipeline import render as rnd
        rnd.close()


if __name__ == "__main__":
    main()
