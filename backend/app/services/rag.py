import json
import uuid
from typing import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.config import settings
from app.models.search_log import SearchLog
from app.services.embeddings import embed_texts

_openai = AsyncOpenAI(api_key=settings.openai_api_key)

_SYSTEM_PROMPTS: dict[str, str] = {
    "es": (
        "Eres un asistente legal experto. Responde basándote ÚNICAMENTE en los fragmentos "
        "de documentos proporcionados. Si la información no está en los fragmentos, indícalo "
        "claramente. Cita siempre los documentos de origen usando [Doc: nombre_documento]."
    ),
    "en": (
        "You are an expert legal assistant. Answer based ONLY on the provided document excerpts. "
        "If the information is not in the excerpts, clearly say so. "
        "Always cite source documents using [Doc: document_name]."
    ),
}

_LABELS: dict[str, dict[str, str]] = {
    "es": {"doc": "Documento", "no_context": "(sin contexto)", "question": "Pregunta"},
    "en": {"doc": "Document",  "no_context": "(no context)",   "question": "Question"},
}

def _system_prompt(lang: str) -> str:
    return _SYSTEM_PROMPTS.get(lang, _SYSTEM_PROMPTS["en"])

def _labels(lang: str) -> dict[str, str]:
    return _LABELS.get(lang, _LABELS["en"])


async def search_chunks(
    db: AsyncSession,
    org_id: uuid.UUID,
    query: str,
    project_id: uuid.UUID | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Embed query and retrieve nearest chunks by cosine similarity."""
    embeddings = await embed_texts([query])
    query_embedding = embeddings[0]
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    if project_id:
        sql = text("""
            SELECT c.id, c.document_id, c.content,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS score,
                   d.title AS doc_title
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.org_id = CAST(:org_id AS uuid)
              AND c.project_id = CAST(:project_id AS uuid)
              AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "org_id": str(org_id),
            "project_id": str(project_id),
            "top_k": top_k,
        })
    else:
        sql = text("""
            SELECT c.id, c.document_id, c.content,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS score,
                   d.title AS doc_title
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.org_id = CAST(:org_id AS uuid)
              AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "org_id": str(org_id),
            "top_k": top_k,
        })

    return [
        {
            "chunk_id": str(row.id),
            "document_id": str(row.document_id),
            "document_title": row.doc_title,
            "content": row.content,
            "score": float(row.score),
        }
        for row in result.fetchall()
    ]


async def rag_stream(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    project_id: uuid.UUID | None = None,
    top_k: int = 5,
    lang: str = "es",
) -> AsyncGenerator[str, None]:
    """Yield SSE events: chunks → tokens → done."""
    # 1. Retrieve relevant chunks
    chunks = await search_chunks(db, org_id, query, project_id, top_k)

    # 2. Send retrieved chunks as first event so the UI can render citations immediately
    yield f"data: {json.dumps({'type': 'chunks', 'chunks': chunks})}\n\n"

    # 3. Build context string for the model
    lbl = _labels(lang)
    context_parts = [
        f"[{i}] {lbl['doc']}: {c['document_title']}\n{c['content']}"
        for i, c in enumerate(chunks, 1)
    ]
    context = "\n\n---\n\n".join(context_parts) if context_parts else lbl["no_context"]

    # 4. Stream GPT-4o completion
    stream = await _openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _system_prompt(lang)},
            {"role": "user", "content": f"{lbl['doc']}s:\n{context}\n\n{lbl['question']}: {query}"},
        ],
        stream=True,
        temperature=0.2,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield f"data: {json.dumps({'type': 'token', 'token': delta})}\n\n"

    # 5. Persist search log
    log = SearchLog(
        org_id=org_id,
        user_id=user_id,
        project_id=project_id,
        query=query,
        result_count=len(chunks),
        cited_chunk_ids=[c["chunk_id"] for c in chunks],
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    yield f"data: {json.dumps({'type': 'done', 'log_id': str(log.id)})}\n\n"
