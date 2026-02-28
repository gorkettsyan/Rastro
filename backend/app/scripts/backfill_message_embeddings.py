"""
One-off script: re-embeds all assistant messages as Q&A pairs.

Run with:
    docker-compose exec backend uv run python -m app.scripts.backfill_message_embeddings
"""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.message import Message
from app.services.embeddings import embed_texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE = 20


async def backfill():
    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.role == "assistant")
            .order_by(Message.created_at.asc())
        )
        messages = result.scalars().all()

    log.info(f"Found {len(messages)} assistant messages to re-embed")

    processed = 0
    async with SessionLocal() as db:
        for msg in messages:
            # Find preceding user message
            preceding = await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == msg.conversation_id,
                    Message.role == "user",
                    Message.created_at <= msg.created_at,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            user_msg = preceding.scalar_one_or_none()

            text_to_embed = (
                f"Q: {user_msg.content}\nA: {msg.content}" if user_msg else msg.content
            )

            try:
                embeddings = await embed_texts([text_to_embed])
                msg.embedding = embeddings[0]
                processed += 1
                log.info(
                    f"[{processed}/{len(messages)}] Re-embedded {msg.id} "
                    f"({'Q&A pair' if user_msg else 'answer only'})"
                )
            except Exception as e:
                log.error(f"Failed to embed {msg.id}: {e}")

            if processed % BATCH_SIZE == 0:
                await db.commit()
                log.info(f"Committed batch of {BATCH_SIZE}")

        await db.commit()

    log.info(f"Done. Re-embedded {processed}/{len(messages)} messages.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
