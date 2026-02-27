import uuid
from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    title: str
    client_name: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    title: str | None = None
    client_name: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    client_name: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectList(BaseModel):
    items: list[ProjectOut]
    total: int
