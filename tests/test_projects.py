import pytest
import uuid
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "Proyecto Nuevo", "client_name": "López S.L."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Proyecto Nuevo"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers, project):
    resp = await client.get("/api/v1/projects", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any(p["title"] == project.title for p in resp.json()["items"])


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers, project):
    resp = await client.get(f"/api/v1/projects/{project.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(project.id)


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient, auth_headers):
    resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers, project):
    resp = await client.patch(
        f"/api/v1/projects/{project.id}",
        json={"status": "closed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers, project):
    resp = await client.delete(f"/api/v1/projects/{project.id}", headers=auth_headers)
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/projects/{project.id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_projects_isolated_by_org(client: AsyncClient, db_session):
    """Projects from another org must not be visible."""
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.project import Project
    from app.security import create_jwt

    org_a = Organization(name="Org A", slug=f"org-a-{uuid.uuid4().hex[:6]}")
    org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:6]}")
    db_session.add_all([org_a, org_b])
    await db_session.flush()

    user_a = User(org_id=org_a.id, email="a@test.es", google_id="ga")
    user_b = User(org_id=org_b.id, email="b@test.es", google_id="gb")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    project_b = Project(org_id=org_b.id, title="Secret Project", created_by=user_b.id)
    db_session.add(project_b)
    await db_session.flush()

    headers_a = {"Authorization": f"Bearer {create_jwt(str(user_a.id))}"}
    resp = await client.get("/api/v1/projects", headers=headers_a)
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["items"]]
    assert str(project_b.id) not in ids


@pytest.mark.asyncio
async def test_projects_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 403
