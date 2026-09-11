"""Shared paths, config loading, and small helpers."""
import hashlib
import json
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
DOCS_DATA = ROOT / "docs" / "data"
LOGS = ROOT / "logs"

METHOD_VERSION = "v2"  # prominence weighting: 10/5/3/1 over top-20, 0 beyond
RUBRIC_VERSION = "v3.1"  # v3 (blind QA round 2) + Israeli tech/business = related, +1; uncertainty -> 0
RUBRIC_PATH = ROOT / "prompts" / f"sentiment_rubric_{RUBRIC_VERSION}.md"
SCORING_MODEL = "claude-sonnet-5"

# Story clustering (bumping CLUSTER_VERSION re-clusters items without
# touching their sentiment scores)
CLUSTER_VERSION = "c1"
CLUSTER_MODEL = "claude-sonnet-5"
CLUSTER_PROMPT_PATH = ROOT / "prompts" / f"cluster_v_{CLUSTER_VERSION}.md"

# International-coverage benchmark (domestic vs. international + topic).
# i2 (2026-09-11): any story with another country as a subject is international,
# including bilateral ones; Israel-as-party stories always get israel-gaza.
INTL_VERSION = "i2"
INTL_MODEL = "claude-haiku-4-5-20251001"
INTL_PROMPT_PATH = ROOT / "prompts" / f"intl_v_{INTL_VERSION}.md"
MAX_INTL_ITEMS_PER_RUN = 600

# Retry scoring for unscored items this long after first_seen (hours)
SCORE_RETRY_WINDOW_H = 48

# Article enrichment (og:image + description) for prominent related items.
# Best-effort, hotlinked URLs only; see pipeline/enrich.py.
ENRICH_MIN_WEIGHT = 3        # only headlines that reached a homepage top-10
ENRICH_MAX_PER_RUN = 40      # article pages fetched per hourly run
ENRICH_MAX_ATTEMPTS = 3      # then give up on that item
ENRICH_BUDGET_S = 120        # hard wall-clock stop for the whole pass
ENRICH_FETCH_TIMEOUT = 12
ENRICH_HOST_GAP_S = 1.0      # politeness gap between fetches to one host


def load_sources():
    with open(CONFIG / "sources.yaml") as f:
        return yaml.safe_load(f)["sources"]


def load_keywords():
    with open(CONFIG / "keywords.yaml") as f:
        kw = yaml.safe_load(f)
    return {lang: [str(t).lower() for t in terms] for lang, terms in kw.items() if lang != "common"}


# Trailing link-text metadata some homepages (notably BBC) append to headlines:
# a relative-time marker ("5 hrs ago", "il y a 3 heures", ...) optionally followed
# by a short section label ("Middle East", "US & Canada"). The time part mutates
# hourly, so it must not participate in the dedup hash. Conservative by design:
# only fires on a recognized time phrase at the very end, never mid-headline.
_META_SUFFIX = re.compile(
    r"""\s+(?:
        \d+\s*(?:min(?:ute)?s?|hrs?|hours?|days?)\s+ago      # en
      | il\s+y\s+a\s+\d+\s*(?:min(?:ute)?s?|heures?|jours?)  # fr
      | vor\s+\d+\s*(?:min(?:ute)?n?\.?|std\.?|stunden?|tag(?:en)?)  # de
      | hace\s+\d+\s*(?:min(?:uto)?s?|horas?|d[ií]as?)       # es
      | \d+\s*(?:minut[oi]|ore?|giorn[oi])\s+fa              # it
    )
    (?:\s+(?:&|[^\W\d][\w'’-]*)(?:\s+(?:&|[^\W\d][\w'’-]*)){0,3})?  # optional section label, <=4 words
    \s*$""",
    re.IGNORECASE | re.VERBOSE | re.UNICODE,
)


def strip_meta_suffix(headline: str) -> str:
    return _META_SUFFIX.sub("", headline)


def item_id(source: str, headline: str) -> str:
    norm = re.sub(r"\s+", " ", strip_meta_suffix(headline).strip().lower())
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
