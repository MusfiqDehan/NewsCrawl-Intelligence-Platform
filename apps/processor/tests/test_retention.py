"""Unit tests for article retention helpers."""

from newscrawl_processor.retention import parse_s3_uri


def test_parse_s3_uri() -> None:
    assert parse_s3_uri("s3://newscrawl-raw-html/prothom/abc.html") == (
        "newscrawl-raw-html",
        "prothom/abc.html",
    )
    assert parse_s3_uri("not-a-uri") is None
    assert parse_s3_uri("s3://bucket-only") is None
