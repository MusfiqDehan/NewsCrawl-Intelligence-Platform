"""64-bit SimHash for near-duplicate detection with banding.

SimHash property: documents that differ slightly produce hashes with a small
Hamming distance. We use word 2-gram shingles over the normalized text, which
works for both Bangla and English (both are whitespace-segmented scripts).

Banding: the 64-bit hash splits into 4 bands of 16 bits. By pigeonhole, two
hashes within Hamming distance 3 must agree exactly on at least one band —
so candidate lookup is 4 indexed equality probes instead of a full scan.

Postgres stores bigint as signed two's complement, so the unsigned 64-bit
hash is converted for storage and back for Hamming math.
"""

import hashlib

from newscrawl_crawler_utils.content import normalize_text

BANDS = 4
BAND_BITS = 64 // BANDS  # 16
_BAND_MASK = (1 << BAND_BITS) - 1
# Max Hamming distance guaranteed caught by banding (pigeonhole: BANDS - 1)
DEFAULT_HAMMING_THRESHOLD = 3


def _features(text: str, shingle_size: int = 2) -> list[str]:
    """Word n-gram shingles over normalized text."""
    words = normalize_text(text).lower().split()
    if len(words) < shingle_size:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + shingle_size]) for i in range(len(words) - shingle_size + 1)]


def _feature_hash(feature: str) -> int:
    return int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")


def simhash64(text: str | None, *, shingle_size: int = 2) -> int:
    """Unsigned 64-bit SimHash of the text (0 for empty text)."""
    if not text:
        return 0
    features = _features(text, shingle_size)
    if not features:
        return 0

    votes = [0] * 64
    for feature in features:
        h = _feature_hash(feature)
        for bit in range(64):
            votes[bit] += 1 if (h >> bit) & 1 else -1

    value = 0
    for bit in range(64):
        if votes[bit] > 0:
            value |= 1 << bit
    return value


def hamming_distance(a: int, b: int) -> int:
    return ((a ^ b) & 0xFFFFFFFFFFFFFFFF).bit_count()


def simhash_bands(value: int) -> tuple[int, ...]:
    """The 4 16-bit bands of an unsigned 64-bit simhash (low band first)."""
    unsigned = value & 0xFFFFFFFFFFFFFFFF
    return tuple((unsigned >> (i * BAND_BITS)) & _BAND_MASK for i in range(BANDS))


def to_signed64(value: int) -> int:
    """Unsigned 64-bit → signed two's complement (Postgres bigint)."""
    value &= 0xFFFFFFFFFFFFFFFF
    return value - (1 << 64) if value >= (1 << 63) else value


def to_unsigned64(value: int) -> int:
    """Signed two's complement (Postgres bigint) → unsigned 64-bit."""
    return value & 0xFFFFFFFFFFFFFFFF
