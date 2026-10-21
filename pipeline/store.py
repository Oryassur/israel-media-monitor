"""Persistence: monthly-partitioned item files and snapshot CSVs.

- data/items/YYYY-MM.jsonl : one row per unique Israel-candidate headline
  (partitioned by first_seen month; rewritten when rows update)
- data/snapshots/YYYY-MM.csv : one row per source per hourly run (append-only)
- data/stories/YYYY-MM.jsonl : story cluster registry (partitioned/rewritten
  like items; rows never hold item lists — items point at stories)
- data/allitems/YYYY-MM.jsonl : every top-20 headline, Israel-related or not,
  for the international benchmark (partitioned/rewritten like items)
- data/intl/YYYY-MM.jsonl : international-coverage aggregates, one row per
  source per run (append-only)
- data/runs/YYYY-MM.jsonl : each run's ranked top-20, one row per source per
  run (append-only, pruned to RUN_RETENTION_DAYS)
"""
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

from .common import DATA, item_id, month_key, read_jsonl, write_jsonl

ITEMS_DIR = DATA / "items"
SNAPS_DIR = DATA / "snapshots"
STORIES_DIR = DATA / "stories"
ALLITEMS_DIR = DATA / "allitems"
INTL_DIR = DATA / "intl"
RUNS_DIR = DATA / "runs"

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Ranked run archive. Everything else in data/ keeps aggregates or per-item
# windows (first_seen/last_seen), so the per-run ORDER used to be lost the
# moment a run ended — which is why every past repair of a parser break had to
# approximate the rows it rewrote (`approx`). One row per (run, source) holds
# the item ids of ranks 1..20 in order; headline and URL for an id live in
# data/allitems and data/items. ~30 rows/run, ~22k rows/month.
RUN_FIELDS = ["ts", "source", "ids"]
RUN_RETENTION_DAYS = 90  # pruned on write, so the store cannot grow without bound

# w_n2..w_p2: Israel prominence weight in each sentiment bucket that run;
# w_u: present but unscored (related not yet decided). Sum == israel_weight.
SNAP_FIELDS = [
    "ts", "source", "fetch_ok", "total_items", "total_weight",
    "israel_items", "israel_weight", "attention_share", "mean_sentiment",
    "w_n2", "w_n1", "w_0", "w_p1", "w_p2", "w_u",
    "approx",  # "1" when the row's Israel weight was re-estimated (2026-09-15 chrome rebuild), else blank
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


def load_recent_stories(months):
    """Return {id: story} for the given YYYY-MM partitions."""
    idx = {}
    for m in months:
        for row in read_jsonl(STORIES_DIR / f"{m}.jsonl"):
            idx[row["id"]] = row
    return idx


def save_stories(index):
    """Write the story registry back to its monthly partitions."""
    by_month = defaultdict(list)
    for row in index.values():
        by_month[month_key(row["first_seen"])].append(row)
    for m, rows in by_month.items():
        rows.sort(key=lambda r: r["first_seen"])
        write_jsonl(STORIES_DIR / f"{m}.jsonl", rows)


def load_all_stories():
    out = []
    if not STORIES_DIR.exists():
        return out
    for path in sorted(STORIES_DIR.glob("*.jsonl")):
        out.extend(read_jsonl(path))
    return out


def load_recent_allitems(months):
    """Return {id: record} for the given YYYY-MM all-item partitions."""
    idx = {}
    for m in months:
        for row in read_jsonl(ALLITEMS_DIR / f"{m}.jsonl"):
            idx[row["id"]] = row
    return idx


def load_all_allitems():
    """Return {id: record} over every all-item partition."""
    idx = {}
    for path in sorted(ALLITEMS_DIR.glob("*.jsonl")):
        for row in read_jsonl(path):
            idx[row["id"]] = row
    return idx


def save_allitems(index):
    """Write the all-item index back to its monthly partitions."""
    by_month = defaultdict(list)
    for row in index.values():
        by_month[month_key(row["first_seen"])].append(row)
    for m, rows in by_month.items():
        rows.sort(key=lambda r: r["first_seen"])
        write_jsonl(ALLITEMS_DIR / f"{m}.jsonl", rows)


def append_intl(ts, rows):
    path = INTL_DIR / f"{month_key(ts)}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_rows(ts, sources, per_source):
    """This run's archive rows: one per fetched source, its top-20 item ids in
    rank order (rank 1 first). Failed or empty fetches get no row — missing,
    never an empty list."""
    rows = []
    for src in sources:
        ps = per_source.get(src["name"]) or {}
        if not ps.get("ok") or not ps.get("top20"):
            continue
        ordered = sorted(ps["top20"], key=lambda t: t[1])  # (headline, rank, weight)
        rows.append({"ts": ts, "source": src["name"],
                     "ids": [item_id(src["name"], h) for h, _, _ in ordered]})
    return rows


def _run_cutoff(ts, days=RUN_RETENTION_DAYS):
    return (datetime.strptime(ts, TS_FMT) - timedelta(days=days)).strftime(TS_FMT)


def prune_runs(ts, days=RUN_RETENTION_DAYS):
    """Drop archived run rows older than `days` (relative to `ts`).

    Month files entirely out of the window are deleted; the month the cutoff
    falls in is filtered row by row. Returns the number of rows dropped.
    """
    if not RUNS_DIR.exists():
        return 0
    cutoff = _run_cutoff(ts, days)
    cut_month = month_key(cutoff)
    dropped = 0
    for path in sorted(RUNS_DIR.glob("*.jsonl")):
        if path.stem > cut_month:  # YYYY-MM sorts lexicographically
            continue
        rows = read_jsonl(path)
        keep = [r for r in rows if r.get("ts", "") >= cutoff]
        if len(keep) == len(rows):
            continue
        dropped += len(rows) - len(keep)
        if keep:
            write_jsonl(path, keep)
        else:
            path.unlink()
    return dropped


def append_runs(ts, rows, retention_days=RUN_RETENTION_DAYS):
    """Append this run's ranked rows ({ts, source, ids}), then prune the store."""
    path = RUNS_DIR / f"{month_key(ts)}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps({k: r[k] for k in RUN_FIELDS}, ensure_ascii=False) + "\n")
    prune_runs(ts, retention_days)


def load_recent_runs(since_ts):
    """Archived run rows with ts >= since_ts, oldest first."""
    out = []
    if not RUNS_DIR.exists():
        return out
    since_month = month_key(since_ts)
    for path in sorted(RUNS_DIR.glob("*.jsonl")):
        if path.stem < since_month:
            continue
        out.extend(r for r in read_jsonl(path) if r.get("ts", "") >= since_ts)
    out.sort(key=lambda r: r["ts"])
    return out


def load_all_runs():
    out = []
    if not RUNS_DIR.exists():
        return out
    for path in sorted(RUNS_DIR.glob("*.jsonl")):
        out.extend(read_jsonl(path))
    return out


def _ensure_snapshot_schema(path):
    """One-time migration when SNAP_FIELDS grows: rewrite the month file with
    the current header, blank-filling new columns. Idempotent (header check).
    Older months are left as-is — consumers must read columns via row.get().
    """
    if not path.exists():
        return
    with open(path, newline="") as f:
        if f.readline().rstrip("\r\n") == ",".join(SNAP_FIELDS):
            return
        f.seek(0)
        rows = list(csv.DictReader(f))
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SNAP_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SNAP_FIELDS})
    os.replace(tmp, path)


def append_snapshots(ts, rows):
    path = SNAPS_DIR / f"{month_key(ts)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_snapshot_schema(path)
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
