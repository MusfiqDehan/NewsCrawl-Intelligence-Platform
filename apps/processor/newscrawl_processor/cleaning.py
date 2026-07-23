"""Cleaning and validation of spider-extracted article fields.

The crawl plane extracts opportunistically (JSON-LD, selectors); the
processing plane is where the data becomes trustworthy: Unicode NFC
normalization (Bangla-safe), whitespace canonicalization that preserves
paragraph structure, datetime parsing, and minimum-quality validation.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from newscrawl_contracts.enums import Language
from newscrawl_crawler_utils import content_hash, normalize_text

from newscrawl_processor.language import detect_language

MIN_TITLE_CHARS = 5
MIN_BODY_CHARS = 100


class UnusableArticleError(ValueError):
    """Extraction did not yield enough content to persist an article."""


@dataclass
class CleanedArticle:
    title: str
    body: str
    language: Language
    content_hash: str
    word_count: int
    subtitle: str | None = None
    author: str | None = None
    category: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    image_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extraction_method: str = "selectors"
    extraction_confidence: float = 0.0


def clean_body(raw: str | None) -> str:
    """Normalize each paragraph, preserving paragraph breaks."""
    if not raw:
        return ""
    paragraphs = [normalize_text(p) for p in raw.split("\n")]
    return "\n\n".join(p for p in paragraphs if p)


def parse_datetime(raw: Any) -> datetime | None:
    """Parse an extracted timestamp into an aware UTC datetime."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        parsed = raw
    else:
        try:
            parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clean_extracted(extracted: dict[str, Any]) -> CleanedArticle:
    """Validate + normalize a spider extraction; raises UnusableArticleError."""
    title = normalize_text(str(extracted.get("title") or ""))
    body = clean_body(str(extracted.get("body") or ""))

    if len(title) < MIN_TITLE_CHARS:
        raise UnusableArticleError(f"Title too short: {title!r}")
    if len(body) < MIN_BODY_CHARS:
        raise UnusableArticleError(f"Body too short: {len(body)} chars")

    author = normalize_text(str(extracted.get("author") or "")) or None
    published_at = parse_datetime(extracted.get("published_at"))

    language = detect_language(title, body[:2000])

    image_urls = [str(u) for u in (extracted.get("image_urls") or []) if u][:20]
    tags = [normalize_text(str(t)) for t in (extracted.get("tags") or []) if t][:50]

    return CleanedArticle(
        title=title,
        body=body,
        language=language,
        content_hash=content_hash(
            title=title,
            author=author,
            published_at=published_at.isoformat() if published_at else None,
            body=body,
        ),
        word_count=len(body.split()),
        subtitle=normalize_text(str(extracted.get("subtitle") or "")) or None,
        author=author,
        category=normalize_text(str(extracted.get("category") or "")) or None,
        summary=normalize_text(str(extracted.get("summary") or "")) or None,
        published_at=published_at,
        updated_at=parse_datetime(extracted.get("updated_at")),
        image_urls=image_urls,
        tags=tags,
        extraction_method=str(extracted.get("extraction_method") or "selectors"),
        extraction_confidence=float(extracted.get("extraction_confidence") or 0.0),
    )
