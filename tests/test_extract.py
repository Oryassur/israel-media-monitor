"""extract_items: page chrome (nav, header, promos, credits, hubs) is never a headline."""
import unittest

from pipeline.extract import extract_items

PAGE = """<html><body><main>
<a href="https://abonnement.lefigaro.fr/abonnement-premium-figaro-vente-flash?app=Figaro">VENTE FLASH -70% par mois pendant 12 mois</a>
<a href="https://www.lefigaro.fr/international/un-vrai-titre-assez-long-pour-passer-20260911">Un vrai titre d'article assez long pour passer le filtre</a>
<a href="https://boutique.lefigaro.fr/offre">Une offre de la boutique avec un texte assez long</a>
<a href="https://sport.lefigaro.fr/football/un-titre-sportif-assez-long">Un titre sportif sur le sous-domaine sport, gardé</a>
</main></body></html>"""


TAGS = """<html><body><main>
<div class="trending"><a href="/tag/us-israel-attack-on-iran-2026">US-Israel attack on Iran 2026 tag link</a></div>
<a href="https://www.euronews.com/topic/israeli-palestinian-conflict-1n5j">Israeli-Palestinian conflict topic hub link</a>
<a href="https://www.euronews.com/2026/09/15/un-urges-full-access-for-investigators">UN urges full access for investigators as Gaza death toll mounts</a>
<a href="https://www.euronews.com/culture/2026/09/14/tags-of-the-year-a-real-headline">Tags of the year: a real article whose path merely contains the word</a>
</main></body></html>"""


class TestSkipTagPages(unittest.TestCase):
    def test_tag_and_topic_hubs_skipped(self):
        got = [it["url"] for it in extract_items(TAGS, "https://www.euronews.com", "main")]
        self.assertEqual(got, [
            "https://www.euronews.com/2026/09/15/un-urges-full-access-for-investigators",
            "https://www.euronews.com/culture/2026/09/14/tags-of-the-year-a-real-headline",
        ])


CHROME = """<html><body>
<header id="site"><a href="/">British Broadcasting Corporation logo link text</a>
  <a href="/programs/europe-today">Europe Today, the flagship morning TV show</a></header>
<div class="ds-burger-popin"><a href="/11-septembre/">Attentats du 11 septembre 2001 tag page link</a></div>
<div class="newsletter-signup"><a href="/2026/09/15/real-looking-newsletter-pitch">Sign up to our newsletter with the week's best photos</a></div>
<main>
 <section data-area="block>magletterarticles"><a href="/fitness/2026/09/15/evergreen-fitness-piece">Hilft mir ein Blutzucker-Tracker dabei, fit zu werden?</a></section>
 <article><header class="headline-group"><a href="/2026/09/15/card-headline-inside-article-header">Card headline inside an article header stays in</a></header></article>
 <a href="/2026/09/15/photo-story"><span>Brendan Smialowski/AFP/Getty Images</span></a>
 <a href="/2026/09/15/photo-story">The real headline that shares the photo's URL</a>
 <a href="/environment/climate-crisis">Climate crisis &amp; environment section link</a>
 <a href="/us/inside-nikes-stock-collapse">Inside Nike's stock collapse, a long slug without digits</a>
 <a href="#top-story">Skip next section Top Story accessibility link</a>
 <a href="/multimedia/video/tagesschau-100">Play tagesschau in 100 Sekunden video teaser</a>
</main></body></html>"""


class TestChrome(unittest.TestCase):
    def test_chrome_dropped_content_kept(self):
        got = [it["url"] for it in extract_items(
            CHROME, "https://www.example.com", "main", ["section[data-area='block>magletterarticles']"])]
        self.assertEqual(got, [
            "https://www.example.com/2026/09/15/card-headline-inside-article-header",
            "https://www.example.com/2026/09/15/photo-story",
            "https://www.example.com/us/inside-nikes-stock-collapse",
        ])
        # the photo-credit link no longer swallows the real headline's URL
        heads = [it["headline"] for it in extract_items(CHROME, "https://www.example.com", "main")]
        self.assertIn("The real headline that shares the photo's URL", heads)

    def test_page_header_and_menus_dropped_without_selector(self):
        heads = [it["headline"] for it in extract_items(CHROME, "https://www.example.com")]
        for bad in ("British Broadcasting", "Europe Today", "Attentats", "Sign up", "Skip next", "Play tagesschau",
                    "Climate crisis", "Getty"):
            self.assertFalse(any(bad in h for h in heads), bad)


USAT = """<html><body><main>
<div class="gnt_m_tt"><div><a class="gnt_m_tl" href="/story/news/2026/09/15/text-column-first-story/1/">Text column story that comes first in the DOM order</a></div>
<div><a class="gnt_m_he" href="/story/tv/2026/09/14/hero-card-story/2/">Hero card story that is displayed first on the page</a></div></div>
<div class="gnt_m_sb"><a href="/story/life/horoscopes/2026/09/15/horoscope/3/">Read your daily horoscope for Tuesday, September 15</a></div>
<div class="gnt_m gnt_m_sc"><a href="/story/tv/2026/09/14/second-column-story/4/">A second-column story that follows the bundles</a></div>
</main><script>gnt.fb = {"More Top Stories":[{"t":"First of the embedded More Top Stories list","u":"/story/news/2026/09/15/more-top-1/5/"},
{"t":"Hero card story that is displayed first on the page","u":"/story/tv/2026/09/14/hero-card-story/2/"}],
"Top Headlines":[{"t":"First of the embedded Top Headlines list","u":"/story/news/2026/09/15/top-headline-1/6/"}]};</script></body></html>"""


class TestUsaToday(unittest.TestCase):
    def test_lead_first_bundles_after_top_table_sidebar_dropped(self):
        got = [it["url"].split("/")[-2] for it in extract_items(
            USAT, "https://www.usatoday.com", "main", [".gnt_m_sb"], "a.gnt_m_he", "usatoday")]
        self.assertEqual(got, ["2", "1", "5", "6", "4"])  # hero, text column, More Top, Top Headlines (dup dropped), rest


class TestSkipHosts(unittest.TestCase):
    def test_commerce_subdomains_skipped(self):
        got = [it["url"] for it in extract_items(PAGE, "https://www.lefigaro.fr", "main")]
        self.assertEqual(got, [
            "https://www.lefigaro.fr/international/un-vrai-titre-assez-long-pour-passer-20260911",
            "https://sport.lefigaro.fr/football/un-titre-sportif-assez-long",
        ])


if __name__ == "__main__":
    unittest.main()
