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

EXTRACTION_PROMPT = """Analiza esta conversación y extrae hechos concretos y útiles sobre el usuario.
Solo incluye información factual y duradera (preferencias, área de trabajo, contexto profesional).
No incluyas el contenido de los documentos, solo información sobre el propio usuario.

Devuelve ÚNICAMENTE un array JSON de strings. Si no hay nada que recordar, devuelve [].

Ejemplos de memorias válidas:
- "Trabaja principalmente en derecho mercantil"
- "Sus clientes suelen ser pymes españolas"
- "Prefiere respuestas en español y concisas"
- "El despacho tiene sede en Madrid"

Ejemplos de memorias NO válidas (no incluir):
- Contenido específico de documentos o contratos
- Información sobre terceros (clientes, contrapartes)
- Preguntas puntuales sin contexto duradero"""

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


async def get_memories_for_prompt(db: AsyncSession, user_id) -> str:
    """
    Returns formatted memory block for system prompt injection.
    Returns empty string if no memories.
    """
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(Memory.created_at.desc())
        .limit(20)
    )
    memories = result.scalars().all()
    if not memories:
        return ""

    lines = "\n".join(f"- {m.content}" for m in memories)
    return f"\n\n[What I remember about this user]\n{lines}"
