"""Add full-text search to chunks and latency_ms to search_logs

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    # Generated tsvector column (Spanish + English) on chunks
    op.execute("""
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('spanish', coalesce(content, '')) ||
            to_tsvector('english', coalesce(content, ''))
        ) STORED
    """)

    # GIN index for fast full-text lookup
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_content_tsv ON chunks USING GIN (content_tsv)"
    )

    # Track RAG latency per search log
    op.add_column("search_logs", sa.Column("latency_ms", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("search_logs", "latency_ms")
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
