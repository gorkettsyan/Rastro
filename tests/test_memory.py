import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_memories_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/memory", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_memory_manual(client: AsyncClient, auth_headers):
    with patch("app.api.memory.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        resp = await client.post(
            "/api/v1/memory",
            json={"content": "Prefiero respuestas en español"},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["source"] == "manual"
    assert resp.json()["content"] == "Prefiero respuestas en español"


@pytest.mark.asyncio
async def test_update_memory(client: AsyncClient, auth_headers):
    with patch("app.api.memory.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        create_resp = await client.post(
            "/api/v1/memory",
            json={"content": "Original"},
            headers=auth_headers,
        )
        memory_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/memory/{memory_id}",
            json={"content": "Actualizado"},
            headers=auth_headers,
        )
    assert update_resp.status_code == 200
    assert update_resp.json()["content"] == "Actualizado"


@pytest.mark.asyncio
async def test_delete_memory(client: AsyncClient, auth_headers):
    with patch("app.api.memory.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        create_resp = await client.post(
            "/api/v1/memory",
            json={"content": "To delete"},
            headers=auth_headers,
        )
        memory_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/memory/{memory_id}", headers=auth_headers)
    assert resp.status_code == 204

    list_resp = await client.get("/api/v1/memory", headers=auth_headers)
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_all_memories(client: AsyncClient, auth_headers):
    with patch("app.api.memory.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        for i in range(3):
            await client.post("/api/v1/memory", json={"content": f"Memory {i}"}, headers=auth_headers)

    resp = await client.delete("/api/v1/memory", headers=auth_headers)
    assert resp.status_code == 204

    list_resp = await client.get("/api/v1/memory", headers=auth_headers)
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_memories_isolated_per_user(client: AsyncClient, db_session, org_and_user):
    from app.models.memory import Memory
    from app.models.user import User
    from app.security import create_jwt

    org, user_a = org_and_user
    user_b = User(org_id=org.id, email="b@mem.es", google_id="gmb")
    db_session.add(user_b)
    await db_session.flush()

    db_session.add(Memory(user_id=user_b.id, org_id=org.id, content="Private memory", source="manual"))
    await db_session.flush()

    headers_a = {"Authorization": f"Bearer {create_jwt(str(user_a.id))}"}
    resp = await client.get("/api/v1/memory", headers=headers_a)
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_memory_extraction_deduplicates(db_session, org_and_user):
    from app.services.memory_extractor import extract_and_store_memories
    from app.models.memory import Memory
    from app.models.conversation import Conversation
    from app.models.message import Message
    from sqlalchemy import select

    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(conversation_id=conv.id, role="user", content="Trabajo en derecho mercantil", sources=[])
    db_session.add(msg)
    await db_session.flush()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(
        message=MagicMock(content='{"memories": ["Trabaja en derecho mercantil"]}')
    )]

    with patch("app.services.memory_extractor._openai") as mock_openai, \
         patch("app.services.memory_extractor.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        count1 = await extract_and_store_memories(db_session, user.id, org.id, conv.id)
        count2 = await extract_and_store_memories(db_session, user.id, org.id, conv.id)

    result = await db_session.execute(select(Memory).where(Memory.user_id == user.id))
    total = len(result.scalars().all())
    assert total == count1  # no duplicates
    assert count2 == 0


@pytest.mark.asyncio
async def test_memory_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/memory")
    assert resp.status_code == 403
