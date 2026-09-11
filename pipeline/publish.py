"""Build the static JSON files the dashboard reads (docs/data/)."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .common import (CLUSTER_VERSION, DATA, DOCS_DATA, ENRICH_MIN_WEIGHT, METHOD_VERSION, ROOT,
                     RUBRIC_VERSION, load_sources, read_jsonl)
from .store import load_all_items, load_all_stories, read_all_snapshots

HOURLY_WINDOW_DAYS = 14
ITEMS_WINDOW_DAYS = 30
LOGOS_DIR = ROOT / "docs" / "logos"

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


def _intl_series(snaps, hourly_cut):
    """International-benchmark rows for the dashboard: per run (hourly window) and per
    day (full history), each [when, source, total_w, intl_w, uncl_w, israel_w] where
    israel_w is the main pipeline's Israel-related weight for that run — the same
    numerator as the attention share, so "share of international coverage" =
    israel_w / intl_w. Only classified rows (iv present) are used."""
    isr = {(r["ts"], r["source"]): int(r["israel_weight"] or 0)
           for r in snaps if r["fetch_ok"] in ("1", 1) and r["israel_weight"] != ""}
    rows = []
    for path in sorted((DATA / "intl").glob("*.jsonl")):
        rows.extend(r for r in read_jsonl(path) if r.get("iv") and (r["ts"], r["source"]) in isr)
    hourly = [[r["ts"], r["source"], r["total_w"], r["intl_w"], r.get("uncl_w", 0), isr[(r["ts"], r["source"])]]
              for r in rows if r["ts"] >= hourly_cut]
    acc = defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        d = acc[(r["ts"][:10], r["source"])]
        d[0] += r["total_w"]; d[1] += r["intl_w"]; d[2] += r.get("uncl_w", 0); d[3] += isr[(r["ts"], r["source"])]
    daily = [[date, src, *v] for (date, src), v in sorted(acc.items())]
    return {"cols": ["when", "source", "total_w", "intl_w", "uncl_w", "israel_w"],
            "hourly": hourly, "daily": daily}


def _source_meta(s, logos_dir: Path):
    """Dashboard-facing descriptor of one source (no URL; domain + logo path)."""
    domain = urlparse(s["url"]).netloc
    if domain.startswith("www."):
        domain = domain[4:]
    logo = None
    for p in sorted(Path(logos_dir).glob(f"{s['name']}.*")):
        logo = f"logos/{p.name}"
        break
    return {
        "name": s["name"], "display": s["display"], "country": s["country"],
        "home": s.get("home", s["country"]), "lang": s["lang"], "lean": s["lean"],
        "type": s["type"], "domain": domain, "logo": logo,
    }


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

    # recent items for the front page + drill-down (confirmed related, or still
    # unscored). Every key is always present (null when absent) so the client
    # stays branch-free.
    recent_items = [
        {"id": r["id"], "src": r["source"], "h": r["headline"], "ht": r.get("ht"),
         "u": r["url"], "fs": r["first_seen"], "ls": r["last_seen"],
         "w": r["best_weight"], "r": r.get("best_rank"),
         "s": r.get("sentiment"), "c": r.get("category"), "st": r.get("story"),
         "img": r.get("img"), "d": r.get("desc")}
        for r in items
        if r["last_seen"] >= items_cut and r.get("related") is not False
        and r["best_weight"] > 0
    ]
    recent_items.sort(key=lambda r: r["fs"], reverse=True)

    # registry entries for the stories the published items point at
    used = {r["st"] for r in recent_items if r.get("st")}
    stories = {
        s["id"]: {"t": s["title"], "fs": s["first_seen"], "ls": s["last_seen"]}
        for s in load_all_stories() if s["id"] in used
    }

    _write("meta.json", {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubric": RUBRIC_VERSION,
        "method": METHOD_VERSION,
        "cluster": CLUSTER_VERSION,
        "hourly_cols": ["ts", "source", "share", "sentiment", "items", "ok", "comp"],
        "daily_cols": ["date", "source", "share", "sentiment", "items", "runs_ok", "runs", "comp"],
        # first snapshot with stored (not approximated) composition columns
        "comp_exact_since": min((s["ts"] for s in snaps if s.get("w_n2", "") != ""), default=None),
        "items_window_days": ITEMS_WINDOW_DAYS,
        "enrich_min_weight": ENRICH_MIN_WEIGHT,
        "sources": [_source_meta(s, LOGOS_DIR) for s in sources],
    })
    _write("intl.json", _intl_series(snaps, hourly_cut))
    _write("hourly.json", hourly)
    _write("daily.json", daily)
    _write("items.json", recent_items)
    _write("stories.json", stories)


if __name__ == "__main__":
    build()
