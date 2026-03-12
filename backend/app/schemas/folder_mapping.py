import uuid
from datetime import datetime
from pydantic import BaseModel


class FolderMappingCreate(BaseModel):
    project_id: uuid.UUID
    folder_id: str
    folder_name: str


class FolderMappingOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    project_id: uuid.UUID
    folder_id: str
    folder_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class FolderMappingList(BaseModel):
    items: list[FolderMappingOut]


class DriveFolderOut(BaseModel):
    id: str
    name: str
