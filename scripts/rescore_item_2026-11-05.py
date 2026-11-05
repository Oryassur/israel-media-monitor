"""One-off (2026-11-05): force a single headline back through sentiment scoring.

  nypost  d90b105eff23b292
  "JD Vance blames Iran war and Israel for GOP midterm bloodbath"  -> stored 0

The rubric already settles this shape at v3.1 line 147:

  "Spain's PM blames Russia, Israel for border crisis" -> -1, diplomacy
  (accusation-focused)

Same verb, same structure, a senior politician blaming Israel for a bad
outcome. So this is the model contradicting its own worked example, not a gap
in the rubric — nothing to bump, nothing to re-score in bulk.

Headlines are scored once and cached, so the only honest way to retry one is to
make it look un-scored to run.py's pending filter, which re-scores anything
whose `rubric` is not the current RUBRIC_VERSION. Clearing `rubric` (and the
`sentiment`/`model` it produced) puts exactly this row back in the queue; the
next hourly run picks it up. The model may well return 0 again — that is a
result too, and the argument for the reliability sample rather than for
hand-editing scores.

Nothing else is touched: no snapshot row is rewritten here. publish recomputes
the dashboard from items on the next run.

    python scripts/rescore_item_2026-11-05.py [--write]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.common import read_jsonl, write_jsonl  # noqa: E402

MONTH = ROOT / "data" / "items" / "2026-11.jsonl"
ITEM_ID = "d90b105eff23b292"
CLEAR = ("sentiment", "model", "rubric")


def main(write):
    rows = read_jsonl(MONTH)
    hit = [r for r in rows if r["id"] == ITEM_ID]
    if not hit:
        print(f"{ITEM_ID} not in {MONTH.name} — already rolled over or re-scored?")
        return 1
    r = hit[0]
    if "rubric" not in r:
        print(f"{ITEM_ID} is already queued for scoring (no rubric field); nothing to do")
        return 0
    print(f"  {r['source']}  {r['headline']}")
    print("  clearing: " + ", ".join(f"{k}={r.get(k)!r}" for k in CLEAR if k in r))
    if not write:
        print("\ndry run — pass --write to apply")
        return 0
    for k in CLEAR:
        r.pop(k, None)
    write_jsonl(MONTH, rows)
    print("\ncleared; the next hourly run will re-score it")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main("--write" in sys.argv))
