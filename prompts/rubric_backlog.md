# Rubric backlog — changes queued for v3.2

Every rubric bump re-scores the whole archive (~500 items, ~$1) and reshuffles
roughly 10% of borderline scores as re-scoring jitter, so changes are batched
into one version. **Decision session: Sunday 2026-09-13, 21:00 Israel time.**

## 1. Precedence in accusation / rebuttal chains (Step 2)

**Problem.** Step 2 scores accusation-focused headlines −1 and rebuttal-focused
+1, but says nothing about a chain — when the critic is the one rebutting.
Seen on the UK sanctions row (Sep 8–10): v3 and v3.1 flipped three headlines
between −1 and +1 with no rule change, because two rules pull opposite ways
(sanctions event −1 vs. criticism of Israel's critics +1).

**Proposed rule.** Score whichever side owns the headline's verb:
- Israel or its allies pushing back against a critic → **+1**
- the critic pushing back against pro-Israel pushback → **−1** (the critic
  still owns the frame)

**Calibration examples to add:**
- "West Bank sanctions will do 'great damage' to Britain, US warns" → +1, diplomacy (an ally rebuts the sanction)
- "Miliband rejects chief rabbi's claim that West Bank sanctions put UK Jews at risk" → −1, diplomacy (the sanctioner owns the rebuttal)
- "Ed Miliband is a 'failed figure' and a 'joke' … blasts Netanyahu's spokesman in Israel sanctions row" → +1, diplomacy (Israel's side rebuts; the quoted insults are reported speech, not a cue against Israel)

## Candidates to settle in the same session

- **Casualty emphasis in military-operation headlines** (Round 2 residual): "…operation ends with four Palestinians dead" — is unspecified-casualty emphasis a −1 cue like "kills 3 children", or factual 0? Owner leaned −1; model 0.
- **Hedged advocacy display**: the "fan + 'I haven't signed yet'" combination — rule says hedged → 0; model gave −1 once. Add the combined headline as an explicit 0 example.
- **Foreign domestic politics with Israel as the football** ("Polanski's seat scuppered by pro-Palestinian Greens") → 0; model gave −1 once. Add as example.
- **International topic vocabulary (intl prompt i2, separate version)**: seed `us-politics`; the generic `other` slug is absorbing it.

## Process for the bump

1. `cp prompts/sentiment_rubric_v3.1.md prompts/sentiment_rubric_v3.2.md`, apply the decided edits, note them in the header.
2. `RUBRIC_VERSION = "v3.2"` in `pipeline/common.py`; the next run re-scores everything.
3. Validate: re-join against the Round 2 QA sheet, spot-check the items that flipped, and diff related/score changes vs v3.1 (expect ~10% jitter as the baseline).
