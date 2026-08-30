"""Keyword pre-filter for Israel-related headlines (multilingual)."""
import re
from functools import lru_cache

from .common import load_keywords


@lru_cache(maxsize=None)
def _patterns(lang: str):
    kw = load_keywords()
    terms = kw.get(lang, kw["en"])
    pats = []
    for t in terms:
        # word-boundary match; allow suffixes for stem-like terms (e.g. "zionis")
        esc = re.escape(t)
        pats.append(re.compile(r"(?<!\w)" + esc + r"\w*", re.I | re.U))
    return terms, pats


def match_keyword(headline: str, lang: str):
    """Return the first matching keyword, or None."""
    terms, pats = _patterns(lang)
    for term, pat in zip(terms, pats):
        if pat.search(headline):
            return term
    return None
