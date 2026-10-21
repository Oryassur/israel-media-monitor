"""End-of-run health check -> logs/health.json for the alerting step.

The LLM passes and every fetch are best-effort by design, so the hourly job
stays green while, say, the API credit runs out (2026-09-18: 3.5 days of
unscored items before anyone noticed). This module turns the run's own
observations into a short list of alert conditions; scripts/alert.py turns
that into a GitHub issue (which emails the owner) and closes it on recovery.

Conditions (each carries a stable `key`, so an unchanged situation is not
re-notified hour after hour):

  llm                   every LLM batch this run failed while there was work
                        to do, or any failure names billing/auth — the API
                        key, not the network, is the problem
  source_down:<name>    a source failed to fetch in every run of the last 24h
                        (>= MIN_RUNS rows), e.g. a new bot wall
  source_empty:<name>   a source fetched fine but extracted zero headlines in
                        every run of the last 24h — parser broke

Parser canaries (2026-10-18) — the loud half of scripts/audit_headlines.py,
reading the stored data, never re-fetching. The audit's short / no-verb /
hub-url signals stay manual: too noisy to mail anyone about.

  rank1_frozen:<name>   the outlet's rank-1 slot (same headline *and* same URL)
                        has not moved for RANK1_FROZEN_DAYS days — the Euronews
                        "trending" tag that sat at rank 1 for a week
  headline_drop:<name>  the last DROP_RECENT_RUNS runs all extracted fewer than
                        half as many headlines as this outlet's own weekly
                        median — how a selector break shows up while the fetch
                        still succeeds
"""
import csv
import json
import re
import statistics
from datetime import timedelta

from .common import DATA, LLM_ERRORS, LOGS, month_key
from .store import load_all_items, load_recent_runs

HEALTH_PATH = LOGS / "health.json"
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
WINDOW_H = 24
MIN_RUNS = 6  # a source must have at least this many rows in the window to be judged
_BILLING_PAT = re.compile(r"credit balance|billing|authentication|invalid x-api-key|api key|"
                          r"permission_error|Error code: 40[13]", re.I)

# rank1_frozen. 4 days is past any real lead story's run at rank 1 while still
# catching a frozen nav link inside the week. The run archive must actually
# reach back across the window (it starts empty, and a source can be down),
# hence the row-count and coverage guards.
RANK1_FROZEN_DAYS = 4
RANK1_MIN_ROWS = 24         # ~hourly runs; fewer than this is too thin to judge
RANK1_COVERAGE_SLACK_H = 3  # the oldest archived row must sit within this of the window start
# The Christian Science Monitor publishes on a near-weekly rhythm; its front
# page legitimately keeps one lead for days (documented in CLAUDE.md).
RANK1_EXEMPT = {"csmonitor"}

# headline_drop. Baseline is the outlet's own median over the past week,
# excluding the runs being judged; a break has to persist over several runs
# before it mails anyone.
DROP_WINDOW_H = 7 * 24
DROP_RECENT_RUNS = 3
DROP_RATIO = 0.5
DROP_MIN_BASELINE_ROWS = 24
DROP_MIN_MEDIAN = 10  # an outlet that normally extracts a handful cannot "collapse"


def _recent_snapshot_rows(now, hours=WINDOW_H):
    """Snapshot rows from the last `hours` hours (current + previous month files)."""
    since = (now - timedelta(hours=hours)).strftime(TS_FMT)
    months = {month_key(now.strftime("%Y-%m")), month_key(since[:7])}
    rows = []
    for m in sorted(months):
        path = DATA / "snapshots" / f"{m}.csv"
        if not path.exists():
            continue
        with open(path, newline="") as f:
            rows.extend(r for r in csv.DictReader(f) if r["ts"] >= since)
    return rows


def rank1_frozen(now, sources):
    """[{key, title, detail}] for outlets whose rank-1 link has not moved.

    Reads data/runs (the ranked archive). An item id is a hash of the
    normalized headline, so comparing ids *is* comparing headlines; the URL is
    compared too wherever data/items knows one, so a lead whose text repeats
    verbatim under a fresh link is not flagged.
    """
    since_dt = now - timedelta(days=RANK1_FROZEN_DAYS)
    since = since_dt.strftime(TS_FMT)
    archive = load_recent_runs(since)  # oldest first
    hist = {}
    for row in archive:
        ids = row.get("ids") or []
        if ids:
            hist.setdefault(row["source"], []).append(ids[0])

    candidates = []
    for src in sources:
        name = src["name"]
        if name in RANK1_EXEMPT:
            continue
        seen = hist.get(name, [])
        if len(seen) < RANK1_MIN_ROWS or len(set(seen)) > 1:
            continue
        candidates.append((src, seen[0], len(seen)))
    if not candidates:
        return []
    # The archive has to span the window, or a store that only started
    # yesterday would flag every outlet at once.
    need_oldest = (since_dt + timedelta(hours=RANK1_COVERAGE_SLACK_H)).strftime(TS_FMT)
    if min(r["ts"] for r in archive) > need_oldest:
        return []

    urls = {r["id"]: r.get("url") for r in load_all_items()}
    alerts = []
    for src, iid, n in candidates:
        url = urls.get(iid)
        alerts.append({
            "key": f"rank1_frozen:{src['name']}",
            "title": (f"{src['display']}: the same link has been rank 1 in all {n} runs "
                      f"of the last {RANK1_FROZEN_DAYS} days"),
            "detail": (f"item {iid}" + (f" — {url}" if url else "")
                       + "; audit with scripts/audit_headlines.py (page chrome at rank 1?)"),
        })
    return alerts


