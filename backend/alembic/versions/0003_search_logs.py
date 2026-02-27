"""search logs

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "search_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("result_count", sa.Integer, server_default="0"),
        sa.Column("cited_chunk_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_search_logs_org_id", "search_logs", ["org_id"])
    op.create_index("ix_search_logs_project_id", "search_logs", ["project_id"])
    op.create_index("ix_search_logs_created_at", "search_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("search_logs")
