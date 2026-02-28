import uuid
import re
from base64 import urlsafe_b64decode
from html.parser import HTMLParser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document import Document
from app.models.integration_token import IntegrationToken
from app.security import decrypt
from app.services.ingestion import chunk_and_embed, make_document
from app.services.storage import upload_text
from app.worker.queue import enqueue


def _gmail_service(access_token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=Credentials(token=access_token))


class _HTMLStripper(HTMLParser):
    # Tags whose entire content (text + children) should be ignored
    _SKIP = frozenset({"style", "script", "head", "meta", "link", "noscript"})

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _html_to_text(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    text = stripper.get_text()
    # Remove full URLs (tracking links, unsubscribe links, etc.)
    text = re.sub(r"https?://\S+", "", text)
    # Remove leftover long alphanumeric tokens (base64 tracking IDs)
    text = re.sub(r"[A-Za-z0-9+/=_~-]{40,}", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _decode_part(data: str) -> str:
    return urlsafe_b64decode(data).decode("utf-8", errors="ignore")


def _extract_body(payload: dict) -> str:
    """Return plain text from a message payload, falling back to stripped HTML."""
    # Single-part message
    if payload.get("body", {}).get("data"):
        raw = _decode_part(payload["body"]["data"])
        return raw if payload.get("mimeType") != "text/html" else _html_to_text(raw)

    parts = payload.get("parts", [])

    # Prefer text/plain
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_part(part["body"]["data"])

    # Fall back to text/html
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return _html_to_text(_decode_part(part["body"]["data"]))

    # Recurse into multipart sub-parts (e.g. multipart/alternative inside multipart/mixed)
    for part in parts:
        if part.get("mimeType", "").startswith("multipart/"):
            result = _extract_body(part)
            if result:
                return result

    return ""


def _extract_thread_text(thread_data: dict) -> tuple[str, str]:
    subject, parts = "", []
    for message in thread_data.get("messages", []):
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
        if not subject:
            subject = headers.get("Subject", "Sin asunto")
        body = _extract_body(message.get("payload", {}))
        parts.append(f"De: {headers.get('From', '')}\nFecha: {headers.get('Date', '')}\n---\n{body}")
    return subject, "\n\n".join(parts)


async def handle_gmail_thread(body: dict, db: AsyncSession) -> None:
    result = await db.execute(select(Document).where(Document.id == body["document_id"]))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document not found: {body['document_id']}")

    token_result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == body["user_id"],
            IntegrationToken.provider == "google",
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise ValueError(f"No Google token for user: {body['user_id']}")

    doc.indexing_status = "indexing"
    await db.flush()

    try:
        service = _gmail_service(decrypt(token.access_token_enc))
        thread_data = service.users().threads().get(userId="me", id=body["source_id"], format="full").execute()
        subject, raw_text = _extract_thread_text(thread_data)

        if not raw_text.strip():
            doc.indexing_status = "done"
            return

        s3_key = f"{doc.org_id}/gmail/{body['source_id']}.txt"
        upload_text(s3_key, raw_text)
        doc.file_path = s3_key
        doc.title = subject

        await chunk_and_embed(db, doc, raw_text, extra_metadata={"source": "gmail", "thread_id": body["source_id"]})
    except Exception as e:
        doc.indexing_status = "error"
        doc.indexing_error = str(e)[:500]


async def enqueue_all_gmail_threads(org_id: str, user_id: str, db: AsyncSession) -> int:
    token_result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user_id,
            IntegrationToken.provider == "google",
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        return 0

    service = _gmail_service(decrypt(token.access_token_enc))
    jobs: list[dict] = []

    # Pass 1: create Document rows, collect job payloads (latest 30 threads only)
    resp = service.users().threads().list(
        userId="me", maxResults=30
    ).execute()

    for thread in resp.get("threads", []):
        existing = await db.execute(
            select(Document).where(
                Document.org_id == org_id,
                Document.source == "gmail",
                Document.source_id == thread["id"],
            )
        )
        doc = existing.scalar_one_or_none()
        if not doc:
            doc = make_document(
                user_id=uuid.UUID(user_id),
                id=uuid.uuid4(),
                org_id=org_id,
                title=thread.get("snippet", "Email thread")[:255],
                source="gmail",
                source_id=thread["id"],
                indexing_status="pending",
            )
            db.add(doc)
            await db.flush()

        jobs.append({
            "job_type": "gmail_thread",
            "org_id": str(org_id),
            "user_id": str(user_id),
            "document_id": str(doc.id),
            "source_id": thread["id"],
        })

    # Pass 2: commit all rows to DB, then enqueue (worker needs rows to exist)
    await db.commit()
    for job in jobs:
        enqueue(job)
    return len(jobs)
