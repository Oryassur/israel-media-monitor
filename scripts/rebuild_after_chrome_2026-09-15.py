"""One-off rebuild (2026-09-15) after the extractor learned to drop page chrome.

Per-run rankings were never stored (only per-run aggregates), so the past
cannot be recomputed exactly. What this does, and how far it can be trusted:

1. Identify chrome records in data/allitems: (a) links that the pre-fix
   extractor returned for today's fetched homepages and the fixed extractor
   does not (chrome is static, so today's set covers most of the week), plus
   (b) headline text that is obviously an affordance or promo. Delete them
   from data/allitems (and data/items, if any).
2. Snapshot rows (per source per run): for each Israel-related item present in
   that run, estimate its rank as its best_rank, count the chrome links that
   sat above it, and re-weight it as if they were gone. The row's exact
   israel_weight is scaled by (re-weighted sum / best-rank sum), so rows where
   nothing sat above the Israel items are unchanged, and rows are never
   invented from scratch. Composition columns scale with it. Adjusted rows get
   approx=1 (new column).
3. Intl rows of affected (source, run) pairs are rebuilt with the same
   presence-window approximation the intl backfill uses, without the chrome.

Run from the repo root after fetching today's homepages into HTML_DIR:
  python scripts/rebuild_after_chrome_2026-09-15.py HTML_DIR OLD_EXTRACT_PY
"""
import csv
import importlib.util
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import store  # noqa: E402
from pipeline.common import INTL_VERSION, item_id, load_sources, read_jsonl, write_jsonl  # noqa: E402
from pipeline.extract import extract_items, prominence_weight  # noqa: E402

CHROME_TEXT = re.compile(
    r"(sign up (for|to|now)|read and subscribe|our (free )?(weekly )?(newsletter|email)|download your free|"
    r"where to buy|see what's live|catch up with the news|catch up on today|^interactive:|überspringen|"
    r"^skip (to|next)|^topic: |pfeil rechts|^new! |shop smarter|tip us off|^go back to (the )?home|retour à la page|"
    r"se connecter|votre compte|partager votre abonnement|fehler melden|tägliches extra|"
    r"premier league table|^good food|search for uni courses|top stories in 90 seconds|"
    r"tagesschau in 100 sekunden|the road to 9/11: download|\bnewsletter$|other offers|subscriber only)",
    re.I,
)


def _scale_int(parts, total):
    """Scale non-negative parts to sum to `total` (largest-remainder rounding); strings."""
    tot = sum(parts)
    if tot <= 0:
        return [str(total)] + ["0"] * (len(parts) - 1) if parts else []
    raw = [p * total / tot for p in parts]
    out = [int(v) for v in raw]
    for i in sorted(range(len(parts)), key=lambda i: raw[i] - int(raw[i]), reverse=True)[:total - sum(out)]:
        out[i] += 1
    return [str(v) for v in out]


