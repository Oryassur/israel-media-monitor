---
name: run-pipeline
description: Run, test, or debug the Israel-media-monitoring pipeline locally, and preview the dashboard. Use whenever the user asks to run the pipeline, fetch fresh data, check why a source is failing, rescore sentiment, or view/work on the dashboard.
---

# Run Pipeline

The whole pipeline is the Python package `pipeline/` (fetch → extract → detect →
score → store → publish). Production runs hourly on GitHub Actions
(`.github/workflows/pipeline.yml`); this skill is for local runs and debugging.

## Commands

```bash
.venv/bin/python -m pipeline.run            # full cycle (sentiment needs ANTHROPIC_API_KEY or a logged-in claude CLI)
.venv/bin/python -m pipeline.run --no-llm   # fetch/volume only, skip sentiment
.venv/bin/python -m pipeline.publish        # rebuild docs/data/*.json from stored data without fetching
```

Preview the dashboard by serving `docs/` (e.g. `python3 -m http.server 8741 --directory docs`)
— it fetches `data/*.json`, so `file://` won't work.

## Key facts

- Sources: `config/sources.yaml` (20 outlets + metadata). Keyword pre-filter: `config/keywords.yaml`.
- Sentiment rubric: `prompts/sentiment_rubric_v2.md`. Changing rubric or model requires bumping
  `RUBRIC_VERSION` in `pipeline/common.py` — never silently mix scoring configurations.
- Data: `data/items/YYYY-MM.jsonl` (unique headlines), `data/snapshots/YYYY-MM.csv` (source-hour stats).
- A source printing `EMPTY EXTRACTION` or repeated `FETCH FAIL` (401/402/403 = bot-blocked)
  should be investigated and, if hard-blocked, swapped for an equivalent outlet
  (keep country/lean balance in sources.yaml).
- Failed fetches are recorded as missing, never zero; charts and aggregates must keep it that way.
