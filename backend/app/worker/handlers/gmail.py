import uuid
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document import Document
from app.models.integration_token import IntegrationToken
from app.security import decrypt
from app.services.ingestion import chunk_and_embed
from app.services.storage import upload_text
from app.worker.queue import enqueue


def _gmail_service(access_token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=Credentials(token=access_token))


def _extract_thread_text(thread_data: dict) -> tuple[str, str]:
    subject, parts = "", []
    for message in thread_data.get("messages", []):
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
        if not subject:
            subject = headers.get("Subject", "Sin asunto")
        body = ""
        payload = message.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        else:
            for part in payload.get("parts", []):
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break
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
    after_date = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y/%m/%d")
    page_token = None
    count = 0

    while True:
        resp = service.users().threads().list(
            userId="me", q=f"after:{after_date}", maxResults=100, pageToken=page_token
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
                doc = Document(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    title=thread.get("snippet", "Email thread")[:255],
                    source="gmail",
                    source_id=thread["id"],
                    indexing_status="pending",
                )
                db.add(doc)
                await db.flush()

            enqueue({
                "job_type": "gmail_thread",
                "org_id": str(org_id),
                "user_id": str(user_id),
                "document_id": str(doc.id),
                "source_id": thread["id"],
            })
            count += 1

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    await db.flush()
    return count
