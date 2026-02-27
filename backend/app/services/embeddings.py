from openai import AsyncOpenAI
from app.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key)
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_BATCH = 512


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    all_embeddings = []
    for i in range(0, len(texts), MAX_BATCH):
        batch = texts[i:i + MAX_BATCH]
        response = await _client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings
