"""Fetch homepages and extract headline links with prominence ranks."""
import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .common import strip_meta_suffix

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# Outlets that edit a separate front page for phones (CNN, USA Today — found by
# fetching every homepage with both identities at the same moment, 2026-09-15)
# are measured on that front: `ua: mobile` in sources.yaml.
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# Link text shorter than this is treated as navigation, not a headline.
MIN_HEADLINE_LEN = 25
# Sections of the page that are never editorial content.
SKIP_ANCESTORS = {"nav", "footer", "aside", "form"}
# A <header> is page chrome only at page level; inside an article/section/list it
# is the card's own headline group (El Mundo, Spiegel, Fox wrap headlines in one).
_CONTENT_TAGS = {"main", "article", "section", "li", "ul"}
# …and containers whose class/id names them as chrome (newsletter boxes, promos,
# subscription pitches, accessibility skip links, sidebars of evergreen links).
SKIP_CLASS_PAT = re.compile(
    r"(^|[\s_-])(newsletter|advert|advertisement|sponsor|sponsored|marketing|"
    r"subscription|subscribe|paywall|skip|skiplink|masthead|topbar|toolbar|breadcrumb|"
    r"popin|popup|modal|drawer|offcanvas|burger|megamenu|mega-menu)"
    r"s?([\s_-]|$)",
    re.I,
)
# Link text that is a photo credit or an accessibility affordance, not a headline.
SKIP_TEXT_PAT = re.compile(
    r"(\s*/\s*(Getty Images|AFP|AP|Reuters|Bloomberg|Shutterstock|EPA|Alamy|NurPhoto|iStockphoto|"
    r"The New York Times|The Washington Post|Los Angeles Times|CNN|File)\b|"
    r"\b(via|for) (Getty|AP|Reuters|AFP|CNN|Shutterstock|Telegram)\b|"
    r"^(skip (to|next|the)|go back to|zum inhalt|direkt zum|aller au contenu|saltar al|vai al contenuto|play )|"
    r"überspringen\b)",
    re.I,
)
# Also topic/tag hub pages: a "Trending" tag in Euronews' header sat at rank 1
# for six days (2026-09-09..15) and SMH's "Israeli-Palestinian conflict" topic
# link at rank 9 — index pages, never headlines.
SKIP_HREF_PAT = re.compile(
    r"/(video|videos|live-tv|newsletters?|podcasts?|games|crosswords?|recipes|"
    r"horoscopes?|account|subscribe|login|signin|register|terms|privacy|about|"
    r"contact|kontakt|contacto|contatti|feedback|help|hilfe|aide|ayuda|aiuto|faq|"
    r"advertis|shop|store|deals|coupons|tags?|topics?|themes?|thema|themen|"
    r"sujets?|temas?|temi|dossiers?|juegos|jeux|giochi|spiele|puzzles?|crucigrama|sudoku|"
    r"kreuzwortraetsel|quiz|abonnement|abo|abos|abbonamenti|suscripci[oó]n(es)?|compte|"
    r"mon-compte|konto|mein-konto|cuenta|profil|profile|programs|programmes|shows|"
    r"galerie|galerien|bildergalerien|multimedia|fotogaleria|"
    r"newsticker|email|emails|pod-force-one|monitornewsletters)(/|$)",
    re.I,
)
# Article URLs carry a date, an id, or a long slug. A short digit-free path is a
# section or hub page ("/goodfood", "/environment/climate-crisis", "/programs/europe-today").
_MIN_SLUG_WORDS = 4


def looks_like_index(path: str) -> bool:
    if any(ch.isdigit() for ch in path):
        return False
    last = path.rstrip("/").rsplit("/", 1)[-1]
    last = re.sub(r"\.(html?|php|aspx?)$", "", last, flags=re.I)
    return len([w for w in re.split(r"[-_]+", last) if w]) < _MIN_SLUG_WORDS
# Commerce / account subdomains of the outlet's own domain (subscription offers,
# shops, job boards) — their links are promos, never headlines.
SKIP_HOST_PAT = re.compile(
    r"^(abonnement|abo|abos|abbonamenti|suscripciones?|subscri(be|ption)s?|boutique|shop|store|"
    r"tienda|jobs|emploi|immobilier|immo|kleinanzeigen|games|jeux|giochi|account|login|"
    r"newsletters?|events?|tickets?)\.",
    re.I,
)


