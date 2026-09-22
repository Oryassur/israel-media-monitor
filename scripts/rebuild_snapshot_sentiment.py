#!/usr/bin/env python3
"""Fill the sentiment composition of snapshot rows written while scoring was down.

    python scripts/rebuild_snapshot_sentiment.py START END [--write]

During an LLM outage the hourly rows keep an exact israel_weight but park every
unscored headline's weight in w_u (sentiment blank). Once the headlines are
scored afterwards (a `retry_hours` backfill run), this redistributes each row's
w_u over the sentiment buckets — the same presence-window approximation the
intl backfill uses: a headline first seen during the outage is assumed present
at its best_weight in every run between first_seen and last_seen. Buckets are
scaled (largest remainder) to the row's exact w_u, a headline the LLM rejected
(related=false) is removed from israel_weight, mean_sentiment is recomputed and
the row is marked approx=1. Rows with w_u == 0 are never touched; rows whose
w_u cannot be attributed to any headline are left as they are and counted.

Dry run by default; --write rewrites data/snapshots in place (originals stay in
git history).
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import DATA  # noqa: E402
from pipeline.store import load_all_items  # noqa: E402

SNAPS = DATA / "snapshots"
BUCKET = {-2: "w_n2", -1: "w_n1", 0: "w_0", 1: "w_p1", 2: "w_p2"}
COMP = ("w_n2", "w_n1", "w_0", "w_p1", "w_p2")


def _scale(vals, total):
    """Largest-remainder scaling of non-negative vals to ints summing to total."""
    s = sum(vals)
    if s <= 0 or total <= 0:
        return [0] * len(vals)
    scaled = [v * total / s for v in vals]
    out = [int(v) for v in scaled]
    order = sorted(range(len(vals)), key=lambda i: scaled[i] - out[i], reverse=True)
    for i in order[:max(0, total - sum(out))]:
        out[i] += 1
    return out


def rebuild(start, end, write):
    # Headlines that were unscored at the time: first seen inside the outage
    # and scored since (rejected ones count too — their weight sat in w_u).
    by_src = {}
    for r in load_all_items():
        if start <= r["first_seen"] < end and "related" in r:
            by_src.setdefault(r["source"], []).append(r)

    touched = orphan = 0
    for path in sorted(SNAPS.glob("*.csv")):
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        if "w_u" not in fields:
            continue
        changed = False
        for row in rows:
            ts = row["ts"]
            if not (start <= ts < end) or row.get("fetch_ok") != "1":
                continue
            w_u = int(row.get("w_u") or 0)
            if w_u <= 0:
                continue
            present = [r for r in by_src.get(row["source"], ())
                       if r["first_seen"] <= ts <= r["last_seen"]]
            if not present:
                orphan += 1
                continue
            weights = [r.get("best_weight", 0) for r in present]
            shares = _scale(weights, w_u)
            comp = {k: int(row.get(k) or 0) for k in COMP}
            rejected = 0
            for r, w in zip(present, shares):
                if r.get("related") is False or r.get("sentiment") is None:
                    rejected += w
                else:
                    comp[BUCKET[r["sentiment"]]] += w
            israel_w = int(row["israel_weight"]) - rejected
            total_w = int(row["total_weight"] or 0)
            s_den = sum(comp.values())
            s_num = sum(comp[BUCKET[b]] * b for b in BUCKET)
            row.update({k: str(v) for k, v in comp.items()})
            row["w_u"] = "0"
            row["israel_weight"] = str(israel_w)
            row["israel_items"] = str(max(0, int(row["israel_items"]) - (1 if rejected else 0)))
            row["attention_share"] = str(round(israel_w / total_w, 5)) if total_w else ""
            row["mean_sentiment"] = str(round(s_num / s_den, 3)) if s_den else ""
            row["approx"] = "1"
            touched += 1
            changed = True
        if changed and write:
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
    mode = "rewritten" if write else "would be rewritten (dry run)"
    print(f"{touched} rows {mode}; {orphan} rows kept (w_u not attributable to any headline)")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(rebuild(args[0], args[1], "--write" in sys.argv))
