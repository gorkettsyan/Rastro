"""Worker handlers for BOE ingestion jobs."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.boe_client import KNOWN_LAWS
from app.services.boe_ingestion import ingest_law, ingest_all_laws

log = logging.getLogger(__name__)


async def handle_boe_ingest(body: dict, db: AsyncSession) -> None:
    """Ingest a single BOE law. Body: {job_type: "boe_ingest", boe_id: "BOE-A-..."}"""
    boe_id = body.get("boe_id")
    if not boe_id:
        log.error("boe_ingest job missing boe_id")
        return

    law_info = next((l for l in KNOWN_LAWS if l["boe_id"] == boe_id), None)
    if not law_info:
        log.error("Unknown boe_id: %s", boe_id)
        return

    count = await ingest_law(db, boe_id, law_info["title"], law_info["short_name"])
    log.info("BOE ingest complete: %s → %d chunks", boe_id, count)


async def handle_boe_sync(body: dict, db: AsyncSession) -> None:
    """Re-sync all known BOE laws. Body: {job_type: "boe_sync"}"""
    results = await ingest_all_laws(db)
    total = sum(v for v in results.values() if v > 0)
    log.info("BOE sync complete: %d total chunks across %d laws", total, len(results))
