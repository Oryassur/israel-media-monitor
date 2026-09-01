"""Dedup stability: trailing time/section metadata must not change item_id."""
import unittest

from pipeline.common import item_id, strip_meta_suffix

BBC_BASE = (
    "Israel says senior Hamas member seized as strikes kill three during Gaza raid "
    "Reports say the Israeli military carried out strikes after a raid by Israeli "
    "special forces and Israel-backed Palestinian militiamen was discovered."
)


class TestStripMetaSuffix(unittest.TestCase):
    def test_bbc_hours_ago_with_section(self):
        for h in ("3", "4", "5", "6"):
            self.assertEqual(
                strip_meta_suffix(f"{BBC_BASE} {h} hrs ago Middle East"), BBC_BASE
            )

    def test_variants(self):
        cases = [
            ("Headline text here 5 mins ago", "Headline text here"),
            ("Headline text here 1 hr ago US & Canada", "Headline text here"),
            ("Headline text here 2 days ago", "Headline text here"),
            ("Un titre quelconque il y a 3 heures", "Un titre quelconque"),
            ("Eine Schlagzeile vor 2 Std. Nahost", "Eine Schlagzeile"),
            ("Un titular cualquiera hace 4 horas", "Un titular cualquiera"),
            ("Un titolo qualsiasi 2 ore fa Medio Oriente", "Un titolo qualsiasi"),
        ]
        for raw, want in cases:
            self.assertEqual(strip_meta_suffix(raw), want)

    def test_no_false_positives(self):
        untouched = [
            "Hostage released after 300 days in Gaza",  # 'days' not followed by 'ago'
            "Minister quits two days ago-style row rumbles on inside coalition",
            "Israel captures top Hamas commander in Gaza strike, defense minister says",
            "How the ceasefire fell apart in 48 hours",
        ]
        for h in untouched:
            self.assertEqual(strip_meta_suffix(h), h)

    def test_item_id_stable_across_hours(self):
        ids = {item_id("BBC", f"{BBC_BASE} {h} hrs ago Middle East") for h in range(1, 24)}
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids.pop(), item_id("BBC", BBC_BASE))

    def test_item_id_distinct_stories_stay_distinct(self):
        self.assertNotEqual(
            item_id("BBC", "Israel strikes Gaza City"),
            item_id("BBC", "Israel strikes Rafah"),
        )


if __name__ == "__main__":
    unittest.main()
