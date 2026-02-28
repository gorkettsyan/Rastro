import uuid
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.search_log import SearchLog
from app.services.rag import stream_rag_response

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/stream")
async def search_stream(
    q: str = Query(..., min_length=1),
    project_id: uuid.UUID | None = Query(None),
    lang: str = Query("en"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint — streams: token events, sources event, done event."""
    async def generate():
        async for event in stream_rag_response(db, user.org_id, user.id, q, project_id, language=lang):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
async def search_history(
    project_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SearchLog)
        .where(SearchLog.org_id == user.org_id)
        .order_by(SearchLog.created_at.desc())
        .limit(limit)
    )
    if project_id:
        stmt = stmt.where(SearchLog.project_id == project_id)

    result = await db.execute(stmt)
    logs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(log.id),
                "query": log.query,
                "result_count": log.result_count,
                "project_id": str(log.project_id) if log.project_id else None,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
    }
