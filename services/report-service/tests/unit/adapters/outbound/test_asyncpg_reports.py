"""Unit tests for asyncpg report/feedback adapters (`asyncpg_reports.py`)."""
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

import app.adapters.outbound.asyncpg_reports as asyncpg_reports
from app.adapters.outbound.asyncpg_reports import (
    AsyncpgFeedbackRepository,
    AsyncpgReportRepository,
    NullFeedbackRepository,
    NullReportRepository,
    parse_asyncpg_dsn,
)
from app.domain.models import Report, ReportSummary, Statistics


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
        """Mock acquire."""
        return FakeAcquire(self._conn)


class FakeConn:
    """Connection stub with configurable `fetchrow` / `fetch` / `fetchval` / `execute`."""

    def __init__(self):
        self.fetchrow_queue: list = []
        self.fetch_queue: list = []
        self.fetchval_queue: list = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query: str, *args):
        """Mock fetchrow."""
        if not self.fetchrow_queue:
            return None
        return self.fetchrow_queue.pop(0)

    async def fetch(self, query: str, *args):
        """Mock fetch."""
        if not self.fetch_queue:
            return []
        return self.fetch_queue.pop(0)

    async def fetchval(self, query: str, *args):
        """Mock fetchval."""
        if not self.fetchval_queue:
            return None
        return self.fetchval_queue.pop(0)

    async def execute(self, query: str, *args):
        """Mock execute."""
        self.execute_calls.append((query, args))


def test_parse_asyncpg_dsn_parses_standard_url():
    """`parse_asyncpg_dsn` should map a postgresql+asyncpg URL into asyncpg connect kwargs."""
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
    """Password segments after the first colon should be preserved (joined back with `:`)."""
    url = "postgresql+asyncpg://u:pa:ss@h:5432/db"
    out = parse_asyncpg_dsn(url)
    assert out["user"] == "u"
    assert out["password"] == "pa:ss"
    assert out["host"] == "h"
    assert out["port"] == 5432
    assert out["database"] == "db"


@pytest.mark.asyncio
async def test_asyncpg_report_repository_get_report_parses_json_file_path():
    """When `file_path` holds JSON, `get_report` should populate `analysis` from it."""
    uid = uuid.uuid4()
    created = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    conn = FakeConn()
    conn.fetchrow_queue.append(
        {
            "id": uid,
            "filename": "d.pdf",
            "status": "DONE",
            "file_path": json.dumps({"components": []}),
            "created_at": created,
        }
    )
    repo = AsyncpgReportRepository(FakePool(conn))
    report = await repo.get_report(str(uid))
    assert report == Report(
        id=str(uid),
        filename="d.pdf",
        status="DONE",
        analysis={"components": []},
        created_at=created,
    )


@pytest.mark.asyncio
async def test_asyncpg_report_repository_get_report_non_json_file_path_becomes_raw():
    """Invalid JSON in `file_path` should yield `analysis == {"raw": ...}`."""
    uid = uuid.uuid4()
    created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    conn = FakeConn()
    conn.fetchrow_queue.append(
        {
            "id": uid,
            "filename": "x.txt",
            "status": "PENDING",
            "file_path": "not-json{",
            "created_at": created,
        }
    )
    repo = AsyncpgReportRepository(FakePool(conn))
    report = await repo.get_report(str(uid))
    assert report is not None
    assert report.analysis == {"raw": "not-json{"}


@pytest.mark.asyncio
async def test_asyncpg_report_repository_get_report_empty_file_path():
    """Falsy `file_path` should leave `analysis` as an empty dict."""
    uid = uuid.uuid4()
    created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    conn = FakeConn()
    conn.fetchrow_queue.append(
        {
            "id": uid,
            "filename": "x.txt",
            "status": "NEW",
            "file_path": None,
            "created_at": created,
        }
    )
    repo = AsyncpgReportRepository(FakePool(conn))
    report = await repo.get_report(str(uid))
    assert report is not None
    assert report.analysis == {}


@pytest.mark.asyncio
async def test_asyncpg_report_repository_get_report_returns_none_when_missing():
    """`get_report` should return None when no row exists."""
    conn = FakeConn()
    conn.fetchrow_queue.append(None)
    repo = AsyncpgReportRepository(FakePool(conn))
    assert await repo.get_report("missing-id") is None


@pytest.mark.asyncio
async def test_asyncpg_report_repository_list_reports_with_status_uppercases_filter():
    """`list_reports` with a status should query with `status.upper()` and map rows."""
    created = datetime(2024, 6, 1, tzinfo=timezone.utc)
    row = {
        "id": uuid.uuid4(),
        "filename": "a.pdf",
        "status": "DONE",
        "created_at": created,
    }
    conn = FakeConn()

    async def capture_fetch(query, *args):
        assert "WHERE status = $1" in query
        assert args[0] == "DONE"
        assert args[1] == 10
        return [row]

    conn.fetch = capture_fetch  # type: ignore[method-assign]

    repo = AsyncpgReportRepository(FakePool(conn))
    out = await repo.list_reports("done", 10)
    assert len(out) == 1
    assert out[0] == ReportSummary(
        id=str(row["id"]),
        filename="a.pdf",
        status="DONE",
        created_at=created,
    )


