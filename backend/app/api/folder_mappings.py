import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update

from app.database import get_db
from app.dependencies import get_current_user
from app.models.folder_mapping import FolderMapping
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.integration_token import IntegrationToken
from app.models.user import User
from app.security import decrypt
from app.schemas.folder_mapping import (
    FolderMappingCreate,
    FolderMappingOut,
    FolderMappingList,
    DriveFolderOut,
)
from app.schemas.document import DocumentOut, DocumentList

router = APIRouter(prefix="/folder-mappings", tags=["folder-mappings"])


async def _assert_project_member(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.org_id == user.org_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=FolderMappingList)
async def list_mappings(
    project_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(FolderMapping).where(FolderMapping.org_id == current_user.org_id)
    if project_id:
        q = q.where(FolderMapping.project_id == project_id)
    result = await db.execute(q.order_by(FolderMapping.created_at.desc()))
    return FolderMappingList(items=result.scalars().all())


@router.post("", response_model=FolderMappingOut, status_code=201)
async def create_mapping(
    body: FolderMappingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_project_member(body.project_id, current_user, db)

    # Check uniqueness (org + folder)
    existing = await db.execute(
        select(FolderMapping).where(
            FolderMapping.org_id == current_user.org_id,
            FolderMapping.folder_id == body.folder_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder already mapped")

    mapping = FolderMapping(
        org_id=current_user.org_id,
        project_id=body.project_id,
        folder_id=body.folder_id,
        folder_name=body.folder_name,
        created_by=current_user.id,
    )
    db.add(mapping)
    await db.flush()

    # Auto-assign existing Drive docs from this folder
    await _assign_docs_by_folder(
        db, current_user.org_id, body.folder_id, body.project_id
    )

    await db.refresh(mapping)
    return FolderMappingOut.model_validate(mapping)


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FolderMapping).where(
            FolderMapping.id == mapping_id,
            FolderMapping.org_id == current_user.org_id,
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.delete(mapping)


@router.get("/drive-folders", response_model=list[DriveFolderOut])
async def list_drive_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List Google Drive folders the user has access to."""
    token_result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == current_user.id,
            IntegrationToken.provider == "google",
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=400, detail="Google not connected")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    service = build(
        "drive", "v3", credentials=Credentials(token=decrypt(token.access_token_enc))
    )

    folders = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q="mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="nextPageToken,files(id,name)",
                pageSize=100,
                pageToken=page_token,
            )
            .execute()
        )
        for f in resp.get("files", []):
            folders.append(DriveFolderOut(id=f["id"], name=f["name"]))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return folders


@router.get("/unassigned", response_model=DocumentList)
async def list_unassigned_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents not assigned to any project (excluding gmail)."""
    result = await db.execute(
        select(Document)
        .where(
            Document.org_id == current_user.org_id,
            Document.project_id.is_(None),
            Document.source != "gmail",
        )
        .order_by(Document.created_at.desc())
    )
    items = result.scalars().all()
    return DocumentList(items=items, total=len(items))


@router.post("/assign-bulk")
async def assign_documents_bulk(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign multiple documents to a project at once."""
    project_id = body.get("project_id")
    document_ids = body.get("document_ids", [])
    if not project_id or not document_ids:
        raise HTTPException(status_code=400, detail="project_id and document_ids required")

    project_uuid = uuid.UUID(project_id)
    await _assert_project_member(project_uuid, current_user, db)

    doc_uuids = [uuid.UUID(d) for d in document_ids]
    await db.execute(
        sa_update(Document)
        .where(
            Document.id.in_(doc_uuids),
            Document.org_id == current_user.org_id,
        )
        .values(project_id=project_uuid)
    )
    await db.execute(
        sa_update(Chunk)
        .where(
            Chunk.document_id.in_(doc_uuids),
            Chunk.org_id == current_user.org_id,
        )
        .values(project_id=project_uuid)
    )
    await db.flush()
    return {"assigned": len(doc_uuids)}


async def _assign_docs_by_folder(
    db: AsyncSession,
    org_id: uuid.UUID,
    folder_id: str,
    project_id: uuid.UUID,
) -> int:
    """Assign existing Drive docs with matching folder_id to a project."""
    result = await db.execute(
        select(Document).where(
            Document.org_id == org_id,
            Document.source == "drive",
            Document.drive_folder_id == folder_id,
            Document.project_id.is_(None),
        )
    )
    docs = result.scalars().all()
    for doc in docs:
        doc.project_id = project_id
    if docs:
        doc_ids = [d.id for d in docs]
        await db.execute(
            sa_update(Chunk)
            .where(Chunk.document_id.in_(doc_ids))
            .values(project_id=project_id)
        )
    await db.flush()
    return len(docs)
