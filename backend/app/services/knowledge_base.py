from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession


class BaseKnowledgePlugin(ABC):
    """ABC for external knowledge source plugins (BOE, CENDOJ, etc.)."""

    name: str
    source_type: str

    @abstractmethod
    async def vector_search(
        self, db: AsyncSession, query_vector: list[float], limit: int = 20,
    ) -> list[dict]:
        ...

    @abstractmethod
    async def bm25_search(
        self, db: AsyncSession, query: str, limit: int = 20,
    ) -> list[dict]:
        ...

    def format_source(self, chunk: dict) -> dict:
        """Default source formatting. Plugins can override for custom fields."""
        return {
            "document_id": chunk.get("document_id", ""),
            "title": chunk.get("title", ""),
            "source": self.source_type,
            "source_url": chunk.get("source_url"),
            "score": round(chunk.get("rerank_score", chunk.get("rrf_score", 0.0)), 3),
            "excerpt": chunk.get("content", "")[:200],
        }
