"""document visibility and indexed_by_user_id

Revision ID: 0005c
Revises: 0005b
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005c"
down_revision = "0005b"


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("visibility", sa.String(20), server_default="private", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("indexed_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_documents_visibility", "documents", ["visibility"])
    op.create_index("ix_documents_indexed_by", "documents", ["indexed_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_indexed_by", table_name="documents")
    op.drop_index("ix_documents_visibility", table_name="documents")
    op.drop_column("documents", "indexed_by_user_id")
    op.drop_column("documents", "visibility")
