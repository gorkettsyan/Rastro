"""add folder_mappings table and drive_folder_id to documents

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "folder_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder_id", sa.String(500), nullable=False),
        sa.Column("folder_name", sa.String(500), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "folder_id", name="uq_folder_mapping_org_folder"),
    )

    op.add_column("documents", sa.Column("drive_folder_id", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "drive_folder_id")
    op.drop_table("folder_mappings")
