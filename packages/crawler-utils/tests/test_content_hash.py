from newscrawl_crawler_utils import content_hash, normalize_text


def test_whitespace_invariant() -> None:
    a = content_hash(title="Big  News", body="Line one.\n\nLine   two.")
    b = content_hash(title="Big News", body="Line one. Line two.")
    assert a == b


def test_unicode_nfc_invariant() -> None:
    # কো as precomposed vs decomposed sequences must hash identically
    composed = "\u0995\u09cb"  # ka + o-kar
    decomposed = "\u0995\u09c7\u09be"  # ka + e-kar + aa-kar (canonically equivalent)
    assert content_hash(title=composed, body="x") == content_hash(title=decomposed, body="x")


def test_field_separation_prevents_collisions() -> None:
    # ("ab", "c") must not collide with ("a", "bc")
    assert content_hash(title="ab", body="c") != content_hash(title="a", body="bc")


def test_author_and_date_affect_hash() -> None:
    base = content_hash(title="t", author="x", published_at="2026-01-01", body="b")
    assert base != content_hash(title="t", author="y", published_at="2026-01-01", body="b")
    assert base != content_hash(title="t", author="x", published_at="2026-01-02", body="b")


def test_none_fields_stable() -> None:
    assert content_hash(title=None, body=None) == content_hash(title="", body="")


def test_normalize_text_bangla() -> None:
    assert normalize_text("  বাংলা   দেশ ") == "বাংলা দেশ"
    # daari must survive
    assert "।" in normalize_text("বাক্য শেষ।")
    # zero-width space stripped, ZWJ kept
    assert normalize_text("র\u200b্যাব") == "র্যাব"
