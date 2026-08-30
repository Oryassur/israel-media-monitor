"""One full pipeline cycle: fetch -> extract -> detect -> score -> store -> publish.

Run:  python -m pipeline.run            (normal hourly cycle)
      python -m pipeline.run --no-llm   (skip sentiment scoring)
"""
import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from . import publish
from .common import LOGS, SCORE_RETRY_WINDOW_H, item_id, load_sources, month_key
from .detect import match_keyword
from .extract import extract_items, fetch_html, prominence_weight
from .score import score_items
from .store import append_snapshots, load_recent_items, save_items


def log(msg):
    print(msg, flush=True)


def run(no_llm=False):
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sources = load_sources()
    months = [month_key(ts), month_key((now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))]
    items_idx = load_recent_items(months)
    known_ids = set(items_idx)

    per_source = {}  # name -> {"ok": bool, "present": [(id, weight)], "total_items", "total_weight"}
    fresh = []       # newly seen candidate items (to be scored)

    for src in sources:
        name = src["name"]
        try:
            html = fetch_html(src["url"])
            extracted = extract_items(html, src["url"], src.get("selector"))
        except Exception as e:  # noqa: BLE001 — one dead source must not kill the run
            log(f"FETCH FAIL {name}: {e}")
            per_source[name] = {"ok": False, "present": [], "total_items": 0, "total_weight": 0}
            continue

        total = len(extracted)
        total_weight = sum(prominence_weight(it["rank"], total) for it in extracted)
        present = []
        for it in extracted:
            kw = match_keyword(it["headline"], src["lang"])
            if not kw:
                continue
            iid = item_id(name, it["headline"])
            weight = prominence_weight(it["rank"], total)
            present.append((iid, weight))
            if iid in items_idx:
                rec = items_idx[iid]
                rec["last_seen"] = ts
                if weight > rec.get("best_weight", 0):
                    rec["best_weight"] = weight
                    rec["best_rank"] = it["rank"]
            else:
                rec = {
                    "id": iid, "source": name, "url": it["url"],
                    "headline": it["headline"], "lang": src["lang"],
                    "first_seen": ts, "last_seen": ts,
                    "best_rank": it["rank"], "best_weight": weight,
                    "keyword": kw,
                }
                items_idx[iid] = rec
                fresh.append(rec)
        per_source[name] = {
            "ok": True, "present": present,
            "total_items": total, "total_weight": total_weight,
        }
        log(f"{name}: {total} items, {len(present)} israel-candidates"
            + ("" if total else "  <-- EMPTY EXTRACTION, check parser"))
        time.sleep(1)  # be polite between hosts

    # Score fresh items plus earlier ones that missed scoring, within the retry window
    cutoff = (now - timedelta(hours=SCORE_RETRY_WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending = [
        r for r in items_idx.values()
        if r["first_seen"] >= cutoff and (
            "related" not in r
            or (r["lang"] != "en" and r.get("related") is not False and "ht" not in r)
        )
    ]
    disp = {s["name"]: s["display"] for s in sources}
    if pending and not no_llm:
        for r in pending:
            r["source_display"] = disp[r["source"]]
        n = score_items(pending, log=log)
        for r in pending:
            r.pop("source_display", None)
        log(f"scored {n}/{len(pending)} pending items ({len(fresh)} new this run)")
    elif pending:
        log(f"scoring skipped (--no-llm); {len(pending)} items pending")

    # Per-source hourly snapshot. Items the LLM rejected (related=false) are
    # excluded; unscored candidates count toward volume but not sentiment.
    snaps = []
    for src in sources:
        name = src["name"]
        ps = per_source[name]
        isr_items, isr_weight, s_num, s_den = 0, 0, 0.0, 0
        for iid, weight in ps["present"]:
            rec = items_idx[iid]
            if rec.get("related") is False:
                continue
            isr_items += 1
            isr_weight += weight
            if rec.get("sentiment") is not None:
                s_num += rec["sentiment"] * weight
                s_den += weight
        snaps.append({
            "ts": ts, "source": name, "fetch_ok": int(ps["ok"]),
            "total_items": ps["total_items"], "total_weight": ps["total_weight"],
            "israel_items": isr_items, "israel_weight": isr_weight,
            "attention_share": round(isr_weight / ps["total_weight"], 5) if ps["total_weight"] else "",
            "mean_sentiment": round(s_num / s_den, 3) if s_den else "",
        })

    save_items(items_idx)
    append_snapshots(ts, snaps)
    publish.build()

    ok = sum(1 for s in snaps if s["fetch_ok"])
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "runs.log", "a") as f:
        f.write(f"{ts} sources_ok={ok}/{len(sources)} new_items={len(fresh)} "
                f"known_items={len(known_ids)}\n")
    log(f"done: {ok}/{len(sources)} sources ok, {len(fresh)} new candidate items")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip sentiment scoring")
    args = ap.parse_args()
    sys.exit(run(no_llm=args.no_llm))
