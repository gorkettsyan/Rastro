import uuid
from datetime import datetime
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    project_id: uuid.UUID | None = None
    first_message: str


class ConversationOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationList(BaseModel):
    items: list[ConversationOut]
    total: int


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: list
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    language: str = "es"


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
