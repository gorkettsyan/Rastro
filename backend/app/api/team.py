import uuid
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.invite import Invite

router = APIRouter(prefix="/team", tags=["team"])


@router.get("")
async def list_team(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.org_id == current_user.org_id).order_by(User.created_at)
    )
    users = result.scalars().all()
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }


@router.post("/invite", status_code=201)
async def create_invite(
    body: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    email = body.get("email", "").strip().lower()
    role = body.get("role", "member")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be admin or member")

    # Check for existing pending invite
    existing = await db.execute(
        select(Invite).where(
            Invite.org_id == current_user.org_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Pending invite already exists for this email")

    token = secrets.token_urlsafe(32)
    invite = Invite(
        org_id=current_user.org_id,
        email=email,
        role=role,
        token=token,
        invited_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.invite_token_expire_hours),
    )
    db.add(invite)
    await db.flush()

    invite_link = f"{settings.app_url}/invite/{token}"
    return {
        "id": str(invite.id),
        "email": invite.email,
        "role": invite.role,
        "token": invite.token,
        "invite_link": invite_link,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.get("/invites")
async def list_invites(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invite).where(
            Invite.org_id == current_user.org_id,
            Invite.accepted_at.is_(None),
        ).order_by(Invite.created_at.desc())
    )
    invites = result.scalars().all()
    return {
        "items": [
            {
                "id": str(inv.id),
                "email": inv.email,
                "role": inv.role,
                "token": inv.token,
                "expires_at": inv.expires_at.isoformat(),
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in invites
        ]
    }


@router.get("/invite/{token}")
async def validate_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at:
        raise HTTPException(status_code=410, detail="Invite already accepted")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite has expired")

    from app.models.organization import Organization
    org_result = await db.execute(select(Organization).where(Organization.id == invite.org_id))
    org = org_result.scalar_one_or_none()

    return {
        "email": invite.email,
        "role": invite.role,
        "org_name": org.name if org else None,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.post("/invite/{token}/accept")
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at:
        raise HTTPException(status_code=410, detail="Invite already accepted")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite has expired")
    if current_user.email != invite.email:
        raise HTTPException(status_code=403, detail="Invite was sent to a different email address")

    # Move user to the inviting org
    current_user.org_id = invite.org_id
    current_user.role = invite.role
    invite.accepted_at = datetime.now(timezone.utc)
    await db.flush()

    return {"detail": "Invite accepted", "org_id": str(invite.org_id)}


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)


@router.patch("/members/{user_id}/role")
async def update_member_role(
    user_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    role = body.get("role", "")
    if role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be admin or member")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    await db.flush()
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role}
