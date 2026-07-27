"""add selectors column to sources

Revision ID: 90c9a0c14f75
Revises: f4a5b6c7d8e9
Create Date: 2026-07-26 07:02:09.430519+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "90c9a0c14f75"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources", sa.Column("selectors", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sources", "selectors")
