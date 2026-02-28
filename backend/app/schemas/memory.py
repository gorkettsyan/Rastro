import uuid
from datetime import datetime
from pydantic import BaseModel


class MemoryOut(BaseModel):
    id: uuid.UUID
    content: str
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class MemoryCreate(BaseModel):
    content: str


class MemoryUpdate(BaseModel):
    content: str


class MemoryList(BaseModel):
    items: list[MemoryOut]
    total: int
