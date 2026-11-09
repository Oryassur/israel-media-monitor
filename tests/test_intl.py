"""intl: which all-items get (re)classified in a run."""
import unittest

from pipeline import intl
from pipeline.common import INTL_PROMPT_PATH, INTL_VERSION, item_id
from pipeline.publish import INTL_GROUPS

TS = "2026-09-11T10:00:00Z"
SRC = {"bbc": {"name": "bbc"}}


def rec(h, **kw):
    r = {"id": item_id("bbc", h), "source": "bbc", "headline": h,
         "first_seen": "2026-09-11T08:00:00Z", "last_seen": TS}
    r.update(kw)
    return r


class TestPendingClassification(unittest.TestCase):
    def test_selection(self):
        on_page = ["Visible old-version headline here", "Visible current-version headline",
                   "Visible never classified headline"]
        recs = [
            rec(on_page[0], intl=True, topic="other", iv="i0"),        # visible, old rubric -> reclassify
            rec(on_page[1], intl=False, topic=None, iv=INTL_VERSION),  # visible, current -> skip
            rec(on_page[2]),                                           # visible, never classified -> classify
            rec("Gone old-version headline", intl=True, topic="x", iv="i0"),  # not visible -> leave (old iv kept)
            rec("Gone stale unclassified", first_seen="2026-09-01T00:00:00Z"),  # outside retry window
            rec("Fresh unclassified not on page"),                     # inside window -> classify
        ]
        retired = rec("From a retired source"); retired["source"] = "ap"
        recs.append(retired)
        allidx = {r["id"]: r for r in recs}
        per_source = {"bbc": {"ok": True, "top20": [(h, i + 1, 5) for i, h in enumerate(on_page)]},
                      "cnn": {"ok": False, "top20": []}}
        got = [r["headline"] for r in intl.pending_classification(allidx, per_source, TS, SRC)]
        self.assertEqual(sorted(got), sorted([on_page[0], on_page[2], "Fresh unclassified not on page"]))
        # on-page items come first so the run's aggregate row is consistent
        self.assertEqual(got[-1], "Fresh unclassified not on page")


class TestUpsertAllitems(unittest.TestCase):
    SOURCES = [{"name": "bbc", "lang": "en"}, {"name": "cnn", "lang": "en"}]

    def test_url_is_stored_on_new_records_and_backfilled_on_visible_old_ones(self):
        new_h, old_h, bare_h = "A brand new front page headline", "An older headline still on the page", "A headline the feed gave no link for"
        old = rec(old_h, best_rank=9, best_weight=3)          # written before urls were stored
        allidx = {old["id"]: old}
        per_source = {
            "bbc": {"ok": True, "top20": [(new_h, 1, 10), (old_h, 2, 5), (bare_h, 3, 5)],
                    "urls": {new_h: "https://www.bbc.com/news/new", old_h: "https://www.bbc.com/news/old"}},
            "cnn": {"ok": False, "top20": []},
        }
        intl.upsert_allitems(allidx, self.SOURCES, per_source, TS)
        new = allidx[item_id("bbc", new_h)]
        self.assertEqual(new["url"], "https://www.bbc.com/news/new")
        self.assertEqual((new["first_seen"], new["best_rank"], new["best_weight"], new["lang"]), (TS, 1, 10, "en"))
        self.assertEqual(old["url"], "https://www.bbc.com/news/old")
        self.assertEqual((old["best_rank"], old["best_weight"], old["last_seen"]), (2, 5, TS))
        self.assertNotIn("url", allidx[item_id("bbc", bare_h)])
        self.assertEqual(len(allidx), 3)

    def test_existing_url_is_never_overwritten_and_missing_urls_key_is_tolerated(self):
        h = "A headline whose link changed its tracking suffix"
        r = rec(h, url="https://www.bbc.com/news/first", best_rank=1, best_weight=10)
        allidx = {r["id"]: r}
        intl.upsert_allitems(allidx, self.SOURCES, {
            "bbc": {"ok": True, "top20": [(h, 4, 5)], "urls": {h: "https://www.bbc.com/news/second"}},
            "cnn": {"ok": True, "top20": [("A headline from a caller that passes no urls", 1, 10)]},
        }, TS)
        self.assertEqual(r["url"], "https://www.bbc.com/news/first")
        self.assertNotIn("url", allidx[item_id("cnn", "A headline from a caller that passes no urls")])


class TestRubricVocabulary(unittest.TestCase):
    def test_groups_cover_prompt_slugs(self):
        self.assertEqual(INTL_VERSION, "i3")
        text = INTL_PROMPT_PATH.read_text()
        for _, slugs in INTL_GROUPS:
            for slug in slugs:
                self.assertIn(f"`{slug}`", text, slug)


if __name__ == "__main__":
    unittest.main()
