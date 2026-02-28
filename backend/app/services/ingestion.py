import hashlib
import uuid
from datetime import datetime, timezone

import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from app.models.document import Document
from app.models.chunk import Chunk
from app.services.base import BaseEmbeddingService
from app.services.embeddings import embedding_service

from typing import Any

_enc = tiktoken.get_encoding("cl100k_base")
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


class IngestionService:
    def __init__(self, embedding_svc: BaseEmbeddingService):
        self._embedding_svc = embedding_svc

    def _split_into_chunks(self, text: str) -> list[str]:
        tokens = _enc.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + CHUNK_SIZE, len(tokens))
            chunks.append(_enc.decode(tokens[start:end]))
            if end == len(tokens):
                break
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return [c for c in chunks if c.strip()]

    @staticmethod
    def extract_text_from_bytes(content: bytes, mime_type: str) -> str:
        if mime_type == "application/pdf":
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(content))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if mime_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            from docx import Document as DocxDoc
            import io
            doc = DocxDoc(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def make_document(user_id: uuid.UUID, **kwargs: Any) -> Document:
        """Create a Document with visibility='private' and indexed_by_user_id set."""
        return Document(
            visibility="private",
            indexed_by_user_id=user_id,
            **kwargs,
        )

    async def chunk_and_embed(
        self,
        db: AsyncSession,
        document: Document,
        raw_text: str,
        extra_metadata: dict | None = None,
    ) -> int:
        """Chunks, embeds, and stores in pgvector. Idempotent. Returns chunk count."""
        if not raw_text or len(raw_text.strip()) < 50:
            document.indexing_status = "done"
            document.chunk_count = 0
            document.indexed_at = datetime.now(timezone.utc)
            return 0

        await db.execute(delete(Chunk).where(Chunk.document_id == document.id))

        chunks = self._split_into_chunks(raw_text)
        if not chunks:
            return 0

        embeddings = await self._embedding_svc.embed_texts(chunks)

        for i, (text, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(Chunk(
                id=uuid.uuid4(),
                document_id=document.id,
                org_id=document.org_id,
                project_id=document.project_id,
                content=text,
                embedding=embedding,
                chunk_index=i,
                metadata_={**(extra_metadata or {})},
            ))

        await db.flush()

        document.chunk_count = len(chunks)
        document.indexing_status = "done"
        document.indexed_at = datetime.now(timezone.utc)
        document.content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        return len(chunks)


ingestion_service = IngestionService(embedding_service)

# Convenience aliases for backward-compatible imports
extract_text_from_bytes = IngestionService.extract_text_from_bytes
make_document = IngestionService.make_document
