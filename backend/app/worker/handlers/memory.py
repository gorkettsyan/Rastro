import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.memory_extractor import memory_extractor_service

log = logging.getLogger(__name__)


async def handle_extract_memories(body: dict, db: AsyncSession) -> None:
    count = await memory_extractor_service.extract_and_store_memories(
        db=db,
        user_id=body["user_id"],
        org_id=body["org_id"],
        conversation_id=body["conversation_id"],
    )
    log.info(f"Extracted {count} new memories for user {body['user_id']}")
