"""Subject & figure tagging: what each Israel-related headline is about, and who
is in it. Feeds the dashboard's "Subjects" cloud.

One LLM pass per hourly run over related items not yet tagged under
SUBJECT_VERSION (newest first, capped), so a version bump re-tags the backlog
over a few runs without a separate backfill. Best-effort like intl/enrich:
per-batch try/except, and run.py wraps the whole pass so it can never fail the
hourly run. Fields written on item records:

  subject  str        one label from a living vocabulary ("Other" when nothing fits)
  figures  list[str]  0-3 people, press short form, names reconciled (see prompt)
  sv       str        SUBJECT_VERSION
  sm       str        model tag

Run:  python -m pipeline.subjects --pending     print the current queue, no LLM calls
"""
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from .common import MAX_SUBJECT_ITEMS_PER_RUN, SUBJECT_MODEL, SUBJECT_PROMPT_PATH, SUBJECT_VERSION, note_llm_error
from .score import pick_backend

BATCH_SIZE = 40
MAX_LABEL_LEN = 32
MAX_FIGURES = 3
# in-use vocabulary offered as context: this many labels of each kind, over this window
IN_USE_TOP = 40
IN_USE_DAYS = 30


def _norm_label(v):
    """Collapse whitespace, cap length; None for anything unusable."""
    if not isinstance(v, str):
        return None
    v = re.sub(r"\s+", " ", v).strip().strip('"\'')
    if not v or len(v) > MAX_LABEL_LEN:
        return None
    return v


def _build_prompt(batch, in_use_subjects, in_use_figures):
    guide = SUBJECT_PROMPT_PATH.read_text()
    lines = [
        {"i": i, "outlet": it.get("source_display", it["source"]), "lang": it["lang"],
         "headline": it.get("ht") or it["headline"]}
        for i, it in enumerate(batch)
    ]
    return (
        f"{guide}\n\n"
        f"Currently-in-use subjects beyond the established list: {json.dumps(in_use_subjects, ensure_ascii=False)}\n"
        f"Currently-in-use figures beyond the established list: {json.dumps(in_use_figures, ensure_ascii=False)}\n\n"
        "Tag every headline below. Respond with ONLY a JSON array (no prose, no markdown "
        'fence), one object per headline, each: {"i": <index>, "subject": "<label>", '
        '"figures": ["<name>", ...]}.\n\n'
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
        subject = _norm_label(obj.get("subject")) or "Other"
        figures, seen = [], set()
        raw = obj.get("figures")
        for f in (raw if isinstance(raw, list) else []):
            f = _norm_label(f)
            if not f or f.casefold() in seen:
                continue
            seen.add(f.casefold())
            figures.append(f)
            if len(figures) == MAX_FIGURES:
                break
        out[i] = {"subject": subject, "figures": figures}
    return out


def _call_api(prompt):
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=SUBJECT_MODEL,
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def _call_cli(prompt):
    res = subprocess.run(
        ["claude", "-p", "--model", SUBJECT_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0 or "API Error" in res.stdout[:200]:
        raise RuntimeError(f"claude CLI failed: {(res.stderr or res.stdout)[:300]}")
    return res.stdout


def in_use(items_idx, now=None):
    """(subjects, figures) currently in use: the most common labels among items
    tagged under the current version in the last IN_USE_DAYS, most common first."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=IN_USE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    subj, figs = Counter(), Counter()
    for r in items_idx.values():
        if r.get("sv") != SUBJECT_VERSION or r["first_seen"] < cutoff:
            continue
        if r.get("subject") and r["subject"] != "Other":
            subj[r["subject"]] += 1
        for f in r.get("figures") or []:
            figs[f] += 1
    return ([s for s, _ in subj.most_common(IN_USE_TOP)],
            [f for f, _ in figs.most_common(IN_USE_TOP)])


def pending_subjects(items_idx):
    """Related items not tagged under the current version, newest first, capped."""
    out = [r for r in items_idx.values()
           if r.get("related") is True and r.get("sv") != SUBJECT_VERSION]
    out.sort(key=lambda r: r["first_seen"], reverse=True)
    return out[:MAX_SUBJECT_ITEMS_PER_RUN]


def tag_items(items, in_use_vocab, backend=None, log=print):
    """Tag items in place: adds subject, figures, sv, sm. Items are left
    untouched on failure (retried next run). Returns the number tagged."""
    backend = backend or pick_backend()
    if not backend:
        log("subjects: no backend available — skipping")
        return 0
    call = _call_api if backend == "api" else _call_cli
    model_tag = SUBJECT_MODEL if backend == "api" else f"{SUBJECT_MODEL} (cli)"
    in_subj, in_figs = in_use_vocab
    done = 0
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        try:
            resp = call(_build_prompt(batch, in_subj, in_figs))
            parsed = _parse_response(resp, len(batch))
        except Exception as e:  # noqa: BLE001 — batch failure must not kill the run
            note_llm_error("subjects", e)
            log(f"subjects: batch {start // BATCH_SIZE} failed ({e}); will retry next run")
            continue
        for i, it in enumerate(batch):
            r = parsed.get(i)
            if r is None:
                continue
            it["subject"] = r["subject"]
            it["figures"] = r["figures"]
            it["sv"] = SUBJECT_VERSION
            it["sm"] = model_tag
            done += 1
    return done


if __name__ == "__main__":
    if sys.argv[1:] != ["--pending"]:
        print(__doc__)
        sys.exit(2)
    from .common import month_key
    from .store import load_recent_items
    now = datetime.now(timezone.utc)
    months = [month_key(now.strftime("%Y-%m")),
              month_key((now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))]
    idx = load_recent_items(months)
    q = pending_subjects(idx)
    subj, figs = in_use(idx, now)
    print(f"{len(q)} items pending tagging under {SUBJECT_VERSION} (cap {MAX_SUBJECT_ITEMS_PER_RUN})")
    print(f"in use: {len(subj)} subjects, {len(figs)} figures")
    for r in q[:10]:
        print(f"  {r['first_seen']} {r['source']:12} {(r.get('ht') or r['headline'])[:80]}")
