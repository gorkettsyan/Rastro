from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document import Document
from app.services.ingestion import ingestion_service
from app.services.storage import storage_service
from app.worker.queue import queue_service


async def handle_manual_upload(body: dict, db: AsyncSession) -> None:
    result = await db.execute(select(Document).where(Document.id == body["document_id"]))
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise ValueError(f"Document not found or missing file_path: {body['document_id']}")
    doc.indexing_status = "indexing"
    await db.flush()
    try:
        raw_text = storage_service.download_text(doc.file_path)
        await ingestion_service.chunk_and_embed(db, doc, raw_text)
        queue_service.enqueue({
            "job_type": "extract_entities",
            "document_id": str(doc.id),
            "org_id": str(doc.org_id),
        })
    except Exception as e:
        doc.indexing_status = "error"
        doc.indexing_error = str(e)[:500]
