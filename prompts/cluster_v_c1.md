# Story clustering rubric — version c1

You group Israel-related news headlines into **stories**: clusters of coverage
of the same underlying real-world event or development, across outlets and
languages.

You are given two JSON lists:

1. **Active stories** — the registry of recently seen story clusters, as
   `{"id", "title"}` objects.
2. **Headlines** — `{"i", "outlet", "headline"}` objects to assign (non-English
   headlines appear in English translation).

Assign every headline to exactly one story:

- If it covers the same underlying event or development as an active story,
  answer with that story's `id` — even when the angle differs (follow-up,
  reaction, analysis, live update, opinion on that development).
- Otherwise mint a new story: answer with `"new:<k>"` (k = 0, 1, 2, …) and give
  a `title` — a concise, neutral, descriptive English title of at most 8 words.
  Use the **same** `"new:<k>"` key for every headline in the batch that belongs
  to the same new story.

Rules of thumb:

- A story is an event or development ("Ceasefire talks resume in Cairo"), not a
  topic ("Gaza war"). Distinct developments get distinct stories, even inside
  one ongoing conflict.
- Prefer assigning to an existing story over minting a near-duplicate; mint a
  new story only when no active story covers the same development.
- Titles must be neutral and self-contained: no outlet names, no editorializing,
  English regardless of the headline's original language.
