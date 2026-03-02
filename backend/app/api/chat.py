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
from app.services.knowledge_registry import get_plugins
from app.worker.queue import queue_service

router = APIRouter(prefix="/chat", tags=["chat"])
_openai = AsyncOpenAI(api_key=settings.openai_api_key)

HISTORY_LIMIT = 20

_INTENT_PROMPT = (
    "Classify this user message as either 'search' or 'chat'.\n"
    "'search' = the user wants information from documents, contracts, files, or data.\n"
    "'chat' = casual conversation, greetings, thanks, small talk, or meta-questions about the assistant.\n"
    "Respond with a single word: search or chat."
)

_CHAT_SYSTEM_PROMPT_BASE = (
    "You are an expert assistant that helps users find information in their organization's documents. "
    "You have persistent memory across conversations. The '[What I remember about this user]' section below "
    "contains facts you have learned about this user from previous interactions — treat them as YOUR memories. "
    "When the user asks if you remember something, check that section and respond naturally as if you recall it yourself. "
    "NEVER say 'I don't have memory of past interactions' if the memory section contains relevant information. "
    "Answer based on the provided document fragments, conversation history, and your memories. "
    "When citing a fragment, use the format [Source N]. "
    "CRITICAL GROUNDING RULE: You may ONLY reference, quote, or paraphrase document content that appears VERBATIM in the provided [Source N] fragments. "
    "NEVER generate, recall, or reconstruct document content from your own knowledge or training data. "
    "When you cite [Source N], the information MUST actually appear in that source's text. "
    "If the relevant clause, article, or section is NOT in the provided sources, you MUST explicitly state: "
    "'The relevant section was not retrieved in the search results' and suggest the user search with more specific terms. "
    "Do NOT fabricate or guess what a document might contain. "
    "Synthesize information from all provided fragments, but ONLY from those fragments. "
    "Never invent data. "
    "Treat each memory item as an independent fact — "
    "do NOT infer connections or relationships between separate memory items. "
)

_CHAT_LANG_INSTRUCTIONS = {
    "en": "IMPORTANT: Always respond in English, regardless of the language of the documents.",
    "es": "IMPORTANTE: Responde siempre en español, independientemente del idioma de los documentos.",
}

_CHAT_BOE_INSTRUCTION = (
    "\n\nSome fragments come from the user's private documents and some from Spanish legislation (BOE). "
    "When BOTH are present, structure your answer as follows:\n"
    "1. First, analyze what the user's contract/document specifically says — cite the clause number and quote the key language.\n"
    "2. Then, explain how the legislation applies to that specific clause — cite the law name and article number.\n"
    "3. Identify any legal risks, compliance issues, or weak points in the contract clause under the applicable law.\n"
    "Be specific: cite clause numbers from the contract AND article numbers from the law. "
    "Do NOT write generic legal summaries — always tie the law back to the user's specific document. "
    "Add a brief disclaimer that legislation may have been updated."
)


def _make_chat_system_prompt(language: str, has_boe_results: bool = False) -> str:
    instruction = _CHAT_LANG_INSTRUCTIONS.get(language, _CHAT_LANG_INSTRUCTIONS["en"])
    prompt = _CHAT_SYSTEM_PROMPT_BASE + instruction
    if has_boe_results:
        prompt += _CHAT_BOE_INSTRUCTION
    return prompt


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

        # 3. Classify intent — skip RAG for casual conversation
        needs_search = True
        try:
            intent_resp = await _openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _INTENT_PROMPT},
                    {"role": "user", "content": body.message},
                ],
                temperature=0,
                max_tokens=5,
            )
            intent = intent_resp.choices[0].message.content.strip().lower()
            needs_search = intent != "chat"
        except Exception:
            pass  # default to search on failure

        # 4. RAG retrieval (only if the message needs document context)
        chunks = []
        context = ""
        if needs_search:
            retrieval_query = body.message
            if history and len(body.message.split()) < 5:
                last_assistant = next(
                    (m for m in reversed(history) if m.role == "assistant"), None
                )
                if last_assistant:
                    retrieval_query = f"{last_assistant.content[:200]} {body.message}"

            query_vector = await rag_service._embed_query(retrieval_query)

            # Private vector + BM25 + plugin searches in parallel
            import asyncio
            search_tasks = [
                rag_service._vector_search(
                    db, current_user.org_id, query_vector, conv.project_id,
                    user_id=current_user.id,
                ),
                rag_service._bm25_search(
                    db, current_user.org_id, retrieval_query, conv.project_id,
                    user_id=current_user.id,
                ),
            ]
            plugins = get_plugins()
            for plugin in plugins:
                search_tasks.append(plugin.vector_search(db, query_vector, limit=10))
                search_tasks.append(plugin.bm25_search(db, retrieval_query, limit=10))

            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            private_vector = search_results[0] if not isinstance(search_results[0], Exception) else []
            private_bm25 = search_results[1] if not isinstance(search_results[1], Exception) else []

            plugin_vector = []
            plugin_bm25 = []
            for i, plugin in enumerate(plugins):
                pv = search_results[2 + i * 2]
                pb = search_results[3 + i * 2]
                if not isinstance(pv, Exception):
                    plugin_vector.extend(pv)
                if not isinstance(pb, Exception):
                    plugin_bm25.extend(pb)

            # RRF fusion across all sources
            all_vector = private_vector + plugin_vector
            all_bm25 = private_bm25 + plugin_bm25
            fused = rag_service._reciprocal_rank_fusion(all_vector, all_bm25)
            chunks = fused[:10]
            context = rag_service._build_context(chunks)

        # 5. Fetch memories
        memory_block = await memory_extractor_service.get_memories_for_prompt(db, current_user.id, current_query=body.message)

        # 6. Build messages array for GPT-4o
        has_boe = any(c.get("source_type") == "boe" or c.get("source") == "boe" for c in chunks)
        system_content = _make_chat_system_prompt(body.language, has_boe_results=has_boe) + memory_block
        gpt_messages = [{"role": "system", "content": system_content}]

        for msg in history:
            gpt_messages.append({"role": msg.role, "content": msg.content})

        current_content = f"{context}\n\n{body.message}" if context else body.message
        gpt_messages.append({"role": "user", "content": current_content})

        # 7. Stream GPT-4o
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

        # 8. Emit sources
        sources = []
        for c in chunks[:5]:
            src = {
                "document_id": str(c["document_id"]),
                "title": c["title"],
                "source": c["source"],
                "source_url": c["source_url"],
                "score": round(c.get("rrf_score", c.get("score", 0)), 3),
                "excerpt": c["content"][:200],
            }
            if c.get("source_type") == "boe":
                src["source_type"] = "boe"
                src["law_name"] = c.get("law_name")
                src["article_number"] = c.get("article_number")
                src["boe_id"] = c.get("boe_id")
            sources.append(src)
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # 9. Save assistant message
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_response,
            sources=sources,
        )
        db.add(assistant_msg)

        # 10. Update conversation timestamp
        conv.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # 11. Enqueue memory extraction and message embedding
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
