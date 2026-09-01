# DJ1 — Israel in Western Media

Hourly pipeline measuring Israel's perception in western media: editorial
attention (prominence-weighted share of 20 major homepages) and headline framing
sentiment (−2…+2, LLM-scored against a versioned rubric), with an interactive
dashboard.

A sibling monitor, **`bibi-media-monitor/`**, applies the same architecture to
Israeli outlets, measuring attention/sentiment toward Benjamin Netanyahu and his
family — see "Bibi monitor" below.

## Architecture

```
config/sources.yaml        21 outlets: url, country, lang, lean (3-way: left/center/right, from AllSides / Ad Fontes ratings — basis commented per source), type
config/keywords.yaml       multilingual Israel keyword pre-filter (en/fr/de/es/it)
prompts/sentiment_rubric_v2.md   the scoring rubric (versioned — see below)
pipeline/                  the whole pipeline (plain Python, no agent in the loop)
  run.py                   hourly cycle: fetch → extract → detect → score → store → publish
  extract.py               homepage HTML → ranked headlines; prominence weights v2 (rank1 ×10, 2–5 ×5, 6–10 ×3, 11–20 ×1, 21+ ×0)
  detect.py                keyword matching per language
  score.py                 LLM sentiment (backends: anthropic API / claude CLI); batch, cached per headline
  store.py                 data/items/YYYY-MM.jsonl + data/snapshots/YYYY-MM.csv
  publish.py               builds docs/data/*.json for the dashboard
docs/                      GitHub Pages dashboard (vanilla JS/SVG, self-contained)
.github/workflows/pipeline.yml   hourly cron on GitHub Actions (secret: ANTHROPIC_API_KEY)
```

## Invariants — keep these true

- **Attention share** (method v2) = Israel-weighted headlines ÷ total weight of the
  top-20 window per homepage. Prominence weights: rank 1 ×10, 2–5 ×5, 6–10 ×3,
  11–20 ×1, 21+ ×0 (tracked + scored as "below fold", outside the indexes); sources are equal-weighted in aggregates. Failed fetches are recorded
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

## Bibi monitor (`bibi-media-monitor/`)

A self-contained fork of the pipeline (own `config/`, `prompts/`, `pipeline/`,
`data/`) monitoring 12 Israeli outlets for attention/sentiment toward Benjamin
Netanyahu and his family. Run from inside the folder: `python -m pipeline.run`.
All invariants above apply, plus:

- Hebrew keyword matching is **substring-based** (prefixes attach: לנתניהו),
  and generic PM references (ראש הממשלה, רה"מ) count as candidates — the LLM
  `related` pass makes the final call.
- Lean (Israeli spectrum) and the `econ: true` tag (Globes, TheMarker,
  Calcalist) are owner-assigned in `bibi-media-monitor/config/sources.yaml`;
  the dashboard has a dedicated econ filter and "Econ vs. general" split.
- Snapshot fields are `topic_items`/`topic_weight` (not `israel_*`).
- Dashboard lives at `docs/bibi/`, reads only `docs/bibi/data/*.json`; Hebrew
  headlines render with `dir="auto"`.
- Separate workflow `.github/workflows/bibi-pipeline.yml` (cron :17/:47) with
  its **own secret `ANTHROPIC_API_KEY_BIBI`** — never reuse the main key.
