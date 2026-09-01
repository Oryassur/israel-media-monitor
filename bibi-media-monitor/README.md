# Bibi Media Monitor — Netanyahu & family in Israeli media

Self-contained fork of the parent Israel-in-western-media pipeline. Monitors 12
major Israeli news homepages hourly, measures the editorial attention Benjamin
Netanyahu and his family receive (prominence-weighted share of each homepage's
top-20 slots), and scores headline framing toward them (−2 hostile … +2
sympathetic, versioned LLM rubric).

- **Sources**: [config/sources.yaml](config/sources.yaml) — lean (Israeli
  spectrum) and the economic-outlet tag are owner-assigned.
- **Keywords**: [config/keywords.yaml](config/keywords.yaml) — Hebrew matching
  is substring-based (prefixes attach: לנתניהו); generic PM references count as
  candidates, and the LLM `related` pass makes the final call.
- **Rubric**: [prompts/sentiment_rubric_v1.md](prompts/sentiment_rubric_v1.md)
- **Runs**: [.github/workflows/bibi-pipeline.yml](../.github/workflows/bibi-pipeline.yml),
  hourly at :17/:47, with its own repo secret `ANTHROPIC_API_KEY_BIBI`.
- **Dashboard**: [docs/bibi/](../docs/bibi/) on the repo's GitHub Pages site.

## Local run (from this folder)

```bash
python -m pipeline.run            # full cycle (needs ANTHROPIC_API_KEY or claude CLI)
python -m pipeline.run --no-llm   # fetch/extract/volume only
python -m pipeline.publish        # rebuild docs/bibi/data/*.json without fetching
```
