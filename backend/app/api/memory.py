import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.memory import Memory
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryList, MemoryOut, MemoryUpdate
from app.services.embeddings import embed_texts

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=MemoryList)
async def list_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == current_user.id)
        .order_by(Memory.created_at.desc())
    )
    items = result.scalars().all()
    return MemoryList(items=items, total=len(items))


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(
    body: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    embeddings = await embed_texts([body.content])
    memory = Memory(
        user_id=current_user.id,
        org_id=current_user.org_id,
        content=body.content,
        embedding=embeddings[0],
        source="manual",
    )
    db.add(memory)
    await db.flush()
    return MemoryOut.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == current_user.id)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    embeddings = await embed_texts([body.content])
    memory.content = body.content
    memory.embedding = embeddings[0]
    await db.flush()
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == current_user.id)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(memory)


@router.delete("", status_code=204)
async def delete_all_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR: user can wipe all their memories at once."""
    result = await db.execute(
        select(Memory).where(Memory.user_id == current_user.id)
    )
    for memory in result.scalars().all():
        await db.delete(memory)
