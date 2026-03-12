import uuid
import pytest
from httpx import AsyncClient

from app.models.document import Document
from app.models.chunk import Chunk
from app.models.folder_mapping import FolderMapping


@pytest.mark.asyncio
async def test_create_mapping(client: AsyncClient, auth_headers, project):
    resp = await client.post(
        "/api/v1/folder-mappings",
        json={
            "project_id": str(project.id),
            "folder_id": "drive_folder_abc",
            "folder_name": "Contracts",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["folder_id"] == "drive_folder_abc"
    assert data["folder_name"] == "Contracts"
    assert data["project_id"] == str(project.id)


@pytest.mark.asyncio
async def test_create_duplicate_mapping_fails(client: AsyncClient, auth_headers, project):
    body = {
        "project_id": str(project.id),
        "folder_id": "drive_folder_dup",
        "folder_name": "Same Folder",
    }
    resp1 = await client.post("/api/v1/folder-mappings", json=body, headers=auth_headers)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/folder-mappings", json=body, headers=auth_headers)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_list_mappings(client: AsyncClient, auth_headers, project):
    await client.post(
        "/api/v1/folder-mappings",
        json={"project_id": str(project.id), "folder_id": "f1", "folder_name": "Folder 1"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/folder-mappings",
        json={"project_id": str(project.id), "folder_id": "f2", "folder_name": "Folder 2"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/folder-mappings", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_list_mappings_by_project(client: AsyncClient, auth_headers, project, db_session, org_and_user):
    org, user = org_and_user
    from app.models.project import Project
    p2 = Project(org_id=org.id, title="Other Project", created_by=user.id)
    db_session.add(p2)
    await db_session.flush()

    await client.post(
        "/api/v1/folder-mappings",
        json={"project_id": str(project.id), "folder_id": "f1", "folder_name": "Folder 1"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/folder-mappings",
        json={"project_id": str(p2.id), "folder_id": "f2", "folder_name": "Folder 2"},
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/folder-mappings?project_id={project.id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["folder_id"] == "f1"


@pytest.mark.asyncio
async def test_delete_mapping(client: AsyncClient, auth_headers, project):
    resp = await client.post(
        "/api/v1/folder-mappings",
        json={"project_id": str(project.id), "folder_id": "f_del", "folder_name": "ToDelete"},
        headers=auth_headers,
    )
    mapping_id = resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/folder-mappings/{mapping_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/v1/folder-mappings", headers=auth_headers)
    assert len(list_resp.json()["items"]) == 0


@pytest.mark.asyncio
async def test_create_mapping_auto_assigns_existing_docs(
    client: AsyncClient, auth_headers, project, db_session, org_and_user
):
    org, user = org_and_user
    # Create an unassigned Drive doc with a folder_id
    doc = Document(
        org_id=org.id,
        title="Existing Contract.pdf",
        source="drive",
        source_id="drive_file_123",
        drive_folder_id="auto_folder",
        indexing_status="done",
        indexed_by_user_id=user.id,
        chunk_count=1,
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = Chunk(
        document_id=doc.id,
        org_id=org.id,
        content="test chunk",
        chunk_index=0,
    )
    db_session.add(chunk)
    await db_session.flush()

    # Map the folder to the project
    resp = await client.post(
        "/api/v1/folder-mappings",
        json={"project_id": str(project.id), "folder_id": "auto_folder", "folder_name": "AutoFolder"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Verify doc was assigned
    await db_session.refresh(doc)
    assert doc.project_id == project.id

    # Verify chunk was also synced
    await db_session.refresh(chunk)
    assert chunk.project_id == project.id


@pytest.mark.asyncio
async def test_unassigned_documents(client: AsyncClient, auth_headers, db_session, org_and_user):
    org, user = org_and_user
    # Unassigned doc
    doc1 = Document(
        org_id=org.id,
        title="Unassigned.pdf",
        source="upload",
        source_id=f"upload-{uuid.uuid4().hex}",
        indexing_status="done",
        indexed_by_user_id=user.id,
        chunk_count=0,
    )
    # Assigned doc
    from app.models.project import Project
    p = Project(org_id=org.id, title="P", created_by=user.id)
    db_session.add(p)
    await db_session.flush()

    doc2 = Document(
        org_id=org.id,
        project_id=p.id,
        title="Assigned.pdf",
        source="upload",
        source_id=f"upload-{uuid.uuid4().hex}",
        indexing_status="done",
        indexed_by_user_id=user.id,
        chunk_count=0,
    )
    # Gmail doc (should be excluded)
    doc3 = Document(
        org_id=org.id,
        title="Email thread",
        source="gmail",
        source_id=f"gmail-{uuid.uuid4().hex}",
        indexing_status="done",
        indexed_by_user_id=user.id,
        chunk_count=0,
    )
    db_session.add_all([doc1, doc2, doc3])
    await db_session.flush()

    resp = await client.get("/api/v1/folder-mappings/unassigned", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Unassigned.pdf"


@pytest.mark.asyncio
async def test_assign_bulk(client: AsyncClient, auth_headers, project, db_session, org_and_user):
    org, user = org_and_user
    docs = []
    for i in range(3):
        doc = Document(
            org_id=org.id,
            title=f"Doc {i}.pdf",
            source="upload",
            source_id=f"upload-{uuid.uuid4().hex}",
            indexing_status="done",
            indexed_by_user_id=user.id,
            chunk_count=0,
        )
        docs.append(doc)
    db_session.add_all(docs)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/folder-mappings/assign-bulk",
        json={
            "project_id": str(project.id),
            "document_ids": [str(d.id) for d in docs],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["assigned"] == 3

    # Verify assignment
    for doc in docs:
        await db_session.refresh(doc)
        assert doc.project_id == project.id
