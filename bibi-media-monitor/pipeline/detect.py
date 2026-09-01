"""Keyword pre-filter for Netanyahu-related headlines (Hebrew + English)."""
import re
from functools import lru_cache

from .common import load_keywords

_HEBREW = re.compile(r"[֐-׿]")


@lru_cache(maxsize=None)
def _patterns(lang: str):
    kw = load_keywords()
    terms = kw.get(lang, kw["en"])
    pats = []
    for t in terms:
        esc = re.escape(t)
        if _HEBREW.search(t):
            # Hebrew: word-boundary match that allows up to two attached
            # one-letter prefixes (לנתניהו, ושביבי) — plain substrings would
            # false-match inside words (תחביבים, תל־אביבי), plain boundaries
            # would miss most real mentions. Spaces in multiword terms also
            # match maqaf/hyphen (ראש־הממשלה).
            esc = esc.replace(r"\ ", r"[\s־\-]+")
            pats.append(re.compile(
                r"(?<![א-ת])[בהוכלמש]{0,2}" + esc + r"(?![א-ת])"))
        else:
            # word-boundary match; allow suffixes (netanyahu's, bibi-ism)
            pats.append(re.compile(r"(?<!\w)" + esc + r"\w*", re.I | re.U))
    return terms, pats


def match_keyword(headline: str, lang: str):
    """Return the first matching keyword, or None."""
    terms, pats = _patterns(lang)
    for term, pat in zip(terms, pats):
        if pat.search(headline):
            return term
    return None
