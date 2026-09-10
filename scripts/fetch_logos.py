#!/usr/bin/env python3
"""One-off: fetch each outlet's favicon / apple-touch-icon into docs/logos/.

    python scripts/fetch_logos.py            # all sources, skip existing
    python scripts/fetch_logos.py bbc nyt    # just these
    python scripts/fetch_logos.py --force    # re-fetch even if a file exists

Saves the largest icon it can find in its native format (png/ico/svg/jpg/webp);
browsers render all of them in <img>. Exit code 1 if any source failed, so the
missing ones can be hand-placed. Logos are committed manually (the hourly
workflow only commits data/, docs/data/, logs/).
"""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import load_sources  # noqa: E402
from pipeline.extract import UA, fetch_html  # noqa: E402

OUT = ROOT / "docs" / "logos"
TIMEOUT = 15

MAGIC = (
    (b"\x89PNG", "png"), (b"\x00\x00\x01\x00", "ico"), (b"\xff\xd8", "jpg"),
    (b"GIF8", "gif"),
)


def sniff(data: bytes):
    for magic, ext in MAGIC:
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:4096].lower()):
        return "svg"
    return None


def _size(link) -> int:
    rel = " ".join(link.get("rel") or []).lower()
    sizes = (link.get("sizes") or "").lower()
    m = re.search(r"(\d+)x(\d+)", sizes)
    if m:
        return int(m.group(1))
    if "apple-touch-icon" in rel:
        return 180
    typ = (link.get("type") or "").lower()
    if "svg" in typ or (link.get("href") or "").lower().endswith(".svg"):
        return 100  # crisp at any size, but often a plain glyph; below touch icons
    return 32


def find_icon_candidates(html: str, base_url: str):
    """[(size, url)] largest first, plus the conventional root fallbacks."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    cands = []
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        if "icon" not in rel:
            continue
        cands.append((_size(link), urljoin(base_url, link["href"].strip())))
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    cands.append((170, root + "/apple-touch-icon.png"))
    cands.append((16, root + "/favicon.ico"))
    seen, out = set(), []
    for size, url in sorted(cands, key=lambda c: c[0], reverse=True):
        if url not in seen:
            seen.add(url)
            out.append((size, url))
    return out


def download(url: str):
    r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.5"})
    r.raise_for_status()
    ext = sniff(r.content)
    if not ext or len(r.content) < 100:
        raise ValueError("not an image")
    return r.content, ext


def fetch_one(src, force=False):
    name = src["name"]
    existing = sorted(OUT.glob(f"{name}.*"))
    if existing and not force:
        return "kept", existing[0].name
    html = fetch_html(src["url"])
    errors = []
    for size, url in find_icon_candidates(html, src["url"]):
        try:
            data, ext = download(url)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url} ({e})")
            continue
        for old in existing:
            old.unlink()
        path = OUT / f"{name}.{ext}"
        path.write_bytes(data)
        return "saved", f"{path.name} {len(data)//1024}KB from {url} (size hint {size})"
    raise RuntimeError("; ".join(errors[:3]) or "no icon candidates")


def main(argv):
    force = "--force" in argv
    names = [a for a in argv if not a.startswith("--")]
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for src in load_sources():
        if names and src["name"] not in names:
            continue
        try:
            status, detail = fetch_one(src, force=force)
            print(f"{src['name']:14} {status:5} {detail}")
        except Exception as e:  # noqa: BLE001
            failed.append(src["name"])
            print(f"{src['name']:14} FAIL  {e}")
    if failed:
        print(f"\n{len(failed)} failed: {' '.join(failed)} — place docs/logos/<name>.png by hand")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
