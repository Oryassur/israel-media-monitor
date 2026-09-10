"""publish: per-source dashboard descriptor."""
import tempfile
import unittest
from pathlib import Path

from pipeline.publish import _source_meta


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


if __name__ == "__main__":
    unittest.main()
