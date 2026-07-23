"""SimHash band expression indexes for near-duplicate candidate lookup.

The 64-bit simhash (signed bigint) splits into 4 bands of 16 bits. Two hashes
within Hamming distance 3 must share at least one band exactly (pigeonhole),
so candidate lookup is 4 indexed equality probes combined with OR (BitmapOr).

Band extraction uses arithmetic shift + mask; the low 16 bits after masking
are identical for signed and unsigned representations (mod 2^16 arithmetic).

Revision ID: c1f2d3a4b5e6
Revises: b6e6ad18fdcc
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c1f2d3a4b5e6"
down_revision: str | None = "b6e6ad18fdcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BANDS = 4
BAND_BITS = 16


def upgrade() -> None:
    for band in range(BANDS):
        shift = band * BAND_BITS
        op.execute(
            f"CREATE INDEX ix_articles_simhash_band{band} "
            f"ON articles (((simhash >> {shift}) & 65535)) "
            f"WHERE simhash IS NOT NULL"
        )


def downgrade() -> None:
    for band in range(BANDS):
        op.execute(f"DROP INDEX IF EXISTS ix_articles_simhash_band{band}")
