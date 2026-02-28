import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.message import Message
from app.services.embeddings import embedding_service

log = logging.getLogger(__name__)


async def handle_embed_message(body: dict, db: AsyncSession) -> None:
    message_id = uuid.UUID(body["message_id"])
    result = await db.execute(select(Message).where(Message.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        log.warning(f"Message {message_id} not found, skipping embed")
        return
    if msg.embedding is not None:
        log.info(f"Message {message_id} already embedded, skipping")
        return

    # Embed as Q&A pair so similarity search captures what the user asked
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

    embeddings = await embedding_service.embed_texts([text_to_embed])
    msg.embedding = embeddings[0]
    log.info(f"Embedded message {message_id} as {'Q&A pair' if user_msg else 'answer only'}")
