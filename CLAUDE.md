# DJ1 — Israel in Western Media

Hourly pipeline measuring Israel's perception in western media: editorial
attention (prominence-weighted share of 20 major homepages) and headline framing
sentiment (−2…+2, LLM-scored against a versioned rubric), with an interactive
dashboard.

A sibling repo, **`Oryassur/il-media-data-stories-monitor`** (local:
`~/Desktop/il-media-data-stories-monitor`), applies the same ingestion
architecture to 12 Israeli outlets; its analysis layer ("data stories") is TBD.
The retired Netanyahu-family monitor (`bibi-media-monitor/`) was moved there as
an archive — its history stays in this repo's git log. A third sibling
("IL media — headlines alignment") is planned, consuming the Israeli repo's raw
archive rather than re-fetching.

## Architecture

```
config/sources.yaml        30 outlets: url, country, lang, lean (3-way: left/center/right, from AllSides / Ad Fontes ratings — basis commented per source), type, optional home scope + selector
config/keywords.yaml       multilingual Israel keyword pre-filter (en/fr/de/es/it)
prompts/sentiment_rubric_v3.1.md the scoring rubric (versioned — see below; older versions kept for history)
prompts/cluster_v_c1.md    story-clustering rubric (versioned via CLUSTER_VERSION)
prompts/intl_v_i1.md       domestic-vs-international rubric (versioned via INTL_VERSION)
pipeline/                  the whole pipeline (plain Python, no agent in the loop)
  run.py                   hourly cycle: fetch → extract → detect → score → cluster → intl → store → publish
  extract.py               homepage HTML → ranked headlines; prominence weights v2 (rank1 ×10, 2–5 ×5, 6–10 ×3, 11–20 ×1, 21+ ×0)
  detect.py                keyword matching per language
  score.py                 LLM sentiment (backends: anthropic API / claude CLI); batch, cached per headline
  cluster.py               LLM story clustering: related items → cross-outlet stories (claude-sonnet-5, "c1")
  intl.py                  LLM international benchmark over ALL top-20 headlines (claude-haiku-4-5-20251001, "i1")
  store.py                 data/items + data/stories + data/allitems (monthly jsonl, rewritten) ·
                           data/snapshots (monthly csv, append-only) · data/intl (monthly jsonl, append-only)
  publish.py               builds docs/data/*.json (incl. stories.json) for the dashboard
docs/                      GitHub Pages dashboard (vanilla JS/SVG, self-contained)
.github/workflows/pipeline.yml   hourly cron on GitHub Actions (secret: ANTHROPIC_API_KEY)
```

## Invariants — keep these true

- **Attention share** (method v2) = Israel-weighted headlines ÷ total weight of the
  top-20 window per homepage. Prominence weights: rank 1 ×10, 2–5 ×5, 6–10 ×3,
  11–20 ×1, 21+ ×0. Only the top-20 window is ingested as items (since
  2026-09-09); stories beyond it count toward total_items/total_weight for
  parser health but are never tracked. Sources are equal-weighted in
  aggregates. Failed fetches are recorded as missing, never zero.
- **Sentiment is framing toward Israel**, not generic positivity. Every score
  stores model + rubric version; changing either means bumping `RUBRIC_VERSION`
  in `pipeline/common.py`, never silently mixing.
- **Each headline is scored once** (cached by id = hash(source, normalized text));
  unscored items retry for 48h.
- **Snapshot composition columns** w_n2,w_n1,w_0,w_p1,w_p2,w_u split each run's
  israel_weight by sentiment bucket (w_u = present but unscored); their sum
  always equals israel_weight, blanks on failed fetches. Old months keep old
  headers — consumers must read via row.get(). publish approximates comp for
  rows older than meta.comp_exact_since.
- **Story clustering**: related items carry story + cluster_v; the registry
  (data/stories/) holds {id,title,first_seen,last_seen,model,cv} and never item
  lists. Bumping `CLUSTER_VERSION` re-clusters without touching sentiment.
- **International benchmark**: every top-20 headline is recorded in
  data/allitems/ and classified (intl/topic/iv/model) against the outlet's
  `home` scope; per-run aggregates append to data/intl/
  ({ts,source,total_w,intl_w,uncl_w,topics}). The whole pass is best-effort —
  it must never fail the hourly run.
- Every new LLM pass follows score.py's pattern: per-batch try/except, log,
  retry next run; model + prompt version recorded on each record.
- Blocked sources (401/402/403) get swapped for an equivalent outlet, preserving
  country/lean balance — WSJ, WaPo, Reuters, Telegraph, Sky, France24, Politico
  are known-blocked (plus, from runner IPs: The Hill, news.com.au, Ouest-France,
  NewsNation).
- Dashboard reads only `docs/data/*.json`; keep it dependency-free (the one
  external resource is the Fraunces display font from Google Fonts, with a
  Georgia fallback) and light/dark-safe — three CSS token blocks (light,
  prefers-dark guarded, `[data-theme=dark]`) that must stay in sync; SVG fills
  use `var(--token)` so theme flips never leave stale colors. Editorial layout
  order is masthead → controls → hero verdict → chart → stories; spike
  annotations come from story clusters (combined view, 7-day items window,
  one per distinct story, measured after the svg is in the DOM).

## Retired: bibi monitor

`bibi-media-monitor/`, `docs/bibi/`, and `bibi-pipeline.yml` were removed
2026-09-09; the monitor and its data live on as `archive/bibi-monitor/` in the
`il-media-data-stories-monitor` repo. Do not re-add them here. The repo secret
`ANTHROPIC_API_KEY_BIBI` is obsolete (owner removes it in GitHub settings).