@pytest.mark.asyncio
async def test_asyncpg_report_repository_list_reports_without_status():
    """`list_reports` without status should omit status filter and pass limit only."""
    created = datetime(2024, 6, 2, tzinfo=timezone.utc)
    row = {
        "id": uuid.uuid4(),
        "filename": "b.pdf",
        "status": "NEW",
        "created_at": created,
    }
    conn = FakeConn()

    async def capture_fetch(query, *args):
        assert "WHERE status" not in query
        assert args == (5,)
        return [row]

    conn.fetch = capture_fetch  # type: ignore[method-assign]

    repo = AsyncpgReportRepository(FakePool(conn))
    out = await repo.list_reports(None, 5)
    assert len(out) == 1
    assert out[0].filename == "b.pdf"


@pytest.mark.asyncio
async def test_asyncpg_report_repository_check_upload_exists():
    """`check_upload_exists` should be True iff `fetchrow` returns a row."""
    conn = FakeConn()
    conn.fetchrow_queue.append({"id": uuid.uuid4()})
    repo_true = AsyncpgReportRepository(FakePool(conn))
    assert await repo_true.check_upload_exists("any") is True

    conn2 = FakeConn()
    conn2.fetchrow_queue.append(None)
    repo_false = AsyncpgReportRepository(FakePool(conn2))
    assert await repo_false.check_upload_exists("any") is False


@pytest.mark.asyncio
async def test_asyncpg_feedback_repository_create_feedback_runs_schema_and_insert():
    """`create_feedback` should run CREATE TABLE IF NOT EXISTS then INSERT."""
    conn = FakeConn()
    repo = AsyncpgFeedbackRepository(FakePool(conn))
    await repo.create_feedback(str(uuid.uuid4()), 4, "ok")
    assert len(conn.execute_calls) == 2
    assert "CREATE TABLE IF NOT EXISTS feedback" in conn.execute_calls[0][0]
    assert "INSERT INTO feedback" in conn.execute_calls[1][0]


@pytest.mark.asyncio
async def test_asyncpg_feedback_repository_get_statistics():
    """`get_statistics` should aggregate uploads and feedback from SQL results."""
    conn = FakeConn()
    conn.fetchval_queue.append(7)  # total uploads
    conn.fetch_queue.append(
        [
            {"status": "DONE", "count": 3},
            {"status": "NEW", "count": 4},
        ]
    )
    conn.fetchval_queue.append(4.2)  # avg_rating
    conn.fetchval_queue.append(11)  # total_feedback

    repo = AsyncpgFeedbackRepository(FakePool(conn))
    stats = await repo.get_statistics()
    assert stats == Statistics(
        total_uploads=7,
        by_status={"DONE": 3, "NEW": 4},
        avg_rating=4.2,
        total_feedback=11,
    )


@pytest.mark.asyncio
async def test_asyncpg_feedback_repository_get_statistics_null_avg_rating():
    """When AVG returns NULL, `avg_rating` should be 0.0."""
    conn = FakeConn()
    conn.fetchval_queue.append(0)
    conn.fetch_queue.append([])
    conn.fetchval_queue.append(None)
    conn.fetchval_queue.append(0)

    repo = AsyncpgFeedbackRepository(FakePool(conn))
    stats = await repo.get_statistics()
    assert stats.avg_rating == 0.0
    assert stats.total_feedback == 0


@pytest.mark.asyncio
async def test_null_report_repository_returns_empty_defaults():
    """Null report repository should behave as no-op / empty results."""
    n = NullReportRepository()
    assert await n.get_report("x") is None
    assert await n.list_reports(None, 10) == []
    assert await n.check_upload_exists("x") is False


@pytest.mark.asyncio
async def test_null_feedback_repository_returns_empty_statistics():
    """Null feedback repository should return zeroed statistics."""
    n = NullFeedbackRepository()
    await n.create_feedback("u", 5, None)  # no-op
    s = await n.get_statistics()
    assert s == Statistics(
        total_uploads=0,
        by_status={},
        avg_rating=0.0,
        total_feedback=0,
    )


@pytest.mark.asyncio
async def test_create_repositories_returns_nulls_when_url_empty():
    """Empty database URL should yield null repositories and no pool."""
    r, f, pool = await asyncpg_reports.create_repositories("")
    assert pool is None
    assert isinstance(r, NullReportRepository)
    assert isinstance(f, NullFeedbackRepository)


@pytest.mark.asyncio
async def test_create_repositories_returns_adapters_when_pool_succeeds(monkeypatch):
    """When `create_pool` succeeds, real async adapters and pool should be returned."""

    class DummyPool:
        pass

    async def fake_create_pool(**kwargs):
        assert kwargs["host"] == "localhost"
        return DummyPool()

    monkeypatch.setattr(asyncpg_reports.asyncpg, "create_pool", fake_create_pool)
    url = "postgresql+asyncpg://u:p@localhost:5432/db"
    r, f, pool = await asyncpg_reports.create_repositories(url)
    assert isinstance(pool, DummyPool)
    assert isinstance(r, AsyncpgReportRepository)
    assert isinstance(f, AsyncpgFeedbackRepository)


@pytest.mark.asyncio
async def test_create_repositories_returns_nulls_when_pool_raises(monkeypatch, caplog):
    """On pool creation failure, null repositories and None pool should be returned."""
    import logging

    async def boom(**kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(asyncpg_reports.asyncpg, "create_pool", boom)
    with caplog.at_level(logging.ERROR):
        r, f, pool = await asyncpg_reports.create_repositories(
            "postgresql+asyncpg://u:p@localhost:5432/db"
        )
    assert pool is None
    assert isinstance(r, NullReportRepository)
    assert isinstance(f, NullFeedbackRepository)
    assert "Failed to initialize report repositories" in caplog.text
