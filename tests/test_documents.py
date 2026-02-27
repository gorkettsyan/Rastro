import io
import pytest
from unittest.mock import patch
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_pdf(client: AsyncClient, auth_headers):
    pdf = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\nxref\n0 2\ntrailer\n<<>>\n%%EOF"
    with patch("app.api.documents.upload_text"), patch("app.api.documents.enqueue"):
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["source"] == "upload"
    assert resp.json()["indexing_status"] == "pending"


@pytest.mark.asyncio
async def test_upload_to_project(client: AsyncClient, auth_headers, project):
    pdf = b"%PDF-1.4\n%%EOF"
    with patch("app.api.documents.upload_text"), patch("app.api.documents.enqueue"):
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.pdf", io.BytesIO(pdf), "application/pdf")},
            data={"project_id": str(project.id)},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["project_id"] == str(project.id)


@pytest.mark.asyncio
async def test_upload_unsupported_type(client: AsyncClient, auth_headers):
    with patch("app.api.documents.upload_text"), patch("app.api.documents.enqueue"):
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("bad.exe", io.BytesIO(b"bin"), "application/octet-stream")},
            headers=auth_headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/documents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_documents_filtered_by_project(client: AsyncClient, auth_headers, project):
    pdf = b"%PDF-1.4\n%%EOF"
    with patch("app.api.documents.upload_text"), patch("app.api.documents.enqueue"):
        await client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
            data={"project_id": str(project.id)},
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/documents/upload",
            files={"file": ("b.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=auth_headers,
        )

    resp = await client.get(f"/api/v1/documents?project_id={project.id}", headers=auth_headers)
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_documents_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/documents")
    assert resp.status_code == 403
