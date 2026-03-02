"""add boe_laws and boe_chunks tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "boe_laws",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("boe_id", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("short_name", sa.String(200), nullable=False),
        sa.Column("publication_date", sa.Date, nullable=True),
        sa.Column("last_update", sa.Date, nullable=True),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("sync_status", sa.String(30), server_default="pending"),
        sa.Column("sync_error", sa.Text, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "boe_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "boe_law_id", UUID(as_uuid=True),
            sa.ForeignKey("boe_laws.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("boe_id", sa.String(50), index=True, nullable=False),
        sa.Column("law_name", sa.String(500), nullable=False),
        sa.Column("article_number", sa.String(50), nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column("block_id", sa.String(100), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("metadata", sa.JSON, server_default="{}"),
        sa.Column("boe_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add vector column (pgvector)
    op.execute("ALTER TABLE boe_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)")

    # ivfflat cosine index for vector search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_boe_chunks_embedding "
        "ON boe_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # Generated tsvector column for Spanish full-text search
    op.execute(
        "ALTER TABLE boe_chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED"
    )

    # GIN index on tsvector
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_boe_chunks_content_tsv "
        "ON boe_chunks USING gin (content_tsv)"
    )


def downgrade() -> None:
    op.drop_table("boe_chunks")
    op.drop_table("boe_laws")
