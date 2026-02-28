import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient

from app.services.rag import rag_service
from app.services.memory_extractor import memory_extractor_service
from app.worker.queue import queue_service


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/chat",
        json={"first_message": "¿Qué dice el contrato?"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "¿Qué dice" in data["title"]


@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/chat", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_send_message_streams(client: AsyncClient, auth_headers, db_session, org_and_user):
    from app.models.conversation import Conversation
    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test")
    db_session.add(conv)
    await db_session.flush()

    mock_stream = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock(delta=MagicMock(content="Hola"))]

    async def _aiter():
        yield mock_chunk

    mock_stream.__aiter__ = lambda self: _aiter()

    with patch("app.api.chat._openai") as mock_openai, \
         patch.object(rag_service, "_embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch.object(rag_service, "_vector_search", new_callable=AsyncMock, return_value=[]), \
         patch.object(memory_extractor_service, "get_memories_for_prompt", new_callable=AsyncMock, return_value=""), \
         patch.object(queue_service, "enqueue"):
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_stream)

        resp = await client.post(
            f"/api/v1/chat/{conv.id}/messages",
            json={"message": "Hola"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_get_conversation_messages(client: AsyncClient, auth_headers, db_session, org_and_user):
    from app.models.conversation import Conversation
    from app.models.message import Message

    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test conv")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(conversation_id=conv.id, role="user", content="Pregunta", sources=[])
    db_session.add(msg)
    await db_session.flush()

    resp = await client.get(f"/api/v1/chat/{conv.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 1


@pytest.mark.asyncio
async def test_conversation_isolated_per_user(client: AsyncClient, db_session, org_and_user):
    from app.models.conversation import Conversation
    from app.models.user import User
    from app.security import create_jwt

    org, user_a = org_and_user
    user_b = User(org_id=org.id, email="b@test.es", google_id="gb")
    db_session.add(user_b)
    await db_session.flush()

    conv_b = Conversation(org_id=org.id, user_id=user_b.id, title="Private conv")
    db_session.add(conv_b)
    await db_session.flush()

    headers_a = {"Authorization": f"Bearer {create_jwt(str(user_a.id))}"}
    resp = await client.get(f"/api/v1/chat/{conv_b.id}", headers=headers_a)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient, auth_headers, db_session, org_and_user):
    from app.models.conversation import Conversation
    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="To delete")
    db_session.add(conv)
    await db_session.flush()

    resp = await client.delete(f"/api/v1/chat/{conv.id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/chat")
    assert resp.status_code == 403
