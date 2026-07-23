"""Language detection + cleaning/validation unit tests."""

import pytest
from newscrawl_contracts.enums import Language
from newscrawl_processor.cleaning import (
    UnusableArticleError,
    clean_body,
    clean_extracted,
    parse_datetime,
)
from newscrawl_processor.language import detect_language

BANGLA_BODY = (
    "ঢাকায় আজ সকালে বৃষ্টি হয়েছে। আবহাওয়া অধিদপ্তর জানিয়েছে, আগামী তিন দিন "
    "দেশের বিভিন্ন অঞ্চলে হালকা থেকে মাঝারি বৃষ্টিপাতের সম্ভাবনা রয়েছে। "
    "নদীবন্দরগুলোকে এক নম্বর সতর্ক সংকেত দেখাতে বলা হয়েছে।"
)

ENGLISH_BODY = (
    "The central bank kept its policy rate unchanged on Wednesday, citing easing "
    "inflation and a stable currency. Analysts had widely expected the decision, "
    "though some argued a cut was overdue given slowing credit growth in the "
    "private sector over the past two quarters."
)


class TestLanguageDetection:
    def test_bangla(self) -> None:
        assert detect_language(BANGLA_BODY) == Language.BANGLA

    def test_english(self) -> None:
        assert detect_language(ENGLISH_BODY) == Language.ENGLISH

    def test_bangla_with_quoted_english_stays_bangla(self) -> None:
        mixed = BANGLA_BODY + ' তিনি বলেন, "The situation is under control."'
        assert detect_language(mixed) == Language.BANGLA

    def test_english_with_a_bangla_name_stays_english(self) -> None:
        mixed = ENGLISH_BODY + " The report quoted the phrase ব্যাংক once."
        assert detect_language(mixed) == Language.ENGLISH

    def test_too_short_is_unknown(self) -> None:
        assert detect_language("404") == Language.UNKNOWN
        assert detect_language(None) == Language.UNKNOWN
        assert detect_language("") == Language.UNKNOWN


class TestCleanBody:
    def test_paragraphs_preserved_whitespace_collapsed(self) -> None:
        raw = "First   paragraph\nSecond\tparagraph\n\n\nThird"
        assert clean_body(raw) == "First paragraph\n\nSecond paragraph\n\nThird"

    def test_empty(self) -> None:
        assert clean_body(None) == ""
        assert clean_body("  \n \n") == ""


class TestParseDatetime:
    def test_iso_with_offset_converted_to_utc(self) -> None:
        parsed = parse_datetime("2026-07-23T14:15:49+06:00")
        assert parsed is not None
        assert parsed.hour == 8
        assert parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_z_suffix(self) -> None:
        parsed = parse_datetime("2026-07-23T07:18:21Z")
        assert parsed is not None and parsed.hour == 7

    def test_naive_assumed_utc(self) -> None:
        parsed = parse_datetime("2026-07-23T07:18:21")
        assert parsed is not None and parsed.tzinfo is not None

    def test_garbage_is_none(self) -> None:
        assert parse_datetime("yesterday") is None
        assert parse_datetime(None) is None


class TestCleanExtracted:
    def test_valid_bangla_article(self) -> None:
        cleaned = clean_extracted(
            {
                "title": "  ঢাকায় বৃষ্টি  ",
                "body": BANGLA_BODY,
                "author": " নিজস্ব প্রতিবেদক ",
                "published_at": "2026-07-23T14:15:49+06:00",
                "extraction_method": "json_ld",
                "extraction_confidence": 0.95,
            }
        )
        assert cleaned.title == "ঢাকায় বৃষ্টি"
        assert cleaned.language == Language.BANGLA
        assert cleaned.author == "নিজস্ব প্রতিবেদক"
        assert cleaned.published_at is not None and cleaned.published_at.hour == 8
        assert cleaned.word_count > 20
        assert len(cleaned.content_hash) == 64

    def test_content_hash_is_stable_under_whitespace_noise(self) -> None:
        base = {"title": "Rate decision", "body": ENGLISH_BODY}
        noisy = {"title": "Rate  decision ", "body": ENGLISH_BODY.replace(" ", "  ")}
        assert clean_extracted(base).content_hash == clean_extracted(noisy).content_hash

    def test_missing_title_rejected(self) -> None:
        with pytest.raises(UnusableArticleError, match="Title"):
            clean_extracted({"title": "", "body": ENGLISH_BODY})

    def test_short_body_rejected(self) -> None:
        with pytest.raises(UnusableArticleError, match="Body"):
            clean_extracted({"title": "A headline", "body": "Too short."})

    def test_image_and_tag_limits(self) -> None:
        cleaned = clean_extracted(
            {
                "title": "A headline here",
                "body": ENGLISH_BODY,
                "image_urls": [f"https://x.example/{i}.jpg" for i in range(40)],
                "tags": [f"tag{i}" for i in range(80)],
            }
        )
        assert len(cleaned.image_urls) == 20
        assert len(cleaned.tags) == 50
