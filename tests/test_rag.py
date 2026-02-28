"""
Tests for the hybrid RAG pipeline (stream_rag_response).
Supersedes PRD-3 tests; all IO is mocked — no real OpenAI/DB calls.
"""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.rag import rag_service
from app.services.reranker import reranker_service


def _fake_stream(*tokens):
    """Returns an async generator that yields fake OpenAI stream chunks."""
    async def _gen():
        for t in tokens:
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content=t))]
            yield chunk
    return _gen()


def _fake_chunk(content: str = "Texto relevante") -> dict:
    return {
        "chunk_id": str(uuid.uuid4()),
        "document_id": uuid.uuid4(),
        "content": content,
        "score": 0.9,
        "title": "Contrato.pdf",
        "source": "upload",
        "source_url": None,
        "retrieval": "vector",
        "rrf_score": 0.03,
    }


# ---------------------------------------------------------------------------
# SSE event format
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_emits_token_events(db_session, org_and_user, project):
    org, user = org_and_user
    chunks = [_fake_chunk()]

    with patch.object(rag_service, "_embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch.object(rag_service, "_vector_search", new_callable=AsyncMock, return_value=chunks), \
         patch.object(rag_service, "_bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_rewrite_query", new_callable=AsyncMock, return_value="q"), \
         patch.object(reranker_service, "rerank", new_callable=AsyncMock, return_value=chunks), \
         patch.object(rag_service, "_openai") as mock_openai:

        mock_openai.chat.completions.create = AsyncMock(
            return_value=_fake_stream("La ", "respuesta")
        )

        events = []
        async for raw in rag_service.stream_rag_response(db_session, org.id, user.id, "¿Qué dice?", project.id):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))

    types = [e["type"] for e in events]
    assert "token" in types
    assert types[-1] == "done"

    token_events = [e for e in events if e["type"] == "token"]
    assert all("content" in e for e in token_events)


@pytest.mark.asyncio
async def test_stream_emits_sources_event(db_session, org_and_user):
    org, user = org_and_user
    chunks = [_fake_chunk(), _fake_chunk("Segundo fragmento")]

    with patch.object(rag_service, "_embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch.object(rag_service, "_vector_search", new_callable=AsyncMock, return_value=chunks), \
         patch.object(rag_service, "_bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_rewrite_query", new_callable=AsyncMock, return_value="q"), \
         patch.object(reranker_service, "rerank", new_callable=AsyncMock, return_value=chunks), \
         patch.object(rag_service, "_openai") as mock_openai:

        mock_openai.chat.completions.create = AsyncMock(return_value=_fake_stream("ok"))

        events = []
        async for raw in rag_service.stream_rag_response(db_session, org.id, user.id, "q"):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))

    sources_events = [e for e in events if e["type"] == "sources"]
    assert len(sources_events) == 1
    assert isinstance(sources_events[0]["sources"], list)
    assert len(sources_events[0]["sources"]) == 2


@pytest.mark.asyncio
async def test_stream_done_is_last_event(db_session, org_and_user):
    org, user = org_and_user

    with patch.object(rag_service, "_embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch.object(rag_service, "_vector_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_rewrite_query", new_callable=AsyncMock, return_value="q"):

        events = []
        async for raw in rag_service.stream_rag_response(db_session, org.id, user.id, "q"):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))

    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Search log persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_creates_search_log(db_session, org_and_user, project):
    from sqlalchemy import select
    from app.models.search_log import SearchLog

    org, user = org_and_user
    chunks = [_fake_chunk()]

    with patch.object(rag_service, "_embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch.object(rag_service, "_vector_search", new_callable=AsyncMock, return_value=chunks), \
         patch.object(rag_service, "_bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_rewrite_query", new_callable=AsyncMock, return_value="q"), \
         patch.object(reranker_service, "rerank", new_callable=AsyncMock, return_value=chunks), \
         patch.object(rag_service, "_openai") as mock_openai:

        mock_openai.chat.completions.create = AsyncMock(return_value=_fake_stream("ok"))

        async for _ in rag_service.stream_rag_response(db_session, org.id, user.id, "pregunta de prueba"):
            pass

    result = await db_session.execute(
        select(SearchLog).where(SearchLog.org_id == org.id)
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.query == "pregunta de prueba"
    assert log.result_count == 1
    assert log.latency_ms is not None


@pytest.mark.asyncio
async def test_stream_log_zero_results_when_no_chunks(db_session, org_and_user):
    from sqlalchemy import select
    from app.models.search_log import SearchLog

    org, user = org_and_user

    with patch.object(rag_service, "_embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch.object(rag_service, "_vector_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(rag_service, "_rewrite_query", new_callable=AsyncMock, return_value="q"):

        async for _ in rag_service.stream_rag_response(db_session, org.id, user.id, "pregunta vacía"):
            pass

    result = await db_session.execute(
        select(SearchLog).where(SearchLog.org_id == org.id)
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.result_count == 0
