# DJ1 — Israel in Western Media

Hourly pipeline measuring Israel's perception in western media: editorial
attention (prominence-weighted share of 20 major homepages) and headline framing
sentiment (−2…+2, LLM-scored against a versioned rubric), with an interactive
dashboard.

## Architecture

```
config/sources.yaml        20 outlets: url, country, lang, lean, type
config/keywords.yaml       multilingual Israel keyword pre-filter (en/fr/de/es/it)
prompts/sentiment_rubric_v1.md   the scoring rubric (versioned — see below)
pipeline/                  the whole pipeline (plain Python, no agent in the loop)
  run.py                   hourly cycle: fetch → extract → detect → score → store → publish
  extract.py               homepage HTML → ranked headlines; prominence weights (top5 ×3, top quarter ×2, rest ×1)
  detect.py                keyword matching per language
  score.py                 LLM sentiment (backends: anthropic API / claude CLI); batch, cached per headline
  store.py                 data/items/YYYY-MM.jsonl + data/snapshots/YYYY-MM.csv
  publish.py               builds docs/data/*.json for the dashboard
docs/                      GitHub Pages dashboard (vanilla JS/SVG, self-contained)
.github/workflows/pipeline.yml   hourly cron on GitHub Actions (secret: ANTHROPIC_API_KEY)
```

## Invariants — keep these true

- **Attention share** = Israel-weighted headlines ÷ total-weighted headlines per
  homepage; sources are equal-weighted in aggregates. Failed fetches are recorded
  as missing, never zero.
- **Sentiment is framing toward Israel**, not generic positivity. Every score
  stores model + rubric version; changing either means bumping `RUBRIC_VERSION`
  in `pipeline/common.py`, never silently mixing.
- **Each headline is scored once** (cached by id = hash(source, normalized text));
  unscored items retry for 48h.
- Blocked sources (401/402/403) get swapped for an equivalent outlet, preserving
  country/lean balance — WSJ, WaPo, Reuters, Telegraph, Sky, France24, Politico
  are known-blocked.
- Dashboard reads only `docs/data/*.json`; keep it dependency-free and
  light/dark-safe (CSS tokens per the dataviz skill's reference palette).
