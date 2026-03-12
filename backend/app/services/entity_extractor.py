import json
import logging
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.entity import Entity, EntityEdge

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a legal document analyzer. Extract the most important entities and their relationships from the text.

Return JSON with:
{
  "entities": [{"name": "...", "type": "organization|person|jurisdiction|clause_type"}],
  "relationships": [{"source": "entity name", "target": "entity name", "relation": "party_to|governed_by|contains_clause|references|employs"}]
}

Rules:
- Use Title Case for all entity names (e.g. "Acme Corp" not "acme corp" or "ACME CORPORATION")
- entity types: organization, person, jurisdiction, clause_type
- Only extract key entities: named parties, people, jurisdictions, and distinctive clause types
- Do NOT extract generic terms like "confidentiality", "termination", "price", "duration" as clause_type — only extract clause types that are specific or unusual
- Do NOT extract document names, risk levels, or generic legal concepts as entities
- Deduplicate entities strictly — merge variants of the same name
- Maximum 15 entities and 20 relationships per extraction
- Keep entity names concise"""


class EntityExtractorService:
    def __init__(self):
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def extract_entities(
        self, db: AsyncSession, document_id: UUID, org_id: UUID
    ) -> int:
        # Resolve project_id from the document
        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        doc = doc_result.scalar_one_or_none()
        project_id = doc.project_id if doc else None

        result = await db.execute(
            select(Chunk).where(Chunk.document_id == document_id).limit(20)
        )
        chunks = result.scalars().all()
        if not chunks:
            return 0

        combined_text = "\n---\n".join(c.content for c in chunks)[:8000]

        try:
            resp = await self._openai.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": combined_text},
                ],
                temperature=0.1,
            )
            data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            log.error(f"Entity extraction failed: {e}")
            return 0

        entities_data = data.get("entities", [])
        relationships_data = data.get("relationships", [])

        entity_map: dict[str, Entity] = {}
        count = 0

        for ent in entities_data:
            name = ent.get("name", "").strip().title()
            etype = ent.get("type", "").strip().lower()
            if not name or not etype:
                continue

            q = select(Entity).where(
                Entity.org_id == org_id,
                Entity.name == name,
                Entity.entity_type == etype,
            )
            if project_id:
                q = q.where(Entity.project_id == project_id)
            else:
                q = q.where(Entity.project_id.is_(None))
            existing = await db.execute(q)
            entity = existing.scalar_one_or_none()
            if entity:
                entity.mention_count += 1
                entity_map[name] = entity
            else:
                entity = Entity(org_id=org_id, project_id=project_id, name=name, entity_type=etype)
                db.add(entity)
                await db.flush()
                entity_map[name] = entity
                count += 1

        for rel in relationships_data:
            src_name = rel.get("source", "").strip()
            tgt_name = rel.get("target", "").strip()
            rel_type = rel.get("relation", "").strip()
            if not src_name or not tgt_name or not rel_type:
                continue
            src = entity_map.get(src_name)
            tgt = entity_map.get(tgt_name)
            if not src or not tgt:
                continue

            existing_edge = await db.execute(
                select(EntityEdge).where(
                    EntityEdge.org_id == org_id,
                    EntityEdge.source_entity_id == src.id,
                    EntityEdge.target_entity_id == tgt.id,
                    EntityEdge.relation_type == rel_type,
                )
            )
            edge = existing_edge.scalar_one_or_none()
            if edge:
                edge.weight += 1
            else:
                edge = EntityEdge(
                    org_id=org_id,
                    source_entity_id=src.id,
                    target_entity_id=tgt.id,
                    relation_type=rel_type,
                    document_id=document_id,
                )
                db.add(edge)
                count += 1

        await db.flush()
        return count


entity_extractor_service = EntityExtractorService()
