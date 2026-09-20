"""tests/test_ip_account_limit.py — Test 1 Account per IP policy."""
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.oauth import upsert_user
from app.switches.models import Base, User


@pytest.fixture
async def db_session():
    """In-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_first_user_signup_from_ip_succeeds(db_session: AsyncSession):
    profile = {"sub": "google_sub_101", "email": "user1@example.com"}
    client_ip = "192.168.1.50"

    user = await upsert_user(db_session, profile, client_ip=client_ip)
    assert user.id is not None
    assert user.created_ip == client_ip


@pytest.mark.asyncio
async def test_second_user_signup_from_same_ip_is_blocked(db_session: AsyncSession):
    profile1 = {"sub": "google_sub_101", "email": "user1@example.com"}
    profile2 = {"sub": "google_sub_102", "email": "user2@example.com"}
    client_ip = "192.168.1.50"

    # First signup succeeds
    await upsert_user(db_session, profile1, client_ip=client_ip)

    # Second signup from same IP fails with 400
    with pytest.raises(HTTPException) as exc_info:
        await upsert_user(db_session, profile2, client_ip=client_ip)

    assert exc_info.value.status_code == 400
    assert "already been registered from this IP address" in exc_info.value.detail


@pytest.mark.asyncio
async def test_existing_user_login_from_same_ip_succeeds(db_session: AsyncSession):
    profile1 = {"sub": "google_sub_101", "email": "user1@example.com"}
    client_ip = "192.168.1.50"

    user1 = await upsert_user(db_session, profile1, client_ip=client_ip)

    # Existing user re-login from same IP succeeds
    user1_relogin = await upsert_user(db_session, profile1, client_ip=client_ip)
    assert user1_relogin.id == user1.id
