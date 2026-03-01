import uuid
from datetime import date, datetime
from pydantic import BaseModel


ALLOWED_TYPES = {
    "termination_notice", "renewal_window", "payment_due",
    "option_exercise", "warranty_expiry", "other",
}

ALLOWED_STATUSES = {"open", "resolved", "snoozed"}


class ObligationCreate(BaseModel):
    document_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    obligation_type: str
    description: str
    due_date: date | None = None


class ObligationUpdate(BaseModel):
    status: str | None = None
    due_date: date | None = None
    description: str | None = None


class ObligationOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    document_id: uuid.UUID | None
    project_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    obligation_type: str
    description: str
    clause_text: str | None
    due_date: date | None
    date_unresolved: bool
    confidence: float
    status: str
    source: str
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    document_title: str | None = None

    class Config:
        from_attributes = True


class ObligationList(BaseModel):
    items: list[ObligationOut]
    total: int