def fetch_html(url: str, timeout: int = 25, ua: str = None) -> str:
    resp = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": UA_MOBILE if ua == "mobile" else UA,
            "Accept-Language": "en-US,en;q=0.8,fr;q=0.6,de;q=0.6,es;q=0.6,it;q=0.6",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    resp.raise_for_status()
    return resp.text


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_items(html: str, base_url: str, selector: str = None, skip=None, lead: str = None,
                  site: str = None):
    """Return headline items in page order: [{rank, headline, url}].

    Rank is the order of first appearance in the DOM, which approximates
    editorial prominence on virtually all news homepages (top story first).
    `selector` scopes extraction to the main content area; `skip` is a list of
    CSS selectors for blocks inside it that are never news (evergreen promo
    boxes, games, personalised "for you" carousels); `lead` is a CSS selector
    for the visual lead story's link(s) when the DOM puts a text column before
    the hero (USA Today) — matching items move to the front; `site` names a
    hook in SITE_HOOKS for outlets that embed part of the front page as data
    rather than markup.
    """
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "template"]):
        t.decompose()
    scope = soup.select_one(selector) if selector else None
    scope = scope or soup.body or soup
    for sel in skip or []:
        for el in scope.select(sel):
            el.decompose()
    lead_urls = set()
    if lead:
        for a in scope.select(lead):
            if a.name == "a" and a.get("href"):
                lead_urls.add(urljoin(base_url, a["href"].split("#")[0]))
    host = urlparse(base_url).netloc.split(":")[0].removeprefix("www.")

    items, seen_text, seen_urls = [], set(), set()
    for a in scope.find_all("a", href=True):
        # skip links inside non-editorial chrome
        if any(_is_chrome(p) for p in a.parents):
            continue
        head = a.find(class_=lambda c: c and "headline" in c.lower())
        raw_text = head.get_text(" ") if head and len(_clean_text(head.get_text(" "))) >= MIN_HEADLINE_LEN else a.get_text(" ")
        text = _strip_labels(strip_meta_suffix(_clean_text(raw_text)))
        if len(text) < MIN_HEADLINE_LEN or len(text) > 300:
            continue
        if SKIP_TEXT_PAT.search(text) or _LABEL_ONLY.match(text):
            continue
        href = urljoin(base_url, a["href"].split("#")[0])
        pu = urlparse(href)
        if pu.scheme not in ("http", "https"):
            continue
        # the homepage itself (logo, "skip to content" anchors) or a section index
        if pu.path in ("", "/") or looks_like_index(pu.path):
            continue
        link_host = pu.netloc.split(":")[0].removeprefix("www.")
        # same site (allow subdomains) only
        if not (link_host == host or link_host.endswith("." + host) or host.endswith("." + link_host)):
            continue
        if SKIP_HREF_PAT.search(pu.path) or SKIP_HOST_PAT.match(link_host):
            continue
        key = text.lower()
        if key in seen_text or href in seen_urls:
            continue
        seen_text.add(key)
        seen_urls.add(href)
        items.append({"headline": text, "url": href, "lead": href in lead_urls})
    if lead_urls:
        items.sort(key=lambda it: not it["lead"])  # stable: leads first, page order otherwise
    if site and site in SITE_HOOKS:
        items = SITE_HOOKS[site](html, base_url, items)
    for i, it in enumerate(items, 1):
        it["rank"] = i
        it.pop("lead", None)
    return items


