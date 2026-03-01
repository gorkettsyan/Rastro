import pytest
import json
import uuid
from datetime import date, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient

from app.models.document import Document
from app.models.chunk import Chunk
from app.models.obligation import Obligation
from app.models.project_member import ProjectMember
from app.services.date_extractor import date_extractor_service
from app.worker.queue import queue_service


# ── 1. Upload handler enqueues extract_dates ──

@pytest.mark.asyncio
async def test_extract_dates_enqueued_after_upload(db_session, org_and_user):
    """After chunk_and_embed succeeds, upload handler enqueues extract_dates."""
    from app.worker.handlers.upload import handle_manual_upload

    org, user = org_and_user
    doc = Document(
        org_id=org.id,
        title="Contract.pdf",
        source="upload",
        source_id=f"upload-{uuid.uuid4().hex}",
        indexing_status="pending",
        chunk_count=0,
        indexed_by_user_id=user.id,
        file_path="some/key.txt",
    )
    db_session.add(doc)
    await db_session.flush()

    enqueued = []
    with patch("app.worker.handlers.upload.storage_service") as mock_storage, \
         patch("app.worker.handlers.upload.ingestion_service") as mock_ingestion, \
         patch.object(queue_service, "enqueue", side_effect=lambda x: enqueued.append(x)):
        mock_storage.download_text.return_value = "some text"
        mock_ingestion.chunk_and_embed = AsyncMock()

        # Use actual UUID objects for SQLite compatibility
        body = {"document_id": doc.id, "org_id": str(org.id), "user_id": str(user.id)}
        await handle_manual_upload(body, db_session)

    assert len(enqueued) == 1
    assert enqueued[0]["job_type"] == "extract_dates"
    assert enqueued[0]["document_id"] == str(doc.id)


# ── 2. Extraction stores results ──

@pytest.mark.asyncio
async def test_extract_obligations_stores_results(db_session, org_and_user, document, project):
    org, user = org_and_user
    # Create chunks
    c = Chunk(
        org_id=org.id, project_id=project.id, document_id=document.id,
        content="Payment due on 2026-06-01", embedding=[0.1] * 1536, chunk_index=0,
    )
    db_session.add(c)
    await db_session.flush()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "obligations": [{
            "type": "payment_due",
            "description": "Payment of $10,000 due",
            "clause_text": "Payment due on 2026-06-01",
            "due_date": "2026-06-01",
            "date_unresolved": False,
            "confidence": 0.95,
            "chunk_index": 0,
        }]
    })

    with patch.object(date_extractor_service, "_openai") as mock_openai:
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        count = await date_extractor_service.extract_obligations(db_session, document.id, org.id)

    assert count == 1
    from sqlalchemy import select
    result = await db_session.execute(select(Obligation).where(Obligation.document_id == document.id))
    obs = result.scalars().all()
    assert len(obs) == 1
    assert obs[0].obligation_type == "payment_due"
    assert obs[0].due_date == date(2026, 6, 1)
    assert obs[0].confidence == 0.95


# ── 3. Idempotent re-extraction ──

@pytest.mark.asyncio
async def test_extract_obligations_idempotent(db_session, org_and_user, document, project):
    org, user = org_and_user
    c = Chunk(
        org_id=org.id, project_id=project.id, document_id=document.id,
        content="Renewal window opens March 2026", embedding=[0.1] * 1536, chunk_index=0,
    )
    db_session.add(c)
    await db_session.flush()

    def make_mock():
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "obligations": [{
                "type": "renewal_window",
                "description": "Renewal window",
                "clause_text": "Renewal window opens March 2026",
                "due_date": "2026-03-01",
                "date_unresolved": False,
                "confidence": 0.9,
                "chunk_index": 0,
            }]
        })
        return mock_response

    # Extract twice
    for _ in range(2):
        with patch.object(date_extractor_service, "_openai") as mock_openai:
            mock_openai.chat.completions.create = AsyncMock(return_value=make_mock())
            await date_extractor_service.extract_obligations(db_session, document.id, org.id)

    from sqlalchemy import select
    result = await db_session.execute(select(Obligation).where(Obligation.document_id == document.id))
    obs = result.scalars().all()
    assert len(obs) == 1  # not 2


