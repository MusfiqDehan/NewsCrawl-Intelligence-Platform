import pytest
from newscrawl_api.schemas.source import SourceCreate
from pydantic import ValidationError


def make_source(**overrides: object) -> SourceCreate:
    payload: dict[str, object] = {
        "name": "Example News",
        "slug": "example-news",
        "base_url": "https://example.com",
        "language": "en",
        "country": "US",
        **overrides,
    }
    return SourceCreate.model_validate(payload)


def test_valid_source() -> None:
    source = make_source()
    assert source.base_url == "https://example.com"


def test_trailing_slash_stripped() -> None:
    source = make_source(base_url="https://example.com/")
    assert source.base_url == "https://example.com"


@pytest.mark.parametrize(
    "bad_url",
    [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "not-a-url",
    ],
)
def test_non_http_schemes_rejected(bad_url: str) -> None:
    with pytest.raises(ValidationError):
        make_source(base_url=bad_url)


@pytest.mark.parametrize("bad_slug", ["Has Space", "UPPER", "under_score", ""])
def test_bad_slugs_rejected(bad_slug: str) -> None:
    with pytest.raises(ValidationError):
        make_source(slug=bad_slug)
