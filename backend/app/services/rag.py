import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings
from app.models.search_log import SearchLog
from app.services.embeddings import embed_texts
from app.services.reranker import rerank

log = logging.getLogger(__name__)
_openai = AsyncOpenAI(api_key=settings.openai_api_key)

SCORE_THRESHOLD = 0.35
TOP_K_VECTOR = 20
TOP_K_BM25 = 20
TOP_K_RERANK = 5
RRF_K = 60

_SYSTEM_PROMPT_BASE = (
    "You are an expert assistant that helps users find information in their organization's documents. "
    "Answer ONLY based on the provided fragments. Cite sources using the format [Source N]. "
    "If you cannot answer with the available information, say so clearly. "
    "Never invent data or assume information not present in the fragments. "
)

_LANG_INSTRUCTIONS = {
    "en": "IMPORTANT: Always respond in English, regardless of the language of the documents.",
    "es": "IMPORTANTE: Responde siempre en español, independientemente del idioma de los documentos.",
}

_SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE + _LANG_INSTRUCTIONS["en"]


def _make_system_prompt(language: str) -> str:
    instruction = _LANG_INSTRUCTIONS.get(language, _LANG_INSTRUCTIONS["en"])
    return _SYSTEM_PROMPT_BASE + instruction

_QUERY_REWRITE_PROMPT = (
    "You are a search query optimizer. Given the user's original query, return an improved "
    "version that is better suited for semantic and keyword search over legal documents. "
    "Rules: keep the same language; expand abbreviations if any; only add synonyms if clearly "
    "useful; if the query is already good return it unchanged. "
    "Reply with the improved query only — no explanation.\n\n"
    "Original query: {query}"
)


async def _rewrite_query(query: str) -> str:
    """Rewrites short queries via GPT-4o-mini. Long queries (≥5 words) pass through unchanged."""
    if len(query.split()) >= 5:
        return query
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": _QUERY_REWRITE_PROMPT.format(query=query)}],
            temperature=0.1,
            max_tokens=100,
        )
        rewritten = response.choices[0].message.content.strip()
        if rewritten and rewritten != query:
            log.debug("Query rewritten: '%s' → '%s'", query, rewritten)
        return rewritten or query
    except Exception as e:
        log.warning("Query rewrite failed: %s", e)
        return query


async def _embed_query(query: str) -> list[float]:
    vectors = await embed_texts([query])
    return vectors[0]


