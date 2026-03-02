import hashlib
import re
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

# Patterns that mark clause boundaries in Spanish contracts
_CLAUSE_PATTERN = re.compile(
    r"^("
    r"\d+\.\d+\.\d+\.?\s+"       # 1.2.3 or 1.2.3.
    r"|\d+\.\d+\.?\s+"           # 1.2 or 1.2.
    r"|\d+\.\s+"                 # 1.
    r"|CG[-‑]?\d+"              # CG-1, CG1
    r"|[Cc]l[áa]usula\s+"       # Cláusula primera
    r"|Art[íi]culo\s+\d+"       # Artículo 1
    r"|PRIMERA\b|SEGUNDA\b|TERCERA\b|CUARTA\b|QUINTA\b"
    r"|SEXTA\b|SÉPTIMA\b|OCTAVA\b|NOVENA\b|DÉCIMA\b"
    r")",
    re.MULTILINE,
)


class IngestionService:
    def __init__(self, embedding_svc: BaseEmbeddingService):
        self._embedding_svc = embedding_svc

    @staticmethod
    def _split_by_clauses(text: str) -> list[str] | None:
        """Try to split text by clause boundaries. Returns None if not clause-structured."""
        matches = list(_CLAUSE_PATTERN.finditer(text))
        if len(matches) < 4:
            return None

        clauses = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            clause_text = text[start:end].strip()
            if not clause_text:
                continue

            tokens = _enc.encode(clause_text)
            if len(tokens) <= CHUNK_SIZE:
                clauses.append(clause_text)
            else:
                # Sub-split long clauses, preserving header
                first_line = clause_text.split("\n")[0]
                header = first_line[:120]
                header_tokens = _enc.encode(header + "\n\n")
                available = CHUNK_SIZE - len(header_tokens)
                if available < 100:
                    available = CHUNK_SIZE
                content_tokens = _enc.encode(clause_text)
                pos = 0
                overlap = 50
                while pos < len(content_tokens):
                    chunk_end = min(pos + available, len(content_tokens))
                    chunk_text = _enc.decode(content_tokens[pos:chunk_end])
                    if pos > 0:
                        chunk_text = f"{header}\n\n{chunk_text}"
                    clauses.append(chunk_text)
                    if chunk_end >= len(content_tokens):
                        break
                    pos += available - overlap

        # Capture any preamble before the first clause
        if matches and matches[0].start() > 100:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                clauses.insert(0, preamble)

        return [c for c in clauses if c.strip()] if clauses else None

    def _split_into_chunks(self, text: str) -> list[str]:
        # Try clause-aware splitting first
        clause_chunks = self._split_by_clauses(text)
        if clause_chunks:
            return clause_chunks

        # Fallback: fixed-size token splitting
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
        # Only set content_hash if not already set (upload endpoint sets it from raw bytes)
        if not document.content_hash:
            document.content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        return len(chunks)


ingestion_service = IngestionService(embedding_service)

# Convenience aliases for backward-compatible imports
extract_text_from_bytes = IngestionService.extract_text_from_bytes
make_document = IngestionService.make_document
