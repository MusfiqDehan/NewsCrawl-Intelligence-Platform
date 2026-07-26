"""Retention deletion audit tables for the dashboard.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_purge_cycles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_hours", sa.Integer(), nullable=False),
        sa.Column("articles_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_html_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "by_language",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "by_source",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retention_purge_cycles")),
    )
    op.create_index(
        "ix_retention_purge_cycles_started_at",
        "retention_purge_cycles",
        ["started_at"],
        unique=False,
    )

    op.create_table(
        "retention_daily_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("articles_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_html_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "by_language",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "by_source",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_retention_daily_stats")),
    )

    op.create_table(
        "retention_delete_by_language",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("articles_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint(
            "day", "language", name=op.f("pk_retention_delete_by_language")
        ),
    )

    op.create_table(
        "retention_delete_by_source",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("articles_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_retention_delete_by_source_source_id_sources"),
        ),
        sa.PrimaryKeyConstraint(
            "day", "source_id", name=op.f("pk_retention_delete_by_source")
        ),
    )


def downgrade() -> None:
    op.drop_table("retention_delete_by_source")
    op.drop_table("retention_delete_by_language")
    op.drop_table("retention_daily_stats")
    op.drop_index("ix_retention_purge_cycles_started_at", table_name="retention_purge_cycles")
    op.drop_table("retention_purge_cycles")
