"""International-coverage benchmark: how much of each homepage's top-20 weight
goes to international stories, and to which topics.

Every top-20 headline (Israel-related or not) is upserted into
data/allitems/YYYY-MM.jsonl and classified domestic/international by an LLM
(backends mirror score.py); per-source aggregates land in data/intl/ as one
append-only row per run. Collection is best-effort by design — run.py wraps
the whole pass in try/except so it can never fail the hourly run.
"""
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta

from .common import INTL_MODEL, INTL_PROMPT_PATH, INTL_VERSION, MAX_INTL_ITEMS_PER_RUN, item_id
from .score import pick_backend
from .store import append_intl, load_recent_allitems, save_allitems

BATCH_SIZE = 50
# Retry classification for unclassified items this long after first_seen (hours)
INTL_RETRY_WINDOW_H = 48
# How many currently-in-use slugs to offer beyond the seeded vocabulary
MAX_CONTEXT_SLUGS = 15

_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _build_prompt(batch, in_use):
    guide = INTL_PROMPT_PATH.read_text()
    lines = [
        {"i": i, "outlet": it["source_display"], "home": it["home"], "headline": it["headline"]}
        for i, it in enumerate(batch)
    ]
    return (
        f"{guide}\n\n"
        f"Currently-in-use slugs beyond the established list: {json.dumps(in_use)}\n\n"
        "Classify every headline below. Respond with ONLY a JSON array (no prose, no markdown "
        'fence), one object per headline, each: {"i": <index>, "intl": <bool>, '
        '"topic": "<slug>" | null}. topic is a slug when intl is true, null when false.\n\n'
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
        intl = bool(obj.get("intl", False))
        topic = obj.get("topic")
        if intl:
            topic = topic.strip().lower() if isinstance(topic, str) else ""
            if not _SLUG.match(topic) or len(topic) > 40:
                topic = "other"
        else:
            topic = None
        out[i] = {"intl": intl, "topic": topic}
    return out


def _call_api(prompt):
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=INTL_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def _call_cli(prompt):
    res = subprocess.run(
        ["claude", "-p", "--model", INTL_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0 or "API Error" in res.stdout[:200]:
        raise RuntimeError(f"claude CLI failed: {(res.stderr or res.stdout)[:300]}")
    return res.stdout


def classify_items(items, in_use, backend=None, log=print):
    """Classify items in place: adds intl, topic, iv, model. Items left
    untouched on failure (retried next run). Each item needs source_display,
    home, headline. Returns the number classified."""
    backend = backend or pick_backend()
    if not backend:
        log("intl: no backend available — skipping classification")
        return 0

    call = _call_api if backend == "api" else _call_cli
    model_tag = INTL_MODEL if backend == "api" else f"{INTL_MODEL} (cli)"
    done = 0
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        try:
            resp = call(_build_prompt(batch, in_use))
            parsed = _parse_response(resp, len(batch))
        except Exception as e:  # noqa: BLE001 — batch failure must not kill the run
            log(f"intl: batch {start // BATCH_SIZE} failed ({e}); will retry next run")
            continue
        for i, it in enumerate(batch):
            r = parsed.get(i)
            if r is None:
                continue
            it["intl"] = r["intl"]
            it["topic"] = r["topic"]
            it["iv"] = INTL_VERSION
            it["model"] = model_tag
            done += 1
    return done


def collect(sources, per_source, ts, months, log=print):
    """The full benchmark pass for one run: upsert all-item records for every
    fetched top-20 headline, classify what's still unclassified, then append
    one aggregate row per fetched source to data/intl/."""
    allidx = load_recent_allitems(months)
    src_by_name = {s["name"]: s for s in sources}

    for src in sources:
        ps = per_source[src["name"]]
        if not ps["ok"]:
            continue
        for headline, rank, weight in ps["top20"]:
            iid = item_id(src["name"], headline)
            rec = allidx.get(iid)
            if rec:
                rec["last_seen"] = ts
                if weight > rec.get("best_weight", 0):
                    rec["best_weight"] = weight
                    rec["best_rank"] = rank
            else:
                allidx[iid] = {
                    "id": iid, "source": src["name"], "headline": headline,
                    "lang": src["lang"], "first_seen": ts, "last_seen": ts,
                    "best_rank": rank, "best_weight": weight,
                }

    cutoff = (datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
              - timedelta(hours=INTL_RETRY_WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending = [r for r in allidx.values() if "intl" not in r and r["first_seen"] >= cutoff]
    pending = pending[:MAX_INTL_ITEMS_PER_RUN]
    if pending:
        in_use = [t for t, _ in Counter(
            r["topic"] for r in allidx.values() if r.get("topic")
        ).most_common(MAX_CONTEXT_SLUGS)]
        for r in pending:
            s = src_by_name[r["source"]]
            r["source_display"] = s["display"]
            r["home"] = s.get("home", s["country"])
        n = classify_items(pending, in_use, log=log)
        for r in pending:
            r.pop("source_display", None)
            r.pop("home", None)
        log(f"intl: classified {n}/{len(pending)} items")

    rows = []
    for src in sources:
        name = src["name"]
        ps = per_source[name]
        if not ps["ok"]:
            continue  # failed fetch: missing, never zero
        total_w, intl_w, uncl_w = 0, 0, 0
        topics = {}
        for headline, rank, weight in ps["top20"]:
            rec = allidx[item_id(name, headline)]
            total_w += weight
            if "intl" not in rec:
                uncl_w += weight
            elif rec["intl"]:
                intl_w += weight
                topics[rec["topic"]] = topics.get(rec["topic"], 0) + weight
        rows.append({"ts": ts, "source": name, "total_w": total_w,
                     "intl_w": intl_w, "uncl_w": uncl_w, "topics": topics})

    save_allitems(allidx)
    append_intl(ts, rows)
    log(f"intl: {len(rows)} source rows appended ({len(allidx)} all-items tracked)")
