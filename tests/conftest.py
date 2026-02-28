import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.project import Project
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.invite import Invite
from app.models.project_member import ProjectMember
from app.security import create_jwt

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org_and_user(db_session):
    org = Organization(name="Test Despacho", slug=f"test-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    user = User(
        org_id=org.id,
        email=f"user-{uuid.uuid4().hex[:6]}@test.es",
        full_name="Test User",
        google_id=f"google-{uuid.uuid4().hex}",
    )
    db_session.add(user)
    await db_session.flush()
    return org, user


@pytest_asyncio.fixture
async def auth_headers(org_and_user):
    _, user = org_and_user
    return {"Authorization": f"Bearer {create_jwt(str(user.id))}"}


def auth_header(user: User) -> dict:
    """Build Authorization header for an arbitrary user."""
    return {"Authorization": f"Bearer {create_jwt(str(user.id))}"}


@pytest_asyncio.fixture
async def org_and_two_users(db_session):
    org = Organization(name="Shared Despacho", slug=f"shared-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    user_a = User(
        org_id=org.id,
        email=f"a-{uuid.uuid4().hex[:6]}@test.es",
        full_name="User A",
        google_id=f"google-{uuid.uuid4().hex}",
        role="admin",
    )
    user_b = User(
        org_id=org.id,
        email=f"b-{uuid.uuid4().hex[:6]}@test.es",
        full_name="User B",
        google_id=f"google-{uuid.uuid4().hex}",
        role="member",
    )
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    return org, user_a, user_b


@pytest_asyncio.fixture
async def new_user(db_session):
    """User in a different org — for invite acceptance tests."""
    org = Organization(name="Other Despacho", slug=f"other-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    user = User(
        org_id=org.id,
        email=f"new-{uuid.uuid4().hex[:6]}@test.es",
        full_name="New User",
        google_id=f"google-{uuid.uuid4().hex}",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def project_doc(db_session, org_and_two_users):
    """Document with visibility='project' and project_id set, indexed by user_a."""
    org, user_a, _ = org_and_two_users
    proj = Project(org_id=org.id, title="Members Project", created_by=user_a.id)
    db_session.add(proj)
    await db_session.flush()
    doc = Document(
        org_id=org.id,
        project_id=proj.id,
        title="Project-visible doc",
        source="upload",
        source_id=f"upload-{uuid.uuid4().hex}",
        indexing_status="done",
        chunk_count=0,
        indexed_by_user_id=user_a.id,
        visibility="project",
    )
    db_session.add(doc)
    await db_session.flush()
    return proj, doc


@pytest_asyncio.fixture
async def project(db_session, org_and_user):
    org, user = org_and_user
    p = Project(
        org_id=org.id,
        title="Proyecto Test",
        client_name="Acme S.L.",
        created_by=user.id,
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest_asyncio.fixture
async def document(db_session, org_and_user, project):
    org, user = org_and_user
    doc = Document(
        org_id=org.id,
        project_id=project.id,
        title="Contrato de servicios.pdf",
        source="upload",
        source_id=f"upload-{uuid.uuid4().hex}",
        indexing_status="done",
        chunk_count=2,
        indexed_by_user_id=user.id,
        visibility="private",
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


@pytest_asyncio.fixture
async def chunks_with_embeddings(db_session, org_and_user, project, document):
    """Two chunks with fake 1536-dim embeddings (stored as text in SQLite)."""
    org, _ = org_and_user
    fake_embedding = [0.1] * 1536
    chunks = []
    for i, text_content in enumerate(["Cláusula de confidencialidad", "Términos de pago"]):
        c = Chunk(
            org_id=org.id,
            project_id=project.id,
            document_id=document.id,
            content=text_content,
            embedding=fake_embedding,
            chunk_index=i,
        )
        db_session.add(c)
        chunks.append(c)
    await db_session.flush()
    return chunks


@pytest_asyncio.fixture
async def seed_gmail_doc(db_session, org_and_user):
    org, user = org_and_user
    doc = Document(
        org_id=org.id,
        title="Email thread: Contract review",
        source="gmail",
        source_id=f"gmail-{uuid.uuid4().hex}",
        indexing_status="done",
        chunk_count=1,
        indexed_by_user_id=user.id,
        visibility="private",
    )
    db_session.add(doc)
    await db_session.flush()
    return doc
