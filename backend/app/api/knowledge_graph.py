from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.entity import Entity, EntityEdge
from app.worker.queue import queue_service

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


@router.get("")
async def get_knowledge_graph(
    project_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.org_id

    result = await db.execute(
        select(Entity)
        .where(Entity.org_id == org_id, Entity.project_id == project_id)
        .order_by(Entity.mention_count.desc())
        .limit(200)
    )
    entities = result.scalars().all()
    entity_ids = {e.id for e in entities}

    edges_list = []
    if entity_ids:
        result = await db.execute(
            select(EntityEdge).where(
                EntityEdge.org_id == org_id,
                EntityEdge.source_entity_id.in_(entity_ids),
                EntityEdge.target_entity_id.in_(entity_ids),
            )
        )
        edges_list = result.scalars().all()

    doc_count_result = await db.execute(
        select(func.count(func.distinct(EntityEdge.document_id))).where(
            EntityEdge.org_id == org_id,
            EntityEdge.document_id.is_not(None),
            EntityEdge.source_entity_id.in_(entity_ids),
        )
    )
    docs_processed = doc_count_result.scalar() or 0

    return {
        "nodes": [
            {
                "id": str(e.id),
                "name": e.name,
                "type": e.entity_type,
                "mention_count": e.mention_count,
            }
            for e in entities
        ],
        "edges": [
            {
                "id": str(e.id),
                "source": str(e.source_entity_id),
                "target": str(e.target_entity_id),
                "relation": e.relation_type,
                "weight": e.weight,
            }
            for e in edges_list
        ],
        "stats": {
            "total_entities": len(entities),
            "total_edges": len(edges_list),
            "documents_processed": docs_processed,
        },
    }


@router.post("/scan")
async def scan_documents(
    project_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue entity extraction for all indexed documents in the project."""
    org_id = current_user.org_id
    result = await db.execute(
        select(Document).where(
            Document.org_id == org_id,
            Document.project_id == project_id,
            Document.indexing_status == "done",
        )
    )
    docs = result.scalars().all()
    for doc in docs:
        queue_service.enqueue({
            "job_type": "extract_entities",
            "document_id": str(doc.id),
            "org_id": str(org_id),
        })
    return {"documents": len(docs)}
