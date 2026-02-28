import logging
from app.config import settings

log = logging.getLogger(__name__)


async def rerank(query: str, chunks: list[dict], top_n: int = 5) -> list[dict]:
    """
    Reranks chunks using Cohere's multilingual reranker.
    Falls back to original RRF order when COHERE_API_KEY is not set or on error.
    """
    if not settings.cohere_api_key or not chunks:
        return chunks[:top_n]

    try:
        import cohere
        co = cohere.AsyncClient(api_key=settings.cohere_api_key)

        response = await co.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=[c["content"] for c in chunks],
            top_n=top_n,
        )

        reranked = []
        for result in response.results:
            chunk = chunks[result.index].copy()
            chunk["rerank_score"] = result.relevance_score
            reranked.append(chunk)

        return reranked

    except Exception as e:
        log.warning("Reranker failed, falling back to RRF order: %s", e)
        return chunks[:top_n]
