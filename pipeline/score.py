"""LLM sentiment scoring of Israel-related headlines.

Backends:
  - "api": Anthropic API (requires ANTHROPIC_API_KEY). Used in GitHub Actions.
  - "cli": local `claude -p` fallback for development on a machine with
    Claude Code installed but no API key in the environment.

Every score records the model and rubric version so data from different
scoring configurations is never silently mixed.
"""
import json
import os
import re
import shutil
import subprocess

from .common import RUBRIC_PATH, RUBRIC_VERSION, SCORING_MODEL

BATCH_SIZE = 25

VALID_CATEGORIES = {
    "israel_action_criticized", "israel_as_victim", "neutral_report",
    "internal_politics", "diplomacy", "opinion", "other",
}


def pick_backend():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    if shutil.which("claude"):
        return "cli"
    return None


def _build_prompt(batch):
    rubric = RUBRIC_PATH.read_text()
    lines = [
        {"i": i, "outlet": it["source_display"], "lang": it["lang"], "headline": it["headline"]}
        for i, it in enumerate(batch)
    ]
    return (
        f"{rubric}\n\n"
        "Score every headline below. Respond with ONLY a JSON array (no prose, no markdown fence), "
        "one object per headline, each: "
        '{"i": <index>, "related": <bool>, "score": <int -2..2>, "category": "<category>"}. '
        "If related is false, still include score 0 and category \"other\".\n\n"
        f"Headlines:\n{json.dumps(lines, ensure_ascii=False, indent=1)}"
    )


def _parse_response(text, batch_len):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError(f"no JSON array in response: {text[:200]}")
    arr = json.loads(m.group(0))
    out = {}
    for obj in arr:
        i = int(obj["i"])
        if not (0 <= i < batch_len):
            continue
        score = max(-2, min(2, int(obj.get("score", 0))))
        cat = obj.get("category", "other")
        out[i] = {
            "related": bool(obj.get("related", True)),
            "score": score,
            "category": cat if cat in VALID_CATEGORIES else "other",
        }
    return out


def _call_api(prompt):
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=SCORING_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_cli(prompt):
    res = subprocess.run(
        ["claude", "-p", "--model", SCORING_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0 or "API Error" in res.stdout[:200]:
        raise RuntimeError(f"claude CLI failed: {(res.stderr or res.stdout)[:300]}")
    return res.stdout


def score_items(items, backend=None, log=print):
    """Score items in place. Each item needs: source_display, lang, headline.

    Adds: related, sentiment, category, model, rubric. Items left untouched on
    failure (they will be retried on a later run).
    Returns the number of items successfully scored.
    """
    backend = backend or pick_backend()
    if not backend:
        log("scoring: no backend available (no ANTHROPIC_API_KEY, no claude CLI) — skipping")
        return 0

    call = _call_api if backend == "api" else _call_cli
    model_tag = SCORING_MODEL if backend == "api" else f"{SCORING_MODEL} (cli)"
    scored = 0
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        try:
            resp = call(_build_prompt(batch))
            parsed = _parse_response(resp, len(batch))
        except Exception as e:  # noqa: BLE001 — batch failure must not kill the run
            log(f"scoring: batch {start // BATCH_SIZE} failed ({e}); will retry next run")
            continue
        for i, it in enumerate(batch):
            r = parsed.get(i)
            if r is None:
                continue
            it["related"] = r["related"]
            it["sentiment"] = r["score"] if r["related"] else None
            it["category"] = r["category"] if r["related"] else None
            it["model"] = model_tag
            it["rubric"] = RUBRIC_VERSION
            scored += 1
    return scored
