import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.security import create_jwt, encrypt, decrypt
from app.models.user import User
from app.models.organization import Organization


# ── Security unit tests ────────────────────────────────────────────────────


def test_create_and_decode_jwt():
    from app.security import decode_jwt
    token = create_jwt("test-user-id")
    assert decode_jwt(token) == "test-user-id"


def test_jwt_invalid_raises():
    from app.security import decode_jwt
    from jose import JWTError
    with pytest.raises(JWTError):
        decode_jwt("not.a.valid.token")


def test_encrypt_decrypt_roundtrip():
    secret = "super-secret-google-token"
    assert decrypt(encrypt(secret)) == secret


def test_encrypt_produces_different_output():
    val = "same-value"
    # Fernet produces non-deterministic ciphertext
    assert encrypt(val) != val


# ── Health check ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Google login URL ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_login_returns_auth_url(client: AsyncClient):
    resp = await client.get("/api/v1/auth/google/login")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]
    assert "drive.readonly" in data["auth_url"]
    assert "gmail.readonly" in data["auth_url"]


# ── Google callback ────────────────────────────────────────────────────────


def _mock_token():
    return {
        "access_token": "ya29.mock-access-token",
        "refresh_token": "1//mock-refresh-token",
        "expires_at": 9999999999,
        "scope": "openid email profile https://www.googleapis.com/auth/drive.readonly",
    }


def _mock_userinfo():
    return {
        "sub": "google-id-12345",
        "email": "abogado@despacho.es",
        "name": "María García",
    }


@pytest.mark.asyncio
async def test_google_callback_creates_user_and_redirects(client: AsyncClient):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.fetch_token = AsyncMock(return_value=_mock_token())

    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_userinfo()
    mock_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.api.auth._oauth_client", return_value=mock_client):
        resp = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "mock-code", "state": "mock-state"},
            follow_redirects=False,
        )

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "/auth/callback?token=" in location


@pytest.mark.asyncio
async def test_google_callback_second_login_updates_user(client: AsyncClient):
    """Second login with same email updates the user, does not create duplicate."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.fetch_token = AsyncMock(return_value=_mock_token())

    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_userinfo()
    mock_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.api.auth._oauth_client", return_value=mock_client):
        # First login
        await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code-1", "state": "state-1"},
            follow_redirects=False,
        )
        # Second login
        resp = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code-2", "state": "state-2"},
            follow_redirects=False,
        )

    assert resp.status_code == 307


# ── /auth/me ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_user_with_valid_jwt(client: AsyncClient, db_session):
    # Seed a user directly
    import uuid
    org = Organization(name="Test Despacho", slug=f"test-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    user = User(
        org_id=org.id,
        email="test@despacho.es",
        full_name="Test User",
        google_id="google-test-id",
    )
    db_session.add(user)
    await db_session.flush()

    token = create_jwt(str(user.id))
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@despacho.es"
    assert data["full_name"] == "Test User"


@pytest.mark.asyncio
async def test_me_returns_401_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 403  # HTTPBearer returns 403 when no header


@pytest.mark.asyncio
async def test_me_returns_401_with_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
