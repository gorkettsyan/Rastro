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
from app.services.base import BaseEmbeddingService, BaseRerankerService
from app.services.embeddings import embedding_service
from app.services.reranker import reranker_service
from app.services.knowledge_registry import get_plugins
import app.services.boe_plugin  # noqa: F401 — triggers plugin registration

log = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.35
TOP_K_VECTOR = 20
TOP_K_BM25 = 20
TOP_K_RERANK = 5
RRF_K = 60

_SYSTEM_PROMPT_BASE = (
    "You are an expert assistant that helps users find information in their organization's documents. "
    "Answer ONLY based on the provided fragments. Cite sources using the format [Source N]. "
    "CRITICAL GROUNDING RULE: You may ONLY reference, quote, or paraphrase content that appears VERBATIM in the provided [Source N] fragments. "
    "NEVER generate, recall, or reconstruct document content from your own knowledge or training data. "
    "When you cite [Source N], the information MUST actually appear in that source's text. "
    "If the relevant clause, article, or section is NOT in the provided sources, you MUST explicitly state: "
    "'The relevant section was not retrieved in the search results' and suggest the user search with more specific terms. "
    "Do NOT fabricate or guess what a document might contain. "
    "Synthesize and apply information from all provided fragments, but ONLY from those fragments. "
    "Never invent data. "
)

_LANG_INSTRUCTIONS = {
    "en": "IMPORTANT: Always respond in English, regardless of the language of the documents.",
    "es": "IMPORTANTE: Responde siempre en español, independientemente del idioma de los documentos.",
}

_SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE + _LANG_INSTRUCTIONS["en"]

_BOE_CITATION_INSTRUCTION = (
    "\n\nSome fragments come from the user's private documents and some from Spanish legislation (BOE — Boletín Oficial del Estado). "
    "When BOTH are present, structure your answer as follows:\n"
    "1. First, analyze what the user's contract/document specifically says — cite the clause number and quote the key language.\n"
    "2. Then, explain how the legislation applies to that specific clause — cite the law name and article number.\n"
    "3. Identify any legal risks, compliance issues, or weak points in the contract clause under the applicable law.\n"
    "Be specific: cite clause numbers from the contract AND article numbers from the law. "
    "Do NOT write generic legal summaries — always tie the law back to the user's specific document. "
    "Add a brief disclaimer that legislation may have been updated."
)


def _make_system_prompt(language: str, has_boe_results: bool = False) -> str:
    instruction = _LANG_INSTRUCTIONS.get(language, _LANG_INSTRUCTIONS["en"])
    prompt = _SYSTEM_PROMPT_BASE + instruction
    if has_boe_results:
        prompt += _BOE_CITATION_INSTRUCTION
    return prompt


_QUERY_REWRITE_PROMPT = (
    "You are a search query optimizer. Given the user's original query, return an improved "
    "version that is better suited for semantic and keyword search over legal documents. "
    "Rules: keep the same language; expand abbreviations if any; only add synonyms if clearly "
    "useful; if the query is already good return it unchanged. "
    "Reply with the improved query only — no explanation.\n\n"
    "Original query: {query}"
)

_DOCUMENT_QUERY_PROMPT = (
    "You are a search query expander for a document retrieval system. "
    "The user asked a conceptual legal question. Your job is to generate a COMPLEMENTARY search query "
    "that uses concrete contract/document vocabulary to find the relevant clauses.\n\n"
    "Rules:\n"
    "- Keep the same language as the original query\n"
    "- Use specific terms that would appear IN a contract: party roles (prestador, cliente, arrendador, "
    "arrendatario), clause markers (CG, cláusula, artículo), actions (modificar, resolver, rescindir, "
    "notificar, indemnizar), timeframes (plazo, preaviso, vigencia)\n"
    "- Do NOT repeat the original query — generate DIFFERENT keywords that would match the actual "
    "contract language for the same concept\n"
    "- Output a single line of 5-10 search keywords, no explanation\n\n"
    "Original query: {query}\n"
    "Document-vocabulary query:"
)


