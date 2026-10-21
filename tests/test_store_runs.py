"""data/runs: the ranked archive of each run's top-20 (order, retention, safety)."""
import tempfile
import unittest
from pathlib import Path

from pipeline import run as pipeline_run
from pipeline import store
from pipeline.common import item_id

SOURCES = [{"name": "bbc"}, {"name": "cnn"}, {"name": "dw"}]
TS = "2026-10-18T10:45:00Z"


def per_source(**kw):
    ps = {"bbc": {"ok": True, "top20": []}, "cnn": {"ok": False, "top20": []},
          "dw": {"ok": True, "top20": []}}
    ps.update(kw)
    return ps


class RunsDirCase(unittest.TestCase):
    """Each test gets its own empty data/runs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "runs"
        real = store.RUNS_DIR
        store.RUNS_DIR = self.dir
        self.addCleanup(lambda: setattr(store, "RUNS_DIR", real))


class TestRunRows(RunsDirCase):
    def test_rank_order_and_missing_sources(self):
        heads = [f"Headline number {i} on the front page" for i in range(1, 5)]
        # extraction order scrambled: the row must come out in rank order
        top20 = [(heads[2], 3, 5), (heads[0], 1, 10), (heads[3], 4, 5), (heads[1], 2, 5)]
        rows = store.run_rows(TS, SOURCES, per_source(bbc={"ok": True, "top20": top20}))
        self.assertEqual([r["source"] for r in rows], ["bbc"])  # cnn down, dw empty
        self.assertEqual(rows[0]["ts"], TS)
        self.assertEqual(rows[0]["ids"], [item_id("bbc", h) for h in heads])

    def test_round_trip_keeps_order(self):
        top20 = [(f"Headline number {i} on the front page", i, 5) for i in range(20, 0, -1)]
        rows = store.run_rows(TS, SOURCES, per_source(bbc={"ok": True, "top20": top20}))
        store.append_runs(TS, rows)
        got = store.load_all_runs()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0], {"ts": TS, "source": "bbc", "ids": rows[0]["ids"]})
        self.assertEqual(len(got[0]["ids"]), 20)
        # the row carries nothing but the three archive fields
        self.assertEqual(sorted(got[0]), sorted(store.RUN_FIELDS))


class TestRetention(RunsDirCase):
    def write(self, ts, source="bbc"):
        store.append_runs(ts, [{"ts": ts, "source": source, "ids": ["a" * 16]}],
                          retention_days=10_000)  # park history without pruning

    def test_prune_drops_out_of_window_keeps_in_window(self):
        old_month = "2026-06-01T00:45:00Z"   # whole file out of window
        edge_old = "2026-07-10T00:45:00Z"    # same month as the cutoff, too old
        edge_new = "2026-07-25T00:45:00Z"    # same month as the cutoff, in window
        fresh = "2026-10-18T10:45:00Z"
        for ts in (old_month, edge_old, edge_new, fresh):
            self.write(ts)
        self.assertEqual(len(store.load_all_runs()), 4)

        dropped = store.prune_runs("2026-10-18T10:45:00Z", days=90)  # cutoff 2026-07-20
        self.assertEqual(dropped, 2)
        self.assertEqual([r["ts"] for r in store.load_all_runs()], [edge_new, fresh])
        self.assertFalse((self.dir / "2026-06.jsonl").exists())  # empty file removed
        self.assertTrue((self.dir / "2026-07.jsonl").exists())

    def test_append_prunes_with_the_default_retention(self):
        self.write("2026-01-05T00:45:00Z")
        store.append_runs(TS, [{"ts": TS, "source": "bbc", "ids": ["b" * 16]}])
        self.assertEqual([r["ts"] for r in store.load_all_runs()], [TS])
        self.assertEqual(store.RUN_RETENTION_DAYS, 90)

    def test_prune_on_empty_store_is_a_no_op(self):
        self.assertEqual(store.prune_runs(TS), 0)

    def test_load_recent_runs_filters_by_ts(self):
        for ts in ("2026-10-16T10:45:00Z", "2026-10-17T10:45:00Z", TS):
            self.write(ts)
        got = store.load_recent_runs("2026-10-17T00:00:00Z")
        self.assertEqual([r["ts"] for r in got], ["2026-10-17T10:45:00Z", TS])


class TestArchivePassNeverRaises(RunsDirCase):
    """The hourly run must survive anything this pass can do."""

    def test_write_failure_is_swallowed_and_logged(self):
        logged = []

        def boom(*a, **kw):
            raise OSError("read-only file system")

        real = pipeline_run.append_runs
        pipeline_run.append_runs = boom
        self.addCleanup(lambda: setattr(pipeline_run, "append_runs", real))
        n = pipeline_run.archive_run(TS, SOURCES, per_source(
            bbc={"ok": True, "top20": [("A headline on the front page", 1, 10)]}),
            log=logged.append)
        self.assertEqual(n, 0)
        self.assertEqual(len(logged), 1)
        self.assertIn("archive failed", logged[0])

    def test_malformed_per_source_is_swallowed(self):
        logged = []
        n = pipeline_run.archive_run(TS, SOURCES, {"bbc": {"ok": True, "top20": "not-a-list"}},
                                    log=logged.append)
        self.assertEqual(n, 0)
        self.assertTrue(logged and "archive failed" in logged[0])
        self.assertEqual(store.load_all_runs(), [])

    def test_happy_path_writes_one_row_per_fetched_source(self):
        logged = []
        n = pipeline_run.archive_run(TS, SOURCES, per_source(
            bbc={"ok": True, "top20": [("A headline on the front page", 1, 10)]},
            dw={"ok": True, "top20": [("Eine Schlagzeile auf der Startseite", 1, 10)]}),
            log=logged.append)
        self.assertEqual(n, 2)
        self.assertEqual([r["source"] for r in store.load_all_runs()], ["bbc", "dw"])

    def test_run_rows_tolerates_a_source_with_no_entry(self):
        self.assertEqual(store.run_rows(TS, SOURCES + [{"name": "ghost"}], per_source()), [])


if __name__ == "__main__":
    unittest.main()
