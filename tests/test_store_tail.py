"""data/tail: ranks 21-40 of each front, recorded for the frontline-wire repo."""
import tempfile
import unittest
from pathlib import Path

from pipeline import run as pipeline_run
from pipeline import store
from pipeline.common import item_id

SOURCES = [{"name": "bbc", "lang": "en"}, {"name": "cnn", "lang": "en"}, {"name": "nyt", "lang": "en"}]
TS = "2026-11-09T10:45:00Z"


def tail(n=20, start=21, tag=""):
    return [(f"Tail headline number {r}{tag} on the page", r, f"https://example.org/{r}{tag}")
            for r in range(start, start + n)]


class TailCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        for name in ("TAIL_RUNS_DIR", "TAIL_ITEMS_DIR", "RUNS_DIR"):
            real = getattr(store, name)
            setattr(store, name, base / name.lower())
            self.addCleanup(lambda n=name, r=real: setattr(store, n, r))


class TestTailRows(TailCase):
    def test_rows_are_in_rank_order_and_failed_or_short_fronts_get_none(self):
        shuffled = list(reversed(tail()))
        runs, items = store.tail_rows(TS, SOURCES, {
            "bbc": {"ok": True, "top20": [], "tail": shuffled},
            "cnn": {"ok": False, "top20": [], "tail": tail()},   # failed fetch
            "nyt": {"ok": True, "top20": [], "tail": []},        # a 15-item feed has no tail
        })
        self.assertEqual([r["source"] for r in runs], ["bbc"])
        self.assertEqual(runs[0]["ids"][0], item_id("bbc", "Tail headline number 21 on the page"))
        self.assertEqual(len(runs[0]["ids"]), 20)
        self.assertEqual([it["rank"] for it in items], list(range(21, 41)))
        self.assertEqual(items[0], {"id": runs[0]["ids"][0], "source": "bbc", "url": "https://example.org/21",
                                    "headline": "Tail headline number 21 on the page", "lang": "en",
                                    "first_seen": TS, "rank": 21})

    def test_missing_url_and_repeated_headline(self):
        t = [("The same headline linked twice in the tail", 21, None),
             ("The same headline linked twice in the tail", 22, "https://example.org/x")]
        runs, items = store.tail_rows(TS, SOURCES, {"bbc": {"ok": True, "tail": t}})
        self.assertEqual(len(runs[0]["ids"]), 1)
        self.assertNotIn("url", items[0])


class TestAppendTail(TailCase):
    def test_items_are_written_once_and_runs_every_time(self):
        ps = {"bbc": {"ok": True, "tail": tail()}}
        self.assertEqual(pipeline_run.archive_tail(TS, SOURCES, ps, log=lambda *_: None), 1)
        later = "2026-11-09T11:45:00Z"
        ps2 = {"bbc": {"ok": True, "tail": tail(19) + [("A headline new to the tail this hour", 40, "https://example.org/new")]}}
        pipeline_run.archive_tail(later, SOURCES, ps2, log=lambda *_: None)
        self.assertEqual([r["ts"] for r in store.load_all_tail_runs()], [TS, later])
        items = store.load_all_tail_items()
        self.assertEqual(len(items), 21)
        self.assertEqual(len({it["id"] for it in items}), 21)
        self.assertEqual(items[-1]["first_seen"], later)

    def test_item_seen_last_month_is_not_rewritten(self):
        pipeline_run.archive_tail("2026-10-31T23:45:00Z", SOURCES, {"bbc": {"ok": True, "tail": tail()}}, log=lambda *_: None)
        pipeline_run.archive_tail("2026-11-01T00:45:00Z", SOURCES, {"bbc": {"ok": True, "tail": tail()}}, log=lambda *_: None)
        self.assertEqual(len(store.load_all_tail_items()), 20)
        self.assertEqual(len(store.load_all_tail_runs()), 2)

    def test_tail_runs_are_pruned_and_data_runs_is_untouched(self):
        store.append_runs("2026-07-01T00:45:00Z", [{"ts": "2026-07-01T00:45:00Z", "source": "bbc", "ids": ["a"]}],
                          retention_days=10_000)
        runs, items = store.tail_rows("2026-07-01T00:45:00Z", SOURCES, {"bbc": {"ok": True, "tail": tail()}})
        store.append_tail("2026-07-01T00:45:00Z", runs, items)
        pipeline_run.archive_tail(TS, SOURCES, {"bbc": {"ok": True, "tail": tail(tag="b")}}, log=lambda *_: None)
        self.assertEqual([r["ts"] for r in store.load_all_tail_runs()], [TS])   # July row is past 90 days
        self.assertEqual(len(store.load_all_runs()), 1)                         # pruning the tail left data/runs alone
        self.assertEqual(len(store.load_all_tail_items()), 40)                  # items are never pruned

    def test_never_raises(self):
        logged = []
        n = pipeline_run.archive_tail(TS, SOURCES, {"bbc": {"ok": True, "tail": "not-a-list"}}, log=logged.append)
        self.assertEqual(n, 0)
        self.assertIn("archive failed", logged[0])
        self.assertEqual(pipeline_run.archive_tail(TS, SOURCES, {}, log=logged.append), 0)


if __name__ == "__main__":
    unittest.main()
