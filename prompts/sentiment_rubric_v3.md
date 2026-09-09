# Sentiment rubric v3 — framing toward Israel in news headlines

You are scoring news homepage headlines for how they frame Israel. This is NOT
generic positive/negative sentiment: a headline about war is almost always a
"negative" event, but it can portray Israel sympathetically, critically, or
neutrally. Score the FRAMING toward Israel, as a typical homepage reader in
that outlet's country would perceive it. Headlines may be in English, French,
German, Spanish, or Italian — score them in their original language.

(v3 changes, calibrated against a second blind human round: boycott/sanction
events are negative; criticism of Israel's critics is positive; framing cues
apply in every category and both directions; analysis with overt editorial
framing counts as opinion; `related` includes non-conflict Israel content.)

For each headline, return:

## 1. `related` (bool)

Is this about Israel, Israelis, or the Israeli-Palestinian/regional conflict —
including politics-adjacent stories where the conflict drives the news (a film
festival roiled by Gaza politics, a foreign government blaming Israel for a
crisis)? Be generous with adjacency. Non-conflict content also counts when the
Israeli identity or setting is part of the story's point: achievements or
obituaries of prominent Israelis, culture/lifestyle pieces set in Israel —
these shape perception too. Mark false only for incidental matches: an
individual's background mentioned in passing, business/sports trivia where
Israeliness is not the point, metaphorical uses ("holding X hostage").

## 2. `score` (int, -2..+2)

**The ±2 band is reserved for advocacy and overt editorializing.** Opinion,
editorial, column, AND analysis pieces whose headline itself argues a thesis
about Israel may use it — even when published in a news section. The test is
the headline's voice: does it assert a charged judgment ("brutality as an
electoral argument", "looking for a fight in every direction") rather than
report an event? Straight news reporting caps at -1/+1 no matter how emotive
the event. Do not shy from ±2 when an opinion headline clearly argues against
Israel (-2) or for Israel / against its critics (+2).

**Step 1 — event baseline.** What does the headline's underlying event reflect
about Israel?

- Misconduct by Israeli actors (settler violence, official cruelty, censorship
  claims) → **-1**. Conduct outweighs speech about it: this baseline holds even
  when the headline's verb is an Israeli official condemning the conduct.
- Palestinian/civilian suffering → **-1 only when attributed to Israeli
  action** (strikes, blockade, restrictions). Suffering attributed elsewhere
  (a funding crisis, internal factions, natural causes) → **0**.
- Violent attacks, incitement, or antisemitic harassment aimed at
  Israelis/Jews in Western societies, or hostility reported with condemnation
  or victim-sympathy framing → **+1** (Israel/Israelis as victims in the
  reader's own world).
- **Institutional boycotts, sanctions, exclusions, or delegitimization moves
  against Israel reported flatly** (a government sanctioning, a mayor blocking
  an Israeli team, a trade-ban campaign) → **-1** — they signal isolation.
- An individual's protest act against Israel reported flatly (an actor quits,
  a celebrity gesture) → **0**; prominent unhedged pro-Palestinian advocacy
  showcased as the story → **-1**; hedged or ambivalent versions → **0**.
- **Criticism or discrediting of Israel's critics, and enforcement against
  Israel's enemies** (a pundit attacked for anti-Israel views, a reporter
  sanctioned for biased language, assets of Hamas seized) → **+1**.
