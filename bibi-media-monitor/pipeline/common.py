"""Shared paths, config loading, and small helpers (bibi-media-monitor).

ROOT is the bibi-media-monitor/ folder; the dashboard JSON is published into
the repo-level docs/bibi/data/ so GitHub Pages serves both monitors.
"""
import hashlib
import json
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent          # bibi-media-monitor/
REPO = ROOT.parent                                     # repo root
CONFIG = ROOT / "config"
DATA = ROOT / "data"
DOCS_DATA = REPO / "docs" / "bibi" / "data"
LOGS = ROOT / "logs"

METHOD_VERSION = "v2"  # prominence weighting: 10/5/3/1 over top-20, 0 beyond
RUBRIC_VERSION = "v1"
RUBRIC_PATH = ROOT / "prompts" / f"sentiment_rubric_{RUBRIC_VERSION}.md"
SCORING_MODEL = "claude-haiku-4-5-20251001"

# Retry scoring for unscored items this long after first_seen (hours)
SCORE_RETRY_WINDOW_H = 48


def load_sources():
    with open(CONFIG / "sources.yaml") as f:
        return yaml.safe_load(f)["sources"]


def load_keywords():
    with open(CONFIG / "keywords.yaml") as f:
        kw = yaml.safe_load(f)
    return {lang: [str(t).lower() for t in terms] for lang, terms in kw.items() if lang != "common"}


def item_id(source: str, headline: str) -> str:
    norm = re.sub(r"\s+", " ", headline.strip().lower())
    return hashlib.sha1(f"{source}|{norm}".encode()).hexdigest()[:16]


def month_key(ts_iso: str) -> str:
    return ts_iso[:7]  # YYYY-MM


def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