def _usatoday_bundles(html: str, base_url: str, items):
    """USA Today ships its "More Top Stories" and "Top Headlines" lists as JSON
    (gnt.fb = {...}, the fallback for a client-side recommendation call) and
    fills the section blocks by script, so the markup alone yields the 7-story
    top table followed by sidebars (pets, photos, horoscopes). Insert the two
    editorial lists right after the top table, in their own order."""
    m = re.search(r"gnt\.fb\s*=\s*(\{)", html)
    if not m:
        return items
    start = m.start(1)
    depth = 0
    for end in range(start, len(html)):
        if html[end] == "{":
            depth += 1
        elif html[end] == "}":
            depth -= 1
            if depth == 0:
                break
    try:
        fb = json.loads(html[start:end + 1])
    except ValueError:
        return items
    seen = {it["url"] for it in items}
    extra = []
    # the phone front splits each list into numbered parts ("More Top Stories 2", …)
    def parts(prefix):
        keys = [k for k in fb if k == prefix or re.fullmatch(re.escape(prefix) + r" \d+", k)]
        return sorted(keys, key=lambda k: int(k.rsplit(" ", 1)[1]) if k != prefix else 1)
    for key in parts("More Top Stories") + parts("Top Headlines"):
        for e in fb.get(key) or []:
            t, u = e.get("t"), e.get("u")
            if not t or not u:
                continue
            u = urljoin(base_url, u)
            if u in seen or len(t) < MIN_HEADLINE_LEN:
                continue
            seen.add(u)
            extra.append({"headline": _clean_text(t), "url": u, "lead": False})
    # The editorial top = everything before the first deferred-section stub
    # (desktop: the top table; mobile: the hero + the first list modules). What
    # follows the stubs on either layout is sidebars and promos — dropped.
    soup = BeautifulSoup(html, "html.parser")
    top = set()
    for a in soup.find_all("a", href=True):
        if a.find_previous(class_="gnt_m_dl") is not None:
            break
        top.add(urljoin(base_url, a["href"].split("#")[0]))
    cut = max((i + 1 for i, it in enumerate(items) if it["url"] in top), default=0)
    return items[:cut] + extra


SITE_HOOKS = {"usatoday": _usatoday_bundles}


def _is_chrome(tag) -> bool:
    if tag.name in SKIP_ANCESTORS:
        return True
    if tag.name == "header" and not any(p.name in _CONTENT_TAGS for p in tag.parents):
        return True
    return _chrome_class(tag)


# Kicker/label decorations some sites render inside the link text: CNN's "• Analysis
# Analysis …" / "Live Updates 8 min ago …" prefixes and the "Show all" suffix on
# package titles. Cosmetic — they only touch the stored headline, never the ranking.
_LABEL_PREFIX = re.compile(
    r"^(?:•\s*)?(?:(?:Analysis|Video|Gallery|Live Updates|CNN Exclusive|Exclusive)\b(?:\s*\d+\s*(?:min|hrs?|hours?)\s+ago)?\s*){1,2}"
    r"(?:by\s+[A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+)?\s+)?",  # "Analysis by Stephen Collinson …" (two-token names)
    re.I,
)
_LABEL_SUFFIX = re.compile(r"\s+(?:Show all|Read more|\d+:\d\d)\s*$", re.I)


# Link text that is nothing but labels, durations and credits ("• Video 4:47 Video 4:47 CNN").
_LABEL_ONLY = re.compile(
    r"^[•\s]*(?:(?:Video|Gallery|Analysis|Live Updates|CNN Exclusive|Exclusive|CNN|Reuters|AP|AFP|"
    r"Getty Images|File|Clipped From Video|\d+:\d\d|via|/|,)\s*)+$",
    re.I,
)


_VIDEO_CARD = re.compile(r"^(?:•\s*)?Video\b.*\d+:\d\d\s*$", re.I)


def _strip_labels(text: str) -> str:
    if re.match(r"^(?:•\s*)?Video\b", text, re.I) and not _VIDEO_CARD.match(text):
        return text  # "Video shows the aftermath of …" is a headline, not a video-card label
    stripped = _LABEL_SUFFIX.sub("", _LABEL_PREFIX.sub("", text)).strip()
    return stripped if len(stripped) >= MIN_HEADLINE_LEN else text


def _chrome_class(tag) -> bool:
    ident = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "") + " " + (tag.get("role") or "")
    return bool(SKIP_CLASS_PAT.search(ident)) or tag.get("role") in ("navigation", "banner", "contentinfo", "complementary")


def prominence_weight(rank: int, total: int = 0) -> int:
    """Method v2: attention is top-heavy, so weights follow a steep curve.

    Rank 1 x10, 2-5 x5, 6-10 x3, 11-20 x1, 21+ x0. Only the top-20 window is
    ingested as items; stories beyond it count toward total_items (parser
    health) but nothing else — which also makes the share denominator
    comparable across long and short homepages.
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
