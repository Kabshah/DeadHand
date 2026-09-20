"""tests/conftest.py — Shared pytest fixtures."""
import asyncio
import pytest
import fakeredis

from unittest.mock import patch


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def fake_redis():
    """fakeredis server with Lua support (lupa installed)."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    return client


@pytest.fixture(autouse=False)
def patch_redis(fake_redis):
    """Patch get_redis() globally to return the fakeredis client."""
    with patch("app.core.redis_client._client", fake_redis):
        yield fake_redis
