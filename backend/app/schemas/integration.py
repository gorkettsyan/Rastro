from datetime import datetime
from pydantic import BaseModel


class IntegrationStatusItem(BaseModel):
    connected: bool
    last_sync: datetime | None
    doc_count: int
    error: str | None


class IntegrationStatusOut(BaseModel):
    google: IntegrationStatusItem


class SyncResponse(BaseModel):
    message: str
    queued: int
