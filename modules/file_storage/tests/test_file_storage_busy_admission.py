"""A contended SQLite quota lock is a retryable 409, not "quota exceeded" (#753)."""

from file_storage import constants, upload_guards
from file_storage_uploads_helpers import API, open_session


async def _busy(_db, _table, *, on_busy):
    raise on_busy


async def test_busy_quota_lock_is_a_retryable_conflict(authenticated_client, storage, monkeypatch):
    storage.settings.quota_bytes = 10
    monkeypatch.setattr(upload_guards, "serialize_sqlite_writes", _busy)
    plain = await authenticated_client.post(
        f"{API}/upload", files={"file": ("a.bin", b"x" * 4, "application/octet-stream")}
    )
    resumable = await open_session(authenticated_client, total=4)
    for response in (plain, resumable):
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == constants.ErrorCode.STORAGE_BUSY
    monkeypatch.undo()
    retried = await authenticated_client.post(
        f"{API}/upload", files={"file": ("a.bin", b"x" * 4, "application/octet-stream")}
    )
    assert retried.status_code == 201