def headline_drop(now, rows, skip=()):
    """[{key, title, detail}] for outlets whose extraction count collapsed
    against their own trailing median.

    `rows` are snapshot rows over DROP_WINDOW_H; `skip` names sources already
    alerting as down/empty, so one broken outlet raises one condition.
    """
    by_src = {}
    for r in rows:
        if r.get("fetch_ok") == "1":
            by_src.setdefault(r["source"], []).append(r)
    alerts = []
    for name, hist in sorted(by_src.items()):
        if name in skip:
            continue
        hist.sort(key=lambda r: r["ts"])
        if len(hist) < DROP_RECENT_RUNS + DROP_MIN_BASELINE_ROWS:
            continue
        counts = [int(r.get("total_items") or 0) for r in hist]
        baseline, recent = counts[:-DROP_RECENT_RUNS], counts[-DROP_RECENT_RUNS:]
        med = statistics.median(baseline)
        if med < DROP_MIN_MEDIAN or max(recent) >= DROP_RATIO * med:
            continue
        alerts.append({
            "key": f"headline_drop:{name}",
            "title": (f"{name}: only {max(recent)} headlines extracted in the last "
                      f"{DROP_RECENT_RUNS} runs, against a median of {med:g}"),
            "detail": (f"last {DROP_RECENT_RUNS} runs: {recent}; 7-day median {med:g}; "
                       "the selector/skip rules probably no longer match the page"),
        })
    return alerts


def check(now, sources, per_source, scored):
    """Return [{key, title, detail}] for the conditions holding after this run.

    `scored` is (n_scored, n_pending) or None when the LLM passes were skipped.
    """
    alerts = []

    errors = list(LLM_ERRORS)
    billing = [m for _, m in errors if _BILLING_PAT.search(m)]
    if billing:
        alerts.append({"key": "llm", "title": "Anthropic API rejected every call (billing/auth)",
                       "detail": billing[-1]})
    elif errors and scored and scored[1] and scored[0] == 0:
        alerts.append({"key": "llm",
                       "title": f"LLM scoring failed for all {scored[1]} pending items",
                       "detail": errors[-1][1]})

    week = _recent_snapshot_rows(now, DROP_WINDOW_H)
    since_24h = (now - timedelta(hours=WINDOW_H)).strftime(TS_FMT)
    rows = [r for r in week if r["ts"] >= since_24h]
    by_src = {}
    for r in rows:
        by_src.setdefault(r["source"], []).append(r)
    for src in sources:
        name = src["name"]
        hist = by_src.get(name, [])
        if len(hist) < MIN_RUNS:
            continue
        ok = [r for r in hist if r.get("fetch_ok") == "1"]
        if not ok:
            err = per_source.get(name, {}).get("err", "")
            alerts.append({"key": f"source_down:{name}",
                           "title": f"{src['display']}: fetch failed in all {len(hist)} runs of the last {WINDOW_H}h",
                           "detail": err})
        elif len(ok) == len(hist) and all(int(r.get("total_items") or 0) == 0 for r in ok):
            alerts.append({"key": f"source_empty:{name}",
                           "title": f"{src['display']}: zero headlines extracted in all {len(hist)} runs of the last {WINDOW_H}h",
                           "detail": "fetch succeeds; the parser (selector/skip/feed) no longer matches the page"})

    # Parser canaries. Each one is wrapped on its own: a bug in a canary must
    # not swallow the conditions above (run.py's try/except would lose them all).
    broken = {k.split(":", 1)[1] for k in (a["key"] for a in alerts) if ":" in k}
    for name, fn in (("rank1_frozen", lambda: rank1_frozen(now, sources)),
                     ("headline_drop", lambda: headline_drop(now, week, broken))):
        try:
            alerts.extend(fn())
        except Exception as e:  # noqa: BLE001
            print(f"health: {name} canary failed ({e}); continuing", flush=True)
    return alerts


def write(ts, alerts):
    LOGS.mkdir(exist_ok=True)
    with open(HEALTH_PATH, "w") as f:
        json.dump({"ts": ts, "alerts": alerts}, f, ensure_ascii=False, indent=1)
