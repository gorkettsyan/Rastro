from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user
from app.models.integration_token import IntegrationToken
from app.models.document import Document
from app.models.user import User
from app.schemas.integration import IntegrationStatusOut, IntegrationStatusItem, SyncResponse
from app.worker.handlers.drive import enqueue_all_drive_files
from app.worker.handlers.gmail import enqueue_all_gmail_threads

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status", response_model=IntegrationStatusOut)
async def integration_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token_result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.org_id == current_user.org_id,
            IntegrationToken.provider == "google",
        )
    )
    token = token_result.scalar_one_or_none()

    if not token:
        return IntegrationStatusOut(
            google=IntegrationStatusItem(connected=False, last_sync=None, doc_count=0, error=None)
        )

    count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.org_id == current_user.org_id,
            Document.source.in_(["drive", "gmail"]),
            Document.indexing_status == "done",
        )
    )

    return IntegrationStatusOut(
        google=IntegrationStatusItem(
            connected=True,
            last_sync=token.updated_at,
            doc_count=count_result.scalar() or 0,
            error=None,
        )
    )


@router.post("/google/sync", response_model=SyncResponse)
async def google_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    drive_count = await enqueue_all_drive_files(str(current_user.org_id), str(current_user.id), db)
    gmail_count = await enqueue_all_gmail_threads(str(current_user.org_id), str(current_user.id), db)
    total = drive_count + gmail_count
    return SyncResponse(message=f"Sync started: {total} files queued", queued=total)
