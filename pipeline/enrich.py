"""Article-page enrichment: og:image + description for prominent related items.

Best-effort pass (same posture as intl): per-item try/except, a cap on fetches
per run, a wall-clock budget, and a per-host politeness gap. Image URLs are
hotlinked, never downloaded. Fields written on item records:

  img    str|None   absolute https image URL (None if none found)
  desc   str|None   article description, <=300 chars (None if none / == headline)
  enr    ISO ts     last attempt
  enr_n  int        attempts so far (gives up after ENRICH_MAX_ATTEMPTS)

Run:  python -m pipeline.enrich URL [URL ...]   dry run: print (img, desc) per URL
      python -m pipeline.enrich --pending       print the current queue, no fetches
"""
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .common import (ENRICH_BUDGET_S, ENRICH_FETCH_TIMEOUT, ENRICH_HOST_GAP_S,
                     ENRICH_MAX_ATTEMPTS, ENRICH_MAX_PER_RUN, ENRICH_MIN_WEIGHT,
                     SCORE_RETRY_WINDOW_H)
from .extract import fetch_html

HEAD_CAP = 300_000  # bytes of HTML we bother parsing
IMG_KEYS = ("og:image", "og:image:url", "og:image:secure_url",
            "twitter:image", "twitter:image:src")
DESC_KEYS = ("og:description", "description", "twitter:description")
MIN_DESC_LEN = 20
MAX_DESC_LEN = 300


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _meta_map(soup):
    """{key: content} over <meta property=...|name=...>, first occurrence wins."""
    out = {}
    for m in soup.find_all("meta"):
        key = (m.get("property") or m.get("name") or "").strip().lower()
        val = (m.get("content") or "").strip()
        if key and val and key not in out:
            out[key] = val
    return out


def _clean_image(v, base_url):
    if not v or v.startswith("data:") or len(v) > 500:
        return None
    u = urljoin(base_url, v.strip())
    if u.startswith("http://"):
        u = "https://" + u[7:]  # Pages is https; http images would be mixed content
    if not u.startswith("https://"):
        return None
    return u


def extract_meta(html: str, base_url: str):
    """(img, desc) from an article page's <head>. Pure; no network."""
    end = html.find("</head>")
    head = html[:end] if end != -1 else html[:HEAD_CAP]
    soup = BeautifulSoup(head[:HEAD_CAP], "html.parser")
    metas = _meta_map(soup)

    img = None
    for k in IMG_KEYS:
        img = _clean_image(metas.get(k), base_url)
        if img:
            break
    if not img:
        link = soup.find("link", rel=lambda r: r and "image_src" in r)
        if link:
            img = _clean_image(link.get("href"), base_url)

    desc = None
    for k in DESC_KEYS:
        d = re.sub(r"\s+", " ", metas.get(k, "")).strip()
        if len(d) >= MIN_DESC_LEN:
            desc = d[:MAX_DESC_LEN].rstrip()
            break
    return img, desc


def pending_enrichment(items_idx: dict, now: datetime):
    """Items that qualify for a fetch this run, most prominent + newest first."""
    cutoff = (now - timedelta(hours=SCORE_RETRY_WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for r in items_idx.values():
        if r.get("related") is not True or not r.get("url"):
            continue
        if r.get("best_weight", 0) < ENRICH_MIN_WEIGHT:
            continue
        if r.get("img") or r.get("desc"):
            continue
        n = r.get("enr_n", 0)
        if n >= ENRICH_MAX_ATTEMPTS:
            continue
        if n > 0 and r["first_seen"] < cutoff:
            continue  # first attempt is unconditional; retries only while fresh
        out.append(r)
    out.sort(key=lambda r: (r["best_weight"], r["first_seen"]), reverse=True)
    return out[:ENRICH_MAX_PER_RUN]


def enrich_items(items_idx: dict, ts: str, log=print, now=None):
    """Fetch article pages for the pending queue. Returns (succeeded, attempted)."""
    now = now or datetime.now(timezone.utc)
    queue = pending_enrichment(items_idx, now)
    if not queue:
        return 0, 0
    t0 = time.monotonic()
    last_hit = {}
    ok = attempted = 0
    for r in queue:
        if time.monotonic() - t0 > ENRICH_BUDGET_S:
            log(f"enrich: budget exhausted, {len(queue) - attempted} deferred to next run")
            break
        host = urlparse(r["url"]).netloc
        wait = ENRICH_HOST_GAP_S - (time.monotonic() - last_hit.get(host, -1e9))
        if wait > 0:
            time.sleep(wait)
        last_hit[host] = time.monotonic()
        attempted += 1
        r["enr"] = ts
        r["enr_n"] = r.get("enr_n", 0) + 1
        try:
            html = fetch_html(r["url"], timeout=ENRICH_FETCH_TIMEOUT)
            img, desc = extract_meta(html, r["url"])
        except Exception as e:  # noqa: BLE001 — one bad page must not stop the pass
            log(f"enrich: {r['source']} {r['url'][:90]}: {e}")
            continue
        if desc and _norm(desc) == _norm(r.get("headline")):
            desc = None
        r["img"] = img
        r["desc"] = desc
        if img or desc:
            ok += 1
    return ok, attempted


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--pending":
        from .common import month_key
        from .store import load_recent_items
        now = datetime.now(timezone.utc)
        months = [month_key(now.strftime("%Y-%m")),
                  month_key((now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))]
        q = pending_enrichment(load_recent_items(months), now)
        print(f"{len(q)} items pending enrichment (cap {ENRICH_MAX_PER_RUN})")
        for r in q[:10]:
            print(f"  w={r['best_weight']} n={r.get('enr_n', 0)} {r['source']:12} {r['url'][:90]}")
        sys.exit(0)
    if not args:
        print(__doc__)
        sys.exit(2)
    for url in args:
        try:
            img, desc = extract_meta(fetch_html(url, timeout=ENRICH_FETCH_TIMEOUT), url)
            print(f"{url}\n  img:  {img}\n  desc: {desc}")
        except Exception as e:  # noqa: BLE001
            print(f"{url}\n  ERROR {e}")
