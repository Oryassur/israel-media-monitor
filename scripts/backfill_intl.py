#!/usr/bin/env python3
"""Backfill the international benchmark under the current INTL_VERSION.

    python scripts/backfill_intl.py classify CACHE.jsonl   # (re)classify every all-item not at
                                                           #   INTL_VERSION; verdicts appended to CACHE
                                                           #   after each batch (safe to interrupt/resume)
    python scripts/backfill_intl.py apply CACHE.jsonl      # merge CACHE into data/allitems, then rebuild
                                                           #   every data/intl row not at INTL_VERSION

Rebuilt rows are approximate: the run's exact total_w is kept, and each headline
is assumed present at its best_weight in every run between first_seen and
last_seen; intl/uncl/topic weights are scaled to total_w. They carry
{"iv": INTL_VERSION, "approx": true}. Exact per-run rows resume with the next
hourly run after the bump. Original rows stay in git history.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import intl  # noqa: E402
from pipeline.common import DATA, INTL_VERSION, load_sources, read_jsonl, write_jsonl  # noqa: E402
from pipeline.store import load_all_allitems, save_allitems  # noqa: E402

INTL_DIR = DATA / "intl"
FIELDS = ("intl", "topic", "iv", "model")


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


def classify(cache_path: Path):
    done = {r["id"] for r in read_jsonl(cache_path)}
    sources = {s["name"]: s for s in load_sources()}
    allidx = load_all_allitems()
    todo = [r for r in allidx.values()
            if r["source"] in sources and r.get("iv") != INTL_VERSION and r["id"] not in done]
    todo.sort(key=lambda r: r["first_seen"])
    print(f"{len(allidx)} all-items; {len(done)} cached; {len(todo)} to classify under {INTL_VERSION}", flush=True)
    in_use = []
    for start in range(0, len(todo), intl.BATCH_SIZE):
        batch = todo[start:start + intl.BATCH_SIZE]
        for r in batch:
            s = sources[r["source"]]
            r["source_display"] = s["display"]
            r["home"] = s.get("home", s["country"])
            for k in FIELDS:
                r.pop(k, None)  # so a failed batch leaves them visibly unclassified
        n = intl.classify_items(batch, in_use, log=lambda m: print(m, flush=True))
        with open(cache_path, "a") as f:
            for r in batch:
                if "intl" in r:
                    f.write(json.dumps({"id": r["id"], **{k: r[k] for k in FIELDS}}) + "\n")
        print(f"batch {start // intl.BATCH_SIZE + 1}/{-(-len(todo) // intl.BATCH_SIZE)}: {n}/{len(batch)}", flush=True)
    return 0


def apply(cache_path: Path):
    cache = {r["id"]: r for r in read_jsonl(cache_path)}
    allidx = load_all_allitems()
    merged = 0
    for iid, v in cache.items():
        r = allidx.get(iid)
        if r is None or r.get("iv") == INTL_VERSION:
            continue
        for k in FIELDS:
            r[k] = v[k]
        merged += 1
    save_allitems(allidx)
    print(f"merged {merged} verdicts into data/allitems", flush=True)

    by_src = {}
    for r in allidx.values():
        by_src.setdefault(r["source"], []).append(r)

    rebuilt = kept = 0
    for path in sorted(INTL_DIR.glob("*.jsonl")):
        rows = read_jsonl(path)
        out = []
        for row in rows:
            if row.get("iv") == INTL_VERSION and not row.get("approx"):
                out.append(row); kept += 1
                continue
            ts = row["ts"]
            present = [r for r in by_src.get(row["source"], ()) if r["first_seen"] <= ts <= r["last_seen"]]
            intl_w = uncl_w = 0
            topics = {}
            for r in present:
                w = r.get("best_weight", 0)
                if r.get("iv") != INTL_VERSION:
                    uncl_w += w
                elif r["intl"]:
                    intl_w += w
                    topics[r["topic"]] = topics.get(r["topic"], 0) + w
            approx_total = sum(r.get("best_weight", 0) for r in present)
            total = row["total_w"]
            dom_w = max(0, approx_total - intl_w - uncl_w)
            si, su, _ = _scale([intl_w, uncl_w, dom_w], total)
            keys = list(topics)
            st = _scale([topics[k] for k in keys], si)
            out.append({"ts": ts, "source": row["source"], "total_w": total, "intl_w": si, "uncl_w": su,
                        "topics": {k: v for k, v in zip(keys, st) if v}, "iv": INTL_VERSION, "approx": True})
            rebuilt += 1
        write_jsonl(path, out)
    print(f"data/intl: {rebuilt} rows rebuilt (approx), {kept} exact {INTL_VERSION} rows kept", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("classify", "apply"):
        print(__doc__); sys.exit(2)
    sys.exit({"classify": classify, "apply": apply}[sys.argv[1]](Path(sys.argv[2])))