def load_old_extractor(path):
    spec = importlib.util.spec_from_file_location("extract_old", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pipeline.extract_old"] = mod
    spec.loader.exec_module(mod)
    return mod


def chrome_ids(html_dir, old_extract):
    """{id: (source, headline)} of links the old extractor returned and the new one drops."""
    out = {}
    for s in load_sources():
        f = html_dir / f"{s['name']}.html"
        if not f.exists():
            continue
        html = f.read_text()
        old = old_extract.extract_items(html, s["url"], s.get("selector"))
        kept = extract_items(html, s["url"], s.get("selector"), s.get("skip"))
        new_heads = {it["headline"] for it in kept}
        new_urls = {it["url"] for it in kept}
        for it in old:
            # dropped by the new rules: neither its text nor its URL survives (a URL
            # that survives under other link text is the same story, not chrome)
            if it["headline"] not in new_heads and it["url"] not in new_urls:
                out[item_id(s["name"], it["headline"])] = (s["name"], it["headline"])
    return out


def main(html_dir, old_path):
    old_extract = load_old_extractor(old_path)
    allidx = store.load_all_allitems()
    chrome = chrome_ids(html_dir, old_extract)
    for r in allidx.values():
        if r["id"] not in chrome and CHROME_TEXT.search(r["headline"]):
            chrome[r["id"]] = (r["source"], r["headline"])
    chrome = {i: v for i, v in chrome.items() if i in allidx}
    print(f"{len(chrome)} chrome records identified:")
    for i, (src, h) in sorted(chrome.items(), key=lambda kv: kv[1]):
        r = allidx[i]
        print(f"  {src:13} r{r['best_rank']:>2} {r['first_seen'][5:10]}→{r['last_seen'][5:10]} {h[:60]}")

    # chrome ranks per source, with presence windows
    chrome_rows = defaultdict(list)
    for i in chrome:
        r = allidx[i]
        chrome_rows[r["source"]].append(r)

    # Israel-related items with windows, per source
    items = [r for r in store.load_all_items() if r.get("related") is True and r["id"] not in chrome]
    isr_rows = defaultdict(list)
    for r in items:
        isr_rows[r["source"]].append(r)

    # ---- snapshots
    adjusted = 0
    for path in sorted(store.SNAPS_DIR.glob("*.csv")):
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            src, ts = row["source"], row["ts"]
            if row.get("fetch_ok") != "1" or not chrome_rows.get(src):
                continue
            iw = float(row["israel_weight"] or 0)
            if iw <= 0:
                continue
            above = sorted(c["best_rank"] for c in chrome_rows[src]
                           if c["first_seen"] <= ts <= c["last_seen"] and c["best_rank"] <= 20)
            if not above:
                continue
            present = [r for r in isr_rows[src] if r["first_seen"] <= ts <= r["last_seen"]]
            old_sum = new_sum = 0
            for r in present:
                rk = r["best_rank"] or 21
                shift = sum(1 for c in above if c < rk)
                old_sum += prominence_weight(rk)
                new_sum += prominence_weight(rk - shift)
            if old_sum <= 0 or new_sum == old_sum:
                continue
            factor = new_sum / old_sum
            total = int(float(row["total_weight"]))
            new_iw = min(total, int(round(iw * factor)))
            if new_iw == int(iw):
                continue
            row["israel_weight"] = str(new_iw)
            row["attention_share"] = f"{new_iw / total:.5f}"
            comp_keys = ("w_n2", "w_n1", "w_0", "w_p1", "w_p2", "w_u")
            if all(row.get(k) not in ("", None) for k in comp_keys):
                # keep the composition invariant: integer parts, Σ == israel_weight
                row.update(zip(comp_keys, _scale_int([float(row[k]) for k in comp_keys], new_iw)))
            row["approx"] = "1"
            adjusted += 1
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=store.SNAP_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in store.SNAP_FIELDS})
    print(f"snapshots: {adjusted} rows re-weighted (approx=1)")

    # ---- allitems: drop chrome, then rebuild intl rows for affected (source, ts)
    for i in chrome:
        allidx.pop(i, None)
    store.save_allitems(allidx)
    by_src = defaultdict(list)
    for r in allidx.values():
        by_src[r["source"]].append(r)
    rebuilt = 0
    for path in sorted(store.INTL_DIR.glob("*.jsonl")):
        rows = read_jsonl(path)
        out = []
        for row in rows:
            src, ts = row["source"], row["ts"]
            hit = any(c["first_seen"] <= ts <= c["last_seen"] and c["best_rank"] <= 20 for c in chrome_rows.get(src, ()))
            if not hit:
                out.append(row)
                continue
            present = [r for r in by_src.get(src, ()) if r["first_seen"] <= ts <= r["last_seen"]]
            present.sort(key=lambda r: r.get("best_rank") or 99)
            intl_w = uncl_w = 0
            topics = {}
            for rank, r in enumerate(present[:20], 1):
                w = prominence_weight(rank)  # re-ranked without the chrome
                if r.get("iv") != INTL_VERSION:
                    uncl_w += w
                elif r["intl"]:
                    intl_w += w
                    topics[r["topic"]] = topics.get(r["topic"], 0) + w
            out.append({"ts": ts, "source": src, "total_w": row["total_w"], "intl_w": intl_w, "uncl_w": uncl_w,
                        "topics": topics, "iv": INTL_VERSION, "approx": True})
            rebuilt += 1
        write_jsonl(path, out)
    print(f"intl: {rebuilt} rows rebuilt without chrome (approx)")


if __name__ == "__main__":
    os.chdir(ROOT)
    main(Path(sys.argv[1]), sys.argv[2])
