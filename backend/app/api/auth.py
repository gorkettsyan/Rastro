import re
import uuid
from datetime import datetime

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.integration_token import IntegrationToken
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import GoogleLoginResponse, UserOut, UserPreferencesUpdate
from app.security import create_jwt, encrypt

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
])


def _make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug}-{str(uuid.uuid4())[:8]}"


def _oauth_client() -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
        scope=GOOGLE_SCOPES,
    )


@router.get("/google/login", response_model=GoogleLoginResponse)
async def google_login():
    """Returns the Google OAuth URL. Frontend redirects the user there."""
    async with _oauth_client() as client:
        uri, state = client.create_authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth",
            access_type="offline",   # get refresh_token
            prompt="consent",        # always show consent to get refresh_token
        )
    return GoogleLoginResponse(auth_url=uri)


@router.get("/google/callback")
async def google_callback(code: str, state: str | None = None, db: AsyncSession = Depends(get_db)):
    """Google redirects here after user consents."""
    async with _oauth_client() as client:
        # Exchange code for tokens
        token = await client.fetch_token(
            "https://oauth2.googleapis.com/token",
            code=code,
        )

        # Fetch user info
        resp = await client.get("https://www.googleapis.com/oauth2/v3/userinfo")
        resp.raise_for_status()
        info = resp.json()

    email: str = info["email"]
    google_id: str = info["sub"]
    full_name: str | None = info.get("name")

    # Upsert user + org
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # First login — create org named after user's email domain
        domain = email.split("@")[1]
        org = Organization(name=domain, slug=_make_slug(domain))
        db.add(org)
        await db.flush()

        user = User(
            org_id=org.id,
            email=email,
            full_name=full_name,
            google_id=google_id,
            role="admin",
        )
        db.add(user)
        await db.flush()
    else:
        # Update name + google_id if changed
        user.full_name = full_name
        user.google_id = google_id

    # Store encrypted Google tokens for PRD 2 ingestion
    expiry = datetime.utcfromtimestamp(token["expires_at"]) if "expires_at" in token else None
    token_result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user.id,
            IntegrationToken.provider == "google",
        )
    )
    integration = token_result.scalar_one_or_none()

    if integration:
        integration.access_token_enc = encrypt(token["access_token"])
        if token.get("refresh_token"):
            integration.refresh_token_enc = encrypt(token["refresh_token"])
        integration.token_expiry = expiry
        integration.scopes = token.get("scope")
    else:
        db.add(IntegrationToken(
            org_id=user.org_id,
            user_id=user.id,
            provider="google",
            access_token_enc=encrypt(token["access_token"]),
            refresh_token_enc=encrypt(token["refresh_token"]) if token.get("refresh_token") else None,
            token_expiry=expiry,
            scopes=token.get("scope"),
        ))

    await db.flush()

    # Issue our own JWT and redirect to frontend
    jwt = create_jwt(str(user.id))
    return RedirectResponse(url=f"{settings.frontend_url}/auth/callback?token={jwt}")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.patch("/me/preferences", response_model=UserOut)
async def update_preferences(
    body: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.learning_mode is not None:
        current_user.learning_mode = body.learning_mode
    await db.flush()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)
