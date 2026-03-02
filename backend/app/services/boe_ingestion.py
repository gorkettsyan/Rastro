"""BOE ingestion: fetches law articles, chunks, embeds, and stores BoeChunk rows."""
import logging
import uuid
from datetime import datetime, timezone

import tiktoken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boe import BoeChunk, BoeLaw
from app.services.boe_client import BoeArticle, BoeLawData, KNOWN_LAWS, fetch_law
from app.services.embeddings import embedding_service

log = logging.getLogger(__name__)

_enc = tiktoken.get_encoding("cl100k_base")
MAX_ARTICLE_TOKENS = 512


def _split_long_article(article: BoeArticle, law_name: str) -> list[dict]:
    """Split an article into sub-chunks if it exceeds MAX_ARTICLE_TOKENS.

    Each sub-chunk preserves the article header (title/article_number) for context.
    """
    tokens = _enc.encode(article.content)

    if len(tokens) <= MAX_ARTICLE_TOKENS:
        return [{"content": article.content, "article": article}]

    # Build header to prepend to each sub-chunk
    header_parts = [law_name]
    if article.section_title:
        header_parts.append(article.section_title)
    if article.article_number:
        header_parts.append(article.article_number)
    header = " — ".join(header_parts)
    header_tokens = _enc.encode(header + "\n\n")
    available = MAX_ARTICLE_TOKENS - len(header_tokens)
    if available < 100:
        available = MAX_ARTICLE_TOKENS

    chunks = []
    content_tokens = _enc.encode(article.content)
    start = 0
    overlap = 50
    while start < len(content_tokens):
        end = min(start + available, len(content_tokens))
        chunk_text = _enc.decode(content_tokens[start:end])
        if start > 0:
            chunk_text = f"{header}\n\n{chunk_text}"
        chunks.append({"content": chunk_text, "article": article})
        if end >= len(content_tokens):
            break
        start += available - overlap

    return chunks


async def ingest_law(db: AsyncSession, boe_id: str, title: str, short_name: str) -> int:
    """Fetch, chunk, embed, and store a single BOE law. Idempotent."""
    # Upsert BoeLaw record
    result = await db.execute(select(BoeLaw).where(BoeLaw.boe_id == boe_id))
    law = result.scalar_one_or_none()
    if not law:
        law = BoeLaw(boe_id=boe_id, title=title, short_name=short_name, sync_status="syncing")
        db.add(law)
        await db.flush()
    else:
        law.sync_status = "syncing"
        law.sync_error = None
        await db.flush()

    try:
        law_data = await fetch_law(boe_id)
        if not law_data or not law_data.articles:
            law.sync_status = "error"
            law.sync_error = "No articles fetched from BOE API"
            await db.flush()
            return 0

        # Delete old chunks for this law
        await db.execute(delete(BoeChunk).where(BoeChunk.boe_law_id == law.id))

        # Build all sub-chunks
        all_chunks: list[dict] = []
        for article in law_data.articles:
            sub_chunks = _split_long_article(article, short_name)
            all_chunks.extend(sub_chunks)

        if not all_chunks:
            law.sync_status = "done"
            law.chunk_count = 0
            law.synced_at = datetime.now(timezone.utc)
            await db.flush()
            return 0

        # Embed all chunk texts
        texts = [c["content"] for c in all_chunks]
        embeddings = await embedding_service.embed_texts(texts)

        # Store BoeChunk rows
        for i, (chunk_data, emb) in enumerate(zip(all_chunks, embeddings)):
            article: BoeArticle = chunk_data["article"]
            db.add(BoeChunk(
                id=uuid.uuid4(),
                boe_law_id=law.id,
                boe_id=boe_id,
                law_name=short_name,
                article_number=article.article_number,
                section_title=article.section_title,
                block_id=article.block_id,
                content=chunk_data["content"],
                embedding=emb,
                chunk_index=i,
                metadata_={
                    "law_title": title,
                    "short_name": short_name,
                },
                boe_url=article.boe_url,
            ))

        await db.flush()

        law.chunk_count = len(all_chunks)
        law.sync_status = "done"
        law.synced_at = datetime.now(timezone.utc)
        await db.flush()

        log.info("Ingested %d chunks for %s (%s)", len(all_chunks), boe_id, short_name)
        return len(all_chunks)

    except Exception as e:
        law.sync_status = "error"
        law.sync_error = str(e)[:500]
        await db.flush()
        log.error("Failed to ingest %s: %s", boe_id, e, exc_info=True)
        raise


async def ingest_all_laws(db: AsyncSession) -> dict:
    """Ingest all known BOE laws. Returns {boe_id: chunk_count}."""
    results = {}
    for law_info in KNOWN_LAWS:
        try:
            count = await ingest_law(db, law_info["boe_id"], law_info["title"], law_info["short_name"])
            results[law_info["boe_id"]] = count
        except Exception as e:
            log.error("Skipping %s due to error: %s", law_info["boe_id"], e)
            results[law_info["boe_id"]] = -1
    return results
