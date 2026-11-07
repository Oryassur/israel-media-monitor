"""One-off (2026-11-07): merge items that are one story stored twice because a
trailing format tag was left on one copy.

  ilgiornale  "…E la grillina Ascari applaude"           b178821bcc90f8f8  w10 r1
  ilgiornale  "…E la grillina Ascari applaude | VIDEO"   b605f136dc4e36b4  w10 r1

An item id is hash(source, normalized headline), so the tag made one story into
two records, each at rank 1. Front-unit bundles sum best_weight across a story's
items with no regard for when each was seen, so that single outlet contributed
w20 and its one-outlet story reached the top four of Top Stories.

extract._LABEL_SUFFIX now strips these tags, which fixes items ingested from here
on. This repairs what is already stored.

What it does, and what it deliberately does not:

- Only merges a suffixed record whose *stripped* id already exists. A tag on the
  only copy of a story is cosmetic and is left alone: rewriting it would change
  its id, and data/runs rows reference ids.
- Refuses to merge a pair whose presence windows overlap. Non-overlapping means
  no single run ever saw both, so no snapshot row double-counted and
  data/snapshots and data/intl need no repair. An overlapping pair would mean
  the opposite, and wants a weight rebuild rather than this script.
- The surviving record takes the earliest first_seen, latest last_seen, best
  (lowest) rank and highest weight of the pair. Scored fields come from the
  survivor, which is the canonical headline.
- data/runs rows naming the dropped id are repointed at the survivor, so the
  ranked archive keeps resolving.

    python scripts/merge_suffix_dupes_2026-11-07.py [--write]
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.common import item_id, read_jsonl, write_jsonl  # noqa: E402
from pipeline.extract import _LABEL_SUFFIX  # noqa: E402

STORES = ("items", "allitems")


def find_pairs(rows):
    """[(survivor, dropped)] for suffixed records whose stripped id already exists."""
    by_id = {r["id"]: r for r in rows}
    pairs = []
    for r in rows:
        if not _LABEL_SUFFIX.search(r["headline"]):
            continue
        canon = item_id(r["source"], _LABEL_SUFFIX.sub("", r["headline"]).strip())
        keep = by_id.get(canon)
        if keep is not None and keep["id"] != r["id"]:
            pairs.append((keep, r))
    return pairs


def overlaps(a, b):
    return not (a["last_seen"] < b["first_seen"] or b["last_seen"] < a["first_seen"])


def merge(keep, drop):
    keep["first_seen"] = min(keep["first_seen"], drop["first_seen"])
    keep["last_seen"] = max(keep["last_seen"], drop["last_seen"])
    if drop.get("best_rank") is not None:
        keep["best_rank"] = min(keep.get("best_rank") or 99, drop["best_rank"])
    if drop.get("best_weight") is not None:
        keep["best_weight"] = max(keep.get("best_weight") or 0, drop["best_weight"])


def main(write):
    remap = {}          # dropped id -> surviving id
    blocked = 0
    for store in STORES:
        for path in sorted((ROOT / "data" / store).glob("*.jsonl")):
            rows = read_jsonl(path)
            pairs = find_pairs(rows)
            if not pairs:
                continue
            drop_here = set()
            for keep, drop in pairs:
                if overlaps(keep, drop):
                    print(f"  SKIP (windows overlap — snapshots would need a rebuild): {drop['id']}")
                    print(f"       {drop['headline'][:76]}")
                    blocked += 1
                    continue
                print(f"  {path.parent.name}/{path.name}: {drop['id']} -> {keep['id']}")
                print(f"       keep {keep['headline'][-54:]}")
                print(f"       drop {drop['headline'][-54:]}")
                print(f"       window {keep['first_seen'][5:16]}..{keep['last_seen'][5:16]}"
                      f" + {drop['first_seen'][5:16]}..{drop['last_seen'][5:16]}")
                merge(keep, drop)
                drop_here.add(drop["id"])
                remap[drop["id"]] = keep["id"]
            if drop_here and write:
                write_jsonl(path, [r for r in rows if r["id"] not in drop_here])


    if remap:
        runs_fixed = 0
        for path in sorted((ROOT / "data" / "runs").glob("*.jsonl")):
            rows = read_jsonl(path)
            touched = False
            for r in rows:
                ids = r.get("ids") or []
                if not remap.keys() & set(ids):
                    continue
                # repoint, and drop a repeat if a row somehow held both
                out, seen = [], set()
                for i in ids:
                    i = remap.get(i, i)
                    if i not in seen:
                        seen.add(i)
                        out.append(i)
                r["ids"] = out
                touched = True
                runs_fixed += 1
            if touched and write:
                write_jsonl(path, rows)
        print(f"\ndata/runs rows repointed: {runs_fixed}")

    print(f"\n{len(remap)} record(s) merged, {blocked} skipped")
    if not write:
        print("dry run — pass --write to apply")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main("--write" in sys.argv))
