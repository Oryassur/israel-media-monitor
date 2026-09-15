"""One-off repair (2026-09-15): two topic-hub links were ingested as headlines
before extract.SKIP_HREF_PAT learned to skip /tag/ and /topic/ paths.

  euronews  "US-Israel attack on Iran 2026"   /tag/…    rank 1 (w10) in every run 09-09..09-15
  smh       "Israeli-Palestinian conflict"    /topic/…  rank 9–20 in 32 of 215 runs

The items are deleted from data/items and data/allitems, and their weight is
taken out of the per-run snapshot rows (israel_items, israel_weight,
attention_share, mean_sentiment, w_0 — both were scored 0) and intl rows
(intl_w, topics.israel-gaza). Rows whose per-run weight cannot be inferred are
left alone (six SMH runs, ≤3 weight each).

Run from the repo root:  python scripts/repair_hub_links_2026-09-15.py
"""
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.common import read_jsonl, write_jsonl  # noqa: E402
from pipeline.store import SNAP_FIELDS  # noqa: E402

MONTH = "2026-09"
ITEMS = ROOT / "data" / "items" / f"{MONTH}.jsonl"
ALLITEMS = ROOT / "data" / "allitems" / f"{MONTH}.jsonl"
SNAPS = ROOT / "data" / "snapshots" / f"{MONTH}.csv"
INTL = ROOT / "data" / "intl" / f"{MONTH}.jsonl"

BAD_IDS = ("f56b08275e3cf77b", "769e5d502042b62e")  # euronews tag, smh topic


def snap_weight(src, row):
    """Weight the hub link carried in this run, or None when it cannot be told."""
    n, w = int(row["israel_items"]), int(float(row["israel_weight"]))
    if n == 0:
        return None
    if src == "euronews":
        return 10  # rank 1 in every run (214 runs: 1 item/w10; 20 runs: 10+5 or 10+1)
    # smh: the topic link sat in the top-20 only some of the time
    if (n, w) == (2, 2):
        return 1
    if (n, w) == (2, 6):
        return 3
    return None  # (2,4) and (1,1): ambiguous, leave


def main():
    # presence window of each link = the record's first/last seen (hourly runs
    # after the parser fix stop extending it)
    BAD = {}
    for r in read_jsonl(ITEMS):
        if r["id"] in BAD_IDS:
            BAD[r["id"]] = {"source": r["source"], "lo": r["first_seen"], "hi": r["last_seen"]}
    assert len(BAD) == len(BAD_IDS), "already repaired?"
    print("windows", BAD)
    removed = {}
    for path in (ITEMS, ALLITEMS):
        rows = read_jsonl(path)
        keep = [r for r in rows if r["id"] not in BAD]
        removed[path.parent.name] = len(rows) - len(keep)
        write_jsonl(path, keep)

    # snapshots
    with open(SNAPS, newline="") as f:
        snaps = list(csv.DictReader(f))
    fixed = {"euronews": 0, "smh": 0}
    per_ts = {}  # (source, ts) -> weight removed, reused for intl rows
    for r in snaps:
        for bad in BAD.values():
            src = bad["source"]
            if r["source"] != src or r["fetch_ok"] != "1" or not (bad["lo"] <= r["ts"] <= bad["hi"]):
                continue
            w = snap_weight(src, r)
            if w is None:
                continue
            iw = int(float(r["israel_weight"]))
            wu = int(float(r["w_u"] or 0))
            scored = iw - wu
            old_mean = float(r["mean_sentiment"]) if r["mean_sentiment"] not in ("", None) else None
            r["israel_items"] = str(int(r["israel_items"]) - 1)
            r["israel_weight"] = str(iw - w)
            r["w_0"] = str(int(float(r["w_0"])) - w)
            r["attention_share"] = f"{(iw - w) / float(r['total_weight']):.5f}"
            if old_mean is not None and scored - w > 0:
                r["mean_sentiment"] = f"{max(-2.0, min(2.0, old_mean * scored / (scored - w))):.2f}"
            elif scored - w <= 0:
                r["mean_sentiment"] = ""
            per_ts[(src, r["ts"])] = w
            fixed[src] += 1
    with open(SNAPS, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=SNAP_FIELDS)
        wr.writeheader()
        wr.writerows(snaps)

    # intl rows: same weight out of intl_w and israel-gaza. Approximate (backfilled)
    # SMH rows carried the link at best_weight (3) for every run in its window.
    intl = read_jsonl(INTL)
    ifixed = {"euronews": 0, "smh": 0}
    for r in intl:
        for bad in BAD.values():
            src = bad["source"]
            if r["source"] != src or not (bad["lo"] <= r["ts"] <= bad["hi"]):
                continue
            w = 10 if src == "euronews" else (3 if r.get("approx") else per_ts.get((src, r["ts"])))
            if not w:
                continue
            ig = r["topics"].get("israel-gaza", 0)
            w = min(w, ig)
            if w <= 0:
                continue
            r["intl_w"] -= w
            r["topics"]["israel-gaza"] = ig - w
            if r["topics"]["israel-gaza"] == 0:
                del r["topics"]["israel-gaza"]
            ifixed[src] += 1
    write_jsonl(INTL, intl)
    print("removed", removed, "snapshot rows fixed", fixed, "intl rows fixed", ifixed)


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
