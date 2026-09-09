"""Build the static JSON files the dashboard reads (docs/data/)."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .common import DOCS_DATA, METHOD_VERSION, RUBRIC_VERSION, load_sources
from .store import load_all_items, read_all_snapshots

HOURLY_WINDOW_DAYS = 14
ITEMS_WINDOW_DAYS = 7

COMP_KEYS = ("w_n2", "w_n1", "w_0", "w_p1", "w_p2", "w_u")


def _write(name, obj):
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    with open(DOCS_DATA / name, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _scale_to(vals, total):
    """Proportionally scale non-negative vals to ints summing to total
    (largest-remainder rounding)."""
    s = sum(vals)
    if s <= 0:
        return None
    scaled = [v * total / s for v in vals]
    out = [int(v) for v in scaled]
    order = sorted(range(len(vals)), key=lambda i: scaled[i] - out[i], reverse=True)
    for i in order[:max(0, total - sum(out))]:
        out[i] += 1
    return out


def _row_comp(s, by_src):
    """Sentiment composition [n2, n1, 0, p1, p2, unscored] of a snapshot row's
    israel_weight, or None (failed fetch / nothing on the homepage).

    Rows written before the w_* columns existed get an approximation from the
    item records visible at that hour (bucketed by their eventual sentiment,
    weighted by best_weight, scaled to the row's israel_weight).
    """
    if s["fetch_ok"] not in ("1", 1):
        return None
    iw = int(s["israel_weight"] or 0)
    if iw == 0:
        return None
    if s.get("w_n2", "") != "":
        return [int(s.get(k) or 0) for k in COMP_KEYS]
    ts = s["ts"]
    acc = [0.0] * 6
    for fs, ls, sent, w in by_src.get(s["source"], ()):
        if fs <= ts <= ls:
            acc[5 if sent is None else sent + 2] += w
    return _scale_to(acc, iw)


def build():
    now = datetime.now(timezone.utc)
    snaps = read_all_snapshots()
    items = load_all_items()
    sources = load_sources()

    hourly_cut = (now - timedelta(days=HOURLY_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items_cut = (now - timedelta(days=ITEMS_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # per-source item tuples for approximating comp on pre-w_* rows
    by_src = defaultdict(list)
    for r in items:
        if r.get("related") is not False and r.get("best_weight", 0) > 0:
            by_src[r["source"]].append(
                (r["first_seen"], r["last_seen"], r.get("sentiment"), r["best_weight"]))
    comps = [_row_comp(s, by_src) for s in snaps]

    # hourly series (recent window), compact arrays per row
    hourly = [
        [s["ts"], s["source"],
         float(s["attention_share"]) if s["attention_share"] != "" else None,
         float(s["mean_sentiment"]) if s["mean_sentiment"] != "" else None,
         int(s["israel_items"]), int(s["fetch_ok"]), comps[i]]
        for i, s in enumerate(snaps) if s["ts"] >= hourly_cut
    ]

    # daily rollup per source over full history
    day_acc = defaultdict(lambda: {"share_sum": 0.0, "share_n": 0, "s_num": 0.0, "s_den": 0.0,
                                   "items": 0, "runs_ok": 0, "runs": 0, "comp": None})
    for i, s in enumerate(snaps):
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
            if comps[i]:
                d["comp"] = [a + b for a, b in zip(d["comp"], comps[i])] if d["comp"] else list(comps[i])
        d["items"] = max(d["items"], int(s["israel_items"] or 0))
    daily = [
        [date, src,
         round(d["share_sum"] / d["share_n"], 5) if d["share_n"] else None,
         round(d["s_num"] / d["s_den"], 3) if d["s_den"] else None,
         d["items"], d["runs_ok"], d["runs"], d["comp"]]
        for (date, src), d in sorted(day_acc.items())
    ]

    # recent items for the drill-down panel (confirmed related, or still unscored)
    recent_items = [
        {"src": r["source"], "h": r["headline"], "ht": r.get("ht"), "u": r["url"],
         "fs": r["first_seen"], "ls": r["last_seen"], "w": r["best_weight"],
         "s": r.get("sentiment"), "c": r.get("category")}
        for r in items
        if r["last_seen"] >= items_cut and r.get("related") is not False
        and r["best_weight"] > 0
    ]
    recent_items.sort(key=lambda r: r["fs"], reverse=True)

    _write("meta.json", {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubric": RUBRIC_VERSION,
        "method": METHOD_VERSION,
        "hourly_cols": ["ts", "source", "share", "sentiment", "items", "ok", "comp"],
        "daily_cols": ["date", "source", "share", "sentiment", "items", "runs_ok", "runs", "comp"],
        # first snapshot with stored (not approximated) composition columns
        "comp_exact_since": min((s["ts"] for s in snaps if s.get("w_n2", "") != ""), default=None),
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
