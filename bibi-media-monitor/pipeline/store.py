"""Persistence: monthly-partitioned item files and snapshot CSVs.

- data/items/YYYY-MM.jsonl : one row per unique Netanyahu-candidate headline
  (partitioned by first_seen month; rewritten when rows update)
- data/snapshots/YYYY-MM.csv : one row per source per hourly run (append-only)
"""
import csv
from collections import defaultdict

from .common import DATA, month_key, read_jsonl, write_jsonl

ITEMS_DIR = DATA / "items"
SNAPS_DIR = DATA / "snapshots"

SNAP_FIELDS = [
    "ts", "source", "fetch_ok", "total_items", "total_weight",
    "topic_items", "topic_weight", "attention_share", "mean_sentiment",
]


def load_recent_items(months):
    """Return {id: item} for the given YYYY-MM partitions (e.g. current + previous)."""
    idx = {}
    for m in months:
        for row in read_jsonl(ITEMS_DIR / f"{m}.jsonl"):
            idx[row["id"]] = row
    return idx


def save_items(index):
    """Write the item index back to its monthly partitions."""
    by_month = defaultdict(list)
    for row in index.values():
        by_month[month_key(row["first_seen"])].append(row)
    for m, rows in by_month.items():
        rows.sort(key=lambda r: r["first_seen"])
        write_jsonl(ITEMS_DIR / f"{m}.jsonl", rows)


def append_snapshots(ts, rows):
    path = SNAPS_DIR / f"{month_key(ts)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SNAP_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def read_all_snapshots():
    rows = []
    if not SNAPS_DIR.exists():
        return rows
    for path in sorted(SNAPS_DIR.glob("*.csv")):
        with open(path, newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def load_all_items():
    out = []
    if not ITEMS_DIR.exists():
        return out
    for path in sorted(ITEMS_DIR.glob("*.jsonl")):
        out.extend(read_jsonl(path))
    return out
