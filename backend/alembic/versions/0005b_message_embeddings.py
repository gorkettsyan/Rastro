"""message embeddings

Revision ID: 0005b
Revises: 0005
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0005b"
down_revision = "0005"


def upgrade() -> None:
    op.add_column("messages", sa.Column("embedding", sa.Text, nullable=True))
    op.execute(
        "ALTER TABLE messages ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
    op.execute(
        "CREATE INDEX ix_messages_embedding ON messages "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_embedding")
    op.drop_column("messages", "embedding")
