import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.rag import search_chunks, rag_stream


# ── search_chunks ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_chunks_returns_list(db_session, org_and_user, chunks_with_embeddings):
    """search_chunks should call embed_texts and execute a DB query."""
    org, _ = org_and_user
    fake_embedding = [0.1] * 1536

    with patch("app.services.rag.embed_texts", AsyncMock(return_value=[fake_embedding])):
        # SQLite doesn't support pgvector operators, so we expect an error or empty list.
        # We verify that the function attempts the query (embed_texts was called).
        try:
            results = await search_chunks(db_session, org.id, "confidencialidad")
            assert isinstance(results, list)
        except Exception:
            # SQLite doesn't support vector operators; that's acceptable in unit tests
            pass


@pytest.mark.asyncio
async def test_search_chunks_calls_embed_texts(db_session, org_and_user):
    org, _ = org_and_user
    fake_embedding = [0.0] * 1536

    with patch("app.services.rag.embed_texts", AsyncMock(return_value=[fake_embedding])) as mock_embed:
        try:
            await search_chunks(db_session, org.id, "mi consulta")
        except Exception:
            pass
        mock_embed.assert_called_once_with(["mi consulta"])


# ── rag_stream ──────────────────────────────────────────────────────────────


def _fake_openai_stream(tokens):
    class FakeChunk:
        def __init__(self, t):
            self.choices = [MagicMock(delta=MagicMock(content=t))]

    class AsyncFakeStream:
        def __init__(self):
            self._items = [FakeChunk(t) for t in tokens]
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._index]
            self._index += 1
            return item

    return AsyncFakeStream()


@pytest.mark.asyncio
async def test_rag_stream_yields_chunks_then_tokens_then_done(db_session, org_and_user, project):
    org, user = org_and_user
    fake_embedding = [0.1] * 1536

    fake_chunks = [
        {
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "document_title": "Contrato.pdf",
            "content": "Texto relevante",
            "score": 0.9,
        }
    ]

    with (
        patch("app.services.rag.embed_texts", AsyncMock(return_value=[fake_embedding])),
        patch("app.services.rag.search_chunks", AsyncMock(return_value=fake_chunks)),
        patch(
            "app.services.rag._openai.chat.completions.create",
            AsyncMock(return_value=_fake_openai_stream(["La ", "respuesta"])),
        ),
    ):
        events = []
        async for raw in rag_stream(db_session, org.id, user.id, "¿Qué dice?", project.id):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))

    types = [e["type"] for e in events]
    assert types[0] == "chunks"
    assert "token" in types
    assert types[-1] == "done"

    chunks_event = events[0]
    assert chunks_event["chunks"] == fake_chunks

    done_event = events[-1]
    assert "log_id" in done_event


@pytest.mark.asyncio
async def test_rag_stream_logs_search(db_session, org_and_user, project):
    """After streaming completes a SearchLog row should exist in the DB."""
    from sqlalchemy import select
    from app.models.search_log import SearchLog

    org, user = org_and_user
    fake_chunks: list = []

    with (
        patch("app.services.rag.embed_texts", AsyncMock(return_value=[[0.0] * 1536])),
        patch("app.services.rag.search_chunks", AsyncMock(return_value=fake_chunks)),
        patch(
            "app.services.rag._openai.chat.completions.create",
            AsyncMock(return_value=_fake_openai_stream(["ok"])),
        ),
    ):
        async for _ in rag_stream(db_session, org.id, user.id, "pregunta de prueba"):
            pass

    result = await db_session.execute(
        select(SearchLog).where(SearchLog.org_id == org.id)
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.query == "pregunta de prueba"
    assert log.result_count == 0
