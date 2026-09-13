"""publish: per-source dashboard descriptor."""
import tempfile
import unittest
from pathlib import Path

from pipeline import publish
from pipeline.publish import INTL_GROUP_LABELS, INTL_GROUPS, _intl_series, _source_meta, _topic_groups


def src(**kw):
    s = {"name": "dw", "display": "DW", "url": "https://www.dw.com/en/", "country": "INT",
         "lang": "en", "lean": "center", "type": "broadcaster"}
    s.update(kw)
    return s


class TestSourceMeta(unittest.TestCase):
    def test_home_fallback_domain_and_logo(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "dw.png").write_bytes(b"\x89PNG")
            m = _source_meta(src(home="DE"), Path(d))
            self.assertEqual(m["home"], "DE")
            self.assertEqual(m["domain"], "dw.com")
            self.assertEqual(m["logo"], "logos/dw.png")
            m = _source_meta(src(name="bbc", url="https://bbc.com/news", country="UK"), Path(d))
            self.assertEqual(m["home"], "UK")
            self.assertEqual(m["domain"], "bbc.com")
            self.assertIsNone(m["logo"])
            self.assertNotIn("url", m)


class TestIntlGroups(unittest.TestCase):
    def test_topic_groups_fold(self):
        g = _topic_groups({"us-politics": 5, "north-america": 1, "israel-gaza": 3, "zzz-unknown": 2})
        self.assertEqual(len(g), len(INTL_GROUPS))
        self.assertEqual(g[INTL_GROUP_LABELS.index("United States")], 6)
        self.assertEqual(g[INTL_GROUP_LABELS.index("Israel")], 3)
        self.assertEqual(g[-1], 2)  # unknown slug -> Other
        self.assertEqual(_topic_groups(None), [0] * len(INTL_GROUPS))
        self.assertEqual(INTL_GROUP_LABELS[2], "Israel")

    def test_intl_series_shape(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "intl").mkdir()
            rows = [
                {"ts": "2026-09-13T01:00:00Z", "source": "bbc", "total_w": 55, "intl_w": 20, "uncl_w": 0,
                 "topics": {"israel-gaza": 6, "us-politics": 10, "other": 4}, "iv": "i3"},
                {"ts": "2026-09-13T02:00:00Z", "source": "bbc", "total_w": 55, "intl_w": 10, "uncl_w": 0,
                 "topics": {"ukraine-russia": 10}, "iv": "i3"},
                {"ts": "2026-09-13T03:00:00Z", "source": "bbc", "total_w": 55, "intl_w": 9, "uncl_w": 9,
                 "topics": {}},  # unclassified (no iv) -> skipped
            ]
            (Path(d) / "intl" / "2026-09.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            snaps = [{"ts": r["ts"], "source": "bbc", "fetch_ok": "1", "israel_weight": "5"} for r in rows]
            orig = publish.DATA
            publish.DATA = Path(d)
            try:
                out = _intl_series(snaps, "2026-09-01T00:00:00Z")
            finally:
                publish.DATA = orig
            self.assertEqual(out["cols"][-1], "g")
            self.assertEqual(len(out["hourly"]), 2)
            self.assertEqual(len(out["hourly"][0]), 7)
            self.assertEqual(out["hourly"][0][6][INTL_GROUP_LABELS.index("Israel")], 6)
            day = out["daily"][0]
            self.assertEqual(day[:6], ["2026-09-13", "bbc", 110, 30, 0, 10])
            self.assertEqual(day[6][INTL_GROUP_LABELS.index("Russia & Ukraine")], 10)
            self.assertEqual(sum(day[6]), 30)


if __name__ == "__main__":
    unittest.main()
