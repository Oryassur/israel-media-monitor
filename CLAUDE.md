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
- **Clustering context** (2026-11-05): the model is NOT given the whole live registry.
  It gets `cluster.shortlist`: the `ACTIVE_RECENT_KEEP` (10) most recently seen stories
  unconditionally, then the rest ranked by vocabulary overlap with the batch, capped at
  `ACTIVE_SHORTLIST` (30). The recency block is load-bearing — a sibling cluster minted
  two hours ago shares no vocabulary yet, and that is exactly the duplicate case (the
  West Bank attack split into two stories 2h05m apart, 11 of 22 outlets filing into
  both). Each candidate also carries `recent`: its `STORY_SAMPLE` (2) newest headlines,
  rebuilt per run in `run.py` from the items index, because the registry deliberately
  holds no item lists. Before this the model matched a headline against ~100 bare
  titles, which is why two phases of one event ("campaign gains momentum" vs "holds
  election") were indistinguishable. Replayed on the run that misfiled DW's youth-vote
  headline: 95 active → 30 offered, both candidates present with discriminating
  evidence, prompt ~2,700 tokens against ~4,400 before — cheaper and better.
  `CLUSTER_VERSION` is deliberately **not** bumped: the rubric's decision rule is
  unchanged, and bumping re-clusters the whole window, which churns story ids
  (`sha1(title|first_seen)`), orphans them and would reshuffle the front page for no
  measured gain. Assignments made before this date simply had thinner context.
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
  leading section flags and relative timestamps ("• Breaking News", "BREAKING:",
  "Live"/"Liveblog", "Explainer", "In pictures", "a min ago") — these are **not**
  cosmetic, because the stored headline is what clustering sees, so a prefix splits one
  story in two; "Live" excludes "Live Aid" and "BREAKING" requires a colon so
  "Breaking point:" survives, and topic-tag prefixes ("Benjamin Netanyahu As a divided
  Israel …") are an arbitrary name and stay uncovered —
  "Skip to…"/"Play …" affordances and hub/utility paths (tags, topics, games,
  account, programs…); sources may add `skip` CSS selectors (Spiegel) or a
  `selector` (Le Monde, Corriere…). Audit with `scripts/audit_headlines.py` —
  a link at the same rank for days is chrome unless the outlet is a slow weekly
  (CS Monitor). Per-run rankings were not stored before 2026-10-21 (see the run
  archive below), so past rows could only be
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
  Parser canaries (2026-10-21) add `rank1_frozen:<name>` (same rank-1 item id in
  every archived run of the last 4 days — needs ≥24 rows and an archive that
  actually spans the window, CS Monitor exempt) and `headline_drop:<name>` (the
  last 3 runs all extracted <50% of that outlet's own 7-day median, median ≥10,
  sources already alerting as down/empty skipped). They are the loud half of
  `scripts/audit_headlines.py`; its short/no-verb/hub-url signals stay manual
  because they are too noisy to mail. Each canary is wrapped on its own so a bug
  in one cannot swallow the conditions above.
- **Run archive** (2026-10-21): `data/runs/YYYY-MM.jsonl` holds one row per
  (run, source) — `{ts, source, ids}`, the top-20 item ids in rank order. Headline
  and URL for an id live in `data/allitems`/`data/items`, so only the ORDER is new
  (~30 rows/run, ~22k rows/month). Pruned to `store.RUN_RETENTION_DAYS` = 90 on
  every write: month files wholly out of window are deleted, the cutoff month is
  filtered row by row. Failed or empty fetches get no row — missing, never an empty
  list. Best-effort like intl/enrich (`run.archive_run` never raises). This is what
  makes a future parser repair exact instead of `approx`; the bot's `git add data`
  already covers it. Rows written before a fix are still the only record of what
  the old parser saw, so never rewrite them in place.
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
- **Chart granularity** (2026-09-30): `publish.HOURLY_WINDOW_DAYS` = 30 (= items
  window) and `meta.hourly_window_days` tells the client. Hourly bars are offered on
  any window that reaches into the published range, not only on windows shorter than
  it; a longer window keeps its own bounds for the card/table figures while the chart
  starts where the hourly detail does. Hourly coverage is derived from the first
  `hourly.json` row (`HOURLY_FROM`), never from a `Date.now()` cutoff — a cutoff moves
  during a render, so a window starting on it (the 30d preset) flips between the
  hourly and daily pools mid-render. Card figures are means over the chart's buckets,
  so they still shift by ~0.1pt between granularities on the same window.
- **Reset** (2026-10-14) belongs to the Filters drawer it sits in: it clears region,
  lean and source only, and is hidden unless one of them is set. The period, custom
  range, granularity, split and story-list mode are chosen elsewhere and survive it.
- **Deep links** (2026-10-14): the view state rides in the query string — `p` (preset),
  `from`/`to` (custom range, YYYY-MM-DD), `g` (only when the user picked a granularity),
  `split`, `region`/`lean`/`src` (sorted comma lists), `list`. Defaults are omitted and
  sets sorted, so one view has exactly one URL; `render()` ends with `syncUrl()`
  and `boot()` calls `applyUrl()` before `buildControls()`.
  Back/Forward work (2026-10-21): `syncUrl` pushes only when the URL actually
  differs (render syncs every time, so otherwise every render would stack a
  duplicate), and the `replaceNext` flag makes the first sync of a page load and
  the sync after a popstate replace instead of push. `popstate` calls `resetView()`
  before `applyUrl()`, because Back hands over a whole URL, not a diff, and
  `applyUrl` only overlays the keys the query carries — without the reset, filters
  from the newer view would survive into the older one. Note `history.length` is a
  poor probe for this: pushing while forward entries exist truncates them, so the
  length can stay flat on a genuine push.
  Unknown keys/values are dropped, not errors. Query, not hash:
  Pages serves index.html for any query string, and `#method` already owns the hash.
  A *path* route (/30d/bbc) is the one thing Pages cannot do without a 404.html hack.
- **Lead card speaks for the bundle** (2026-11-05): the top-four cards are clusters of up to
  27 outlets, so the card leads with the cluster's own title (`STORIES[st].t`), not with one
  member headline — promoting a member made the card speak with one voice, and which voice was
  decided by who published an image (the slot went to Il Giornale 8% of cards, NY Post 8%,
  Washington Examiner 7%, i.e. whoever reliably carries pictures). `pickVoices` quotes
  **one outlet per lean** (owner's rule, 2026-11-05), ordered by the weight each bloc gave the
  story, so the rows mirror the bars above them. Each row prints its lean and that weight,
  because weight order is not the bars' fixed L-C-R order and a reader would otherwise map row 1
  to bar 1 and be wrong. Within a bloc the quote is chosen to be *typical* of it: target score 0
  when the bloc's mean framing sits inside ±`VOICE_MID` (0.2 since 2026-11-05, owner's call;
  was 0.33), −1 or +1 below/above, then the
  best-placed item carrying that score. **±2 items are never quoted** — they are opinion, and the
  Opinion & analysis strip is where they belong. The target bucket exists in 98% of bloc slots;
  the rest fall back to the nearest score, then to best placement.
  This shows *less* contrast than quoting each bloc's outlier would (measured spread 0.53 against
  2.33) and that is the intent: the bars measure the difference, the quotes illustrate what a bloc
  typically said. Expect ~60% of cards to show one score on all three rows, because 58% of bloc
  means fall inside the band — the blocs agreeing, not the rule failing. The band is a weak lever
  on that figure: ±0.2 moves 14% of bloc slots off the 0 target but leaves flat cards at 60%,
  because a card only reads flat when all three blocs land on the same bucket. A bloc with weight 0 **keeps its row** and says
  no outlet of that lean carried the story; never backfilled from another bloc, because the mark
  above draws a red tick for exactly that and a backfilled row would contradict it.
  A row stands for the **bloc, not the article** (2026-11-05): the left column carries the lean
  and that bloc's mean framing (the number its bar is coloured by), and the quoted article's own
  score is not shown — the row is the bloc's position and the quote is only its evidence. The
  article names itself underneath as `{placement} at {wordmark} + N more sites`, N being the other
  outlets **in that bloc**; the card-level "+ N news sites" is gone (`bundleMeta(b,false,false)`).
  Prominence weight is never printed — it is an internal unit.
  Headlines use `ht` (translation) when present, clamped to 3 lines. `+ N news sites` opens `#bundleDlg` (every headline
  plus the bloc grid); the old inline `#frontExpand` panel is gone. The lead image carries the plain
  `sentChip` (the bundle mean), **not** the compound chip: the lean rows state each bloc's framing
  and bar height stood for prominence weight, which the card no longer prints. The side rows (stories 2-4, 2026-11-05)
  follow the lead: same kicker, the cluster title as the headline, and one quoted article in the
  lead's row format. With a single quote the left column states the **whole story** — its mean plus
  `blocMark` — rather than a lean, and the picture carries no chip at all
  (`imageBox(..., withChip=false)`). The quote is `storyQuote`: the best-placed headline
  from the bloc with the most attention — the loudest voice in the loudest room, not the most
  typical one (owner's rule, 2026-11-05). The figure and `blocMark` sit under the picture
  (`.thcol`), not in the text column, so the headline keeps the full width.
  **Digests are never quoted** anywhere (`isDigest`): a "Morning Rundown:" link is several
  unrelated stories under one headline and sits at rank 1, so it kept winning slots. It still
  counts toward attention like any other front-page link — the rule governs quoting only. The
  prefix is the only reliable signal; "What to Know" explainers are single-subject and must stay
  (4 matches across 3,498 related headlines, all genuine NBC digests, no false positives). `.vb` is 19px, not 18, because border-box plus
  the 1px baseline rule would otherwise leave a 17px content area for the 18px scale `blocMark`
  draws to. The lead image cross-fades
  through up to three outlets' photographs from the story (`leadImage`, pure CSS; a
  `prefers-reduced-motion` viewer sees only the first frame) and carries **no outlet credit** —
  the card speaks for the bundle, so crediting one outlet would imply its lean over the rest, and
  `bundleMeta(b,false)` drops the "Top story at X" line on the lead for the same reason.
  **Story titles are coined once
  and never revisited** (see clustering), so the kicker dates the story — a 48-day-old title in
  21px needs the "since" anchor to read as an arc.
- **Format tags are never part of a headline** (2026-11-07): an item id is
  `hash(source, normalized headline)`, so a trailing `| VIDEO` / `– live` / `| FOTO` /
  `Show all` turns one story into two records, each keeping its own rank. Front-unit bundles
  sum `best_weight` across a story's items regardless of when each was seen, so one outlet's
  duplicate counted twice: Il Giornale ran the same headline 75 minutes apart, both at rank 1,
  and its **one-outlet** story reached the front unit's top four. `extract._LABEL_SUFFIX` strips
  these (a separator is required, so "returns home alive" survives; `MIN_HEADLINE_LEN` still
  guards a too-short remainder). `scripts/merge_suffix_dupes_2026-11-07.py` repaired the 11
  already stored and repointed 34 `data/runs` rows. It merges only when the stripped id already
  exists — a tag on the only copy is cosmetic, and rewriting it would change an id that
  `data/runs` references — and refuses a pair whose windows overlap, because that means a run
  saw both and the snapshots need a weight rebuild, not a merge (1 such pair was skipped).
- **Copy is American English** (2026-11-07, owner's call): color, center, labeled, normalized,
  favorable. The page had drifted British (17 `colour`), so the whole visible surface and the
  comments beside it were converted in one pass; keep new copy American.
- **One spelling for a lean** (2026-11-07): `center` is the stored value — `sources.yaml`,
  `LEAN_ORDER`, the `?lean=` query — and never changes; renaming it would break saved links and
  the archive. Everything a reader sees goes through `LEAN_CAP` ("Center") or `LEAN_LC`
  ("center"), defined beside `LEAN_ORDER`. Never render a lean with `cap()` or raw: that is how
  three spellings went live at once — "Center" in the lean filter, the by-lean legend and the
  outlets table, "center" in the bar tooltips and the bloc grid, "Centre" only on the lead card.
- **Lean blocs / "Where outlets diverge"** (2026-10-21, client-side only, no pipeline
  change): per story cluster, items are grouped by the outlet's `lean` from
  `META.sources` into left/center/right. A bloc carries weight (Σ `w`), outlets
  (distinct `src`) and framing (Σ`w·s`/Σ`w` over scored items — the same
  prominence-weighted mean as bundle sentiment). Divergence Δ = max − min framing
  over blocs that have one; undefined below two. Both marks are driven by one
  quantity, the bloc's **share of the story's weight** — never raw weight on one
  and share on the other. The row mark normalises that share **per row** (the
  story's largest bloc fills 18px, floored at 3px: a global ceiling flattens every
  ordinary story, since per-outlet weight spans ~110×). Colour comes from `dvBar`,
  **not** the chips' `dvMix` (2026-10-22): a chip prints its number so colour there
  is only a hint, while a bar has no number and colour is its whole signal, so the
  gentle `|v|/2` tint rendered every story the same beige. `dvBar` reads the five
  `--dv-*` tokens as real stops — ±0.5 = full mid token, ±1 = full end token, past
  that it mixes toward `--ink` — and saturates at ±1 because a bloc mean of ±1 means
  every outlet in that bloc framed the story identically. It pivots on `--dv-pivot`,
  `--dv-0` de-yellowed to the `--grid` chroma level (light `#d6d0c3`; the dark
  `--dv-0` is already low-chroma, so dark reuses it), because `--dv-0` at chroma 10.4
  pulls 0.00 toward the red half. Do not "fix" that pivot by greying it: the blue
  stops sit closer to grey than the red ones, so a true grey swings the scale's
  imbalance from 5% to 21% the other way. `--dv-0` still paints the chips, where the
  warmth sits behind a printed number and costs nothing. A bloc with weight but
  nothing scored is `--dv-u`. **Omission** (weight 0) draws no bar at all, only a
  2px `--dv-n2` tick on the baseline — "covered it lightly" must stay distinct from
  "did not cover it", which is why the 3px floor exists. The **Divided** list mode
  sorts by Δ desc; a story needs ≥2 framed blocs and `MIN_SCORED` (4) scored
  headlines to get a figure, else it draws bars, shows nothing and does not rank.
  The **top four** cards carry the same bars inside the image chip (`blocChip`, 2026-10-22):
  one object holding the bundle mean and its blocs, because the average on the image
  with the breakdown elsewhere reads as two unrelated things. Its plate is `--surface`,
  not a sentiment colour — the chip used to state its sentiment twice, as the number
  and as the plate behind it, and that freed channel is what the bars spend. Single
  articles (opinion cards) keep the plain coloured `sentChip`: no bloc data. The
  front-unit expansion head therefore passes `showMark=false` — the card above it
  already shows the bars and its own `blocDetail` grid is the breakdown.
  Exactly one missing bloc has no full Δ: it ranks on the gap between the two that
  are present and reads "no L/C/R" — never a synthesised Δ, never forced to the top.
  That rule lives in one place, `blocStats`.
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
- **Expansion** (decided 2026-10-18, not yet started): grow into **Asia**, **deeper Europe** and
  **Latin America**. Three things constrain it, and the first two are easy to miss.
  1. **The lean blocs are exactly 10 / 10 / 10 today.** That is why a bloc's raw weight compares
     fairly against another's in `blocStats`, the bars and Δ. Add outlets unevenly and those
     figures start measuring bloc headcount instead of editorial choice — either keep the balance
     or normalise per bloc size, deliberately, not by accident.
  2. **There is no real region field.** `REGION()` in the dashboard is a country ternary —
     US / UK / EU(FR,DE,ES,IT,INT) / Other — so Canada and Australia already fall into "Other".
     Non-western outlets need an explicit region in `sources.yaml` before they arrive, or the
     region filter and the By-region split become meaningless.
  3. **The headline attention figure stays western** (owner's call): new regions are a dimension
     to filter and compare by, not a redefinition, so the existing series stays continuous.
  Also: `config/keywords.yaml` covers en/fr/de/es/it only — Latin America needs Portuguese, and
  anything beyond the Latin alphabet is new ground. Current spread: 30 outlets, US 9, UK 5, DE 4,
  FR 3, IT 2, CA 2, AU 2, INT 2, ES 1.
  **Blocked outlets** may be recovered with real-browser rendering (owner approved), with a line:
  an honest user agent and robots.txt respected, never defeating bot detection or CAPTCHAs — NYT
  stays on its feed. Expect roughly half the blocked list back, not all of it.
  Vetting a new source, in order: a published lean rating (AllSides / Ad Fontes, basis commented),
  the desktop-vs-mobile front comparison (see Mobile fronts), then a week of
  `scripts/audit_headlines.py` before it enters aggregates.
- **One outlet, one vote** (2026-11-07): `outletVotes(items)` is the single place a story is
  reduced to its outlets — each gets its **best placement** as weight and **its own**
  prominence-weighted mean as framing — and `voteMean` combines them. Every figure a story reports
  runs through it: bundle rank, story-list order, the story's mean sentiment, and `blocStats`
  (bloc weight, bar height, bar color, Δ). Before, all four summed raw items, so a newsroom filing
  one story sixteen ways counted sixteen times: Corriere filed 16 of the Pillay story's 36 items
  and dragged its mean to −0.33, where per-outlet it is −0.03 and the press was simply split
  (Δ rose 1.35 → 1.72, measuring outlets rather than articles). `blocStats.scored` still counts
  scored *headlines*, because it is a data-sufficiency floor for `MIN_SCORED`, not a weight.
- **Bundle ranking** (2026-11-07): `score = reach × n/(n+1)`, where `reach` sums **each outlet's
  best placement only** and `n` is the distinct outlets. Summing every item let a newsroom filing
  one story four ways vote four times — the equal-weighting invariant stopped at the bundle — and
  that is how a one-outlet story took a top-four slot. The two terms cover opposite windows and
  neither is sufficient alone: measured over live data, `reach` changes **0 ranks at 24h** (churn
  needs days to accumulate) but 276 of 326 at 30d, while `n/(n+1)` moves 2 at 24h, 37 at 7d and
  199 at 30d. A penalty, never a floor: 78% of 24h bundles are single-outlet (88% under the US
  filter), so excluding them would empty the front unit. `b.reach` is kept on the bundle for
  debugging. `groupByStory` orders the story list by the same score (it used to sort by
  `items.length`, which rewarded the newsroom that filed most often).
- **Front-page bundles** are computed client-side from items.json: clustered
  items only, ranked by that score within the selected period + filters;
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
