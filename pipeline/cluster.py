"""LLM story clustering: group related headlines into cross-outlet stories.

Backends mirror score.py ("api" / "cli"). Every assignment records the model
and cluster version (cv) so a CLUSTER_VERSION bump re-clusters cleanly without
touching sentiment scores.
"""
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta

from .common import CLUSTER_MODEL, CLUSTER_PROMPT_PATH, CLUSTER_VERSION
from .score import pick_backend

BATCH_SIZE = 40
# Stories with an assignment in this window are offered as clustering context
ACTIVE_WINDOW_DAYS = 7


def _build_prompt(batch, active):
    guide = CLUSTER_PROMPT_PATH.read_text()
    lines = [
        {"i": i, "outlet": it["source_display"],
         "headline": it["ht"] if it.get("lang") != "en" and it.get("ht") else it["headline"]}
        for i, it in enumerate(batch)
    ]
    return (
        f"{guide}\n\n"
        "Assign every headline below. Respond with ONLY a JSON array (no prose, no markdown fence), "
        "one object per headline, each: "
        '{"i": <index>, "story": "<active story id>" | "new:<k>", "title": "<max 8 words>"}. '
        "Include \"title\" only when story is \"new:<k>\".\n\n"
        f"Active stories:\n{json.dumps(active, ensure_ascii=False, indent=1)}\n\n"
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
        story = obj.get("story")
        if not isinstance(story, str) or not story.strip():
            continue
        title = obj.get("title")
        out[i] = {
            "story": story.strip(),
            "title": title.strip() if isinstance(title, str) and title.strip() else None,
        }
    return out


def _call_api(prompt):
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=CLUSTER_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    # content may open with thinking blocks (e.g. Sonnet) — join only text blocks
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def _call_cli(prompt):
    res = subprocess.run(
        ["claude", "-p", "--model", CLUSTER_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0 or "API Error" in res.stdout[:200]:
        raise RuntimeError(f"claude CLI failed: {(res.stderr or res.stdout)[:300]}")
    return res.stdout


def _story_id(title, first_seen):
    return hashlib.sha1(f"{title}|{first_seen}".encode()).hexdigest()[:12]


def cluster_items(items, stories, ts, backend=None, log=print):
    """Assign a story id to each item in place; mint new stories into `stories`.

    Each item needs: source_display, lang, headline (ht used when present).
    Adds to items: story, cluster_v. Items left untouched on failure (they will
    be retried on a later run). Returns the number of items assigned.
    """
    backend = backend or pick_backend()
    if not backend:
        log("clustering: no backend available — skipping")
        return 0

    call = _call_api if backend == "api" else _call_cli
    model_tag = CLUSTER_MODEL if backend == "api" else f"{CLUSTER_MODEL} (cli)"
    active_cut = (datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                  - timedelta(days=ACTIVE_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assigned = 0
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        # rebuilt per batch so stories minted by one batch are context for the next
        active = [{"id": s["id"], "title": s["title"]}
                  for s in stories.values() if s["last_seen"] >= active_cut]
        try:
            resp = call(_build_prompt(batch, active))
            parsed = _parse_response(resp, len(batch))
        except Exception as e:  # noqa: BLE001 — batch failure must not kill the run
            log(f"clustering: batch {start // BATCH_SIZE} failed ({e}); will retry next run")
            continue
        new_map = {}  # "new:<k>" -> minted story id
        for i, it in enumerate(batch):
            r = parsed.get(i)
            if r is None:
                continue
            sid = r["story"]
            if sid.startswith("new:"):
                if sid not in new_map:
                    # fall back to the (translated) headline if the title is missing
                    title = r["title"] or " ".join(
                        (it["ht"] if it.get("lang") != "en" and it.get("ht")
                         else it["headline"]).split()[:8])
                    story = {"id": _story_id(title, ts), "title": title,
                             "first_seen": ts, "last_seen": ts,
                             "model": model_tag, "cv": CLUSTER_VERSION}
                    stories[story["id"]] = story
                    new_map[sid] = story["id"]
                sid = new_map[sid]
            elif sid not in stories:
                continue  # unknown id: leave unassigned, retried next run
            it["story"] = sid
            it["cluster_v"] = CLUSTER_VERSION
            assigned += 1
    return assigned
