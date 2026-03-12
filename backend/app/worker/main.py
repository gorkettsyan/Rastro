"""SQS worker — run as: python -m app.worker.main"""
import asyncio
import logging
import signal

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings
from app.worker.queue import queue_service
from app.worker.handlers.upload import handle_manual_upload
from app.worker.handlers.drive import handle_drive_file
from app.worker.handlers.gmail import handle_gmail_thread
from app.worker.handlers.memory import handle_extract_memories
from app.worker.handlers.message_embedder import handle_embed_message
from app.worker.handlers.boe import handle_boe_ingest, handle_boe_sync
from app.worker.handlers.entity_extraction import handle_extract_entities

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

HANDLERS = {
    "manual_upload": handle_manual_upload,
    "drive_file": handle_drive_file,
    "gmail_thread": handle_gmail_thread,
    "extract_memories": handle_extract_memories,
    "embed_message": handle_embed_message,
    "boe_ingest": handle_boe_ingest,
    "boe_sync": handle_boe_sync,
    "extract_entities": handle_extract_entities,
}

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
_running = True


def _shutdown(sig, frame):
    global _running
    log.info("Shutting down worker...")
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


async def process(msg: dict) -> None:
    body, receipt = msg["body"], msg["receipt_handle"]
    handler = HANDLERS.get(body.get("job_type"))
    if not handler:
        log.warning(f"Unknown job_type: {body.get('job_type')}")
        queue_service.delete_message(receipt)
        return

    async with SessionLocal() as db:
        try:
            log.info(f"Processing {body['job_type']} document_id={body.get('document_id')}")
            await handler(body, db)
            await db.commit()
            queue_service.delete_message(receipt)
            log.info(f"Done: {body['job_type']} document_id={body.get('document_id')}")
        except Exception as e:
            await db.rollback()
            log.error(f"Failed {body['job_type']}: {e}", exc_info=True)
            # Don't delete — SQS retries up to 3x then sends to DLQ


async def run():
    log.info("Worker started, polling SQS...")
    while _running:
        for msg in queue_service.poll(wait_seconds=20):
            await process(msg)
    log.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(run())
