import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _reciprocal_rank_fusion
# ---------------------------------------------------------------------------

def _make_chunk(cid: str, score: float = 0.9, retrieval: str = "vector") -> dict:
    return {
        "chunk_id": cid,
        "content": f"Content {cid}",
        "document_id": uuid.uuid4(),
        "score": score,
        "title": f"Doc {cid}",
        "source": "upload",
        "source_url": None,
        "retrieval": retrieval,
    }


def test_rrf_boosts_documents_in_both_lists():
    from app.services.rag import _reciprocal_rank_fusion

    id_a, id_b, id_c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    vector_results = [_make_chunk(id_a), _make_chunk(id_b, 0.8)]
    bm25_results = [_make_chunk(id_b, 0.7, "bm25"), _make_chunk(id_c, 0.5, "bm25")]

    fused = _reciprocal_rank_fusion(vector_results, bm25_results)

    # id_b appears in both lists — must rank first
    assert fused[0]["chunk_id"] == id_b


def test_rrf_handles_empty_bm25():
    from app.services.rag import _reciprocal_rank_fusion

    id_a = str(uuid.uuid4())
    fused = _reciprocal_rank_fusion([_make_chunk(id_a)], [])
    assert len(fused) == 1
    assert fused[0]["chunk_id"] == id_a


def test_rrf_handles_empty_vector():
    from app.services.rag import _reciprocal_rank_fusion

    id_a = str(uuid.uuid4())
    fused = _reciprocal_rank_fusion([], [_make_chunk(id_a, retrieval="bm25")])
    assert len(fused) == 1
    assert fused[0]["chunk_id"] == id_a


def test_rrf_attaches_rrf_score():
    from app.services.rag import _reciprocal_rank_fusion

    id_a = str(uuid.uuid4())
    fused = _reciprocal_rank_fusion([_make_chunk(id_a)], [])
    assert "rrf_score" in fused[0]
    assert fused[0]["rrf_score"] > 0


# ---------------------------------------------------------------------------
# _rewrite_query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rewrite_skips_long_queries():
    """Queries with >= 5 words must bypass the LLM entirely."""
    from app.services.rag import _rewrite_query

    long_query = "¿Cuáles son los términos de rescisión del contrato?"
    result = await _rewrite_query(long_query)
    assert result == long_query


@pytest.mark.asyncio
async def test_query_rewrite_short_query():
    from app.services.rag import _rewrite_query

    with patch("app.services.rag._openai") as mock_openai:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="rescisión cláusula contrato"))
        ]
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await _rewrite_query("rescisión")
        assert result == "rescisión cláusula contrato"


@pytest.mark.asyncio
async def test_query_rewrite_fallback_on_error():
    from app.services.rag import _rewrite_query

    with patch("app.services.rag._openai") as mock_openai:
        mock_openai.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
        result = await _rewrite_query("contrato")
        assert result == "contrato"


# ---------------------------------------------------------------------------
# reranker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reranker_fallback_without_api_key():
    from app.services.reranker import rerank

    chunks = [_make_chunk(str(uuid.uuid4())) for _ in range(10)]
    with patch("app.services.reranker.settings") as mock_settings:
        mock_settings.cohere_api_key = None
        result = await rerank("test", chunks, top_n=5)

    assert len(result) == 5
    assert result == chunks[:5]


@pytest.mark.asyncio
async def test_reranker_reorders_by_relevance():
    from app.services.reranker import rerank

    chunks = [_make_chunk(str(uuid.uuid4())) for _ in range(5)]

    mock_result = MagicMock()
    mock_result.results = [
        MagicMock(index=2, relevance_score=0.95),
        MagicMock(index=0, relevance_score=0.80),
        MagicMock(index=4, relevance_score=0.70),
    ]

    with patch("app.services.reranker.settings") as mock_settings, \
         patch("cohere.AsyncClient") as mock_cohere_cls:
        mock_settings.cohere_api_key = "test-key"
        mock_cohere_cls.return_value.rerank = AsyncMock(return_value=mock_result)
        result = await rerank("test", chunks, top_n=3)

    assert len(result) == 3
    assert result[0]["chunk_id"] == chunks[2]["chunk_id"]
    assert result[0]["rerank_score"] == 0.95


