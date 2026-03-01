from sqlalchemy.ext.asyncio import AsyncSession
from app.services.date_extractor import date_extractor_service


async def handle_extract_dates(body: dict, db: AsyncSession) -> None:
    document_id = body["document_id"]
    org_id = body["org_id"]
    await date_extractor_service.extract_obligations(db, document_id, org_id)
