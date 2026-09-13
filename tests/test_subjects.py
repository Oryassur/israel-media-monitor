"""subjects: pending selection, response normalisation, rubric vocabulary."""
import json
import re
import unittest
from datetime import datetime, timezone

from pipeline import subjects
from pipeline.common import MAX_SUBJECT_ITEMS_PER_RUN, SUBJECT_PROMPT_PATH, SUBJECT_VERSION

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def rec(i, **kw):
    r = {"id": f"i{i}", "source": "bbc", "headline": f"Headline {i}", "lang": "en",
         "first_seen": f"2026-09-{1 + i % 12:02d}T08:00:00Z", "related": True}
    r.update(kw)
    return r


class TestPendingSubjects(unittest.TestCase):
    def test_selection_and_order(self):
        idx = {r["id"]: r for r in [
            rec(1),                                   # never tagged -> pending
            rec(2, sv=SUBJECT_VERSION, subject="Gaza war", figures=[]),  # done
            rec(3, sv="s0", subject="Gaza war", figures=[]),  # old version -> pending
            rec(4, related=False),                    # rejected by the scorer
            rec(5, related=None),                     # unscored
        ]}
        got = [r["id"] for r in subjects.pending_subjects(idx)]
        self.assertEqual(sorted(got), ["i1", "i3"])
        # newest first
        fs = [idx[i]["first_seen"] for i in got]
        self.assertEqual(fs, sorted(fs, reverse=True))

    def test_cap(self):
        idx = {f"i{i}": rec(i) for i in range(MAX_SUBJECT_ITEMS_PER_RUN + 25)}
        self.assertEqual(len(subjects.pending_subjects(idx)), MAX_SUBJECT_ITEMS_PER_RUN)

    def test_in_use_counts_current_version_only(self):
        idx = {r["id"]: r for r in [
            rec(1, sv=SUBJECT_VERSION, subject="Hostages", figures=["Netanyahu", "Trump"],
                first_seen="2026-09-12T08:00:00Z"),
            rec(2, sv=SUBJECT_VERSION, subject="Hostages", figures=["Netanyahu"],
                first_seen="2026-09-12T09:00:00Z"),
            rec(3, sv=SUBJECT_VERSION, subject="Other", figures=[],
                first_seen="2026-09-12T09:00:00Z"),          # "Other" never offered
            rec(4, sv="s0", subject="Old label", figures=["Ghost"],
                first_seen="2026-09-12T09:00:00Z"),          # old version ignored
            rec(5, sv=SUBJECT_VERSION, subject="Stale", figures=[],
                first_seen="2026-07-01T09:00:00Z"),          # outside the window
        ]}
        subj, figs = subjects.in_use(idx, NOW)
        self.assertEqual(subj, ["Hostages"])
        self.assertEqual(figs, ["Netanyahu", "Trump"])


class TestParseResponse(unittest.TestCase):
    def test_normalisation(self):
        text = 'Here you go:\n[{"i": 0, "subject": "  West Bank\\n settlements ", '
        text += '"figures": ["Netanyahu", "netanyahu", " Smotrich ", "Katz", "Herzog"]},'
        text += '{"i": 1, "subject": null, "figures": "Trump"},'
        text += '{"i": 2, "subject": "' + "x" * 40 + '", "figures": []},'
        text += '{"i": 7, "subject": "Out of range", "figures": []}]'
        got = subjects._parse_response(text, 3)
        self.assertEqual(got[0], {"subject": "West Bank settlements",
                                  "figures": ["Netanyahu", "Smotrich", "Katz"]})
        self.assertEqual(got[1], {"subject": "Other", "figures": []})
        self.assertEqual(got[2]["subject"], "Other")
        self.assertNotIn(7, got)

    def test_no_array_raises(self):
        with self.assertRaises(ValueError):
            subjects._parse_response("I cannot help with that.", 1)

    def test_tag_items_skips_failed_batch(self):
        items = [rec(1), rec(2)]
        calls = []

        def fake_call(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return '[{"i": 0, "subject": "Hostages", "figures": ["Trump"]}]'
            raise RuntimeError("boom")

        orig, subjects._call_api = subjects._call_api, fake_call
        try:
            n = subjects.tag_items(items, ([], []), backend="api", log=lambda m: None)
        finally:
            subjects._call_api = orig
        self.assertEqual(n, 1)
        self.assertEqual(items[0]["subject"], "Hostages")
        self.assertEqual(items[0]["figures"], ["Trump"])
        self.assertEqual(items[0]["sv"], SUBJECT_VERSION)
        self.assertNotIn("subject", items[1])  # index 1 was missing from the reply

    def test_prompt_uses_translation_and_in_use(self):
        p = subjects._build_prompt([rec(1, lang="de", headline="Original", ht="Translated")],
                                   ["Hostages"], ["Netanyahu"])
        self.assertIn('"headline": "Translated"', p)
        self.assertIn('["Hostages"]', p)
        self.assertIn('["Netanyahu"]', p)


class TestRubric(unittest.TestCase):
    def test_version_and_vocabulary(self):
        self.assertEqual(SUBJECT_VERSION, "s1")
        text = SUBJECT_PROMPT_PATH.read_text()
        for label in ["Gaza war", "Hostages", "West Bank settlements", "Israel–Iran",
                      "Hezbollah & Lebanon", "Israel–UK relations", "Antisemitism abroad",
                      "Pro-Palestinian protests", "Israeli politics", "Media & celebrities"]:
            self.assertIn(f"`{label}`", text)
        for name in ["Netanyahu", "Zamir", "Starmer", "Trump", "Khamenei"]:
            self.assertIn(f"`{name}`", text)
        self.assertIn("figures", text)


if __name__ == "__main__":
    unittest.main()
