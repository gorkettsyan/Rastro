import json
import logging
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.config import settings
from app.models.memory import Memory
from app.models.message import Message
from app.services.embeddings import embed_texts

log = logging.getLogger(__name__)
_openai = AsyncOpenAI(api_key=settings.openai_api_key)

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


async def extract_and_store_memories(
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
        response = await _openai.chat.completions.create(
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

    embeddings = await embed_texts(candidates)

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
    db: AsyncSession, user_id, current_query: str | None = None
) -> str:
    """
    Returns formatted memory block for system prompt injection.
    Part 1: extracted facts about the user (always included).
    Part 2: semantically relevant past exchanges (when current_query provided).
    Returns empty string if no data found.
    """
    parts = []

    if current_query:
        try:
            query_embeddings = await embed_texts([current_query])
            vector_str = "[" + ",".join(str(v) for v in query_embeddings[0]) + "]"

            # Fetch only memories that are semantically relevant to the current query.
            # This prevents unrelated memories from being combined by the model.
            mem_sql = text("""
                SELECT content,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM memories
                WHERE user_id = :user_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT 5
            """)
            async with db.begin_nested():
                mem_result = await db.execute(
                    mem_sql, {"user_id": str(user_id), "embedding": vector_str}
                )
                mem_rows = mem_result.fetchall()

            # Only include memories with meaningful similarity (score > 0.5)
            relevant_memories = [r for r in mem_rows if r.score > 0.5]

            log.info(
                f"Memories: {len(mem_rows)} candidates, {len(relevant_memories)} relevant "
                f"for user {user_id}. Scores: "
                + ", ".join(f"{r.score:.2f}" for r in mem_rows[:5])
            )

            if relevant_memories:
                lines = "\n".join(f"- {r.content}" for r in relevant_memories)
                parts.append(f"[What I remember about this user]\n{lines}")

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
                f"(thresholds 0.55–0.88)"
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
            log.warning(f"Memory/exchange retrieval failed: {e}")  # pgvector unavailable or embed failed
            # Fallback: inject most recent memories without semantic filtering
            fallback = await db.execute(
                select(Memory)
                .where(Memory.user_id == user_id)
                .order_by(Memory.created_at.desc())
                .limit(10)
            )
            memories = fallback.scalars().all()
            if memories:
                lines = "\n".join(f"- {m.content}" for m in memories)
                parts.append(f"[What I remember about this user]\n{lines}")
    else:
        # No query available — inject most recent memories without semantic filtering
        fallback = await db.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(10)
        )
        memories = fallback.scalars().all()
        if memories:
            lines = "\n".join(f"- {m.content}" for m in memories)
            parts.append(f"[What I remember about this user]\n{lines}")

    if not parts:
        return ""
    result = "\n\n" + "\n\n".join(parts)
    log.info(f"Memory block injected for user {user_id}:\n{result}")
    return result
