"""Enrichment: meta extraction precedence and the pending queue rules."""
import unittest
from datetime import datetime, timezone

from pipeline import enrich
from pipeline.enrich import extract_meta, pending_enrichment

BASE = "https://www.example.com/news/2026/09/10/some-article"
NOW = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)


def page(head_inner: str, body: str = "<p>body</p>") -> str:
    return f"<!doctype html><html><head>{head_inner}</head><body>{body}</body></html>"


class TestExtractMeta(unittest.TestCase):
    def test_og_over_twitter_over_link(self):
        html = page(
            '<meta name="twitter:image" content="https://cdn.example.com/tw.jpg">'
            '<link rel="image_src" href="/link.jpg">'
            '<meta property="og:image" content="https://cdn.example.com/og.jpg">'
            '<meta property="og:description" content="A sufficiently long og description here.">'
            '<meta name="description" content="A plain description that should lose to og.">'
        )
        img, desc = extract_meta(html, BASE)
        self.assertEqual(img, "https://cdn.example.com/og.jpg")
        self.assertEqual(desc, "A sufficiently long og description here.")

    def test_twitter_then_link_fallbacks(self):
        html = page('<meta name="twitter:image" content="https://cdn.example.com/tw.jpg">')
        self.assertEqual(extract_meta(html, BASE)[0], "https://cdn.example.com/tw.jpg")
        html = page('<link rel="image_src" href="/img/link.jpg">')
        self.assertEqual(extract_meta(html, BASE)[0], "https://www.example.com/img/link.jpg")

    def test_relative_and_http_rewrite(self):
        html = page('<meta property="og:image" content="http://www.example.com/a.png">')
        self.assertEqual(extract_meta(html, BASE)[0], "https://www.example.com/a.png")
        html = page('<meta property="og:image" content="../pics/b.png">')
        self.assertEqual(extract_meta(html, BASE)[0], "https://www.example.com/news/2026/09/pics/b.png")

    def test_rejects_data_uri_and_short_desc(self):
        html = page(
            '<meta property="og:image" content="data:image/png;base64,AAAA">'
            '<meta name="description" content="too short">'
        )
        self.assertEqual(extract_meta(html, BASE), (None, None))

    def test_desc_whitespace_and_cap(self):
        long = "word " * 100
        html = page(f'<meta name="description" content="  spaced\n\n out  {long}">')
        _, desc = extract_meta(html, BASE)
        self.assertTrue(desc.startswith("spaced out word"))
        self.assertLessEqual(len(desc), enrich.MAX_DESC_LEN)

    def test_no_head(self):
        self.assertEqual(extract_meta("<html><body>nothing</body></html>", BASE), (None, None))
        self.assertEqual(extract_meta("", BASE), (None, None))


def item(i, **kw):
    r = {"id": f"i{i}", "source": "nyt", "url": f"https://www.nytimes.com/{i}",
         "headline": f"Headline {i}", "related": True, "best_weight": 5,
         "first_seen": "2026-09-10T20:00:00Z"}
    r.update(kw)
    return r


class TestPendingEnrichment(unittest.TestCase):
    def test_filters(self):
        idx = {r["id"]: r for r in [
            item(1),                                   # qualifies
            item(2, best_weight=1),                    # below top-10
            item(3, related=False),                    # rejected by scorer
            item(4, related=None),                     # unscored
            item(5, img="https://x/y.jpg"),            # already enriched
            item(6, desc="has a description already"),  # already enriched
            item(7, enr_n=3),                          # gave up
            item(8, enr_n=1, first_seen="2026-09-01T00:00:00Z"),  # retry too old
            item(9, enr_n=0, first_seen="2026-08-01T00:00:00Z"),  # first attempt: unconditional
            item(10, url=""),                          # no url
        ]}
        got = [r["id"] for r in pending_enrichment(idx, NOW)]
        self.assertEqual(sorted(got), ["i1", "i9"])

    def test_order_and_cap(self):
        idx = {}
        for i in range(60):
            idx[f"i{i}"] = item(i, best_weight=[1, 3, 5, 10][i % 4] if i % 4 else 3,
                                first_seen=f"2026-09-10T{i % 24:02d}:00:00Z")
        got = pending_enrichment(idx, NOW)
        self.assertLessEqual(len(got), enrich.ENRICH_MAX_PER_RUN)
        weights = [r["best_weight"] for r in got]
        self.assertEqual(weights, sorted(weights, reverse=True))
        # within equal weight, newest first
        tens = [r["first_seen"] for r in got if r["best_weight"] == 10]
        self.assertEqual(tens, sorted(tens, reverse=True))

    def test_enrich_items_marks_attempt_and_skips_headline_desc(self):
        idx = {"a": item(1, headline="Exactly the description"), "b": item(2)}
        calls = []

        def fake_fetch(url, timeout=0):
            calls.append(url)
            if url.endswith("/2"):
                raise RuntimeError("boom")
            return page('<meta property="og:description" content="Exactly the description">'
                        '<meta property="og:image" content="https://cdn/x.jpg">')

        orig = enrich.fetch_html
        enrich.fetch_html = fake_fetch
        try:
            ok, attempted = enrich.enrich_items(idx, "2026-09-11T00:00:00Z", log=lambda m: None, now=NOW)
        finally:
            enrich.fetch_html = orig
        self.assertEqual((ok, attempted), (1, 2))
        self.assertEqual(idx["a"]["img"], "https://cdn/x.jpg")
        self.assertIsNone(idx["a"]["desc"])
        self.assertEqual(idx["a"]["enr_n"], 1)
        self.assertEqual(idx["b"]["enr_n"], 1)
        self.assertNotIn("img", idx["b"])


if __name__ == "__main__":
    unittest.main()
