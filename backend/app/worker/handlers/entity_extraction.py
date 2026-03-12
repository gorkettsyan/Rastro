import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.entity_extractor import entity_extractor_service

log = logging.getLogger(__name__)


async def handle_extract_entities(body: dict, db: AsyncSession) -> None:
    count = await entity_extractor_service.extract_entities(
        db=db,
        document_id=body["document_id"],
        org_id=body["org_id"],
    )
    log.info(f"Extracted {count} entities from document {body['document_id']}")
