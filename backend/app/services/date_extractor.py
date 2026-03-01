import json
import logging
from datetime import date
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.config import settings
from app.models.chunk import Chunk
from app.models.obligation import Obligation

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a legal document analyzer. Extract all deadlines and time-sensitive obligations from this contract text.

For each obligation found, return:
- type: one of "termination_notice", "renewal_window", "payment_due", "option_exercise", "warranty_expiry", "other"
- description: plain-language summary of the obligation (1-2 sentences)
- clause_text: the exact quote from the document (max 300 chars)
- due_date: ISO date (YYYY-MM-DD) if a specific date is stated, null otherwise
- date_unresolved: true if the date is relative ("30 days after signing") and cannot be resolved to a specific date
- confidence: 0.0-1.0 how confident you are this is a real obligation with a real deadline
- chunk_index: which chunk number contains this obligation (0-based)

Return JSON: {"obligations": [...]}
If no obligations found, return {"obligations": []}

The document text follows, with chunk markers like [CHUNK 0], [CHUNK 1], etc."""


class DateExtractorService:
    def __init__(self):
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def extract_obligations(
        self, db: AsyncSession, document_id, org_id
    ) -> int:
        result = await db.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index.asc())
        )
        chunks = result.scalars().all()
        if not chunks:
            return 0

        doc_text = "\n\n".join(
            f"[CHUNK {c.chunk_index}]\n{c.content}" for c in chunks
        )
        chunk_map = {c.chunk_index: c.id for c in chunks}

        try:
            response = await self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": doc_text},
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            candidates = parsed.get("obligations", [])
        except Exception as e:
            log.error(f"Obligation extraction failed for doc {document_id}: {e}")
            return 0

        if not candidates:
            return 0

        # Delete previous auto-extracted obligations (idempotent on re-ingestion)
        await db.execute(
            delete(Obligation).where(
                Obligation.document_id == document_id,
                Obligation.source == "auto",
            )
        )

        # Get project_id from the first chunk
        project_id = chunks[0].project_id if chunks else None

        stored = 0
        for item in candidates:
            due_date_val = None
            if item.get("due_date"):
                try:
                    due_date_val = date.fromisoformat(item["due_date"])
                except (ValueError, TypeError):
                    pass

            chunk_index = item.get("chunk_index", 0)
            chunk_id = chunk_map.get(chunk_index)

            ob = Obligation(
                org_id=org_id,
                document_id=document_id,
                project_id=project_id,
                chunk_id=chunk_id,
                obligation_type=item.get("type", "other"),
                description=item.get("description", ""),
                clause_text=(item.get("clause_text") or "")[:500] or None,
                due_date=due_date_val,
                date_unresolved=bool(item.get("date_unresolved", False)),
                confidence=float(item.get("confidence", 1.0)),
                status="open",
                source="auto",
            )
            db.add(ob)
            stored += 1

        await db.flush()
        log.info(f"Extracted {stored} obligations from document {document_id}")
        return stored


date_extractor_service = DateExtractorService()
