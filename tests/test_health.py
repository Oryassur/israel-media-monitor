"""health: the parser canaries (rank1_frozen, headline_drop).

The point of these tests is as much the negatives as the positives: the owner
gets one email per incident, so a healthy outlet must never trip a canary.
"""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import health, store

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
SOURCES = [{"name": "bbc", "display": "BBC News"},
           {"name": "cnn", "display": "CNN"},
           {"name": "csmonitor", "display": "Christian Science Monitor"}]


def ts(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime(TS_FMT)


def snap(source, hours_ago, total_items, fetch_ok="1"):
    return {"ts": ts(hours_ago), "source": source, "fetch_ok": fetch_ok,
            "total_items": str(total_items)}


class TempDataCase(unittest.TestCase):
    """Isolate data/runs and data/items (the canaries read both)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for attr, name in (("RUNS_DIR", "runs"), ("ITEMS_DIR", "items")):
            real = getattr(store, attr)
            setattr(store, attr, Path(self.tmp.name) / name)
            self.addCleanup(lambda a=attr, r=real: setattr(store, a, r))

    def archive(self, source, rank1_ids, start_hours_ago=95):
        """One archived run per hour, rank 1 taken from `rank1_ids` in order."""
        for i, iid in enumerate(rank1_ids):
            t = ts(start_hours_ago - i)
            store.append_runs(t, [{"ts": t, "source": source,
                                   "ids": [iid, "filler0000000001", "filler0000000002"]}],
                              retention_days=10_000)


class TestRank1Frozen(TempDataCase):
    def test_frozen_rank1_alerts(self):
        self.archive("bbc", ["chrome0000000001"] * 90)
        alerts = health.rank1_frozen(NOW, SOURCES)
        self.assertEqual([a["key"] for a in alerts], ["rank1_frozen:bbc"])
        self.assertIn("BBC News", alerts[0]["title"])
        self.assertIn("chrome0000000001", alerts[0]["detail"])

    def test_healthy_outlet_is_not_flagged(self):
        # a real front page: the lead changes every few hours
        ids = [f"story{i // 4:011d}" for i in range(90)]
        self.archive("bbc", ids)
        self.assertEqual(health.rank1_frozen(NOW, SOURCES), [])

    def test_one_change_in_the_window_is_enough(self):
        ids = ["aaaa000000000001"] * 89 + ["bbbb000000000002"]
        self.archive("bbc", ids)
        self.assertEqual(health.rank1_frozen(NOW, SOURCES), [])

    def test_slow_weekly_is_exempt(self):
        self.archive("csmonitor", ["weekly0000000001"] * 90)
        self.assertEqual(health.rank1_frozen(NOW, SOURCES), [])

    def test_thin_archive_is_not_judged(self):
        self.archive("bbc", ["chrome0000000001"] * (health.RANK1_MIN_ROWS - 1))
        self.assertEqual(health.rank1_frozen(NOW, SOURCES), [])

    def test_archive_must_span_the_window(self):
        # 30 rows, but all from the last day: a store that started yesterday
        # knows nothing about the last four days
        self.archive("bbc", ["chrome0000000001"] * 30, start_hours_ago=23)
        self.assertEqual(health.rank1_frozen(NOW, SOURCES), [])

    def test_empty_archive(self):
        self.assertEqual(health.rank1_frozen(NOW, SOURCES), [])


class TestHeadlineDrop(unittest.TestCase):
    def rows(self, counts, source="bbc"):
        """counts newest-last, one row per hour."""
        n = len(counts)
        return [snap(source, n - i, c) for i, c in enumerate(counts)]

    def test_selector_break_alerts(self):
        rows = self.rows([50] * 40 + [4, 3, 5])
        alerts = health.headline_drop(NOW, rows)
        self.assertEqual([a["key"] for a in alerts], ["headline_drop:bbc"])
        self.assertIn("median of 50", alerts[0]["title"])
        self.assertIn("[4, 3, 5]", alerts[0]["detail"])

    def test_collapse_to_zero_alerts(self):
        alerts = health.headline_drop(NOW, self.rows([50] * 40 + [0, 0, 0]))
        self.assertEqual([a["key"] for a in alerts], ["headline_drop:bbc"])

    def test_healthy_outlet_is_not_flagged(self):
        self.assertEqual(health.headline_drop(NOW, self.rows([50, 46, 61, 55] * 12)), [])

    def test_single_run_dip_is_not_flagged(self):
        # one bad fetch (half a page rendered) must not mail anyone
        self.assertEqual(health.headline_drop(NOW, self.rows([50] * 42 + [3])), [])

    def test_small_outlet_cannot_collapse(self):
        self.assertEqual(health.headline_drop(NOW, self.rows([8] * 40 + [1, 2, 1])), [])

    def test_thin_history_is_not_judged(self):
        self.assertEqual(health.headline_drop(NOW, self.rows([50] * 10 + [1, 1, 1])), [])

    def test_failed_fetches_are_ignored_not_counted_as_zero(self):
        rows = self.rows([50] * 40) + [snap("bbc", 3, 0, fetch_ok="0"),
                                       snap("bbc", 2, 0, fetch_ok="0"),
                                       snap("bbc", 1, 0, fetch_ok="0")]
        self.assertEqual(health.headline_drop(NOW, rows), [])

    def test_already_down_source_is_skipped(self):
        rows = self.rows([50] * 40 + [0, 0, 0])
        self.assertEqual(health.headline_drop(NOW, rows, skip={"bbc"}), [])

    def test_sources_are_judged_independently(self):
        rows = self.rows([50] * 40 + [2, 2, 2]) + self.rows([50] * 43, source="cnn")
        self.assertEqual([a["key"] for a in health.headline_drop(NOW, rows)],
                         ["headline_drop:bbc"])


class TestCheckWiring(TempDataCase):
    """check() must emit the canaries alongside the old conditions, and must
    not lose the old ones if a canary blows up."""

    def setUp(self):
        super().setUp()
        snaps = Path(self.tmp.name) / "snapshots"
        snaps.mkdir(parents=True)
        real = health.DATA
        health.DATA = Path(self.tmp.name)
        self.addCleanup(lambda: setattr(health, "DATA", real))
        rows = []
        for h in range(43, 0, -1):  # a week's worth is not needed: 43 runs suffice
            rows.append(snap("bbc", h, 50 if h > 3 else 2))
            rows.append(snap("cnn", h, 40))
        for month in {r["ts"][:7] for r in rows}:
            with open(snaps / f"{month}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ts", "source", "fetch_ok", "total_items"])
                w.writeheader()
                for r in rows:
                    if r["ts"].startswith(month):
                        w.writerow(r)

    def test_canaries_reach_the_alert_list(self):
        self.archive("cnn", ["chrome0000000001"] * 90)
        keys = {a["key"] for a in health.check(NOW, SOURCES, {}, (0, 0))}
        self.assertIn("headline_drop:bbc", keys)
        self.assertIn("rank1_frozen:cnn", keys)

    def test_a_broken_canary_does_not_lose_the_other_conditions(self):
        def boom(*a, **kw):
            raise RuntimeError("canary bug")

        real = health.rank1_frozen
        health.rank1_frozen = boom
        self.addCleanup(lambda: setattr(health, "rank1_frozen", real))
        keys = {a["key"] for a in health.check(NOW, SOURCES, {}, (0, 0))}
        self.assertIn("headline_drop:bbc", keys)
        self.assertNotIn("rank1_frozen:cnn", keys)


class TestAlertKeysAreGeneric(unittest.TestCase):
    def test_alert_script_does_not_enumerate_keys(self):
        """scripts/alert.py groups by whatever keys health emits; a new key must
        not need a change there."""
        src = (Path(__file__).resolve().parents[1] / "scripts" / "alert.py").read_text()
        for key in ("source_down", "source_empty", "rank1_frozen", "headline_drop"):
            self.assertNotIn(key, src)


if __name__ == "__main__":
    unittest.main()
