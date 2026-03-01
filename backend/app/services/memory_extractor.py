import json
import logging
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.config import settings
from app.models.memory import Memory
from app.models.message import Message
from app.services.base import BaseEmbeddingService
from app.services.embeddings import embedding_service

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze this conversation and extract two types of useful information about the user.

TYPE 1 — DURABLE FACTS: Long-term facts about the user (preferences, work area, professional context, communication style).
Examples:
- "Works primarily in corporate/mercantile law"
- "Clients are typically Spanish SMEs"
- "Prefers concise responses"
- "Office is based in Madrid"

TYPE 2 — RECENT TOPICS: Topics, questions, or tasks the user engaged with in this conversation. These help recall cross-conversation context.
Examples:
- "Asked about chess.com streak notification emails received in February 2026"
- "Searched for rent contract clauses related to early termination"
- "Discussed a supplier agreement with a 30-day payment term"

Do NOT include:
- Specific sensitive document content (names, amounts, parties)
- Pure debugging or meta questions ("why is it slow?")

Return a JSON object with a single key "memories" whose value is an array of strings.
If there is nothing worth capturing, return {"memories": []}."""

DUPLICATE_THRESHOLD = 0.92


class MemoryExtractorService:
    def __init__(self, embedding_svc: BaseEmbeddingService):
        self._embedding_svc = embedding_svc
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def extract_and_store_memories(
        self,
        db: AsyncSession,
        user_id,
        org_id,
        conversation_id,
    ) -> int:
        """
        Runs after a conversation turn. Extracts memories and deduplicates against existing ones.
        Returns number of new memories stored.
        """
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        messages = list(reversed(result.scalars().all()))
        if not messages:
            return 0

        conversation_text = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in messages
        )

        try:
            response = await self._openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": conversation_text},
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                candidates = parsed.get("memories", parsed.get("items", []))
            else:
                candidates = parsed
        except Exception as e:
            log.error(f"Memory extraction failed: {e}")
            return 0

        if not candidates:
            return 0

        embeddings = await self._embedding_svc.embed_texts(candidates)

        stored = 0
        for content, embedding in zip(candidates, embeddings):
            vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
            is_duplicate = False
            try:
                dup_result = await db.execute(text(f"""
                    SELECT id FROM memories
                    WHERE user_id = :user_id
                      AND 1 - (embedding <=> '{vector_str}'::vector) > :threshold
                    LIMIT 1
                """), {"user_id": str(user_id), "threshold": DUPLICATE_THRESHOLD})
                if dup_result.fetchone():
                    is_duplicate = True
            except Exception:
                # SQLite fallback: deduplicate by exact content match
                existing = await db.execute(
                    select(Memory).where(
                        Memory.user_id == user_id,
                        Memory.content == content,
                    )
                )
                if existing.scalar_one_or_none():
                    is_duplicate = True

            if is_duplicate:
                continue

            db.add(Memory(
                user_id=user_id,
                org_id=org_id,
                content=content,
                embedding=embedding,
                source="auto",
                conversation_id=conversation_id,
            ))
            stored += 1

        await db.flush()
        return stored

    async def get_memories_for_prompt(
        self, db: AsyncSession, user_id, current_query: str | None = None
    ) -> str:
        """
        Returns formatted memory block for system prompt injection.
        Part 1: extracted facts about the user (ALWAYS included — no filtering).
        Part 2: semantically relevant past exchanges (when current_query provided).
        Returns empty string if no data found.
        """
        parts = []

        # Part 1: Always inject user memories. Cap at ~2000 chars (~500 tokens)
        # to avoid crowding out document fragments in the context window.
        # Most recent memories first; stop adding when budget is exhausted.
        MEMORY_CHAR_BUDGET = 2000
        mem_result = await db.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(50)
        )
        memories = mem_result.scalars().all()
        if memories:
            lines = []
            used = 0
            for m in memories:
                line = f"- {m.content}"
                if used + len(line) > MEMORY_CHAR_BUDGET:
                    break
                lines.append(line)
                used += len(line)
            parts.append(f"[What I remember about this user]\n" + "\n".join(lines))
            log.info(f"Injected {len(lines)}/{len(memories)} memories for user {user_id} ({used} chars)")

        # Part 2: Semantically relevant past exchanges (only when query provided)
        if current_query:
            try:
                query_embeddings = await self._embedding_svc.embed_texts([current_query])
                vector_str = "[" + ",".join(str(v) for v in query_embeddings[0]) + "]"

                past_sql = text("""
                    SELECT
                        a_msg.content AS answer,
                        (SELECT u.content FROM messages u
                         WHERE u.conversation_id = a_msg.conversation_id
                           AND u.role = 'user'
                           AND u.created_at <= a_msg.created_at
                         ORDER BY u.created_at DESC
                         LIMIT 1) AS question,
                        1 - (a_msg.embedding <=> CAST(:embedding AS vector)) AS score
                    FROM messages a_msg
                    JOIN conversations c ON c.id = a_msg.conversation_id
                    WHERE c.user_id = :user_id
                      AND a_msg.embedding IS NOT NULL
                      AND a_msg.role = 'assistant'
                    ORDER BY a_msg.embedding <=> CAST(:embedding AS vector)
                    LIMIT 10
                """)
                # Use a savepoint so a SQL failure (e.g. pgvector unavailable) does not
                # abort the outer transaction — only this nested block is rolled back.
                async with db.begin_nested():
                    past_result = await db.execute(
                        past_sql, {"user_id": str(user_id), "embedding": vector_str}
                    )
                    past_rows = past_result.fetchall()

                # Deduplicate: skip answers that start identically (e.g. repeated
                # "I don't have access" responses), keep at most 3 unique exchanges.
                seen_prefixes: set[str] = set()
                unique_rows = []
                for row in past_rows:
                    prefix = row.answer[:80].strip()
                    if prefix in seen_prefixes:
                        continue
                    seen_prefixes.add(prefix)
                    unique_rows.append(row)
                    if len(unique_rows) == 3:
                        break

                log.info(
                    f"Past exchanges: {len(past_rows)} found, {len(unique_rows)} unique "
                    f"for user {user_id}. Scores: "
                    + ", ".join(f"{r.score:.2f}" for r in past_rows[:5])
                )

                # Only inject past exchanges with a meaningful (but not near-identical)
                # similarity score. Near-identical scores (> 0.88) mean the user is
                # re-asking the same question — injecting the old answer creates a
                # feedback loop that permanently enshrines wrong answers.
                quality_rows = [r for r in unique_rows if 0.55 < r.score < 0.88]
                log.info(
                    f"Past exchanges after quality filter: {len(quality_rows)}/{len(unique_rows)} kept "
                    f"(thresholds 0.55-0.88)"
                )

                if quality_rows:
                    lines = []
                    for row in quality_rows:
                        if row.question:
                            lines.append(f"- Q: {row.question[:200]}\n  A: {row.answer[:300]}")
                        else:
                            lines.append(f"- {row.answer[:300]}")
                    parts.append("[Relevant past exchanges]\n" + "\n".join(lines))
            except Exception as e:
                log.warning(f"Past exchange retrieval failed: {e}")

        if not parts:
            return ""
        result = "\n\n" + "\n\n".join(parts)
        log.info(f"Memory block injected for user {user_id}:\n{result}")
        return result


memory_extractor_service = MemoryExtractorService(embedding_service)
