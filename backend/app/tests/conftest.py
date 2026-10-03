import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
from app.main import app
from app.db.session import Base, get_db
from app.core.rate_limit import limiter
from app.models.models import UserRole
from app.services.user_service import create_user
from app.schemas.schemas import UserCreate

# ── Test database ─────────────────────────────────────────────────────────────
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://codifyai:changeme@localhost:5432/codifyai_test"
)

test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)

USER_PASSWORD = "TestPass123!"
ADMIN_PASSWORD = "AdminPass123!"


@pytest.fixture(autouse=True)
def no_rate_limits():
    """Rate limits are exercised explicitly in test_rate_limit; off elsewhere."""
    limiter.enabled = False
    limiter.reset()
    yield
    limiter.enabled = False


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create all tables once per test session, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db():
    """
    Isolated DB session per test. Everything runs inside one outer transaction
    that is rolled back at the end; the session uses SAVEPOINTs, so commit() and
    rollback() inside app code behave as they do in production.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest_asyncio.fixture
async def client(db):
    """HTTP test client whose get_db mirrors the real one: commit on success,
    roll back on any exception (including HTTPException)."""
    async def override_get_db():
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def make_user(db, email, password=USER_PASSWORD, role=UserRole.coder, name="Test User"):
    user = await create_user(db, UserCreate(email=email, password=password, full_name=name), role=role)
    await db.commit()
    return user


async def login(client, email, password=USER_PASSWORD):
    res = await client.post("/api/v1/auth/token", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res


@pytest_asyncio.fixture
async def test_user(db):
    """A regular coder user."""
    return await make_user(db, "testcoder@codifyai.com", name="Test Coder")


@pytest_asyncio.fixture
async def admin_user(db):
    return await make_user(db, "admin@codifyai.com", ADMIN_PASSWORD, UserRole.admin, "Ada Admin")


@pytest_asyncio.fixture
async def auth_headers(client, test_user):
    """Auth headers for an authenticated test user."""
    res = await login(client, "testcoder@codifyai.com")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client, admin_user):
    res = await login(client, "admin@codifyai.com", ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
