"""Admin API — BOE ingestion management."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.boe import BoeLaw
from app.models.user import User
from app.services.boe_client import KNOWN_LAWS
from app.worker.queue import queue_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/boe/ingest", status_code=202)
async def ingest_boe(
    boe_id: str | None = Query(None, description="Specific BOE ID to ingest, or omit for all"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Queue BOE ingestion. If boe_id given, ingest one law. Otherwise ingest all."""
    if boe_id:
        law = next((l for l in KNOWN_LAWS if l["boe_id"] == boe_id), None)
        if not law:
            return {"error": f"Unknown boe_id: {boe_id}", "known": [l["boe_id"] for l in KNOWN_LAWS]}
        queue_service.enqueue({"job_type": "boe_ingest", "boe_id": boe_id})
        return {"status": "queued", "boe_id": boe_id, "title": law["title"]}
    else:
        queue_service.enqueue({"job_type": "boe_sync"})
        return {"status": "queued", "message": f"Full sync of {len(KNOWN_LAWS)} laws queued"}


@router.get("/boe/status")
async def boe_status(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all BOE laws with their sync status."""
    result = await db.execute(select(BoeLaw).order_by(BoeLaw.short_name))
    laws = result.scalars().all()

    items = []
    for law in laws:
        items.append({
            "boe_id": law.boe_id,
            "title": law.title,
            "short_name": law.short_name,
            "sync_status": law.sync_status,
            "chunk_count": law.chunk_count,
            "synced_at": law.synced_at.isoformat() if law.synced_at else None,
            "sync_error": law.sync_error,
        })

    # Include known laws that haven't been ingested yet
    ingested_ids = {law.boe_id for law in laws}
    for known in KNOWN_LAWS:
        if known["boe_id"] not in ingested_ids:
            items.append({
                "boe_id": known["boe_id"],
                "title": known["title"],
                "short_name": known["short_name"],
                "sync_status": "not_ingested",
                "chunk_count": 0,
                "synced_at": None,
                "sync_error": None,
            })

    return {"laws": items, "total": len(items)}


@router.post("/boe/sync", status_code=202)
async def sync_boe(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Queue a full re-sync of all BOE laws."""
    queue_service.enqueue({"job_type": "boe_sync"})
    return {"status": "queued", "message": f"Full re-sync of {len(KNOWN_LAWS)} laws queued"}
