"""Parser-health audit: which ingested "headlines" look like page chrome
rather than stories? Reads data/allitems (every top-20 headline, all outlets)
and data/items (Israel-related, with URLs) and prints, per outlet, the records
that trip any of these signals:

  stale     on the homepage for >= STALE_DAYS continuously (nav links, hubs, promos)
  hub-url   related items whose URL looks like a tag / topic / section index page
  short     headline of <= SHORT_WORDS words (labels, not sentences)
  no-verb   title-case noun phrases with no lowercase function word ("Israeli-Palestinian conflict")

plus a per-outlet summary: total headlines, how many stale, and the longest
stay at rank 1 — an outlet whose rank-1 slot never changes has a parser problem.

Run from the repo root:  python scripts/audit_headlines.py [--days 3] [--source euronews]
"""
import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.store import load_all_allitems, load_all_items  # noqa: E402

HUB_URL = re.compile(r"/(tags?|topics?|themes?|thema|themen|sujets?|temas?|temi|dossiers?|"
                     r"category|categories|rubrique|rubriques|section|sections|author|authors|"
                     r"autor|auteur|firma|live-blog|liveblog)(/|$)", re.I)
SHORT_WORDS = 4
FUNCTION_WORDS = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "as", "at", "by", "with",
                  "is", "are", "was", "were", "has", "have", "will", "says", "over", "after", "from",
                  "le", "la", "les", "de", "des", "du", "et", "en", "un", "une", "der", "die", "das",
                  "und", "im", "am", "zu", "von", "mit", "il", "lo", "gli", "di", "e", "che", "el",
                  "los", "las", "y", "del", "con", "por"}


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def signals(r, stale_days, url=None):
    out = []
    days = (ts(r["last_seen"]) - ts(r["first_seen"])).total_seconds() / 86400
    if days >= stale_days:
        out.append(f"stale {days:.1f}d")
    if url and HUB_URL.search(url):
        out.append("hub-url")
    words = r["headline"].split()
    if len(words) <= SHORT_WORDS:
        out.append("short")
    elif not any(w.lower().strip(",.:;'\"“”’") in FUNCTION_WORDS for w in words) and len(words) <= 7:
        out.append("no-verb")
    return out, days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=3, help="stale threshold in days (default 3)")
    ap.add_argument("--source", help="only this outlet")
    ap.add_argument("--all", action="store_true", help="list short/no-verb hits too (noisy)")
    args = ap.parse_args()

    urls = {r["id"]: r["url"] for r in load_all_items()}
    allitems = load_all_allitems().values()
    by_src = defaultdict(list)
    for r in allitems:
        if args.source and r["source"] != args.source:
            continue
        by_src[r["source"]].append(r)

    print(f"{'outlet':14} {'headlines':>9} {'stale':>5} {'top-1 longest':>14}  worst rank-1 headline")
    flagged = []
    for src in sorted(by_src):
        rows = by_src[src]
        stale = 0
        top1 = (0, "")
        for r in rows:
            sig, days = signals(r, args.days, urls.get(r["id"]))
            if any(s.startswith("stale") for s in sig):
                stale += 1
            if r.get("best_rank") == 1 and days > top1[0]:
                top1 = (days, r["headline"])
            strong = [s for s in sig if s.startswith("stale") or s == "hub-url"]
            if strong or (args.all and sig):
                flagged.append((src, sig, r, urls.get(r["id"])))
        print(f"{src:14} {len(rows):9d} {stale:5d} {top1[0]:13.1f}d  {top1[1][:60]}")

    print("\nflagged records (stale / hub-url" + (" / short / no-verb" if args.all else "") + "):")
    for src, sig, r, url in sorted(flagged, key=lambda t: (t[0], -(t[2].get("best_weight") or 0))):
        rel = "ISRAEL" if r["id"] in urls else "      "
        print(f"  {src:12} {rel} r{r.get('best_rank') or '?':>3} w{r.get('best_weight') or 0:>2} "
              f"{r['first_seen'][:10]}→{r['last_seen'][:10]} [{', '.join(sig)}] {r['headline'][:70]}"
              + (f"\n{'':36}{url[:100]}" if url else ""))


if __name__ == "__main__":
    main()
