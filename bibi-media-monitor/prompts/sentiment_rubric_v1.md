# Sentiment rubric v1 — framing toward Benjamin Netanyahu and his family in Israeli news headlines

You are scoring news homepage headlines from ISRAELI outlets for how they frame
Benjamin Netanyahu ("Bibi") and his family — his wife Sara and his sons Yair
and Avner. This is NOT generic positive/negative sentiment: a headline about a
crisis is almost always a "negative" event, but it can portray Netanyahu
sympathetically, critically, or neutrally. Score the FRAMING toward Netanyahu
and his family, as a typical Israeli homepage reader would perceive it.
Headlines may be in Hebrew or English — score them in their original language.

For each headline, return:

1. `related` (bool) — is this actually about Benjamin Netanyahu or his family?
   Mark true for: headlines naming Netanyahu, Bibi, Sara, Yair, or Avner
   Netanyahu; headlines about "ראש הממשלה" / "רה"מ" / "the prime minister"
   where the reference is to Netanyahu himself (his decisions, statements,
   trial, meetings, household); headlines about the Netanyahu family's
   affairs (the Balfour/Caesarea residences, gifts, expenses).
   Mark false for: another country's prime minister; government/coalition
   stories that don't involve Netanyahu personally (a minister acting alone,
   Knesset votes without him); incidental mentions (e.g., a photo caption).

2. `score` (int, -2..+2) — framing toward Netanyahu and his family:
   - **-2** Strongly critical/hostile framing: Netanyahu presented as corrupt,
     dangerous, dishonest, or a failure; accusatory, mocking, or scandal-driven
     language; blame for disasters or for putting personal interest above the
     country; family portrayed as abusive, extravagant, or above the law.
   - **-1** Mildly critical: his actions or the family's conduct cast in a
     negative light, but with hedged or attributed language ("לטענת", "מקורבים
     טוענים", "accused of", "under fire"), or criticism balanced with context.
   - **0** Neutral/factual: dry reporting of his schedule, statements,
     meetings, court sessions, or coalition mechanics where the headline
     itself doesn't tilt either way; also genuinely mixed framings.
   - **+1** Mildly sympathetic: Netanyahu framed as acting reasonably,
     leading, achieving, or being unfairly targeted, with hedged language;
     respectful coverage of family moments.
   - **+2** Strongly sympathetic: clearly admiring or celebratory framing —
     statesman, victor, defender of Israel; the trial or attacks on him framed
     as persecution ("witch hunt"); family framed warmly as victims of unfair
     treatment.

3. `category` — one of:
   - `criticism` — Netanyahu/family conduct or decisions cast negatively
   - `support` — praising, defending, or celebratory coverage
   - `legal` — his trial, investigations, testimony, court rulings
   - `family` — Sara, Yair, or Avner as the story's focus; household affairs
   - `coalition_politics` — coalition, elections, appointments, party politics involving him
   - `security_war` — his decisions/role in war, security, hostages
   - `neutral_report` — factual reporting without tilt, none of the above fits better
   - `opinion` — clearly an op-ed/analysis/column
   - `other` — related but none of the above

Category describes the TOPIC; score describes the FRAMING — a `legal` headline
can be -2 (guilt-presuming) or +2 (persecution-framing).

## Calibration examples

- "נתניהו בעדותו: לא ביקשתי דבר מפרוטוקול" → related: true, score: 0, category: legal (dry court report)
- "עדות נתניהו נדחתה שוב — הנימוק: מצבו הבריאותי" → related: true, score: 0, category: legal
- "כך נתניהו מקריב את החטופים כדי לשרוד פוליטית" → related: true, score: -2, category: criticism (accusatory, unhedged)
- "מקורבים: נתניהו זועם על הרמטכ\"ל; בליכוד מאשימים את הפרקליטות" → related: true, score: -1, category: coalition_politics (internal strife, attributed)
- "נתניהו: ניצחון היסטורי — 'שינינו את פני המזרח התיכון'" → related: true, score: +1, category: support (his own framing, quoted)
- "ראש הממשלה הכריע: ישראל תגיב הלילה" → related: true, score: 0, category: security_war (decisive but factual)
- "ההצגה של שרה נתניהו: כמה עלתה לנו החופשה" → related: true, score: -2, category: family (mocking, expense scandal)
- "יאיר נתניהו בפוסט חריף נגד השופטים" → related: true, score: -1, category: family (his provocation reported, mildly negative light)
- "Netanyahu meets Trump at White House ahead of summit" → related: true, score: 0, category: neutral_report
- "Opinion: The endless trial of Benjamin Netanyahu is a witch hunt" → related: true, score: +2, category: opinion
- "ראש ממשלת בריטניה בהודעה דרמטית" → related: false (another country's PM)
- "הממשלה אישרה את התקציב" → related: false (government story, no Netanyahu involvement in the headline)

When genuinely uncertain between two scores, choose the one closer to 0.
