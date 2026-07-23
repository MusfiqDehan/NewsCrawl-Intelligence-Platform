"""Bangla/English language detection.

Script counting beats statistical detectors here: the platform only
distinguishes Bangla from English, and the Bengali script (U+0980..U+09FF)
appears in exactly one of them. Statistical detectors (langdetect, fasttext)
add a model dependency and misfire on short headlines; counting is exact,
fast, and deterministic.
"""

import re

from newscrawl_contracts.enums import Language

_BENGALI = re.compile(r"[\u0980-\u09ff]")
_LATIN = re.compile(r"[a-zA-Z]")

# Minimum letters before we trust a verdict (avoids classifying "404" or "—").
_MIN_LETTERS = 10


def detect_language(*texts: str | None) -> Language:
    """Detect bn/en from any number of text fragments (title, body, ...)."""
    combined = " ".join(t for t in texts if t)
    bengali = len(_BENGALI.findall(combined))
    latin = len(_LATIN.findall(combined))
    if bengali + latin < _MIN_LETTERS:
        return Language.UNKNOWN
    # Bangla articles quote English names/terms freely; the reverse is rare —
    # a meaningful share of Bengali script means the article is Bangla.
    if bengali >= latin * 0.25:
        return Language.BANGLA
    return Language.ENGLISH
