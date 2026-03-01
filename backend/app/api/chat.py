import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationOut,
    MessageOut,
)
from app.services.memory_extractor import memory_extractor_service
from app.services.rag import rag_service
from app.worker.queue import queue_service

router = APIRouter(prefix="/chat", tags=["chat"])
_openai = AsyncOpenAI(api_key=settings.openai_api_key)

HISTORY_LIMIT = 20

_CHAT_SYSTEM_PROMPT_BASE = (
    "You are an expert assistant that helps users find information in their organization's documents. "
    "You have persistent memory across conversations. The '[What I remember about this user]' section below "
    "contains facts you have learned about this user from previous interactions — treat them as YOUR memories. "
    "When the user asks if you remember something, check that section and respond naturally as if you recall it yourself. "
    "NEVER say 'I don't have memory of past interactions' if the memory section contains relevant information. "
    "Answer based on the provided document fragments, conversation history, and your memories. "
    "When citing a fragment, use the format [Source N]. "
    "If you cannot find relevant information in any of these sources, say so clearly. "
    "Never invent data. "
    "Treat each memory item as an independent fact — "
    "do NOT infer connections or relationships between separate memory items. "
)

_CHAT_LANG_INSTRUCTIONS = {
    "en": "IMPORTANT: Always respond in English, regardless of the language of the documents.",
    "es": "IMPORTANTE: Responde siempre en español, independientemente del idioma de los documentos.",
}


def _make_chat_system_prompt(language: str) -> str:
    instruction = _CHAT_LANG_INSTRUCTIONS.get(language, _CHAT_LANG_INSTRUCTIONS["en"])
    return _CHAT_SYSTEM_PROMPT_BASE + instruction


@router.get("", response_model=ConversationList)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    items = result.scalars().all()
    return ConversationList(items=items, total=len(items))


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    title = body.first_message[:60] + ("..." if len(body.first_message) > 60 else "")
    conv = Conversation(
        org_id=current_user.org_id,
        user_id=current_user.id,
        project_id=body.project_id,
        title=title,
    )
    db.add(conv)
    await db.flush()
    await db.commit()
    return ConversationOut.model_validate(conv)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return ConversationDetail(
        conversation=ConversationOut.model_validate(conv),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    async def generate():
        # 1. Save user message
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=body.message,
            sources=[],
        )
        db.add(user_msg)
        await db.flush()

        # 2. Fetch conversation history
        history_result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.id != user_msg.id,
            )
            .order_by(Message.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
        history = list(reversed(history_result.scalars().all()))

        # 3. RAG retrieval — enrich short follow-up queries with recent context
        retrieval_query = body.message
        if history and len(body.message.split()) < 5:
            last_assistant = next(
                (m for m in reversed(history) if m.role == "assistant"), None
            )
            if last_assistant:
                retrieval_query = f"{last_assistant.content[:200]} {body.message}"

        query_vector = await rag_service._embed_query(retrieval_query)
        chunks = await rag_service._vector_search(
            db, current_user.org_id, query_vector, conv.project_id,
            user_id=current_user.id,
        )
        context = rag_service._build_context(chunks)

        # 4. Fetch memories
        memory_block = await memory_extractor_service.get_memories_for_prompt(db, current_user.id, current_query=body.message)

        # 5. Build messages array for GPT-4o
        system_content = _make_chat_system_prompt(body.language) + memory_block
        gpt_messages = [{"role": "system", "content": system_content}]

        for msg in history:
            gpt_messages.append({"role": msg.role, "content": msg.content})

        current_content = f"{context}\n\n{body.message}" if context else body.message
        gpt_messages.append({"role": "user", "content": current_content})

        # 6. Stream GPT-4o
        stream = await _openai.chat.completions.create(
            model="gpt-4o",
            messages=gpt_messages,
            stream=True,
            temperature=0.2,
            max_tokens=1024,
        )

        full_response = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_response += delta
                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

        # 7. Emit sources
        sources = [
            {
                "document_id": str(c["document_id"]),
                "title": c["title"],
                "source": c["source"],
                "source_url": c["source_url"],
                "score": round(c["score"], 3),
                "excerpt": c["content"][:200],
            }
            for c in chunks[:5]
        ]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # 8. Save assistant message
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_response,
            sources=sources,
        )
        db.add(assistant_msg)

        # 9. Update conversation timestamp
        conv.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # 10. Enqueue memory extraction and message embedding
        queue_service.enqueue({
            "job_type": "extract_memories",
            "user_id": str(current_user.id),
            "org_id": str(current_user.org_id),
            "conversation_id": str(conversation_id),
        })
        queue_service.enqueue({
            "job_type": "embed_message",
            "message_id": str(assistant_msg.id),
        })

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