@pytest.mark.asyncio
async def test_reranker_fallback_on_cohere_error():
    from app.services.reranker import rerank

    chunks = [_make_chunk(str(uuid.uuid4())) for _ in range(5)]
    with patch("app.services.reranker.settings") as mock_settings, \
         patch("cohere.AsyncClient") as mock_cohere_cls:
        mock_settings.cohere_api_key = "test-key"
        mock_cohere_cls.return_value.rerank = AsyncMock(side_effect=Exception("api error"))
        result = await rerank("test", chunks, top_n=3)

    assert len(result) == 3
    assert result == chunks[:3]


# ---------------------------------------------------------------------------
# stream_rag_response (integration-style, all IO mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hybrid_search_calls_both_retrievers(db_session, org_and_user):
    from app.services.rag import stream_rag_response

    org, user = org_and_user

    with patch("app.services.rag._embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch("app.services.rag._vector_search", new_callable=AsyncMock, return_value=[]) as mock_v, \
         patch("app.services.rag._bm25_search", new_callable=AsyncMock, return_value=[]) as mock_b, \
         patch("app.services.rag._rewrite_query", new_callable=AsyncMock, return_value="query"), \
         patch("app.services.rag.rerank", new_callable=AsyncMock, return_value=[]):

        async for _ in stream_rag_response(db_session, org.id, user.id, "query"):
            pass

        assert mock_v.called
        assert mock_b.called


@pytest.mark.asyncio
async def test_no_results_returns_graceful_message(db_session, org_and_user):
    from app.services.rag import stream_rag_response

    org, user = org_and_user

    with patch("app.services.rag._embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch("app.services.rag._vector_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.rag._bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.rag._rewrite_query", new_callable=AsyncMock, return_value="q"):

        events = []
        async for event in stream_rag_response(db_session, org.id, user.id, "q"):
            events.append(event)

    parsed = [json.loads(e.replace("data: ", "").strip()) for e in events if e.strip()]
    token_events = [e for e in parsed if e["type"] == "token"]
    assert any("No encontré" in e["content"] for e in token_events)


@pytest.mark.asyncio
async def test_sse_done_event_present(db_session, org_and_user):
    from app.services.rag import stream_rag_response

    org, user = org_and_user

    with patch("app.services.rag._embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch("app.services.rag._vector_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.rag._bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.rag._rewrite_query", new_callable=AsyncMock, return_value="q"):

        events = []
        async for event in stream_rag_response(db_session, org.id, user.id, "q"):
            events.append(event)

    parsed = [json.loads(e.replace("data: ", "").strip()) for e in events if e.strip()]
    assert any(e["type"] == "done" for e in parsed)


@pytest.mark.asyncio
async def test_sources_event_present_when_results(db_session, org_and_user):
    from app.services.rag import stream_rag_response

    org, user = org_and_user
    doc_id = uuid.uuid4()
    fake_chunks = [
        {**_make_chunk(str(uuid.uuid4())), "document_id": doc_id, "rrf_score": 0.03}
        for _ in range(3)
    ]

    stream_chunk = MagicMock()
    stream_chunk.choices = [MagicMock(delta=MagicMock(content="answer"))]

    async def _fake_stream():
        yield stream_chunk

    with patch("app.services.rag._embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch("app.services.rag._vector_search", new_callable=AsyncMock, return_value=fake_chunks), \
         patch("app.services.rag._bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.rag._rewrite_query", new_callable=AsyncMock, return_value="q"), \
         patch("app.services.rag.rerank", new_callable=AsyncMock, return_value=fake_chunks[:2]), \
         patch("app.services.rag._openai") as mock_openai:

        mock_openai.chat.completions.create = AsyncMock(return_value=_fake_stream())

        events = []
        async for event in stream_rag_response(db_session, org.id, user.id, "q"):
            events.append(event)

    parsed = [json.loads(e.replace("data: ", "").strip()) for e in events if e.strip()]
    sources_events = [e for e in parsed if e["type"] == "sources"]
    assert len(sources_events) == 1
    assert isinstance(sources_events[0]["sources"], list)