# ── 4. List obligations API ──

@pytest.mark.asyncio
async def test_list_obligations(client: AsyncClient, auth_headers, db_session, org_and_user):
    org, user = org_and_user
    ob = Obligation(
        org_id=org.id, obligation_type="payment_due",
        description="Pay vendor", due_date=date.today() + timedelta(days=10),
        status="open", source="manual", created_by=user.id,
    )
    db_session.add(ob)
    await db_session.flush()

    resp = await client.get("/api/v1/obligations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["description"] == "Pay vendor"


# ── 5. Visibility filter ──

@pytest.mark.asyncio
async def test_list_obligations_respects_visibility(client: AsyncClient, db_session, org_and_two_users, project_doc):
    org, user_a, user_b = org_and_two_users
    proj, doc = project_doc

    ob = Obligation(
        org_id=org.id, document_id=doc.id, project_id=proj.id,
        obligation_type="other", description="Secret obligation",
        status="open", source="auto",
    )
    db_session.add(ob)
    await db_session.flush()

    from tests.conftest import auth_header

    # user_b is NOT a project member and the doc is project-visibility
    resp = await client.get("/api/v1/obligations", headers=auth_header(user_b))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Add user_b as project member
    pm = ProjectMember(project_id=proj.id, user_id=user_b.id, role="viewer")
    db_session.add(pm)
    await db_session.flush()

    resp = await client.get("/api/v1/obligations", headers=auth_header(user_b))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# ── 6. Create manual obligation ──

@pytest.mark.asyncio
async def test_create_manual_obligation(client: AsyncClient, auth_headers, db_session, org_and_user):
    resp = await client.post(
        "/api/v1/obligations",
        json={
            "obligation_type": "payment_due",
            "description": "Invoice #123 due",
            "due_date": "2026-04-15",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source"] == "manual"
    assert data["obligation_type"] == "payment_due"
    assert data["due_date"] == "2026-04-15"


# ── 7. Update obligation status ──

@pytest.mark.asyncio
async def test_update_obligation_status(client: AsyncClient, auth_headers, db_session, org_and_user):
    org, user = org_and_user
    ob = Obligation(
        org_id=org.id, obligation_type="other",
        description="Review contract", status="open", source="manual",
        created_by=user.id,
    )
    db_session.add(ob)
    await db_session.flush()

    resp = await client.patch(
        f"/api/v1/obligations/{ob.id}",
        json={"status": "resolved"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


# ── 8. Delete obligation ──

@pytest.mark.asyncio
async def test_delete_obligation(client: AsyncClient, auth_headers, db_session, org_and_user):
    org, user = org_and_user
    ob = Obligation(
        org_id=org.id, obligation_type="other",
        description="To be deleted", status="open", source="manual",
        created_by=user.id,
    )
    db_session.add(ob)
    await db_session.flush()

    resp = await client.delete(f"/api/v1/obligations/{ob.id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/obligations", headers=auth_headers)
    assert resp.json()["total"] == 0


# ── 9. Upcoming obligations ──

@pytest.mark.asyncio
async def test_upcoming_obligations(client: AsyncClient, auth_headers, db_session, org_and_user):
    org, user = org_and_user
    today = date.today()

    # One due in 5 days (should appear)
    ob1 = Obligation(
        org_id=org.id, obligation_type="payment_due",
        description="Due soon", due_date=today + timedelta(days=5),
        status="open", source="manual", created_by=user.id,
    )
    # One due in 60 days (should NOT appear)
    ob2 = Obligation(
        org_id=org.id, obligation_type="other",
        description="Due later", due_date=today + timedelta(days=60),
        status="open", source="manual", created_by=user.id,
    )
    # One resolved (should NOT appear)
    ob3 = Obligation(
        org_id=org.id, obligation_type="other",
        description="Already done", due_date=today + timedelta(days=3),
        status="resolved", source="manual", created_by=user.id,
    )
    db_session.add_all([ob1, ob2, ob3])
    await db_session.flush()

    resp = await client.get("/api/v1/obligations/upcoming", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["description"] == "Due soon"
