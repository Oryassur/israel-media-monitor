"""intl: which all-items get (re)classified in a run."""
import unittest

from pipeline import intl
from pipeline.common import INTL_VERSION, item_id

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


if __name__ == "__main__":
    unittest.main()
