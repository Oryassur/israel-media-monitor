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
"""
import csv
import json
import re
from datetime import timedelta

from .common import DATA, LLM_ERRORS, LOGS, month_key

HEALTH_PATH = LOGS / "health.json"
WINDOW_H = 24
MIN_RUNS = 6  # a source must have at least this many rows in the window to be judged
_BILLING_PAT = re.compile(r"credit balance|billing|authentication|invalid x-api-key|api key|"
                          r"permission_error|Error code: 40[13]", re.I)


def _recent_snapshot_rows(now):
    """Snapshot rows from the last WINDOW_H hours (current + previous month files)."""
    since = (now - timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    months = {month_key(now.strftime("%Y-%m")), month_key(since[:7])}
    rows = []
    for m in sorted(months):
        path = DATA / "snapshots" / f"{m}.csv"
        if not path.exists():
            continue
        with open(path, newline="") as f:
            rows.extend(r for r in csv.DictReader(f) if r["ts"] >= since)
    return rows


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

    rows = _recent_snapshot_rows(now)
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
    return alerts


def write(ts, alerts):
    LOGS.mkdir(exist_ok=True)
    with open(HEALTH_PATH, "w") as f:
        json.dump({"ts": ts, "alerts": alerts}, f, ensure_ascii=False, indent=1)
