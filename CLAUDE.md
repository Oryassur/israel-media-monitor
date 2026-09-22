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
prompts/subjects_v_s1.md   subject + figures tagging rubric (versioned via SUBJECT_VERSION; living vocabulary + name reconciliation)
prompts/intl_v_i3.md       domestic-vs-international rubric (versioned via INTL_VERSION; i2 = any story with another
                           country as a subject is intl, incl. bilateral; Israel-as-party ⇒ israel-gaza; i3 adds
                           north-america + royals). publish.INTL_GROUPS folds slugs into the dashboard's 12 subject groups
pipeline/                  the whole pipeline (plain Python, no agent in the loop)
  run.py                   hourly cycle: fetch → extract → detect → score → cluster → subjects → intl → enrich → store → publish → health
                           (--retry-hours N: one-off backfill of the unscored backlog after an outage)
  extract.py               homepage HTML → ranked headlines; prominence weights v2 (rank1 ×10, 2–5 ×5, 6–10 ×3, 11–20 ×1, 21+ ×0);
                           fetch_feed: bot-walled outlets measured on their front-page RSS (`feed:` in sources.yaml — NYT)
  health.py                end-of-run alert conditions → logs/health.json (LLM dead, source down/empty 24h); never committed
  detect.py                keyword matching per language
  score.py                 LLM sentiment (backends: anthropic API / claude CLI); batch, cached per headline
  cluster.py               LLM story clustering: related items → cross-outlet stories (claude-sonnet-5, "c1")
  subjects.py              LLM subject + figures per related item (claude-sonnet-5, "s1"); ≤300/run newest first, self-backfilling
  intl.py                  LLM international benchmark over ALL top-20 headlines (claude-haiku-4-5-20251001, "i3")
  enrich.py                article-page og:image + description for related top-10 items (no LLM; best-effort)
  store.py                 data/items + data/stories + data/allitems (monthly jsonl, rewritten) ·
                           data/snapshots (monthly csv, append-only) · data/intl (monthly jsonl, append-only)
  publish.py               builds docs/data/*.json for the dashboard (items 30d w/ img+desc; stories {id:{t,fs,ls}};
                           meta.sources w/ home, domain, logo)
scripts/alert.py           workflow's last step: health.json → one GitHub issue per incident (@mentions the owner ⇒ email),
                           updated when the condition set changes, auto-closed on the first clean run
scripts/fetch_wordmarks.py one-off: outlet wordmark logos (Wikipedia infobox, header <img> fallback) → docs/logos/<name>.svg|png
                           (committed by hand; re-run on source swaps; foxnews.svg + bbc.svg are hand-placed variants;
                           fetch_logos.py is the square-favicon fallback)
docs/                      GitHub Pages dashboard "The Israel Mirror" (vanilla JS/SVG, self-contained) + docs/logos/ + docs/fonts/
.github/workflows/pipeline.yml   hourly on GitHub Actions (secret: ANTHROPIC_API_KEY). GitHub's cron fires ~24% of its
                           slots; the real scheduler is an external pinger (cron-job.org → workflow_dispatch at :45,
                           99% hourly recall). Dispatch input `retry_hours` = backfill run.
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
  ({ts,source,total_w,intl_w,uncl_w,topics,iv}). Bumping `INTL_VERSION`
  re-classifies whatever is on a homepage first (older-version records count
  as unclassified in that run's row), so no row mixes rubric versions; rows
  before the bump keep their old `iv` unless backfilled with
  `scripts/backfill_intl.py` (re-classifies every all-item, then rebuilds old
  rows approximately — headline present at best_weight between first/last seen,
  scaled to the run's exact total_w — and marks them `approx: true`). The whole
  pass is best-effort — it must never fail the hourly run.
- **Subjects** (V2.5, 2026-09-13): every related item carries `subject` (one label:
  established list → in-use label → newly minted, never "Other" unless nothing
  fits), `figures` (≤3 people, press short form, titles/bynames reconciled to one
  name), `sv`, `sm`. Bumping `SUBJECT_VERSION` re-tags the backlog over a few
  hourly runs (newest first, `MAX_SUBJECT_ITEMS_PER_RUN`); no backfill workflow.
  Best-effort — must never fail the hourly run. The dashboard's Subjects cloud
  (third strip of the attention card) is built client-side from `sj`/`fg`.
- Every new LLM pass follows score.py's pattern: per-batch try/except, log,
  retry next run; model + prompt version recorded on each record.
- **Enrichment** (V2, 2026-09-11): items with `related` and (`best_weight ≥ 3` or
  `category == "opinion"`, any rank) get
  one article-page fetch per run slot (≤40/run, 120 s budget, ≤3 attempts, retries
  only within 48 h of first_seen) storing `img` (hotlinked https URL, never
  downloaded), `desc` (≤300 chars), `enr`, `enr_n`. Best-effort — must never fail
  the hourly run. NYT article pages 403 from everywhere; expected to give up.
- **Page chrome is never a headline** (2026-09-15): extract.py drops page-level
  headers, nav/menus/popins, newsletter/promo/subscription containers, links to
  the homepage or to digit-free short-slug index pages, photo-credit link text,
  "Skip to…"/"Play …" affordances and hub/utility paths (tags, topics, games,
  account, programs…); sources may add `skip` CSS selectors (Spiegel) or a
  `selector` (Le Monde, Corriere…). Audit with `scripts/audit_headlines.py` —
  a link at the same rank for days is chrome unless the outlet is a slow weekly
  (CS Monitor). Per-run rankings are not stored, so past rows could only be
  re-estimated: snapshot rows with `approx=1` had their Israel weight re-scaled
  as if the chrome above each Israel item were gone (2026-09-09..15, 189 rows),
  and intl rows for those runs were rebuilt from presence windows (`approx`).
- **Mobile fronts** (2026-09-15, owner's choice "option 2"): CNN and USA Today edit a
  separate front page for phones (same-moment fetch showed 18% / 33% top-10 overlap
  with desktop; the other 28 outlets serve one front). They are fetched with the
  iPhone user agent (`ua: mobile` in sources.yaml) and measured on that front.
  Re-run the desktop-vs-mobile comparison when adding a source. Per-source knobs:
  `selector`, `skip` (CSS blocks), `lead` (visual lead link → rank 1), `site_hook`
  (extract.SITE_HOOKS, e.g. USA Today's embedded `gnt.fb` lists), `ua`.
- Parser health: Corriere needed `selector: main` (fixed 2026-09-11; its rows from
  2026-09-09 to 2026-09-11 07:45 UTC counted columnist boxes as headlines — attention 0,
  intl 0 — and are not recoverable). When a source's Israel share is flat zero, check
  its extracted headlines before trusting it.
- Blocked sources (401/402/403) get swapped for an equivalent outlet, preserving
  country/lean balance — WSJ, WaPo, Reuters, Telegraph, Sky, France24, Politico
  are known-blocked (plus, from runner IPs: The Hill, news.com.au, Ouest-France,
  NewsNation). Exception — **feed mode** (2026-09-22): an outlet with a curated
  *homepage* RSS feed in editorial order can keep being measured on it (`feed:`
  in sources.yaml; rank = feed position, same top-20 window/weights, items arrive
  with img/desc from the feed so enrichment is skipped). NYT is measured this way
  since 2026-09-22 (DataDome-walled from 2026-09-15, 100% failed 09-18..22; it
  blocks archive.org's crawler too, so Wayback is no fallback). Never point
  `feed:` at a chronological section feed.
- **Alerting** (2026-09-22): the run stays green through LLM/fetch failures by
  design, so `health.check` runs last and `scripts/alert.py` opens/updates/closes
  a `pipeline-alert` GitHub issue (⇒ owner email). Keys: `llm` (billing/auth
  message, or 0/N scored with errors), `source_down:<name>`, `source_empty:<name>`
  (all runs of the last 24h, ≥6 rows), `run_failed`. Every LLM batch except-block
  calls `note_llm_error`.
- **Outage 2026-09-18 22:45 → 09-22 ~09:00 UTC** (API credits exhausted): no item
  scored/clustered/tagged, intl rows have uncl_w ≈ total_w, snapshot rows carry
  the candidates in w_u (attention slightly overstated by the LLM's usual ~3%
  rejections; sentiment blank). Recovery: `retry_hours` backfill run (scores +
  clusters the backlog past the 48 h window) and the backfill-intl workflow
  (its `apply` now also rebuilds rows with >25% unclassified weight, marked
  `approx`), then `scripts/rebuild_snapshot_sentiment.py START END --write`
  (redistributes each row's w_u over the sentiment buckets from the now-scored
  headlines, presence-window approximation, rows marked `approx=1`; 897 rows).
  Only the exact per-run rank of each headline is unrecoverable.
- Dashboard reads only `docs/data/*.json`; keep it dependency-free (the one
  external resource is the Fraunces display font from Google Fonts, with a
  Georgia fallback; the masthead uses the self-hosted "Old London" TTF in docs/fonts/) and light/dark-safe — three CSS token blocks (light,
  prefers-dark guarded, `[data-theme=dark]`) that must stay in sync; SVG fills
  use `var(--token)` so theme flips never leave stale colors. Editorial layout
  order is a sticky band (masthead → subtitle → rule → filters + live line) →
  front unit (attention card | lead story | stories 2–4, with a shared
  expansion row for "and N more") → chart → stories list; spike annotations come
  from story clusters (combined view, items window = meta.items_window_days,
  one per distinct story, measured after the svg is in the DOM).
- **Front-page bundles** are computed client-side from items.json: clustered
  items only, ranked by Σ prominence weight within the selected period + filters;
  card headline = best placement (ties → best rank → newest) that has an image,
  else the lead text-only; bundle sentiment = prominence-weighted mean (shown as a
  chip overlaid on the card image). Every headline row shows the outlet's
  wordmark (no flags since 2026-09-12) with no chip/background (dark mode inverts text-only wordmarks via
  CSS filter; logos in `FIELD_LOGOS` keep their own colored field; uppercase-name fallback) —
  the outlet name is never repeated as text. Headlines truncate at 100 chars,
  the lead standfirst at 150; date + hour and the sentiment chip sit right-aligned
  on every card. No "top story / top N" placement labels in the UI.

## Retired: bibi monitor

`bibi-media-monitor/`, `docs/bibi/`, and `bibi-pipeline.yml` were removed
2026-09-09; the monitor and its data live on as `archive/bibi-monitor/` in the
`il-media-data-stories-monitor` repo. Do not re-add them here. The repo secret
`ANTHROPIC_API_KEY_BIBI` is obsolete (owner removes it in GitHub settings).
