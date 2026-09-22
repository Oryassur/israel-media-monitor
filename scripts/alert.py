#!/usr/bin/env python3
"""Turn logs/health.json into an email: one GitHub issue per incident.

Runs as the last workflow step (always, even after a failed pipeline step).
GitHub emails the repository owner for issues they are @mentioned in, so the
issue is the mail — no SMTP secrets needed.

  alerts present, no open `pipeline-alert` issue  -> open one (email)
  alerts present, open issue, same set of keys    -> nothing (no hourly spam)
  alerts present, open issue, set changed         -> comment with the new list (email)
  no alerts, open issue                           -> comment "recovered" + close (email)

Env (all set by GitHub Actions): GH_TOKEN, GITHUB_REPOSITORY, GITHUB_REPOSITORY_OWNER,
GITHUB_SERVER_URL, GITHUB_RUN_ID, plus PIPELINE_OUTCOME (the pipeline step's
outcome, passed from the workflow).  `--dry-run` prints the gh commands instead.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEALTH = ROOT / "logs" / "health.json"
LABEL = "pipeline-alert"
MARK = "<!-- pipeline-alert keys: "
DRY = "--dry-run" in sys.argv


def gh(*args, capture=False):
    cmd = ["gh", *args]
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and args[0] in ("issue", "label"):
        cmd += ["-R", repo]
    if DRY:
        print("DRY:", " ".join(a if len(a) < 60 else a[:57] + "..." for a in cmd))
        return ""
    res = subprocess.run(cmd, text=True, capture_output=capture, check=False)
    if res.returncode:
        sys.exit(f"gh failed ({res.returncode}): {' '.join(args[:3])}\n{res.stderr if capture else ''}")
    return res.stdout if capture else ""


def load_alerts():
    alerts = []
    ts = None
    if HEALTH.exists():
        h = json.loads(HEALTH.read_text())
        alerts, ts = list(h.get("alerts", [])), h.get("ts")
    outcome = os.environ.get("PIPELINE_OUTCOME", "success")
    if outcome not in ("success", ""):
        alerts.insert(0, {"key": "run_failed", "title": f"pipeline step ended with outcome '{outcome}'",
                          "detail": "see the run log"})
    return alerts, ts


def run_url():
    base, rid = os.environ.get("GITHUB_SERVER_URL", "https://github.com"), os.environ.get("GITHUB_RUN_ID")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    return f"{base}/{repo}/actions/runs/{rid}" if rid and repo else "(local run)"


def body_for(alerts, ts):
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    lines = [f"@{owner} — the hourly pipeline detected:" if owner else "The hourly pipeline detected:", ""]
    for a in alerts:
        d = f" — `{a['detail'][:200]}`" if a.get("detail") else ""
        lines.append(f"- **{a['title']}**{d}")
    lines += ["", f"Run: {run_url()} · detected at {ts or 'n/a'}", "",
              "This issue is closed automatically once a run comes back clean.",
              f"{MARK}{','.join(a['key'] for a in alerts)} -->"]
    return "\n".join(lines)


def keys_in(body):
    i = body.find(MARK)
    if i < 0:
        return set()
    return set(k for k in body[i + len(MARK):body.find("-->", i)].strip().split(",") if k)


def main():
    alerts, ts = load_alerts()
    out = gh("issue", "list", "--label", LABEL, "--state", "open", "--limit", "1",
             "--json", "number,body", capture=True)
    open_issues = json.loads(out) if out else []
    issue = open_issues[0] if open_issues else None

    if not alerts:
        if issue:
            gh("issue", "comment", str(issue["number"]), "--body",
               f"Recovered: the run at {ts or 'n/a'} came back clean. {run_url()}")
            gh("issue", "close", str(issue["number"]))
            print(f"closed #{issue['number']} (recovered)")
        else:
            print("healthy, nothing open")
        return 0

    title = "Pipeline alert: " + " · ".join(a["title"] for a in alerts)[:200]
    body = body_for(alerts, ts)
    if issue is None:
        gh("label", "create", LABEL, "--color", "d73a4a", "--force",
           "--description", "opened by the hourly pipeline's health check")
        gh("issue", "create", "--title", title, "--label", LABEL, "--body", body)
        print(f"opened issue: {title}")
    elif keys_in(issue["body"]) != {a["key"] for a in alerts}:
        gh("issue", "comment", str(issue["number"]), "--body", "Update — " + body)
        gh("issue", "edit", str(issue["number"]), "--title", title, "--body", body)
        print(f"updated #{issue['number']}: {title}")
    else:
        print(f"#{issue['number']} already covers: {', '.join(a['key'] for a in alerts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
