import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_embed_message_handler_embeds_new_message(db_session, org_and_user):
    from app.worker.handlers.message_embedder import handle_embed_message
    from app.models.conversation import Conversation
    from app.models.message import Message
    from sqlalchemy import select

    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(conversation_id=conv.id, role="assistant", content="This is an answer", sources=[])
    db_session.add(msg)
    await db_session.flush()

    with patch("app.worker.handlers.message_embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.5] * 1536]):
        await handle_embed_message({"message_id": str(msg.id)}, db_session)

    result = await db_session.execute(select(Message).where(Message.id == msg.id))
    updated = result.scalar_one()
    assert updated.embedding is not None


@pytest.mark.asyncio
async def test_embed_message_handler_skips_already_embedded(db_session, org_and_user):
    from app.worker.handlers.message_embedder import handle_embed_message
    from app.models.conversation import Conversation
    from app.models.message import Message

    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content="Answer",
        sources=[],
        embedding=[0.1] * 1536,
    )
    db_session.add(msg)
    await db_session.flush()

    with patch("app.worker.handlers.message_embedder.embed_texts", new_callable=AsyncMock) as mock_embed:
        await handle_embed_message({"message_id": str(msg.id)}, db_session)
        mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_embed_message_handler_embeds_qa_pair(db_session, org_and_user):
    from app.worker.handlers.message_embedder import handle_embed_message
    from app.models.conversation import Conversation
    from app.models.message import Message

    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test")
    db_session.add(conv)
    await db_session.flush()

    user_msg = Message(conversation_id=conv.id, role="user", content="What is chess.com?", sources=[])
    db_session.add(user_msg)
    await db_session.flush()

    asst_msg = Message(conversation_id=conv.id, role="assistant", content="Chess.com is a platform.", sources=[])
    db_session.add(asst_msg)
    await db_session.flush()

    captured = []
    async def mock_embed(texts):
        captured.extend(texts)
        return [[0.5] * 1536]

    with patch("app.worker.handlers.message_embedder.embed_texts", side_effect=mock_embed):
        await handle_embed_message({"message_id": str(asst_msg.id)}, db_session)

    assert len(captured) == 1
    assert "Q: What is chess.com?" in captured[0]
    assert "A: Chess.com is a platform." in captured[0]


@pytest.mark.asyncio
async def test_embed_message_handler_skips_missing_message(db_session):
    from app.worker.handlers.message_embedder import handle_embed_message

    # Should not raise
    await handle_embed_message({"message_id": str(uuid.uuid4())}, db_session)


@pytest.mark.asyncio
async def test_get_memories_returns_empty_string_when_no_data(db_session, org_and_user):
    from app.services.memory_extractor import get_memories_for_prompt

    _, user = org_and_user
    result = await get_memories_for_prompt(db_session, user.id)
    assert result == ""


@pytest.mark.asyncio
async def test_get_memories_returns_extracted_facts(db_session, org_and_user):
    from app.services.memory_extractor import get_memories_for_prompt
    from app.models.memory import Memory

    org, user = org_and_user
    db_session.add(Memory(user_id=user.id, org_id=org.id, content="Expert in tax law", source="manual"))
    await db_session.flush()

    result = await get_memories_for_prompt(db_session, user.id)
    assert "Expert in tax law" in result
    assert "What I remember about this user" in result


@pytest.mark.asyncio
async def test_get_memories_past_exchanges_sqlite_fallback(db_session, org_and_user):
    """In SQLite, pgvector query fails gracefully — only Part 1 returned."""
    from app.services.memory_extractor import get_memories_for_prompt
    from app.models.memory import Memory

    org, user = org_and_user
    db_session.add(Memory(user_id=user.id, org_id=org.id, content="Works in law", source="manual"))
    await db_session.flush()

    with patch("app.services.memory_extractor.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        result = await get_memories_for_prompt(db_session, user.id, current_query="legal documents")

    # Part 1 is present, no exception raised
    assert "Works in law" in result
    assert "What I remember about this user" in result


@pytest.mark.asyncio
async def test_chat_enqueues_embed_message(client: AsyncClient, auth_headers, db_session, org_and_user):
    from app.models.conversation import Conversation

    org, user = org_and_user
    conv = Conversation(org_id=org.id, user_id=user.id, title="Test")
    db_session.add(conv)
    await db_session.flush()

    mock_stream = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock(delta=MagicMock(content="Answer"))]

    async def _aiter():
        yield mock_chunk

    mock_stream.__aiter__ = lambda self: _aiter()

    enqueued = []
    with patch("app.api.chat._openai") as mock_openai, \
         patch("app.api.chat._embed_query", new_callable=AsyncMock, return_value=[0.1] * 1536), \
         patch("app.api.chat._similarity_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.api.chat.get_memories_for_prompt", new_callable=AsyncMock, return_value=""), \
         patch("app.api.chat.enqueue", side_effect=lambda x: enqueued.append(x)):
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_stream)

        resp = await client.post(
            f"/api/v1/chat/{conv.id}/messages",
            json={"message": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    job_types = [e["job_type"] for e in enqueued]
    assert "extract_memories" in job_types
    assert "embed_message" in job_types
