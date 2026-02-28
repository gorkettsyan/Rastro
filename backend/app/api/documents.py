import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update, or_, and_, exists

from app.database import get_db
from app.dependencies import get_current_user
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.document import DocumentOut, DocumentList, DocumentUpdate
from app.services.storage import upload_text
from app.services.ingestion import extract_text_from_bytes, make_document
from app.worker.queue import enqueue

router = APIRouter(prefix="/documents", tags=["documents"])

def _visible_to_user(user: User):
    """SQLAlchemy clause: doc owner OR org-wide visibility OR project member."""
    project_member_exists = exists(
        select(ProjectMember.id).where(
            and_(
                ProjectMember.project_id == Document.project_id,
                ProjectMember.user_id == user.id,
            )
        )
    )
    return or_(
        Document.indexed_by_user_id == user.id,
        Document.visibility == "org",
        and_(Document.visibility == "project", Document.project_id.isnot(None), project_member_exists),
    )


ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


@router.get("", response_model=DocumentList)
async def list_documents(
    project_id: uuid.UUID | None = None,
    include_emails: bool = Query(False),
    source: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Document).where(
        Document.org_id == current_user.org_id,
        _visible_to_user(current_user),
    )
    if not include_emails:
        q = q.where(Document.source != "gmail")
    if source:
        q = q.where(Document.source == source)
    if project_id:
        q = q.where(Document.project_id == project_id)
    result = await db.execute(q.order_by(Document.created_at.desc()))
    items = result.scalars().all()
    return DocumentList(items=items, total=len(items))


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    project_id: uuid.UUID | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()
    raw_text = extract_text_from_bytes(content, file.content_type)

    s3_key = f"{current_user.org_id}/upload/{content_hash}.txt"
    upload_text(s3_key, raw_text)

    doc = make_document(
        user_id=current_user.id,
        org_id=current_user.org_id,
        project_id=project_id,
        title=file.filename or "Documento sin título",
        source="upload",
        file_path=s3_key,
        content_hash=content_hash,
        file_size_bytes=len(content),
        mime_type=file.content_type,
        indexing_status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    enqueue({
        "job_type": "manual_upload",
        "org_id": str(current_user.org_id),
        "user_id": str(current_user.id),
        "document_id": str(doc.id),
        "source_id": str(doc.id),
    })

    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc_result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == current_user.org_id,
            _visible_to_user(current_user),
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks_result = await db.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index.asc())
    )
    chunks = chunks_result.scalars().all()
    content = "\n\n".join(c.content for c in chunks)

    return {
        "id": str(doc.id),
        "title": doc.title,
        "source": doc.source,
        "source_url": doc.source_url,
        "content": content,
    }


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == current_user.org_id,
            _visible_to_user(current_user),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.project_id = body.project_id

    # Keep chunks in sync so project-scoped search stays correct
    await db.execute(
        sa_update(Chunk)
        .where(Chunk.document_id == document_id)
        .values(project_id=body.project_id)
    )

    await db.flush()
    return DocumentOut.model_validate(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == current_user.org_id,
            _visible_to_user(current_user),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