- Rhetorical hostility from geopolitical adversaries (Iran, Hezbollah, enemy
  states' statements/threats) → **0** — priced in, moves no reader. This
  includes adversary accusations against third parties (Iran accusing the US).
- **Support or defense of Israel coming FROM an adversary/pariah state**
  (Russia siding with Israel) → **0**; **-1** when the alignment itself is the
  headline's focus — the pairing taints, not helps.
- State-level cooperation, alliances, normalization with Western/regional
  partners, Israel as a desirable partner → **+1**.
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
carries a clear framing device. Cues apply in EVERY category (internal
politics included) and in BOTH directions (a +1 baseline can drop to 0):

- temporal indictment ("after weeks of…", "finally", "amid mounting…") — frames
  a response as late/insufficient → one step negative
- scare quotes casting doubt on Israeli claims ("'captured'") → one step negative
- delegitimizing verb choice for lawful operations ("kidnap" for an arrest,
  "abduct" for a capture) → one step negative
- loaded characterization of Israel or its politics ("radicalizes", "tears
  itself apart", "spoils for a fight", "hidden from the public") → one step
  negative, even in `internal_politics`
- a skeptical qualifier undercutting a positive story ("exceptionally high
  sum" on an arms deal) → one step negative
- loaded words discrediting Israel's critics ("rant", "toady", "vile slur") →
  one step positive
- cues never push straight news past ±1, and never manufacture a ±2

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
- `opinion` — op-ed/analysis/column, incl. news-section analysis with an argued thesis (the only category allowed ±2)
- `other` — related but none of the above

## Calibration examples (from two blind human rounds)

- "Netanyahu condemns rioters after weeks of West Bank settler violence" → -1, israel_action_criticized (settler-conduct baseline; "after weeks of" frames the condemnation as late)
- "Iran's supreme leader calls for Muslim unity against US and Israel" → 0, neutral_report (adversary rhetoric)
- "Iran accuses US of 'war crime' after missile blast kills four at wedding" → 0, neutral_report (adversary accusation against a third party)
- "Russia joins Israel and attacks Spain's PM over the Ceuta 'hoaxes'" → -1, diplomacy (adversary alignment is the headline)
- "Belgian soccer club blocked by mayor from hosting Israeli opponent" → -1, other (institutional exclusion reported flatly)
- "UK must end all trade with Israel, says co-founder of BDS movement" → -1, other (delegitimization campaign)
- "Israel warns it will retaliate if UK imposes sanctions" → -1, diplomacy (sanctions context signals isolation)
- "Actor quits West End show over co-star's pro-Israel views" → 0, other (individual protest act, flat)
- "Former actor who quit over pro-Israel views 'liked' vile 'Zio hag' slur" → +1, israel_as_victim (condemnation cue)
- "Grow up, Maureen Lipman tells actor who withdrew from her play over Israel" → +1, israel_as_victim (boycotter mocked)
- "Celebrity opens film festival with pro-Palestine fan" → -1, other (unhedged advocacy showcased)
- "Presenter on the pro-Palestine appeal: 'I haven't signed yet, I want to understand better'" → 0, other (hedged)
- "Van Jones calls out pundit for 'insane' belief he's 'smarter than Obama' on Israel policy" → +1, other (Israel-critic discredited)
- "BBC reporter broke impartiality rules by referring to 'genocide' in Gaza" → +1, other (sanction against biased language)
- "DOJ seizes over $560,000 in Hamas-linked cryptocurrency" → +1, other (enforcement against Israel's enemy)
- "U.N. agency to halve West Bank food aid amid funding crisis" → 0, neutral_report (suffering not attributed to Israel)
- "Israeli strike on Gaza school kills dozens, health ministry says" → -1, israel_action_criticized (suffering attributed to Israeli action)
- "Israel signs €3 billion arms deal with Greece" → +1, diplomacy (cooperation)
- "Submarine deal leads to exceptionally high sum in weapons exports to Israel" → 0, diplomacy (cooperation +1, cut by the skeptical qualifier)
- "Israel captures top Hamas commander in Gaza strike, defense minister says" → 0, military_operation
- "Israeli intelligence agents kidnap Hamas security chief in Gaza" → -1, military_operation ("kidnap" delegitimizes an arrest; compare "Israel says it arrested…" → 0)
- "In Israel, the right, threatened with defeat, tears itself apart and radicalizes" → -1, internal_politics (loaded characterization overrides the 0 default)
- "Netanyahu, Trailing in the Polls, Spoils for a Fight to Aid His Campaign" → -1, internal_politics (cynical-motive framing)
- "Ceuta: Israel accuses Sánchez of 'blatant lie'" → +1, diplomacy (denial-focused)
- "Spain's PM blames Russia, Israel for border crisis" → -1, diplomacy (accusation-focused)
- "Far-left streamer compares Israel's 'right to exist' to Nazi Germany in interview rant" → +1, opinion ("rant" discredits the critic)
- Op-ed: "Yes, we can talk about genocide in Gaza" → -2, opinion (advocacy)
- "Netanyahu's Israel Is Looking for a Fight in Every Direction" → -2, opinion (argued thesis, hostile)
- "AI video of starving prisoners: for minister Ben Gvir, brutality as an electoral argument" → -2, opinion (news-section analysis with an argued charged judgment)
- "Media fixation on Israel eclipses global suffering and fuels antisemitism" → +2, opinion (media-criticism defending Israel)
- "The media moved on from Gaza — but only to find a new Israel story on the West Bank" → +2, opinion (same genre: advocacy for Israel against its coverage)
- "Ada Yonath, Chemist and First Israeli Woman to Receive a Nobel, Dies at 87" → related: true, +1, other (Israeli identity is the point; non-conflict positive representation)
- "Sand wedding in Tel Aviv" → related: true, 0, other (lifestyle set in Israel)
- "Netanyahu's son evacuated from US over Iran threat" → 0, internal_politics (family personal story)
- "Michigan's top Jewish Democrat skips convention over Israel harassment fears" → 0, other (foreign domestic politics)
- "Israeli startup raises $200M for AI chips" → related: false (Israeliness incidental — business trivia)

When genuinely uncertain between two scores, choose the one closer to 0.
