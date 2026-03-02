"""BOE knowledge plugin — vector + BM25 search over boe_chunks table."""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge_base import BaseKnowledgePlugin
from app.services.knowledge_registry import register_plugin

log = logging.getLogger(__name__)

BOE_SCORE_THRESHOLD = 0.30


class BoeKnowledgePlugin(BaseKnowledgePlugin):
    name = "boe"
    source_type = "boe"

    async def vector_search(
        self, db: AsyncSession, query_vector: list[float], limit: int = 20,
    ) -> list[dict]:
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
        sql = text("""
            SELECT
                bc.id,
                bc.content,
                bc.boe_id,
                bc.law_name,
                bc.article_number,
                bc.section_title,
                bc.boe_url,
                1 - (bc.embedding <=> CAST(:embedding AS vector)) AS score
            FROM boe_chunks bc
            WHERE bc.embedding IS NOT NULL
            ORDER BY bc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)
        result = await db.execute(sql, {"embedding": vector_str, "limit": limit})
        rows = result.fetchall()
        return [
            {
                "chunk_id": f"boe:{row.id}",
                "content": row.content,
                "document_id": f"boe:{row.boe_id}",
                "score": float(row.score),
                "title": f"{row.law_name} — {row.article_number or row.section_title or 'General'}",
                "source": "boe",
                "source_url": row.boe_url,
                "law_name": row.law_name,
                "article_number": row.article_number,
                "boe_id": row.boe_id,
                "source_type": "boe",
                "retrieval": "vector",
            }
            for row in rows
            if float(row.score) >= BOE_SCORE_THRESHOLD
        ]

    async def bm25_search(
        self, db: AsyncSession, query: str, limit: int = 20,
    ) -> list[dict]:
        sql = text("""
            SELECT
                bc.id,
                bc.content,
                bc.boe_id,
                bc.law_name,
                bc.article_number,
                bc.section_title,
                bc.boe_url,
                ts_rank_cd(bc.content_tsv, websearch_to_tsquery('spanish', :query)) AS score
            FROM boe_chunks bc
            WHERE bc.content_tsv @@ websearch_to_tsquery('spanish', :query)
            ORDER BY score DESC
            LIMIT :limit
        """)
        try:
            result = await db.execute(sql, {"query": query, "limit": limit})
            rows = result.fetchall()
            return [
                {
                    "chunk_id": f"boe:{row.id}",
                    "content": row.content,
                    "document_id": f"boe:{row.boe_id}",
                    "score": float(row.score),
                    "title": f"{row.law_name} — {row.article_number or row.section_title or 'General'}",
                    "source": "boe",
                    "source_url": row.boe_url,
                    "law_name": row.law_name,
                    "article_number": row.article_number,
                    "boe_id": row.boe_id,
                    "source_type": "boe",
                    "retrieval": "bm25",
                }
                for row in rows
            ]
        except Exception as e:
            log.warning("BOE BM25 search failed: %s", e)
            return []

    def format_source(self, chunk: dict) -> dict:
        return {
            "document_id": chunk.get("document_id", ""),
            "title": chunk.get("title", ""),
            "source": "boe",
            "source_url": chunk.get("source_url"),
            "score": round(chunk.get("rerank_score", chunk.get("rrf_score", 0.0)), 3),
            "excerpt": chunk.get("content", "")[:200],
            "source_type": "boe",
            "law_name": chunk.get("law_name"),
            "article_number": chunk.get("article_number"),
            "boe_id": chunk.get("boe_id"),
        }


# Auto-register on import
_boe_plugin = BoeKnowledgePlugin()
register_plugin(_boe_plugin)
