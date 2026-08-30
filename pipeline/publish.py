"""Build the static JSON files the dashboard reads (docs/data/)."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .common import DOCS_DATA, METHOD_VERSION, RUBRIC_VERSION, load_sources
from .store import load_all_items, read_all_snapshots

HOURLY_WINDOW_DAYS = 14
ITEMS_WINDOW_DAYS = 7


def _write(name, obj):
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    with open(DOCS_DATA / name, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def build():
    now = datetime.now(timezone.utc)
    snaps = read_all_snapshots()
    items = load_all_items()
    sources = load_sources()

    hourly_cut = (now - timedelta(days=HOURLY_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items_cut = (now - timedelta(days=ITEMS_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # hourly series (recent window), compact arrays per row
    hourly = [
        [s["ts"], s["source"],
         float(s["attention_share"]) if s["attention_share"] else None,
         float(s["mean_sentiment"]) if s["mean_sentiment"] else None,
         int(s["israel_items"]), int(s["fetch_ok"])]
        for s in snaps if s["ts"] >= hourly_cut
    ]

    # daily rollup per source over full history
    day_acc = defaultdict(lambda: {"share_sum": 0.0, "share_n": 0, "s_num": 0.0, "s_den": 0.0,
                                   "items": 0, "runs_ok": 0, "runs": 0})
    for s in snaps:
        d = day_acc[(s["ts"][:10], s["source"])]
        d["runs"] += 1
        if s["fetch_ok"] == "1" or s["fetch_ok"] == 1:
            d["runs_ok"] += 1
            if s["attention_share"] != "":
                d["share_sum"] += float(s["attention_share"])
                d["share_n"] += 1
            if s["mean_sentiment"] != "" and s["israel_weight"] not in ("", "0"):
                w = float(s["israel_weight"])
                d["s_num"] += float(s["mean_sentiment"]) * w
                d["s_den"] += w
        d["items"] = max(d["items"], int(s["israel_items"] or 0))
    daily = [
        [date, src,
         round(d["share_sum"] / d["share_n"], 5) if d["share_n"] else None,
         round(d["s_num"] / d["s_den"], 3) if d["s_den"] else None,
         d["items"], d["runs_ok"], d["runs"]]
        for (date, src), d in sorted(day_acc.items())
    ]

    # recent items for the drill-down panel (confirmed related, or still unscored)
    recent_items = [
        {"src": r["source"], "h": r["headline"], "ht": r.get("ht"), "u": r["url"],
         "fs": r["first_seen"], "ls": r["last_seen"], "w": r["best_weight"],
         "s": r.get("sentiment"), "c": r.get("category")}
        for r in items
        if r["last_seen"] >= items_cut and r.get("related") is not False
    ]
    recent_items.sort(key=lambda r: r["fs"], reverse=True)

    _write("meta.json", {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubric": RUBRIC_VERSION,
        "method": METHOD_VERSION,
        "hourly_cols": ["ts", "source", "share", "sentiment", "items", "ok"],
        "daily_cols": ["date", "source", "share", "sentiment", "items", "runs_ok", "runs"],
        "sources": [
            {"name": s["name"], "display": s["display"], "country": s["country"],
             "lang": s["lang"], "lean": s["lean"], "type": s["type"]}
            for s in sources
        ],
    })
    _write("hourly.json", hourly)
    _write("daily.json", daily)
    _write("items.json", recent_items)


if __name__ == "__main__":
    build()
