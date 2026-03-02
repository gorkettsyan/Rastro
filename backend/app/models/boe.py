import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.database import Base


class BoeLaw(Base):
    __tablename__ = "boe_laws"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    boe_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    short_name: Mapped[str] = mapped_column(String(200), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_update: Mapped[date | None] = mapped_column(Date, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    sync_status: Mapped[str] = mapped_column(String(30), default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BoeChunk(Base):
    __tablename__ = "boe_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    boe_law_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boe_laws.id", ondelete="CASCADE"), nullable=False, index=True
    )
    boe_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    law_name: Mapped[str] = mapped_column(String(500), nullable=False)
    article_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    boe_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
