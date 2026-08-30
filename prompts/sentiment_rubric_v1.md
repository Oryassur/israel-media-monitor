# Sentiment rubric v1 — framing toward Israel in news headlines

You are scoring news homepage headlines for how they frame Israel. This is NOT
generic positive/negative sentiment: a headline about war is almost always a
"negative" event, but it can portray Israel sympathetically, critically, or
neutrally. Score the FRAMING toward Israel, as a typical homepage reader in
that outlet's country would perceive it. Headlines may be in English, French,
German, Spanish, or Italian — score them in their original language.

For each headline, return:

1. `related` (bool) — is this actually about Israel, Israelis, or the
   Israeli-Palestinian/regional conflict? Mark false for incidental matches
   (e.g., an Israeli tech company's earnings, a chess player's nationality,
   sports results), true for anything about the state, the conflict, its
   politics, or its people in a political/security context.

2. `score` (int, -2..+2) — framing toward Israel:
   - **-2** Strongly critical/hostile framing: Israel presented as aggressor or
     wrongdoer; emphasis on harm caused by Israel; accusatory language
     ("massacre", "slaughter", "starving Gaza"); condemnations given without
     counter-context.
   - **-1** Mildly critical: Israel's actions cast in a negative light, but
     with hedged or attributed language ("officials say", "accused of"), or
     criticism balanced with some context.
   - **0** Neutral/factual: dry reporting of events, diplomacy, or logistics
     where the headline itself doesn't tilt either way; also genuinely mixed
     framings that balance out.
   - **+1** Mildly sympathetic: Israel or Israelis framed as acting reasonably,
     defending themselves, or as victims, with hedged language; positive
     non-conflict coverage (culture, tech, science) that reflects well.
   - **+2** Strongly sympathetic: Israelis clearly framed as victims of
     aggression or terror; emphasis on Israeli suffering; admiring or
     celebratory framing of Israel or its actions.

3. `category` — one of:
   - `israel_action_criticized` — Israel's military/government actions cast negatively
   - `israel_as_victim` — attacks on Israel/Israelis, hostages' plight
   - `neutral_report` — factual conflict/diplomacy reporting without tilt
   - `internal_politics` — Israeli domestic politics (govt, protests, courts)
   - `diplomacy` — negotiations, international relations, statements
   - `opinion` — clearly an op-ed/analysis/column
   - `other` — related but none of the above (culture, tech, sports, etc.)

## Calibration examples

- "Israeli strike on Gaza school kills dozens, health ministry says" → related: true, score: -1, category: israel_action_criticized (negative event attributed to Israel, but hedged/attributed language)
- "How Israel is starving Gaza" → related: true, score: -2, category: israel_action_criticized (accusatory, unhedged)
- "Hezbollah rockets rain on northern Israel, families flee homes" → related: true, score: +2, category: israel_as_victim
- "Hostage families mark 300 days with vigil in Tel Aviv" → related: true, score: +1, category: israel_as_victim
- "Ceasefire talks resume in Cairo as mediators press both sides" → related: true, score: 0, category: diplomacy
- "Netanyahu's coalition survives no-confidence vote" → related: true, score: 0, category: internal_politics
- "Israeli startup raises $200M for AI chips" → related: false (business news, incidental)
- "Opinion: The West's silence on Gaza is shameful" → related: true, score: -2, category: opinion

When genuinely uncertain between two scores, choose the one closer to 0.
