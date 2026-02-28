import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document import Document
from app.models.integration_token import IntegrationToken
from app.security import decrypt
from app.services.ingestion import chunk_and_embed, extract_text_from_bytes
from app.services.storage import upload_text
from app.worker.queue import enqueue

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.document",
    "text/plain",
}


def _drive_service(access_token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=Credentials(token=access_token))


async def handle_drive_file(body: dict, db: AsyncSession) -> None:
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
        service = _drive_service(decrypt(token.access_token_enc))
        file_meta = service.files().get(fileId=body["source_id"], fields="id,name,mimeType").execute()
        mime_type = file_meta["mimeType"]

        if mime_type == "application/vnd.google-apps.document":
            content = service.files().export(fileId=body["source_id"], mimeType="text/plain").execute()
            raw_text = content.decode("utf-8", errors="ignore")
        else:
            content = service.files().get_media(fileId=body["source_id"]).execute()
            raw_text = extract_text_from_bytes(content, mime_type)

        s3_key = f"{doc.org_id}/drive/{body['source_id']}.txt"
        upload_text(s3_key, raw_text)
        doc.file_path = s3_key

        await chunk_and_embed(db, doc, raw_text, extra_metadata={"source": "drive", "file_name": file_meta["name"]})
    except Exception as e:
        doc.indexing_status = "error"
        doc.indexing_error = str(e)[:500]


async def enqueue_all_drive_files(org_id: str, user_id: str, db: AsyncSession) -> int:
    token_result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user_id,
            IntegrationToken.provider == "google",
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        return 0

    service = _drive_service(decrypt(token.access_token_enc))
    mime_query = " or ".join(f"mimeType='{m}'" for m in SUPPORTED_MIME_TYPES)
    page_token = None
    jobs: list[dict] = []

    # Pass 1: create Document rows, collect job payloads
    while True:
        resp = service.files().list(
            q=f"({mime_query}) and trashed=false",
            fields="nextPageToken,files(id,name,mimeType)",
            pageSize=100,
            pageToken=page_token,
        ).execute()

        for file in resp.get("files", []):
            existing = await db.execute(
                select(Document).where(
                    Document.org_id == org_id,
                    Document.source == "drive",
                    Document.source_id == file["id"],
                )
            )
            doc = existing.scalar_one_or_none()
            if not doc:
                doc = Document(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    title=file["name"],
                    source="drive",
                    source_id=file["id"],
                    source_url=f"https://drive.google.com/file/d/{file['id']}",
                    mime_type=file["mimeType"],
                    indexing_status="pending",
                )
                db.add(doc)
                await db.flush()

            jobs.append({
                "job_type": "drive_file",
                "org_id": str(org_id),
                "user_id": str(user_id),
                "document_id": str(doc.id),
                "source_id": file["id"],
            })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # Pass 2: commit all rows to DB, then enqueue (worker needs rows to exist)
    await db.commit()
    for job in jobs:
        enqueue(job)
    return len(jobs)
