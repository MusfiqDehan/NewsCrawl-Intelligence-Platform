"""Content hashing over a normalized article representation.

Raw HTML is never hashed directly — ads, timestamps, and tracking markup change
on every request. Instead we hash a canonical representation of the fields that
define the article's identity.
"""

import hashlib
import unicodedata

_FIELD_SEPARATOR = "\x1e"  # ASCII record separator — cannot appear in clean text


def normalize_text(text: str | None) -> str:
    """Whitespace + Unicode NFC normalization, safe for Bangla and English.

    NFC (not NFKC/NFKD): compatibility decomposition would corrupt Bengali
    conjuncts and punctuation like the daari (u0964).
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    # Zero-width joiners are meaningful inside Bangla words (e.g. র্\u200dযা);
    # strip other zero-width/formatting characters that vary between renders.
    normalized = normalized.replace("\u200b", "").replace("\ufeff", "")
    return " ".join(normalized.split())


def content_hash(
    *,
    title: str | None,
    author: str | None = None,
    published_at: str | None = None,
    body: str | None,
    extra: dict[str, str] | None = None,
) -> str:
    """sha256 over the normalized identity fields of an article."""
    parts = [
        normalize_text(title),
        normalize_text(author),
        normalize_text(published_at),
        normalize_text(body),
    ]
    if extra:
        parts.extend(f"{key}={normalize_text(value)}" for key, value in sorted(extra.items()))
    payload = _FIELD_SEPARATOR.join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
