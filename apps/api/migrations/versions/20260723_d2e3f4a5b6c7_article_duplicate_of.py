"""articles.duplicate_of — semantic-dedup verdicts.

Exact and SimHash duplicates are never persisted; embedding-stage duplicates
(rewrites of the same story) are persisted but marked, so queries can
collapse them while the raw record stays auditable.

Revision ID: d2e3f4a5b6c7
Revises: c1f2d3a4b5e6
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1f2d3a4b5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("duplicate_of", sa.Uuid(), sa.ForeignKey("articles.id"), nullable=True),
    )
    op.create_index("ix_articles_duplicate_of", "articles", ["duplicate_of"])


def downgrade() -> None:
    op.drop_index("ix_articles_duplicate_of", table_name="articles")
    op.drop_column("articles", "duplicate_of")
