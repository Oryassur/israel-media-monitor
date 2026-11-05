"""Clustering context: which candidate stories a batch is offered, and with what
evidence behind them. The rule the pipeline relies on is that a sibling cluster
minted minutes ago is always a candidate, however little vocabulary it shares."""
import unittest

from pipeline.cluster import (ACTIVE_RECENT_KEEP, ACTIVE_SHORTLIST, STORY_SAMPLE,
                              _build_prompt, _tokens, shortlist)


def story(i, title, last_seen, recent=None):
    s = {"id": f"s{i}", "title": title, "last_seen": last_seen}
    if recent:
        s["recent"] = recent
    return s


def head(text, lang="en", ht=None):
    return {"source_display": "BBC News", "lang": lang, "headline": text, "ht": ht}


FILLER = [story(100 + i, f"Unrelated development number {i}", "2026-10-01T00:00:00Z")
          for i in range(60)]


class TestShortlist(unittest.TestCase):
    def test_small_registry_is_passed_through(self):
        act = FILLER[:ACTIVE_SHORTLIST - 1]
        self.assertEqual(shortlist(act, [head("anything at all")]), act)

    def test_capped_at_the_limit(self):
        out = shortlist(FILLER, [head("anything at all")])
        self.assertEqual(len(out), ACTIVE_SHORTLIST)

    def test_newest_stories_are_always_offered(self):
        """A cluster minted two hours ago shares no vocabulary yet — it must still
        be on the list, or the model mints a duplicate of it."""
        fresh = story(1, "Qqq zzz wholly unrelated wording", "2026-11-05T12:00:00Z")
        out = shortlist([fresh] + FILLER, [head("Shooting attack injures Israelis in West Bank")])
        self.assertIn("s1", [s["id"] for s in out])

    def test_vocabulary_overlap_selects_the_rest(self):
        match = story(2, "West Bank lockdown ordered", "2026-09-01T00:00:00Z")
        out = shortlist(FILLER + [match], [head("Israel orders West Bank lockdown after attack")])
        picked = [s["id"] for s in out]
        self.assertIn("s2", picked)
        # it is not there merely by being recent: it is older than the recency block
        self.assertNotIn("s2", [s["id"] for s in out[:ACTIVE_RECENT_KEEP]])

    def test_recent_headlines_count_toward_overlap(self):
        """Title alone is the failure this fixes: two phases of one event look
        alike as labels and differ in their contents."""
        by_title = story(3, "Campaign gains momentum", "2026-09-01T00:00:00Z")
        by_recent = story(4, "A quite differently worded title", "2026-09-01T00:00:00Z",
                          recent=["Israelis shatter turnout records in election"])
        out = shortlist(FILLER + [by_title, by_recent],
                        [head("Israelis vote in record numbers in the election")])
        picked = [s["id"] for s in out]
        self.assertIn("s4", picked)              # matched on its headlines
        self.assertNotIn("s4", picked[:ACTIVE_RECENT_KEEP])   # not merely by recency

    def test_translation_is_what_gets_matched(self):
        match = story(5, "Knesset election decision", "2026-09-01T00:00:00Z")
        out = shortlist(FILLER + [match],
                        [head("Knesset-Wahl 2026: Israel vor der Entscheidung",
                              lang="de", ht="Knesset election 2026: Israel faces the decision")])
        self.assertIn("s5", [s["id"] for s in out])

    def test_common_words_do_not_decide(self):
        """Israel/Gaza/war appear in nearly every headline; they must not score."""
        self.assertEqual(_tokens("Israel and Gaza at war"), set())


class TestPrompt(unittest.TestCase):
    def test_evidence_reaches_the_prompt(self):
        act = [{"id": "s1", "title": "Israel holds election",
                "recent": ["Polls open across Israel", "Turnout records shattered"]}]
        p = _build_prompt([head("Youth vote could play crucial role")], act)
        self.assertIn("Turnout records shattered", p)
        self.assertIn("Youth vote could play crucial role", p)

    def test_sample_size_is_bounded(self):
        self.assertLessEqual(STORY_SAMPLE, 3)


if __name__ == "__main__":
    unittest.main()