async def _vector_search(
    db: AsyncSession,
    org_id: uuid.UUID,
    query_vector: list[float],
    project_id: uuid.UUID | None = None,
    limit: int = TOP_K_VECTOR,
) -> list[dict]:
    """Cosine similarity search using pgvector."""
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    scope = "AND c.project_id = CAST(:project_id AS uuid)" if project_id else ""

    sql = text(f"""
        SELECT
            c.id,
            c.content,
            c.document_id,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS score,
            d.title,
            d.source,
            d.source_url
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.org_id = CAST(:org_id AS uuid)
          {scope}
          AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    params: dict = {"embedding": vector_str, "org_id": str(org_id), "limit": limit}
    if project_id:
        params["project_id"] = str(project_id)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "document_id": row.document_id,
            "score": float(row.score),
            "title": row.title,
            "source": row.source,
            "source_url": row.source_url,
            "retrieval": "vector",
        }
        for row in rows
        if float(row.score) >= SCORE_THRESHOLD
    ]


async def _bm25_search(
    db: AsyncSession,
    org_id: uuid.UUID,
    query: str,
    project_id: uuid.UUID | None = None,
    limit: int = TOP_K_BM25,
) -> list[dict]:
    """Full-text search using the stored content_tsv column (Spanish + English configs)."""
    scope = "AND c.project_id = CAST(:project_id AS uuid)" if project_id else ""

    sql = text(f"""
        SELECT
            c.id,
            c.content,
            c.document_id,
            ts_rank_cd(c.content_tsv,
                websearch_to_tsquery('spanish', :query) ||
                websearch_to_tsquery('english', :query)
            ) AS score,
            d.title,
            d.source,
            d.source_url
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.org_id = CAST(:org_id AS uuid)
          {scope}
          AND c.content_tsv @@ (
                websearch_to_tsquery('spanish', :query) ||
                websearch_to_tsquery('english', :query)
          )
        ORDER BY score DESC
        LIMIT :limit
    """)

    params: dict = {"query": query, "org_id": str(org_id), "limit": limit}
    if project_id:
        params["project_id"] = str(project_id)

    try:
        result = await db.execute(sql, params)
        rows = result.fetchall()
        return [
            {
                "chunk_id": str(row.id),
                "content": row.content,
                "document_id": row.document_id,
                "score": float(row.score),
                "title": row.title,
                "source": row.source,
                "source_url": row.source_url,
                "retrieval": "bm25",
            }
            for row in rows
        ]
    except Exception as e:
        log.warning("BM25 search failed: %s", e)
        return []


def _reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    """Merges two ranked lists with RRF. Chunks appearing in both lists rank highest."""
    scores: dict[str, float] = {}
    chunks_by_id: dict[str, dict] = {}

    for rank, chunk in enumerate(vector_results, 1):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunks_by_id[cid] = chunk

    for rank, chunk in enumerate(bm25_results, 1):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunks_by_id[cid] = chunk

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    result = []
    for cid in sorted_ids:
        chunk = chunks_by_id[cid].copy()
        chunk["rrf_score"] = scores[cid]
        result.append(chunk)
    return result


# Alias for chat API (test patches app.api.chat._similarity_search)
_similarity_search = _vector_search
# Public export for chat API
SYSTEM_PROMPT = _SYSTEM_PROMPT


def _build_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[Source {i}]\n{c['content']}" for i, c in enumerate(chunks, 1)
    )


async def stream_rag_response(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    project_id: uuid.UUID | None = None,
    language: str = "en",
) -> AsyncGenerator[str, None]:
    """
    Full hybrid RAG pipeline as an async SSE generator.

    Steps:
      1. Rewrite short/vague queries (GPT-4o-mini)
      2. Embed rewritten query
      3. Vector search + BM25 in parallel
      4. RRF fusion
      5. Cohere reranker (graceful fallback to RRF order)
      6. Stream GPT-4o answer
      7. Emit sources event
      8. Emit done event + persist SearchLog
    """
    start = time.monotonic()

    log_entry = SearchLog(
        org_id=org_id,
        user_id=user_id,
        project_id=project_id,
        query=query,
    )
    db.add(log_entry)
    await db.flush()

    try:
        # 1. Query rewriting
        rewritten = await _rewrite_query(query)

        # 2. Embed
        query_vector = await _embed_query(rewritten)

        # 3. Parallel retrieval
        vector_results, bm25_results = await asyncio.gather(
            _vector_search(db, org_id, query_vector, project_id),
            _bm25_search(db, org_id, rewritten, project_id),
        )

        # 4. RRF fusion
        fused = _reciprocal_rank_fusion(vector_results, bm25_results)

        if not fused:
            no_results_msg = (
                "No encontré información relevante en los documentos disponibles."
                if language == "es"
                else "I couldn't find relevant information in the available documents."
            )
            yield f"data: {json.dumps({'type': 'token', 'content': no_results_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            log_entry.result_count = 0
            log_entry.latency_ms = int((time.monotonic() - start) * 1000)
            await db.flush()
            return

        # 5. Rerank
        top_chunks = await rerank(query, fused[:50], top_n=TOP_K_RERANK)

        # 6. Stream GPT-4o
        context = _build_context(top_chunks)
        stream = await _openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _make_system_prompt(language)},
                {"role": "user", "content": f"{context}\n\n{query}"},
            ],
            stream=True,
            temperature=0.2,
            max_tokens=1024,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

        # 7. Sources
        sources = [
            {
                "document_id": str(c["document_id"]),
                "title": c["title"],
                "source": c["source"],
                "source_url": c["source_url"],
                "score": round(c.get("rerank_score", c.get("rrf_score", 0.0)), 3),
                "excerpt": c["content"][:200],
            }
            for c in top_chunks
        ]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # 8. Persist log
        log_entry.result_count = len(top_chunks)
        log_entry.cited_chunk_ids = [c["chunk_id"] for c in top_chunks]
        log_entry.latency_ms = int((time.monotonic() - start) * 1000)
        await db.commit()

    except Exception as e:
        log.exception("RAG pipeline error")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        raise
