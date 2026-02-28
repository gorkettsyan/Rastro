import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.models.search_log import SearchLog
from app.services.rag import rag_service
from sqlalchemy import select


# ── /search/history ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_history_empty(client: AsyncClient, auth_headers, org_and_user):
    resp = await client.get("/api/v1/search/history", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


@pytest.mark.asyncio
async def test_search_history_returns_logs(
    client: AsyncClient, auth_headers, db_session, org_and_user
):
    org, user = org_and_user
    log = SearchLog(
        org_id=org.id,
        user_id=user.id,
        query="¿Qué dice la cláusula 3?",
        result_count=2,
        cited_chunk_ids=[],
    )
    db_session.add(log)
    await db_session.flush()

    resp = await client.get("/api/v1/search/history", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["query"] == "¿Qué dice la cláusula 3?"
    assert items[0]["result_count"] == 2


@pytest.mark.asyncio
async def test_search_history_filtered_by_project(
    client: AsyncClient, auth_headers, db_session, org_and_user, project
):
    org, user = org_and_user
    # Log belonging to project
    log_in = SearchLog(
        org_id=org.id,
        user_id=user.id,
        project_id=project.id,
        query="consulta del proyecto",
        result_count=1,
        cited_chunk_ids=[],
    )
    # Log without project
    log_out = SearchLog(
        org_id=org.id,
        user_id=user.id,
        query="consulta global",
        result_count=0,
        cited_chunk_ids=[],
    )
    db_session.add(log_in)
    db_session.add(log_out)
    await db_session.flush()

    resp = await client.get(
        "/api/v1/search/history",
        params={"project_id": str(project.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["query"] == "consulta del proyecto"


@pytest.mark.asyncio
async def test_search_history_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/search/history")
    assert resp.status_code == 403


# ── /search/stream ─────────────────────────────────────────────────────────


def _make_openai_stream(tokens: list[str]):
    """Build a fake async iterator that looks like an OpenAI streaming response."""

    class FakeChunk:
        def __init__(self, token):
            self.choices = [MagicMock(delta=MagicMock(content=token))]

    class FakeStream:
        def __init__(self):
            self._tokens = tokens
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._tokens):
                raise StopAsyncIteration
            token = self._tokens[self._index]
            self._index += 1
            return FakeChunk(token)

    return FakeStream()


@pytest.mark.asyncio
async def test_search_stream_returns_sse_events(
    client: AsyncClient, auth_headers, db_session, org_and_user, chunks_with_embeddings
):
    org, user = org_and_user

    fake_chunks = [
        {
            "chunk_id": str(chunks_with_embeddings[0].id),
            "document_id": str(chunks_with_embeddings[0].document_id),
            "document_title": "Contrato.pdf",
            "content": "Cláusula de confidencialidad",
            "score": 0.92,
        }
    ]

    with patch.object(rag_service, "stream_rag_response") as mock_rag_stream:
        async def _gen(*args, **kwargs):
            yield f"data: {json.dumps({'type': 'chunks', 'chunks': fake_chunks})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'token': 'Hola'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'log_id': 'test-log-id'})}\n\n"

        mock_rag_stream.side_effect = _gen

        resp = await client.get(
            "/api/v1/search/stream",
            params={"q": "¿Qué dice sobre confidencialidad?"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    lines = [l for l in resp.text.split("\n") if l.startswith("data: ")]
    events = [json.loads(l[6:]) for l in lines]

    assert events[0]["type"] == "chunks"
    assert events[1]["type"] == "token"
    assert events[2]["type"] == "done"


@pytest.mark.asyncio
async def test_search_stream_requires_query_param(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/search/stream", headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_stream_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/search/stream", params={"q": "test"})
    assert resp.status_code == 403
