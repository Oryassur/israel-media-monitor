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

from .common import CLUSTER_MODEL, CLUSTER_PROMPT_PATH, CLUSTER_VERSION, note_llm_error
from .score import pick_backend

BATCH_SIZE = 40
# Stories with an assignment in this window are offered as clustering context
ACTIVE_WINDOW_DAYS = 7
# The registry runs to ~100 live stories. Offering every one of them as a bare
# title made the model match a headline against a wall of labels with nothing
# behind them, and near-identical phases of one event ("campaign gains momentum"
# vs "holds election") became indistinguishable. So: fewer candidates, each with
# evidence. The newest are always offered — a sibling cluster minted two hours
# ago is exactly the one a lexical score would miss.
ACTIVE_SHORTLIST = 30
ACTIVE_RECENT_KEEP = 10
STORY_SAMPLE = 2  # recent headlines shown per candidate story

_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_STOP = frozenset("""the a an and or of in on at to for from with over after as
    its his her their this that new says said will amid against israeli israel
    israels gaza war""".split())


def _tokens(text):
    return {w.lower() for w in _WORD.findall(text or "")} - _STOP


def shortlist(active, batch, limit=ACTIVE_SHORTLIST, keep_recent=ACTIVE_RECENT_KEEP):
    """The candidate stories to offer for this batch: the most recently seen,
    plus whichever others share vocabulary with the headlines being assigned."""
    if len(active) <= limit:
        return active
    want = set()
    for it in batch:
        want |= _tokens(it["ht"] if it.get("lang") != "en" and it.get("ht") else it["headline"])
    by_recent = sorted(active, key=lambda s: s.get("last_seen") or "", reverse=True)
    keep = by_recent[:keep_recent]
    taken = {s["id"] for s in keep}
    # newest first, then a stable sort by overlap: ties go to the fresher story,
    # which is the one a batch arriving now is most likely to belong to
    rest = [s for s in by_recent if s["id"] not in taken]
    rest.sort(key=lambda s: -len(want & _tokens(" ".join([s["title"], *s.get("recent", [])]))))
    return keep + rest[:max(0, limit - len(keep))]


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


def cluster_items(items, stories, ts, backend=None, log=print, recent=None):
    """Assign a story id to each item in place; mint new stories into `stories`.

    Each item needs: source_display, lang, headline (ht used when present).
    `recent` maps story id -> that story's newest headlines, used as evidence
    behind each candidate title (the registry itself never holds item lists).
    Adds to items: story, cluster_v. Items left untouched on failure (they will
    be retried on a later run). Returns the number of items assigned.
    """
    recent = recent or {}
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
        active = [{"id": s["id"], "title": s["title"], "last_seen": s["last_seen"],
                   **({"recent": recent[s["id"]][:STORY_SAMPLE]} if recent.get(s["id"]) else {})}
                  for s in stories.values() if s["last_seen"] >= active_cut]
        active = shortlist(active, batch)
        for a in active:
            a.pop("last_seen", None)  # ordering input only; the model does not need it
        try:
            resp = call(_build_prompt(batch, active))
            parsed = _parse_response(resp, len(batch))
        except Exception as e:  # noqa: BLE001 — batch failure must not kill the run
            note_llm_error("clustering", e)
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
