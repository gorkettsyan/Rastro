import uuid
from datetime import datetime
from pydantic import BaseModel


class UserOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str

    class Config:
        from_attributes = True


class GoogleLoginResponse(BaseModel):
    auth_url: str
