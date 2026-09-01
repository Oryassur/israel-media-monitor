# Sentiment rubric v2 — framing toward Israel in news headlines

You are scoring news homepage headlines for how they frame Israel. This is NOT
generic positive/negative sentiment: a headline about war is almost always a
"negative" event, but it can portray Israel sympathetically, critically, or
neutrally. Score the FRAMING toward Israel, as a typical homepage reader in
that outlet's country would perceive it. Headlines may be in English, French,
German, Spanish, or Italian — score them in their original language.

(v2 changes, calibrated against blind human ratings: ±2 reserved for advocacy
content; explicit event-baselines; a framing-cue rule; ambiguity defaults to 0.)

For each headline, return:

## 1. `related` (bool)

Is this about Israel, Israelis, or the Israeli-Palestinian/regional conflict —
including politics-adjacent stories where the conflict drives the news (a film
festival roiled by Gaza politics, a foreign government blaming Israel for a
crisis)? Be generous with adjacency. Mark false only for incidental matches:
an individual's nationality or background in a personal/cultural profile,
business/sports trivia, metaphorical uses ("holding X hostage").

## 2. `score` (int, -2..+2)

**The ±2 band is reserved for advocacy.** Only opinion/editorial/column content
that itself argues against Israel (-2) or for Israel (+2) may use it. News
reporting caps at -1/+1 no matter how emotive the event.

**Step 1 — event baseline.** What does the headline's underlying event reflect
about Israel?

- Misconduct by Israeli actors (settler violence, official cruelty, censorship
  claims) → **-1**. Conduct outweighs speech about it: this baseline holds even
  when the headline's verb is an Israeli official condemning the conduct.
- Harm or hostility directed at Israel/Israelis inside Western societies
  (attacks, incitement, antisemitic harassment tied to Israel) → **+1**
  (Israel/Israelis framed as victims in the reader's own world).
- Rhetorical hostility from geopolitical adversaries (Iran, Hezbollah, enemy
  states' statements/threats) → **0** — priced in, moves no reader.
- State-level cooperation, alliances, normalization, Israeli-Arab cooperation,
  Israel as a desirable partner → **+1**.
- Military operations reported factually (strikes, captures, casualties in
  combat framing) → **0**, category `military_operation`, regardless of
  success or failure.
- Israeli internal politics reported factually → **0**.
- Netanyahu-family personal stories, and foreign domestic politics where
  Israel is the football rather than the actor → **0**.
- Diplomacy/process news (talks, rulings, statements) → **0**.

**Step 2 — talk-vs-talk focus.** For accusation/denial coverage (no conduct in
the headline, only claims): score follows which side owns the headline —
accusation-focused → -1, denial/rebuttal-focused → +1, balanced → 0.

**Step 3 — framing-cue scan.** Shift the baseline ONE step when the headline
carries a clear framing device; otherwise the baseline stands:

- temporal indictment ("after weeks of…", "finally", "amid mounting…") — frames
  a response as late/insufficient → one step negative
- scare quotes casting doubt on Israeli claims ("'captured'") → one step negative
- loaded words discrediting Israel's critics ("rant", "toady") → one step positive
- cues never push news past ±1, and never manufacture a ±2

**Ambiguity defaults to 0.** If it is genuinely unclear whom the headline
criticizes (Israel or its accuser; a platform or a speaker), score 0 — unless a
Step-3 cue resolves it.

## 3. `category` — one of:

- `israel_action_criticized` — Israeli actors' conduct cast negatively
- `israel_as_victim` — attacks/hostility toward Israel/Israelis, hostages' plight
- `military_operation` — combat/operational news reported factually
- `neutral_report` — other factual conflict reporting without tilt
- `internal_politics` — Israeli domestic politics (govt, elections, courts, Netanyahu family)
- `diplomacy` — negotiations, international relations, statements, cooperation
- `opinion` — clearly an op-ed/analysis/column (the only category allowed ±2)
- `other` — related but none of the above

## Calibration examples (from blind human QA)

- "Netanyahu condemns rioters after weeks of West Bank settler violence" → -1, israel_action_criticized (settler-conduct baseline; "after weeks of" frames the condemnation as late)
- "Iran's supreme leader calls for Muslim unity against US and Israel" → 0, neutral_report (adversary rhetoric)
- "Rapper calls for violence against Israel at left-wing Berlin rally" → +1, israel_as_victim (incitement inside a Western society)
- "Israel signs €3 billion arms deal with Greece" → +1, diplomacy (cooperation)
- "Israel captures top Hamas commander in Gaza strike, defense minister says" → 0, military_operation
- "Israeli strike on Gaza school kills dozens, health ministry says" → -1, israel_action_criticized
- "Ceuta: Israel accuses Sánchez of 'blatant lie'" → +1, diplomacy (denial-focused)
- "Spain's PM blames Russia, Israel for border crisis" → -1, diplomacy (accusation-focused)
- "Far-left streamer equates Israel's right to exist to Nazi Germany" → 0, opinion (ambiguous target)
- "Far-left streamer compares Israel's 'right to exist' to Nazi Germany in interview rant" → +1, opinion ("rant" discredits the critic)
- "Hostage survivor Mia Schem is now a top model" → +1, israel_as_victim (news caps at +1)
- "'Summer camps in our prisons are over': Ben Gvir mocks detained Palestinian women" → -1, israel_action_criticized (reporting cruelty is still reporting)
- Op-ed: "Yes, we can talk about genocide in Gaza" → -2, opinion (advocacy)
- "Netanyahu's son evacuated from US over Iran threat" → 0, internal_politics (family personal story)
- "Michigan's top Jewish Democrat skips convention over Israel harassment fears" → 0, other (foreign domestic politics)
- "Leader of Israel's Islamist Party introduces a new No. 2: a Zionist" → +1, internal_politics (Israeli-Arab cooperation)
- "Israeli startup raises $200M for AI chips" → related: false

When genuinely uncertain between two scores, choose the one closer to 0.
