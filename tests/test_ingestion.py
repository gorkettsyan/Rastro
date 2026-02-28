import pytest
import uuid
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_extract_plaintext():
    from app.services.ingestion import extract_text_from_bytes
    text = extract_text_from_bytes("Hola mundo".encode(), "text/plain")
    assert "Hola mundo" in text


@pytest.mark.asyncio
async def test_extract_pdf_no_crash():
    from app.services.ingestion import extract_text_from_bytes
    pdf = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog>>\nendobj\nxref\n0 2\ntrailer\n<<>>\n%%EOF"
    result = extract_text_from_bytes(pdf, "application/pdf")
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_chunk_and_embed_creates_chunks(db_session):
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.document import Document
    from app.models.chunk import Chunk
    from app.services.ingestion import chunk_and_embed
    from sqlalchemy import select

    org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    user = User(org_id=org.id, email="u@test.es", full_name="U", google_id=f"g-{uuid.uuid4().hex}")
    db_session.add(user)
    await db_session.flush()

    doc = Document(org_id=org.id, title="Test", source="upload", indexing_status="indexing", indexed_by_user_id=user.id)
    db_session.add(doc)
    await db_session.flush()

    raw_text = "Esta es una cláusula de contrato muy importante. " * 30

    with patch("app.services.ingestion.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        count = await chunk_and_embed(db_session, doc, raw_text)

    assert count >= 1
    assert doc.indexing_status == "done"
    result = await db_session.execute(select(Chunk).where(Chunk.document_id == doc.id))
    assert len(result.scalars().all()) == count


@pytest.mark.asyncio
async def test_chunk_and_embed_skips_short_text(db_session):
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.document import Document
    from app.services.ingestion import chunk_and_embed

    org = Organization(name="Org2", slug=f"org2-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    user = User(org_id=org.id, email="u2@test.es", full_name="U2", google_id=f"g-{uuid.uuid4().hex}")
    db_session.add(user)
    await db_session.flush()

    doc = Document(org_id=org.id, title="Empty", source="upload", indexing_status="indexing", indexed_by_user_id=user.id)
    db_session.add(doc)
    await db_session.flush()

    count = await chunk_and_embed(db_session, doc, "too short")
    assert count == 0


@pytest.mark.asyncio
async def test_chunk_and_embed_is_idempotent(db_session):
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.document import Document
    from app.models.chunk import Chunk
    from app.services.ingestion import chunk_and_embed
    from sqlalchemy import select

    org = Organization(name="Org3", slug=f"org3-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    user = User(org_id=org.id, email="u3@test.es", full_name="U3", google_id=f"g-{uuid.uuid4().hex}")
    db_session.add(user)
    await db_session.flush()

    doc = Document(org_id=org.id, title="Doc", source="upload", indexing_status="indexing", indexed_by_user_id=user.id)
    db_session.add(doc)
    await db_session.flush()

    text = "Contenido del documento para pruebas de idempotencia. " * 30

    with patch("app.services.ingestion.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 1536]):
        count1 = await chunk_and_embed(db_session, doc, text)
        count2 = await chunk_and_embed(db_session, doc, text)

    result = await db_session.execute(select(Chunk).where(Chunk.document_id == doc.id))
    assert len(result.scalars().all()) == count2
    assert count1 == count2
