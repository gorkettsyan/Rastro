import hashlib
import uuid
from datetime import datetime, timezone

import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from app.models.document import Document
from app.models.chunk import Chunk
from app.services.embeddings import embed_texts

_enc = tiktoken.get_encoding("cl100k_base")
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


def _split_into_chunks(text: str) -> list[str]:
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


async def chunk_and_embed(
    db: AsyncSession,
    document: Document,
    raw_text: str,
    extra_metadata: dict | None = None,
) -> int:
    """Chunks, embeds, and stores in pgvector. Idempotent. Returns chunk count."""
    if not raw_text or len(raw_text.strip()) < 50:
        return 0

    await db.execute(delete(Chunk).where(Chunk.document_id == document.id))

    chunks = _split_into_chunks(raw_text)
    if not chunks:
        return 0

    embeddings = await embed_texts(chunks)

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
