#!/usr/bin/env python3
"""One-off: fetch each outlet's full wordmark logo into docs/logos/.

    python scripts/fetch_wordmarks.py            # all sources, skip existing
    python scripts/fetch_wordmarks.py bbc nyt    # just these
    python scripts/fetch_wordmarks.py --force

Source of truth is the logo in the outlet's Wikipedia infobox (usually an SVG
or PNG wordmark used for identification); the homepage header <img> whose alt
names the outlet is the fallback. Saves docs/logos/<name>.<ext> (svg preferred)
and writes docs/logos/contact-sheet.html for a visual check. Exit 1 if any
source failed so it can be hand-placed.
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import load_sources  # noqa: E402
from pipeline.extract import UA, fetch_html  # noqa: E402

OUT = ROOT / "docs" / "logos"
TIMEOUT = 20
HDRS = {"User-Agent": "israel-media-monitor/2.0 (logo fetch; github.com/Oryassur/israel-media-monitor)"}

# Wikipedia article whose infobox carries the wordmark
WIKI = {
    "nyt": "The New York Times", "usatoday": "USA Today", "nypost": "New York Post", "cnn": "CNN",
    "foxnews": "Fox News", "nbcnews": "NBC News", "newsweek": "Newsweek",
    "csmonitor": "The Christian Science Monitor", "washexaminer": "Washington Examiner",
    "bbc": "BBC News", "guardian": "The Guardian", "thetimes": "The Times", "dailymail": "Daily Mail",
    "independent": "The Independent", "dw": "Deutsche Welle", "euronews": "Euronews",
    "lemonde": "Le Monde", "lefigaro": "Le Figaro", "lacroix": "La Croix", "spiegel": "Der Spiegel",
    "bild": "Bild", "faz": "Frankfurter Allgemeine Zeitung", "tagesschau": "Tagesschau (German TV programme)",
    "elmundo": "El Mundo (Spain)", "corriere": "Corriere della Sera", "ilgiornale": "Il Giornale",
    "cbc": "CBC News", "globeandmail": "The Globe and Mail", "abcau": "ABC News (Australia)",
    "smh": "The Sydney Morning Herald",
}


def sniff(data: bytes):
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:600].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:6000].lower()):
        return "svg"
    return None


def wiki_get(params):
    """Paced, 429-tolerant call to the Wikipedia API."""
    for attempt in range(4):
        time.sleep(1.5)
        r = requests.get("https://en.wikipedia.org/w/api.php", timeout=TIMEOUT, headers=HDRS,
                         params={**params, "format": "json"})
        if r.status_code == 429:
            time.sleep(8 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("wikipedia: rate limited")


NOT_LOGO = re.compile(r"front[_ -]?page|cover|edition|building|headquarters|newsroom|studio|photo|screenshot|"
                      r"\d{4}-\d{2}-\d{2}\.jpg|issue|disambig|wiktionary|commons-logo|ambox|question_book|"
                      r"edit-|icon|symbol|flag_of|wikidata", re.I)
IS_LOGO = re.compile(r"logo|wordmark|masthead|nameplate", re.I)


def wiki_infobox_images(title: str):
    """Image file names referenced from the article's infobox, best candidates first:
    SVGs and logo-named files ahead of photos; front pages / buildings excluded."""
    html = wiki_get({"action": "parse", "page": title, "prop": "text", "redirects": 1})["parse"]["text"]["*"]
    m = re.search(r'<table class="infobox[^"]*"(.*?)</table>', html, re.S)
    box = m.group(1) if m else html[:20000]
    names = []
    for src in re.findall(r'<img[^>]+src="([^"]+)"', box):
        fn = re.search(r"/([^/]+\.(?:svg|png|jpg|jpeg|webp))(?:/|$)", src, re.I)
        if fn:
            n = unquote(fn.group(1))
            if n not in names and not NOT_LOGO.search(n):
                names.append(n)
    rank = lambda n: (0 if n.lower().endswith(".svg") else 1, 0 if IS_LOGO.search(n) else 1)
    return sorted(names, key=rank)


def wiki_original_url(filename: str):
    j = wiki_get({"action": "query", "titles": f"File:{filename}", "prop": "imageinfo", "iiprop": "url|mime"})
    for page in j["query"]["pages"].values():
        for ii in page.get("imageinfo", []):
            return ii["url"]
    return None


def download(url: str):
    r = requests.get(url, timeout=TIMEOUT, headers={**HDRS, "Accept": "image/*,*/*;q=0.5"})
    r.raise_for_status()
    ext = sniff(r.content)
    if not ext or len(r.content) < 200:
        raise ValueError("not an image")
    return r.content, ext


LOGO_HINT = re.compile(r"logo|wordmark|masthead|brand", re.I)


def homepage_candidates(src):
    """<img> in the homepage whose alt/src names the outlet or says logo."""
    from bs4 import BeautifulSoup
    html = fetch_html(src["url"])
    soup = BeautifulSoup(html, "html.parser")
    words = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", src["display"])]
    out = []
    for img in soup.find_all("img"):
        if img.find_parent("header") is None:
            continue
        alt = (img.get("alt") or "").lower()
        s = img.get("src") or img.get("data-src") or ""
        if not s or s.startswith("data:"):
            continue
        named = all(w in alt for w in words[:2]) if words else False
        if not (named or LOGO_HINT.search(s)):
            continue
        out.append(((0 if s.lower().endswith(".svg") else 1, 0 if named else 1), urljoin(src["url"], s)))
    return [u for _, u in sorted(out)]


# Hand-placed files (owner-chosen variants): foxnews.svg is the horizontal wordmark composed from
# the Commons stacked SVG's own paths; bbc.svg is the 1997-2021 blocks recolored red. Skipped
# unless named explicitly on the command line.
HAND_PLACED = {"foxnews", "bbc"}


def fetch_one(src, force=False, explicit=False):
    name = src["name"]
    if name in HAND_PLACED and not explicit:
        return "kept", "hand-placed"
    existing = sorted(p for p in OUT.glob(f"{name}.*") if p.suffix != ".html")
    if existing and not force:
        return "kept", existing[0].name
    errors = []
    tried = []
    title = WIKI.get(name)
    if title:
        try:
            for fn in wiki_infobox_images(title)[:3]:
                url = wiki_original_url(fn)
                if url:
                    tried.append(url)
        except Exception as e:  # noqa: BLE001
            errors.append(f"wiki: {e}")
    try:
        tried += homepage_candidates(src)[:3]
    except Exception as e:  # noqa: BLE001
        errors.append(f"homepage: {e}")
    for url in tried:
        try:
            data, ext = download(url)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url} ({e})")
            continue
        for old in existing:
            old.unlink()
        path = OUT / f"{name}.{ext}"
        path.write_bytes(data)
        return "saved", f"{path.name} {len(data)//1024}KB from {url}"
    raise RuntimeError("; ".join(errors[:3]) or "no candidates")


def contact_sheet(sources):
    rows = []
    for s in sources:
        files = sorted(p for p in OUT.glob(f"{s['name']}.*") if p.suffix != ".html")
        img = f'<img src="{files[0].name}">' if files else "<i>missing</i>"
        rows.append(f'<div class="c"><div class="chip">{img}</div><div class="chip dark">{img}</div>'
                    f'<span>{s["name"]} — {s["display"]}</span></div>')
    (OUT / "contact-sheet.html").write_text(
        '<meta charset="utf-8"><style>body{font:13px system-ui;padding:20px;background:#faf7f1}'
        '.c{display:flex;align-items:center;gap:14px;padding:6px 0;border-bottom:1px solid #ddd}'
        '.chip{background:#fff;border:1px solid #ccc;border-radius:5px;padding:3px 7px;height:28px;'
        'display:inline-flex;align-items:center}.chip.dark{background:#1c1917}'
        '.chip img{height:100%;width:auto;max-width:140px;object-fit:contain}</style>'
        + "\n".join(rows))


def main(argv):
    force = "--force" in argv
    names = [a for a in argv if not a.startswith("--")]
    OUT.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    failed = []
    for src in sources:
        if names and src["name"] not in names:
            continue
        try:
            status, detail = fetch_one(src, force=force, explicit=src["name"] in names)
            print(f"{src['name']:14} {status:5} {detail}")
        except Exception as e:  # noqa: BLE001
            failed.append(src["name"])
            print(f"{src['name']:14} FAIL  {e}")
    contact_sheet(sources)
    if failed:
        print(f"\n{len(failed)} failed: {' '.join(failed)} — place docs/logos/<name>.svg|png by hand")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
