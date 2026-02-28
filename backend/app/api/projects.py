import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut, ProjectList

router = APIRouter(prefix="/projects", tags=["projects"])


async def _assert_project_access(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> Project:
    """Return project if user is in same org, else 404."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.org_id == user.org_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _assert_project_owner_or_admin(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> Project:
    """Return project if user is org admin or project owner, else 403."""
    project = await _assert_project_access(project_id, user, db)
    if user.role == "admin":
        return project
    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
            ProjectMember.role == "owner",
        )
    )
    if not member_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Owner or admin access required")
    return project


@router.get("", response_model=ProjectList)
async def list_projects(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Project).where(Project.org_id == current_user.org_id)
    if status:
        q = q.where(Project.status == status)
    result = await db.execute(q.order_by(Project.updated_at.desc()))
    items = result.scalars().all()
    return ProjectList(items=items, total=len(items))


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = Project(org_id=current_user.org_id, created_by=current_user.id, **body.model_dump())
    db.add(project)
    await db.flush()

    # Auto-add creator as project owner
    membership = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(membership)
    await db.flush()

    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.org_id == current_user.org_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.org_id == current_user.org_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(project, field, val)
    await db.flush()
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.org_id == current_user.org_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)


# ── Project membership endpoints ──


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_project_access(project_id, current_user, db)
    result = await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    )
    rows = result.all()
    return {
        "items": [
            {
                "id": str(pm.id),
                "user_id": str(pm.user_id),
                "email": u.email,
                "full_name": u.full_name,
                "role": pm.role,
                "created_at": pm.created_at.isoformat() if pm.created_at else None,
            }
            for pm, u in rows
        ]
    }


@router.post("/{project_id}/members", status_code=201)
async def add_project_member(
    project_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_project_owner_or_admin(project_id, current_user, db)

    user_id = body.get("user_id")
    role = body.get("role", "viewer")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if role not in ("owner", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be owner, editor, or viewer")

    user_id = uuid.UUID(user_id)
    # Verify user belongs to the same org
    target = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    if not target.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found in organization")

    # Check for duplicate
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a project member")

    membership = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    db.add(membership)
    await db.flush()
    return {
        "id": str(membership.id),
        "user_id": str(membership.user_id),
        "role": membership.role,
    }


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_project_owner_or_admin(project_id, current_user, db)
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(member)


@router.patch("/{project_id}/members/{user_id}/role")
async def update_project_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_project_owner_or_admin(project_id, current_user, db)
    role = body.get("role", "")
    if role not in ("owner", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be owner, editor, or viewer")
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = role
    await db.flush()
    return {"id": str(member.id), "user_id": str(member.user_id), "role": member.role}
