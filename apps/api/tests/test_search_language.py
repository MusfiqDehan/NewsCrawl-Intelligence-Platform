"""Unit tests for query language detection (no DB)."""

from newscrawl_api.services.search import detect_query_language


def test_detect_bangla_query() -> None:
    assert detect_query_language("প্রশ্নফাঁস") == "bn"
    assert detect_query_language("প্রশ্ন ফাঁস রুখতে আইন") == "bn"


def test_detect_english_query() -> None:
    assert detect_query_language("question paper leak") == "en"
    assert detect_query_language("election in Bangladesh") == "en"


def test_detect_ambiguous_or_short() -> None:
    assert detect_query_language("a") is None
    assert detect_query_language("১") is None
