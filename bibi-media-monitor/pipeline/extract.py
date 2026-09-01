"""Fetch homepages and extract headline links with prominence ranks."""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Link text shorter than this is treated as navigation, not a headline.
# Hebrew packs more meaning per character than English, so its floor is lower.
MIN_HEADLINE_LEN = {"he": 15, "en": 25}
# Sections of the page that are never editorial content.
SKIP_ANCESTORS = {"nav", "footer", "aside", "form"}
SKIP_HREF_PAT = re.compile(
    r"/(video|videos|live-tv|newsletters?|podcasts?|games|crosswords?|recipes|"
    r"horoscopes?|account|subscribe|login|signin|register|terms|privacy|about|"
    r"contact|advertis|shop|store|deals|coupons|tags?|category|redmail)(/|$)",
    re.I,
)


def fetch_html(url: str, timeout: int = 25) -> str:
    resp = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": UA,
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.7,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    resp.raise_for_status()
    return resp.text


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_items(html: str, base_url: str, selector: str = None, lang: str = "he"):
    """Return headline items in page order: [{rank, headline, url}].

    Rank is the order of first appearance in the DOM, which approximates
    editorial prominence on virtually all news homepages (top story first).
    """
    soup = BeautifulSoup(html, "html.parser")
    scope = soup.select_one(selector) if selector else None
    scope = scope or soup.body or soup
    host = urlparse(base_url).netloc.split(":")[0].removeprefix("www.")
    min_len = MIN_HEADLINE_LEN.get(lang, MIN_HEADLINE_LEN["en"])

    items, seen_text, seen_urls = [], set(), set()
    for a in scope.find_all("a", href=True):
        # skip links inside non-editorial chrome
        if any(p.name in SKIP_ANCESTORS for p in a.parents):
            continue
        text = _clean_text(a.get_text(" "))
        if len(text) < min_len or len(text) > 300:
            continue
        href = urljoin(base_url, a["href"].split("#")[0])
        pu = urlparse(href)
        if pu.scheme not in ("http", "https"):
            continue
        link_host = pu.netloc.split(":")[0].removeprefix("www.")
        # same site (allow subdomains) only
        if not (link_host == host or link_host.endswith("." + host) or host.endswith("." + link_host)):
            continue
        if SKIP_HREF_PAT.search(pu.path):
            continue
        key = text.lower()
        if key in seen_text or href in seen_urls:
            continue
        seen_text.add(key)
        seen_urls.add(href)
        items.append({"rank": len(items) + 1, "headline": text, "url": href})
    return items


def prominence_weight(rank: int, total: int = 0) -> int:
    """Method v2: attention is top-heavy, so weights follow a steep curve.

    Rank 1 x10, 2-5 x5, 6-10 x3, 11-20 x1, 21+ x0. Weight-0 stories are still
    captured, scored, and shown in the drill-down ("below fold"), but the
    attention/sentiment indexes measure the top-20 window only — which also
    makes the share denominator comparable across long and short homepages.
    """
    if rank == 1:
        return 10
    if rank <= 5:
        return 5
    if rank <= 10:
        return 3
    if rank <= 20:
        return 1
    return 0
