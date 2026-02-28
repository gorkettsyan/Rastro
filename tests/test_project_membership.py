import pytest

from tests.conftest import auth_header
from app.models.project_member import ProjectMember


@pytest.mark.asyncio
async def test_add_member_to_project(client, db_session, org_and_two_users, project_doc):
    """Admin can add a user as project member."""
    org, user_a, user_b = org_and_two_users
    proj, _ = project_doc
    headers = auth_header(user_a)

    resp = await client.post(
        f"/api/v1/projects/{proj.id}/members",
        json={"user_id": str(user_b.id), "role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == str(user_b.id)
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_project_member_sees_project_docs(client, db_session, org_and_two_users, project_doc):
    """A project member can see documents with visibility='project'."""
    org, user_a, user_b = org_and_two_users
    proj, doc = project_doc

    # Add user_b as project member
    pm = ProjectMember(project_id=proj.id, user_id=user_b.id, role="viewer")
    db_session.add(pm)
    await db_session.flush()

    headers = auth_header(user_b)
    resp = await client.get(f"/api/v1/documents?project_id={proj.id}", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(d["id"] == str(doc.id) for d in items)


@pytest.mark.asyncio
async def test_non_member_cannot_see_project_docs(client, db_session, org_and_two_users, project_doc):
    """A non-member cannot see documents with visibility='project'."""
    _, _, user_b = org_and_two_users
    proj, doc = project_doc

    headers = auth_header(user_b)
    resp = await client.get(f"/api/v1/documents?project_id={proj.id}", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert not any(d["id"] == str(doc.id) for d in items)


@pytest.mark.asyncio
async def test_viewer_cannot_add_members(client, db_session, org_and_two_users, project_doc):
    """A member with role='member' (not org admin/project owner) cannot add project members."""
    org, user_a, user_b = org_and_two_users
    proj, _ = project_doc

    # Give user_b viewer membership (not owner)
    pm = ProjectMember(project_id=proj.id, user_id=user_b.id, role="viewer")
    db_session.add(pm)
    await db_session.flush()

    headers = auth_header(user_b)
    resp = await client.post(
        f"/api/v1/projects/{proj.id}/members",
        json={"user_id": str(user_a.id), "role": "editor"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_member_409(client, db_session, org_and_two_users, project_doc):
    """Adding the same user twice returns 409."""
    org, user_a, user_b = org_and_two_users
    proj, _ = project_doc
    headers = auth_header(user_a)

    resp1 = await client.post(
        f"/api/v1/projects/{proj.id}/members",
        json={"user_id": str(user_b.id), "role": "viewer"},
        headers=headers,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/v1/projects/{proj.id}/members",
        json={"user_id": str(user_b.id), "role": "editor"},
        headers=headers,
    )
    assert resp2.status_code == 409
