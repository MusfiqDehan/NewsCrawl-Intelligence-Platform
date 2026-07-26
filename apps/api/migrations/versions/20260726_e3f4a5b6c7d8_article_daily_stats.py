"""Durable daily article crawl counts for dashboard charts.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_daily_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("articles_created", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_article_daily_stats")),
    )
    # Seed from whatever articles are still retained.
    op.execute(
        """
        INSERT INTO article_daily_stats (day, articles_created)
        SELECT created_at::date, count(*)::int
        FROM articles
        GROUP BY 1
        ON CONFLICT (day) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("article_daily_stats")
