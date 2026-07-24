"""Lightweight fallback when cloud/local LLMs are unavailable.

Used only after the provider chain is exhausted so the sentiment/summary
pipeline keeps moving instead of dead-lettering every article during quota
outages.
"""

from __future__ import annotations

import re

from newscrawl_processor.llm.schema import ArticleAnalysis

_POS_EN = {
    "win",
    "wins",
    "victory",
    "growth",
    "surge",
    "record",
    "hope",
    "peace",
    "aid",
    "rescue",
    "success",
    "improve",
    "improved",
    "celebrate",
    "breakthrough",
}
_NEG_EN = {
    "kill",
    "killed",
    "death",
    "dead",
    "attack",
    "attacked",
    "crash",
    "flood",
    "flooding",
    "disaster",
    "crisis",
    "war",
    "protest",
    "arrest",
    "arrested",
    "violence",
    "bomb",
    "fail",
    "failed",
    "collapse",
    "corruption",
}
_POS_BN = {"জয়", "উন্নতি", "সাফল্য", "শান্তি", "উদ্ধার", "আশা", "উৎসব", "বৃদ্ধি"}
_NEG_BN = {"মৃত্যু", "নিহত", "হামলা", "বন্যা", "দুর্যোগ", "সংকট", "যুদ্ধ", "বন্দি", "দুর্নীতি", "ধ্বংস", "হামলার"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\w\u0980-\u09FF]+", text.lower()) if len(t) > 2}


def heuristic_analysis(*, title: str, body: str, language: str) -> ArticleAnalysis:
    """Best-effort sentiment + short summary without an LLM call."""
    blob = f"{title}\n{body[:800]}"
    tokens = _tokens(blob)
    pos = len(tokens & _POS_EN) + len({t for t in tokens if any(b in t for b in _POS_BN)})
    # Bangla keywords may be whole tokens
    pos += sum(1 for b in _POS_BN if b in blob)
    neg = len(tokens & _NEG_EN) + sum(1 for b in _NEG_BN if b in blob)

    if pos > neg + 1:
        sentiment: str = "positive"
    elif neg > pos + 1:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Prefer the lead sentences as a stand-in summary.
    cleaned = re.sub(r"\s+", " ", body.strip())
    if len(cleaned) < 40:
        cleaned = title.strip()
    summary = cleaned[:400].rsplit(" ", 1)[0] if len(cleaned) > 400 else cleaned
    if len(summary) < 10:
        summary = (title.strip() or "Article summary unavailable.")[:200]
    if len(summary) < 10:
        summary = "Article summary unavailable."

    keywords = [t for t in list(tokens)[:12] if t.isalpha() or any("\u0980" <= c <= "\u09FF" for c in t)]
    return ArticleAnalysis(
        summary=summary,
        topics=[],
        entities=[],
        sentiment=sentiment,  # type: ignore[arg-type]
        event_type=None,
        political_category=None,
        keywords=keywords[:12],
    )
