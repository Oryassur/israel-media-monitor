"""Real-browser fetch for fronts a plain HTTP client cannot read.

Two kinds of homepage defeat `extract.fetch_html`: pages that ship no headlines
in their HTML and build the front in JavaScript (Clarín, Onet, Süddeutsche, the
Schibsted and Finnish papers), and pages behind a bot wall that answers a plain
request with 401/402/403 or a JavaScript challenge (AP, the Reach and DPG Media
fronts). `render_html` loads the page in headless Chromium and returns the DOM
once scripts have run, so `extract_items` sees what a reader sees.

The line the owner drew (CLAUDE.md, Expansion): an honest user agent and
robots.txt respected, never defeating bot detection or CAPTCHAs. So:

- the browser presents its own default user agent, which names HeadlessChrome;
  nothing is spoofed, and a site that chooses to refuse headless browsers is
  simply recorded as a failed fetch like any other 403;
- robots.txt is fetched first and the homepage is only loaded if the rules for
  our token (or the `*` group) allow it — a disallow raises `RobotsDisallowed`,
  which run.py logs as a fetch failure;
- images, media and fonts are not downloaded (we only need the markup), one
  browser is shared across the run and closed at the end.

Playwright is imported lazily so the plain pipeline keeps running where it is not
installed; only sources with `render: browser` in sources.yaml come through here.
"""
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests

BOT_TOKEN = "israel-media-monitor"
ROBOTS_UA = f"{BOT_TOKEN}/2.0 (+https://github.com/Oryassur/israel-media-monitor)"
SETTLE_MS = 2500        # scripts get this long after DOMContentLoaded to place the headlines
PAGE_TIMEOUT_MS = 45000
BLOCKED_RESOURCES = {"image", "media", "font"}

_pw = None
_browser = None
_robots_cache = {}


class RobotsDisallowed(Exception):
    pass


def robots_allows(url: str, timeout: int = 10) -> bool:
    """True unless the site's robots.txt disallows `url` for our token or for `*`.

    Unreachable or malformed robots.txt counts as allowed (the conventional
    reading), a 401/403 on robots.txt as disallowed, as urllib's parser does.
    """
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    rp = _robots_cache.get(origin)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(urljoin(origin, "/robots.txt"), timeout=timeout,
                             headers={"User-Agent": ROBOTS_UA})
            if r.status_code in (401, 403):
                rp.disallow_all = True
            elif r.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(r.text.splitlines())
        except requests.RequestException:
            rp.allow_all = True
        _robots_cache[origin] = rp
    return rp.can_fetch(BOT_TOKEN, url)


def _get_browser():
    global _pw, _browser
    if _pw is None:
        from playwright.sync_api import sync_playwright  # lazy: optional dependency
        _pw = sync_playwright().start()  # started once per process; a second start() breaks the sync API
    if _browser is None:
        try:
            _browser = _pw.chromium.launch(headless=True)
        except Exception:  # noqa: BLE001 — no chromium_headless_shell build: use the full Chromium headless
            _browser = _pw.chromium.launch(headless=True, channel="chromium")
    return _browser


def render_html(url: str, timeout_ms: int = PAGE_TIMEOUT_MS, settle_ms: int = SETTLE_MS) -> str:
    """Load `url` in headless Chromium and return the rendered document."""
    if not robots_allows(url):
        raise RobotsDisallowed(f"robots.txt disallows {url}")
    browser = _get_browser()
    ctx = browser.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
    try:
        ctx.route("**/*", lambda route: route.abort()
                  if route.request.resource_type in BLOCKED_RESOURCES else route.continue_())
        page = ctx.new_page()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if resp is not None and resp.status >= 400:
            raise requests.HTTPError(f"{resp.status} for {url}")
        page.wait_for_timeout(settle_ms)
        return page.content()
    finally:
        ctx.close()


def close():
    """Shut the shared browser down (end of run; safe to call when unused)."""
    global _pw, _browser
    try:
        if _browser is not None:
            _browser.close()
        if _pw is not None:
            _pw.stop()
    finally:
        _browser = None
        _pw = None
