from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document import Document
from app.services.ingestion import chunk_and_embed
from app.services.storage import download_text


async def handle_manual_upload(body: dict, db: AsyncSession) -> None:
    result = await db.execute(select(Document).where(Document.id == body["document_id"]))
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise ValueError(f"Document not found or missing file_path: {body['document_id']}")
    doc.indexing_status = "indexing"
    await db.flush()
    try:
        raw_text = download_text(doc.file_path)
        await chunk_and_embed(db, doc, raw_text)
    except Exception as e:
        doc.indexing_status = "error"
        doc.indexing_error = str(e)[:500]
