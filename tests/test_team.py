import pytest
from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header
from app.models.invite import Invite


@pytest.mark.asyncio
async def test_admin_can_invite(client, db_session, org_and_two_users):
    """Admin (user_a) can create an invite."""
    org, user_a, user_b = org_and_two_users
    headers = auth_header(user_a)
    resp = await client.post(
        "/api/v1/team/invite",
        json={"email": "invite-target@test.es", "role": "member"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "invite-target@test.es"
    assert data["role"] == "member"
    assert "token" in data
    assert "invite_link" in data


@pytest.mark.asyncio
async def test_member_cannot_invite(client, db_session, org_and_two_users):
    """Non-admin (user_b, role=member) cannot create an invite."""
    _, _, user_b = org_and_two_users
    headers = auth_header(user_b)
    resp = await client.post(
        "/api/v1/team/invite",
        json={"email": "someone@test.es", "role": "member"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_validate_invite_token(client, db_session, org_and_two_users):
    """Public endpoint validates a pending invite token."""
    org, user_a, _ = org_and_two_users
    invite = Invite(
        org_id=org.id,
        email="validate@test.es",
        role="member",
        token="test-token-validate",
        invited_by=user_a.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db_session.add(invite)
    await db_session.flush()

    resp = await client.get("/api/v1/team/invite/test-token-validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "validate@test.es"
    assert data["role"] == "member"


@pytest.mark.asyncio
async def test_accept_invite_joins_org(client, db_session, org_and_two_users, new_user):
    """Accepting an invite moves the user to the inviting org."""
    org, user_a, _ = org_and_two_users
    invite = Invite(
        org_id=org.id,
        email=new_user.email,
        role="member",
        token="test-token-accept",
        invited_by=user_a.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db_session.add(invite)
    await db_session.flush()

    headers = auth_header(new_user)
    resp = await client.post("/api/v1/team/invite/test-token-accept/accept", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["org_id"] == str(org.id)

    await db_session.refresh(new_user)
    assert new_user.org_id == org.id
    assert new_user.role == "member"


@pytest.mark.asyncio
async def test_wrong_email_rejected(client, db_session, org_and_two_users, new_user):
    """Invite sent to different email cannot be accepted by another user."""
    org, user_a, _ = org_and_two_users
    invite = Invite(
        org_id=org.id,
        email="someone-else@test.es",
        role="member",
        token="test-token-wrong",
        invited_by=user_a.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db_session.add(invite)
    await db_session.flush()

    headers = auth_header(new_user)
    resp = await client.post("/api/v1/team/invite/test-token-wrong/accept", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_invite_409(client, db_session, org_and_two_users):
    """Creating a second pending invite for the same email returns 409."""
    org, user_a, _ = org_and_two_users
    headers = auth_header(user_a)

    resp1 = await client.post(
        "/api/v1/team/invite",
        json={"email": "dup@test.es", "role": "member"},
        headers=headers,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/team/invite",
        json={"email": "dup@test.es", "role": "member"},
        headers=headers,
    )
    assert resp2.status_code == 409
