import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, exists

from app.database import get_db
from app.dependencies import get_current_user
from app.models.document import Document
from app.models.obligation import Obligation
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.obligation import (
    ObligationCreate, ObligationUpdate, ObligationOut, ObligationList,
    ALLOWED_TYPES, ALLOWED_STATUSES,
)

router = APIRouter(prefix="/obligations", tags=["obligations"])


def _visible_obligations(user: User):
    """Only show obligations from documents the user can see."""
    project_member_exists = exists(
        select(ProjectMember.id).where(
            and_(
                ProjectMember.project_id == Document.project_id,
                ProjectMember.user_id == user.id,
            )
        )
    )
    doc_visible = or_(
        Document.indexed_by_user_id == user.id,
        Document.visibility == "org",
        and_(Document.visibility == "project", Document.project_id.isnot(None), project_member_exists),
    )
    return or_(
        Obligation.document_id.is_(None),  # manual obligations without document
        exists(select(Document.id).where(Document.id == Obligation.document_id, doc_visible)),
    )


async def _obligation_to_out(db: AsyncSession, ob: Obligation) -> ObligationOut:
    doc_title = None
    if ob.document_id:
        doc_result = await db.execute(select(Document.title).where(Document.id == ob.document_id))
        row = doc_result.first()
        if row:
            doc_title = row[0]
    return ObligationOut(
        id=ob.id,
        org_id=ob.org_id,
        document_id=ob.document_id,
        project_id=ob.project_id,
        chunk_id=ob.chunk_id,
        obligation_type=ob.obligation_type,
        description=ob.description,
        clause_text=ob.clause_text,
        due_date=ob.due_date,
        date_unresolved=ob.date_unresolved,
        confidence=ob.confidence,
        status=ob.status,
        source=ob.source,
        created_by=ob.created_by,
        created_at=ob.created_at,
        updated_at=ob.updated_at or ob.created_at,
        document_title=doc_title,
    )


@router.get("", response_model=ObligationList)
async def list_obligations(
    status: str | None = Query(None),
    project_id: uuid.UUID | None = Query(None),
    obligation_type: str | None = Query(None),
    days_ahead: int | None = Query(None),
    include_resolved: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Obligation).where(
        Obligation.org_id == current_user.org_id,
        _visible_obligations(current_user),
    )
    if status:
        q = q.where(Obligation.status == status)
    elif not include_resolved:
        q = q.where(Obligation.status != "resolved")
    if project_id:
        q = q.where(Obligation.project_id == project_id)
    if obligation_type:
        q = q.where(Obligation.obligation_type == obligation_type)
    if days_ahead is not None:
        cutoff = date.today() + timedelta(days=days_ahead)
        q = q.where(or_(Obligation.due_date <= cutoff, Obligation.due_date.is_(None)))

    q = q.order_by(Obligation.due_date.asc().nullslast(), Obligation.created_at.desc())
    result = await db.execute(q)
    obligations = result.scalars().all()

    items = []
    for ob in obligations:
        items.append(await _obligation_to_out(db, ob))

    return ObligationList(items=items, total=len(items))


@router.get("/upcoming", response_model=ObligationList)
async def upcoming_obligations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    cutoff = today + timedelta(days=30)
    q = select(Obligation).where(
        Obligation.org_id == current_user.org_id,
        Obligation.status == "open",
        Obligation.due_date.isnot(None),
        Obligation.due_date <= cutoff,
        _visible_obligations(current_user),
    ).order_by(Obligation.due_date.asc()).limit(10)

    result = await db.execute(q)
    obligations = result.scalars().all()

    items = []
    for ob in obligations:
        items.append(await _obligation_to_out(db, ob))

    return ObligationList(items=items, total=len(items))


@router.post("", response_model=ObligationOut, status_code=201)
async def create_obligation(
    body: ObligationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.obligation_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Allowed: {', '.join(sorted(ALLOWED_TYPES))}")

    ob = Obligation(
        org_id=current_user.org_id,
        document_id=body.document_id,
        project_id=body.project_id,
        obligation_type=body.obligation_type,
        description=body.description,
        due_date=body.due_date,
        status="open",
        source="manual",
        created_by=current_user.id,
    )
    db.add(ob)
    await db.flush()
    return await _obligation_to_out(db, ob)


@router.patch("/{obligation_id}", response_model=ObligationOut)
async def update_obligation(
    obligation_id: uuid.UUID,
    body: ObligationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Obligation).where(
            Obligation.id == obligation_id,
            Obligation.org_id == current_user.org_id,
        )
    )
    ob = result.scalar_one_or_none()
    if not ob:
        raise HTTPException(status_code=404, detail="Obligation not found")

    if body.status is not None:
        if body.status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(ALLOWED_STATUSES))}")
        ob.status = body.status
    if body.due_date is not None:
        ob.due_date = body.due_date
    if body.description is not None:
        ob.description = body.description

    await db.flush()
    await db.refresh(ob)
    return await _obligation_to_out(db, ob)


@router.delete("/{obligation_id}", status_code=204)
async def delete_obligation(
    obligation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Obligation).where(
            Obligation.id == obligation_id,
            Obligation.org_id == current_user.org_id,
        )
    )
    ob = result.scalar_one_or_none()
    if not ob:
        raise HTTPException(status_code=404, detail="Obligation not found")
    await db.delete(ob)
