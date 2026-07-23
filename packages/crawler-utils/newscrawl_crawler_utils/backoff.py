"""Retry backoff policy shared by the frontier and processing consumers."""

import random


def compute_backoff_seconds(
    retry_count: int,
    *,
    base_seconds: float = 60.0,
    max_seconds: float = 6 * 3600.0,
    jitter_ratio: float = 0.2,
) -> float:
    """Exponential backoff with jitter: base * 2^(retry-1), capped.

    Jitter avoids retry stampedes when many URLs fail simultaneously
    (e.g. a source going down takes out a whole batch).
    """
    if retry_count < 1:
        retry_count = 1
    delay = min(base_seconds * (2 ** (retry_count - 1)), max_seconds)
    jitter = delay * jitter_ratio
    return float(delay + random.uniform(-jitter, jitter))  # noqa: S311 - not cryptographic
