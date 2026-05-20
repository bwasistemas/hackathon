"""Unit tests for AsyncpgFeedbackRepository and NullFeedbackRepository."""
import uuid

import pytest

import app.adapters.outbound.asyncpg_reports as asyncpg_reports
from app.adapters.outbound.asyncpg_reports import (
    AsyncpgFeedbackRepository,
    NullFeedbackRepository,
    parse_asyncpg_dsn,
)


class FakeAcquire:
    """Async context manager that yields a fixed connection."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakePool:
    """Minimal pool stub: `acquire()` returns `FakeAcquire(conn)`."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return FakeAcquire(self._conn)


class FakeConn:
    """Connection stub with configurable `fetchval` / `execute`."""

    def __init__(self):
        self.fetchval_queue: list = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchval(self, query: str, *args):
        if not self.fetchval_queue:
            return None
        return self.fetchval_queue.pop(0)

    async def execute(self, query: str, *args):
        self.execute_calls.append((query, args))


# ---------------------------------------------------------------------------
# parse_asyncpg_dsn
# ---------------------------------------------------------------------------

def test_parse_asyncpg_dsn_parses_standard_url():
    """`parse_asyncpg_dsn` should map a postgresql+asyncpg URL into asyncpg kwargs."""
    url = "postgresql+asyncpg://myuser:mypass@db.example.com:5432/mydb"
    out = parse_asyncpg_dsn(url)
    assert out == {
        "host": "db.example.com",
        "port": 5432,
        "user": "myuser",
        "password": "mypass",
        "database": "mydb",
    }


def test_parse_asyncpg_dsn_preserves_colons_in_password():
    """Password segments after the first colon should be preserved."""
    url = "postgresql+asyncpg://u:pa:ss@h:5432/db"
    out = parse_asyncpg_dsn(url)
    assert out["user"] == "u"
    assert out["password"] == "pa:ss"
    assert out["host"] == "h"
    assert out["port"] == 5432
    assert out["database"] == "db"


# ---------------------------------------------------------------------------
# AsyncpgFeedbackRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_feedback_executes_insert():
    """`create_feedback` should run a single INSERT into the feedback table."""
    conn = FakeConn()
    repo = AsyncpgFeedbackRepository(FakePool(conn))
    uid = str(uuid.uuid4())
    await repo.create_feedback(uid, 4, "good")
    assert len(conn.execute_calls) == 1
    sql, args = conn.execute_calls[0]
    assert "INSERT INTO feedback" in sql
    assert args == (uid, 4, "good")


@pytest.mark.asyncio
async def test_create_feedback_accepts_null_comment():
    """`create_feedback` should pass None as comment without error."""
    conn = FakeConn()
    repo = AsyncpgFeedbackRepository(FakePool(conn))
    await repo.create_feedback(str(uuid.uuid4()), 5, None)
    assert conn.execute_calls[0][1][2] is None


@pytest.mark.asyncio
async def test_get_feedback_stats_returns_avg_and_count():
    """`get_feedback_stats` should return avg_rating and total_feedback."""
    conn = FakeConn()
    conn.fetchval_queue.append(4.2)  # AVG(rating)
    conn.fetchval_queue.append(11)   # COUNT(*)
    repo = AsyncpgFeedbackRepository(FakePool(conn))
    stats = await repo.get_feedback_stats()
    assert stats == {"avg_rating": 4.2, "total_feedback": 11}


@pytest.mark.asyncio
async def test_get_feedback_stats_null_avg_returns_zero():
    """NULL AVG (no rows yet) should yield avg_rating=0.0."""
    conn = FakeConn()
    conn.fetchval_queue.append(None)  # AVG returns NULL
    conn.fetchval_queue.append(0)     # COUNT
    repo = AsyncpgFeedbackRepository(FakePool(conn))
    stats = await repo.get_feedback_stats()
    assert stats["avg_rating"] == 0.0
    assert stats["total_feedback"] == 0


# ---------------------------------------------------------------------------
# NullFeedbackRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_null_feedback_create_is_noop():
    """`NullFeedbackRepository.create_feedback` must not raise."""
    repo = NullFeedbackRepository()
    await repo.create_feedback(str(uuid.uuid4()), 3, "comment")


@pytest.mark.asyncio
async def test_null_feedback_get_feedback_stats_returns_zeros():
    """`NullFeedbackRepository.get_feedback_stats` should return zeroed dict."""
    repo = NullFeedbackRepository()
    stats = await repo.get_feedback_stats()
    assert stats == {"avg_rating": 0.0, "total_feedback": 0}


# ---------------------------------------------------------------------------
# create_feedback_repository factory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_feedback_repository_returns_null_when_url_empty():
    """Empty URL should yield a NullFeedbackRepository and no pool."""
    repo, pool = await asyncpg_reports.create_feedback_repository("")
    assert pool is None
    assert isinstance(repo, NullFeedbackRepository)


@pytest.mark.asyncio
async def test_create_feedback_repository_returns_adapter_when_pool_succeeds(monkeypatch):
    """Successful pool creation should yield AsyncpgFeedbackRepository and the pool."""
    conn = FakeConn()
    fake_pool = FakePool(conn)

    async def fake_create_pool(**kwargs):
        assert kwargs["host"] == "localhost"
        return fake_pool

    monkeypatch.setattr(asyncpg_reports.asyncpg, "create_pool", fake_create_pool)
    url = "postgresql+asyncpg://u:p@localhost:5432/db"
    repo, returned_pool = await asyncpg_reports.create_feedback_repository(url)
    assert returned_pool is fake_pool
    assert isinstance(repo, AsyncpgFeedbackRepository)
    assert any("CREATE TABLE" in call[0] for call in conn.execute_calls)


@pytest.mark.asyncio
async def test_create_feedback_repository_returns_null_on_pool_failure(monkeypatch, caplog):
    """Pool creation failure should yield NullFeedbackRepository and no pool."""
    import logging

    async def boom(**kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(asyncpg_reports.asyncpg, "create_pool", boom)
    with caplog.at_level(logging.ERROR):
        repo, pool = await asyncpg_reports.create_feedback_repository(
            "postgresql+asyncpg://u:p@localhost:5432/db"
        )
    assert pool is None
    assert isinstance(repo, NullFeedbackRepository)
