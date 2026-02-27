import uuid
from pydantic import BaseModel


class SearchQuery(BaseModel):
    query: str
    project_id: uuid.UUID | None = None
    top_k: int = 5


class CitedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    score: float


class SearchHistoryItem(BaseModel):
    id: uuid.UUID
    query: str
    result_count: int
    project_id: uuid.UUID | None
    created_at: str

    class Config:
        from_attributes = True


class SearchHistoryResponse(BaseModel):
    items: list[SearchHistoryItem]
