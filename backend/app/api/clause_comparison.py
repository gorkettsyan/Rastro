import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.clause_comparison import ClauseComparisonExport
from app.services.clause_comparison import clause_comparison_service

router = APIRouter(prefix="/clause-comparison", tags=["clause-comparison"])


@router.get("/stream")
async def stream_comparison(
    q: str = Query(..., min_length=1),
    project_id: uuid.UUID | None = Query(None),
    lang: str = Query("es"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async def generate():
        async for event in clause_comparison_service.compare_clauses(
            db, user.org_id, user.id, q, project_id, language=lang
        ):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/export")
async def export_comparison(
    body: ClauseComparisonExport,
    format: str = Query("docx"),
    user: User = Depends(get_current_user),
):
    if format == "pdf":
        buf = clause_comparison_service.generate_pdf(
            body.query, body.results, body.missing, body.language
        )
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=clause_comparison.pdf"},
        )

    buf = clause_comparison_service.generate_docx(
        body.query, body.results, body.missing, body.language
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=clause_comparison.docx"},
    )
