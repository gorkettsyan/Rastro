import uuid
from datetime import datetime
from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    source: str
    source_url: str | None
    drive_folder_id: str | None = None
    chunk_count: int
    indexing_status: str
    visibility: str
    indexing_error: str | None
    indexed_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    project_id: uuid.UUID | None = None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
