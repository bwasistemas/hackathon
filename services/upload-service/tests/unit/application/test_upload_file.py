"""Unit tests for upload application use cases (`upload_file.py`)."""
import uuid
from datetime import datetime, timezone

import pytest

import app.application.upload_file as upload_file_mod
from app.application.upload_file import (
    GetUploadUseCase,
    ListUploadsUseCase,
    UploadFileUseCase,
)
from app.domain.exceptions import FileTooLargeError, MessageQueueError, StorageError
from app.domain.models import Upload, UploadResult


class FakeStorage:
    """Fake `StoragePort` that records calls and optionally fails."""

    def __init__(self, url: str = "https://storage.example/uploads/obj", fail: bool = False):
        self.url = url
        self.fail = fail
        self.calls: list[tuple[bytes, str, str]] = []

    async def upload_file(self, file_content: bytes, object_name: str, content_type: str) -> str:
        self.calls.append((file_content, object_name, content_type))
        if self.fail:
            raise RuntimeError("storage unavailable")
        return self.url


class FakeRepository:
    """Fake `UploadRepositoryPort` for create/list/get."""

    def __init__(self, fail_create: bool = False, uploads: list[Upload] | None = None):
        self.fail_create = fail_create
        self.create_calls: list[dict] = []
        self.list_uploads_calls: list[int] = []
        self.get_calls: list[str] = []
        self._uploads = uploads or []

    async def create_upload(
        self,
        upload_id: str,
        filename: str,
        content_type: str,
        file_size: int,
        file_path: str,
        minio_url: str,
    ) -> None:
        """Mock create upload."""
        if self.fail_create:
            raise RuntimeError("db error")
        self.create_calls.append(
            {
                "upload_id": upload_id,
                "filename": filename,
                "content_type": content_type,
                "file_size": file_size,
                "file_path": file_path,
                "minio_url": minio_url,
            }
        )

    async def get_upload(self, upload_id: str):
        """Mock get upload."""
        self.get_calls.append(upload_id)
        for u in self._uploads:
            if u.id == upload_id:
                return u
        return None

    async def list_uploads(self, limit: int = 50):
        """Mock list uploads."""
        self.list_uploads_calls.append(limit)
        return self._uploads[:limit]

    async def update_status(self, upload_id: str, status: str) -> None:
        """Mock update status."""
        pass