class RAGService:
    def __init__(self, embedding_svc: BaseEmbeddingService, reranker_svc: BaseRerankerService):
        self._embedding_svc = embedding_svc
        self._reranker_svc = reranker_svc
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def _rewrite_query(self, query: str) -> str:
        """Rewrites short queries via GPT-4o-mini. Long queries (>=5 words) pass through unchanged."""
        if len(query.split()) >= 5:
            return query
        try:
            response = await self._openai.chat.completions.create(
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

    async def _expand_query_for_documents(self, query: str) -> str | None:
        """Generate a complementary query using document/contract vocabulary."""
        try:
            response = await self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": _DOCUMENT_QUERY_PROMPT.format(query=query)}],
                temperature=0.3,
                max_tokens=80,
            )
            expanded = response.choices[0].message.content.strip()
            if expanded and expanded != query:
                log.debug("Document query expansion: '%s' → '%s'", query, expanded)
                return expanded
            return None
        except Exception as e:
            log.warning("Document query expansion failed: %s", e)
            return None

    async def _embed_query(self, query: str) -> list[float]:
        vectors = await self._embedding_svc.embed_texts([query])
        return vectors[0]

    async def _vector_search(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        query_vector: list[float],
        project_id: uuid.UUID | None = None,
        limit: int = TOP_K_VECTOR,
        user_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Cosine similarity search using pgvector."""
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
        scope = "AND c.project_id = CAST(:project_id AS uuid)" if project_id else ""
        visibility = (
            "AND (d.indexed_by_user_id = CAST(:user_id AS uuid) OR d.visibility = 'org')"
            if user_id else ""
        )

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
              {visibility}
              AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        params: dict = {"embedding": vector_str, "org_id": str(org_id), "limit": limit}
        if project_id:
            params["project_id"] = str(project_id)
        if user_id:
            params["user_id"] = str(user_id)

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
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        query: str,
        project_id: uuid.UUID | None = None,
        limit: int = TOP_K_BM25,
        user_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Full-text search using the stored content_tsv column (Spanish + English configs)."""
        scope = "AND c.project_id = CAST(:project_id AS uuid)" if project_id else ""
        visibility = (
            "AND (d.indexed_by_user_id = CAST(:user_id AS uuid) OR d.visibility = 'org')"
            if user_id else ""
        )

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
              {visibility}
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
        if user_id:
            params["user_id"] = str(user_id)

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

    @staticmethod
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

    @staticmethod
    def _diversify_sources(chunks: list[dict], top_n: int) -> list[dict]:
        """Interleave private and plugin chunks so neither source type dominates the final output."""
        def _is_plugin(c: dict) -> bool:
            return c.get("source_type") == "boe" or c.get("source") == "boe"

        private = [c for c in chunks if not _is_plugin(c)]
        plugin = [c for c in chunks if _is_plugin(c)]

        if not private or not plugin:
            return chunks[:top_n]

        result: list[dict] = []
        seen: set[str] = set()
        pi, qi = 0, 0
        while len(result) < top_n and (pi < len(private) or qi < len(plugin)):
            if pi < len(private):
                cid = private[pi]["chunk_id"]
                if cid not in seen:
                    result.append(private[pi])
                    seen.add(cid)
                pi += 1
            if len(result) >= top_n:
                break
            if qi < len(plugin):
                cid = plugin[qi]["chunk_id"]
                if cid not in seen:
                    result.append(plugin[qi])
                    seen.add(cid)
                qi += 1
        return result

    @staticmethod
    def _build_context(chunks: list[dict]) -> str:
        parts = []
        for i, c in enumerate(chunks, 1):
            if c.get("source_type") == "boe" or c.get("source") == "boe":
                law = c.get("law_name", "")
                art = c.get("article_number", "")
                label = f" ({law}, {art})" if law and art else f" ({law})" if law else ""
                parts.append(f"[Source {i}]{label}\n{c['content']}")
            else:
                parts.append(f"[Source {i}]\n{c['content']}")
        return "\n\n".join(parts)

    async def stream_rag_response(
        self,
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
            # 0. Intent classification — skip RAG for greetings / casual queries
            try:
                intent_resp = await self._openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": (
                            "Classify this user message as either 'search' or 'chat'.\n"
                            "'search' = the user wants information from documents, contracts, files, or data.\n"
                            "'chat' = casual conversation, greetings, thanks, small talk, or meta-questions about the assistant.\n"
                            "Respond with a single word: search or chat."
                        )},
                        {"role": "user", "content": query},
                    ],
                    temperature=0,
                    max_tokens=5,
                )
                intent = intent_resp.choices[0].message.content.strip().lower()
                if intent == "chat":
                    yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    log_entry.result_count = 0
                    log_entry.latency_ms = int((time.monotonic() - start) * 1000)
                    await db.flush()
                    return
            except Exception:
                pass  # default to search on failure

            # 1. Query rewriting + document-vocabulary expansion (parallel)
            rewritten, doc_query = await asyncio.gather(
                self._rewrite_query(query),
                self._expand_query_for_documents(query),
            )

            # 2. Embed primary query (+ expanded query if available)
            embed_tasks = [self._embed_query(rewritten)]
            if doc_query:
                embed_tasks.append(self._embed_query(doc_query))
            embed_results = await asyncio.gather(*embed_tasks)
            query_vector = embed_results[0]
            doc_vector = embed_results[1] if doc_query else None

            # 3. Parallel retrieval (primary + expanded + plugins)
            tasks = [
                self._vector_search(db, org_id, query_vector, project_id, user_id=user_id),
                self._bm25_search(db, org_id, rewritten, project_id, user_id=user_id),
            ]
            # Expanded document query — private docs only (no plugins)
            if doc_vector and doc_query:
                tasks.append(self._vector_search(db, org_id, doc_vector, project_id, user_id=user_id))
                tasks.append(self._bm25_search(db, org_id, doc_query, project_id, user_id=user_id))

            plugins = get_plugins()
            plugin_start_idx = len(tasks)
            for plugin in plugins:
                tasks.append(plugin.vector_search(db, query_vector))
                tasks.append(plugin.bm25_search(db, rewritten))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            vector_results = results[0] if not isinstance(results[0], Exception) else []
            bm25_results = results[1] if not isinstance(results[1], Exception) else []

            # Merge expanded query results into primary results
            if doc_vector and doc_query:
                exp_vector = results[2] if not isinstance(results[2], Exception) else []
                exp_bm25 = results[3] if not isinstance(results[3], Exception) else []
                vector_results = vector_results + exp_vector
                bm25_results = bm25_results + exp_bm25

            # Collect plugin results
            plugin_vector_all: list[dict] = []
            plugin_bm25_all: list[dict] = []
            for i, plugin in enumerate(plugins):
                pv_idx = plugin_start_idx + i * 2
                pb_idx = plugin_start_idx + i * 2 + 1
                pv = results[pv_idx] if not isinstance(results[pv_idx], Exception) else []
                pb = results[pb_idx] if not isinstance(results[pb_idx], Exception) else []
                if isinstance(pv, Exception):
                    log.warning("Plugin %s vector search failed: %s", plugin.name, pv)
                    pv = []
                if isinstance(pb, Exception):
                    log.warning("Plugin %s bm25 search failed: %s", plugin.name, pb)
                    pb = []
                plugin_vector_all.extend(pv)
                plugin_bm25_all.extend(pb)

            # 4. RRF fusion (primary + expanded + plugin results merged)
            all_vector = vector_results + plugin_vector_all
            all_bm25 = bm25_results + plugin_bm25_all
            fused = self._reciprocal_rank_fusion(all_vector, all_bm25)

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

            # 5. Rerank (get extra candidates, then diversify sources)
            reranked = await self._reranker_svc.rerank(query, fused[:50], top_n=TOP_K_RERANK * 3)
            top_chunks = self._diversify_sources(reranked, TOP_K_RERANK)

            # 6. Stream GPT-4o
            has_boe = any(c.get("source_type") == "boe" or c.get("source") == "boe" for c in top_chunks)
            context = self._build_context(top_chunks)
            stream = await self._openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _make_system_prompt(language, has_boe_results=has_boe)},
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

            # 7. Sources — use plugin format_source for plugin chunks
            plugin_map = {p.name: p for p in plugins}
            sources = []
            for c in top_chunks:
                if c.get("source_type") and c["source_type"] in plugin_map:
                    sources.append(plugin_map[c["source_type"]].format_source(c))
                else:
                    sources.append({
                        "document_id": str(c["document_id"]),
                        "title": c["title"],
                        "source": c["source"],
                        "source_url": c["source_url"],
                        "score": round(c.get("rerank_score", c.get("rrf_score", 0.0)), 3),
                        "excerpt": c["content"][:200],
                    })
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


rag_service = RAGService(embedding_service, reranker_service)

# Public export for chat API
SYSTEM_PROMPT = _SYSTEM_PROMPT
