# Israel in Western Media — attention & sentiment tracker

Hourly pipeline that monitors 20 major western news homepages, measures how much
editorial attention Israel receives (steeply prominence-weighted share of each
homepage's top-20 slots: lead story ×10, 2–5 ×5, 6–10 ×3, 11–20 ×1),
scores the framing of every Israel-related headline (−2 hostile … +2 sympathetic,
via a versioned LLM rubric), and publishes an interactive dashboard.

- **Methodology**: see [prompts/sentiment_rubric_v1.md](prompts/sentiment_rubric_v1.md) and [CLAUDE.md](CLAUDE.md)
- **Sources**: 20 outlets across US / UK / FR / DE / ES / IT / CA / AU + wires,
  with 3-way political lean (Left/Center/Right) assigned from AllSides / Ad Fontes
  published ratings — [config/sources.yaml](config/sources.yaml)
- **Runs**: GitHub Actions, hourly ([.github/workflows/pipeline.yml](.github/workflows/pipeline.yml))
- **Dashboard**: GitHub Pages, served from [docs/](docs/)

## Data

- `data/items/YYYY-MM.jsonl` — every unique Israel-related headline: source, text,
  first/last seen on homepage, best prominence, sentiment score + category
- `data/snapshots/YYYY-MM.csv` — per source per hour: total headlines, Israel
  headlines, attention share, mean sentiment, fetch status

## Local run

```bash
pip install -r requirements.txt
python -m pipeline.run            # full cycle (needs ANTHROPIC_API_KEY or claude CLI for sentiment)
python -m pipeline.run --no-llm   # fetch/extract/volume only
```

## Caveats

- Headlines only (what homepage readers see), not full articles.
- Attention share is relative to what each site server-renders on its homepage.
- Sentiment is model-scored against a fixed rubric; scores record model + rubric
  version, and the rubric is periodically validated against human ratings.