class FakePublisher:
    """Fake `MessagePublisherPort` that records calls and optionally fails."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[dict] = []

    async def publish_upload_event(
        self,
        upload_id: str,
        filename: str,
        file_path: str,
        content_type: str,
    ) -> None:
        if self.fail:
            raise RuntimeError("queue down")
        self.calls.append(
            {
                "upload_id": upload_id,
                "filename": filename,
                "file_path": file_path,
                "content_type": content_type,
            }
        )


def _fixed_upload_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.asyncio
async def test_upload_file_execute_raises_when_content_exceeds_max_size():
    """`UploadFileUseCase.execute` must reject payloads larger than `MAX_FILE_SIZE`."""
    use_case = UploadFileUseCase(
        storage=FakeStorage(),
        repository=FakeRepository(),
        publisher=FakePublisher(),
    )
    big = b"x" * (use_case.MAX_FILE_SIZE + 1)
    with pytest.raises(FileTooLargeError):
        await use_case.execute("f.bin", big, "application/octet-stream")


@pytest.mark.asyncio
async def test_upload_file_execute_success_flow(monkeypatch):
    """On success, storage upload, repository create, and publisher run with consistent IDs and URLs."""
    monkeypatch.setattr(upload_file_mod.uuid, "uuid4", _fixed_upload_id)

    storage = FakeStorage(url="https://minio/bucket/key")
    repository = FakeRepository()
    publisher = FakePublisher()
    use_case = UploadFileUseCase(storage=storage, repository=repository, publisher=publisher)

    content = b"hello"
    result = await use_case.execute("doc.pdf", content, "application/pdf")
    uid = str(_fixed_upload_id())

    assert result == UploadResult(
        id=uid,
        filename="doc.pdf",
        status="RECEIVED",
        message="File uploaded successfully. Processing will start shortly.",
        minio_url="https://minio/bucket/key",
    )

    assert len(storage.calls) == 1
    body, object_name, ctype = storage.calls[0]
    assert body == content
    assert object_name == f"uploads/{uid}_doc.pdf"
    assert ctype == "application/pdf"

    assert len(repository.create_calls) == 1
    row = repository.create_calls[0]
    assert row["upload_id"] == uid
    assert row["filename"] == "doc.pdf"
    assert row["content_type"] == "application/pdf"
    assert row["file_size"] == len(content)
    assert row["file_path"] == "https://minio/bucket/key"
    assert row["minio_url"] == "https://minio/bucket/key"

    assert len(publisher.calls) == 1
    pub = publisher.calls[0]
    assert pub["upload_id"] == uid
    assert pub["filename"] == "doc.pdf"
    assert pub["file_path"] == "https://minio/bucket/key"
    assert pub["content_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_upload_file_execute_wraps_storage_upload_failure():
    """Storage failures during upload must be raised as `StorageError`."""
    use_case = UploadFileUseCase(
        storage=FakeStorage(fail=True),
        repository=FakeRepository(),
        publisher=FakePublisher(),
    )
    with pytest.raises(StorageError, match="Failed to upload file to storage"):
        await use_case.execute("a.txt", b"data", "text/plain")


@pytest.mark.asyncio
async def test_upload_file_execute_wraps_repository_failure(monkeypatch):
    """Repository failures after storage must be raised as `StorageError`."""
    monkeypatch.setattr(upload_file_mod.uuid, "uuid4", _fixed_upload_id)
    use_case = UploadFileUseCase(
        storage=FakeStorage(),
        repository=FakeRepository(fail_create=True),
        publisher=FakePublisher(),
    )
    with pytest.raises(StorageError, match="Failed to save upload metadata"):
        await use_case.execute("a.txt", b"data", "text/plain")


@pytest.mark.asyncio
async def test_upload_file_execute_wraps_publisher_failure(monkeypatch):
    """Publisher failures must be raised as `MessageQueueError`."""
    monkeypatch.setattr(upload_file_mod.uuid, "uuid4", _fixed_upload_id)
    use_case = UploadFileUseCase(
        storage=FakeStorage(),
        repository=FakeRepository(),
        publisher=FakePublisher(fail=True),
    )
    with pytest.raises(MessageQueueError, match="Failed to publish upload event"):
        await use_case.execute("a.txt", b"data", "text/plain")


@pytest.mark.asyncio
async def test_list_uploads_execute_maps_domain_to_results():
    """`ListUploadsUseCase.execute` should map repository `Upload` rows to `UploadResult` list."""
    now = datetime.now(timezone.utc)
    uploads = [
        Upload(
            id="u1",
            filename="a.pdf",
            content_type="application/pdf",
            file_size=10,
            status="DONE",
            file_path="/p",
            created_at=now,
            updated_at=now,
            minio_url="http://m/a",
        ),
    ]
    repo = FakeRepository(uploads=uploads)
    use_case = ListUploadsUseCase(repository=repo)

    out = await use_case.execute(limit=10)
    assert repo.list_uploads_calls == [10]
    assert len(out) == 1
    assert out[0].id == "u1"
    assert out[0].filename == "a.pdf"
    assert out[0].status == "DONE"
    assert out[0].message == ""
    assert out[0].minio_url == "http://m/a"


@pytest.mark.asyncio
async def test_get_upload_execute_returns_upload_when_present():
    """`GetUploadUseCase.execute` should return the upload when the repository finds it."""
    now = datetime.now(timezone.utc)
    u = Upload(
        id="id-1",
        filename="x.png",
        content_type="image/png",
        file_size=5,
        status="RECEIVED",
        file_path="/x",
        created_at=now,
        updated_at=now,
        minio_url=None,
    )
    repo = FakeRepository(uploads=[u])
    use_case = GetUploadUseCase(repository=repo)

    got = await use_case.execute("id-1")
    assert got == u
    assert repo.get_calls == ["id-1"]


@pytest.mark.asyncio
async def test_get_upload_execute_returns_none_when_missing():
    """`GetUploadUseCase.execute` should return None when the upload does not exist."""
    repo = FakeRepository(uploads=[])
    use_case = GetUploadUseCase(repository=repo)

    assert await use_case.execute("missing") is None
    assert repo.get_calls == ["missing"]
