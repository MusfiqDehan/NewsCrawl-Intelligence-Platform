"""Staged article deduplication.

Cheapest check first; each stage only runs when the previous one found
nothing:

  1. URL — already handled upstream by the frontier's unique url_hash.
  2. Exact — SHA-256 of the normalized identity representation
     (title + author + published_at + body).
  3. Near — 64-bit SimHash: banded candidate lookup (4 indexed equality
     probes), then exact Hamming distance against each candidate.
  4. Semantic — embedding cosine similarity, evaluated only for SimHash
     candidates that fall in the "gray zone" above the accept threshold.
     Wired in by the embedding worker (Phase 13); this module exposes the
     candidates so that stage stays cheap.
"""

import uuid
from dataclasses import dataclass, field

from newscrawl_api.models import Article
from newscrawl_crawler_utils.simhash import (
    BAND_BITS,
    BANDS,
    DEFAULT_HAMMING_THRESHOLD,
    hamming_distance,
    simhash64,
    simhash_bands,
    to_signed64,
    to_unsigned64,
)
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

# SimHash distances in (threshold, gray_zone] are "suspicious but not
# conclusive" — they are surfaced for the semantic stage instead of being
# declared duplicates outright.
GRAY_ZONE_HAMMING = 6


@dataclass
class DedupResult:
    is_duplicate: bool = False
    duplicate_of: uuid.UUID | None = None
    stage: str | None = None  # "exact" | "simhash"
    hamming: int | None = None
    # SimHash candidates too far for auto-dedup but close enough to warrant
    # the semantic (embedding) stage.
    semantic_candidates: list[uuid.UUID] = field(default_factory=list)


class DedupService:
    def __init__(self, hamming_threshold: int = DEFAULT_HAMMING_THRESHOLD) -> None:
        if hamming_threshold > BANDS - 1:
            # Banding only guarantees recall up to BANDS - 1 bit flips.
            msg = f"hamming_threshold must be <= {BANDS - 1} for {BANDS}-band lookup"
            raise ValueError(msg)
        self.hamming_threshold = hamming_threshold

    async def find_duplicate(
        self,
        db: AsyncSession,
        *,
        content_hash: str,
        simhash: int,
        source_id: uuid.UUID | None = None,
        exclude_article_id: uuid.UUID | None = None,
    ) -> DedupResult:
        exact = await self._find_exact(db, content_hash, exclude_article_id)
        if exact is not None:
            return DedupResult(is_duplicate=True, duplicate_of=exact, stage="exact", hamming=0)
        if not simhash:
            return DedupResult()
        return await self._find_near(db, simhash, source_id, exclude_article_id)

    async def _find_exact(
        self,
        db: AsyncSession,
        content_hash: str,
        exclude_article_id: uuid.UUID | None,
    ) -> uuid.UUID | None:
        stmt = select(Article.id).where(Article.content_hash == content_hash).limit(1)
        if exclude_article_id is not None:
            stmt = stmt.where(Article.id != exclude_article_id)
        result: uuid.UUID | None = await db.scalar(stmt)
        return result

    async def _find_near(
        self,
        db: AsyncSession,
        simhash: int,
        source_id: uuid.UUID | None,
        exclude_article_id: uuid.UUID | None,
    ) -> DedupResult:
        unsigned = to_unsigned64(simhash)
        bands = simhash_bands(unsigned)
        # Inline integer literals: Postgres' >> wants (bigint, integer), and
        # the expression must match the band indexes created in the migration.
        band_predicates = [
            text(f"((simhash >> {band_index * BAND_BITS}) & 65535) = :band{band_index}").bindparams(
                **{f"band{band_index}": band_value}
            )
            for band_index, band_value in enumerate(bands)
        ]
        stmt = (
            select(Article.id, Article.simhash)
            .where(Article.simhash.is_not(None))
            .where(or_(*band_predicates))
            .limit(500)
        )
        if exclude_article_id is not None:
            stmt = stmt.where(Article.id != exclude_article_id)

        best_id: uuid.UUID | None = None
        best_distance: int | None = None
        gray: list[tuple[int, uuid.UUID]] = []
        for candidate_id, candidate_simhash in (await db.execute(stmt)).all():
            distance = hamming_distance(unsigned, to_unsigned64(candidate_simhash))
            if distance <= self.hamming_threshold:
                if best_distance is None or distance < best_distance:
                    best_id, best_distance = candidate_id, distance
            elif distance <= GRAY_ZONE_HAMMING:
                gray.append((distance, candidate_id))

        if best_id is not None:
            return DedupResult(
                is_duplicate=True,
                duplicate_of=best_id,
                stage="simhash",
                hamming=best_distance,
            )
        gray.sort(key=lambda pair: pair[0])
        return DedupResult(semantic_candidates=[candidate_id for _, candidate_id in gray[:10]])


def article_simhash(title: str | None, body: str | None) -> int:
    """Signed 64-bit simhash of an article's identity text (Postgres-ready)."""
    text = f"{title or ''}\n{body or ''}"
    return to_signed64(simhash64(text))
