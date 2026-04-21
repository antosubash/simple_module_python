"""Unit tests for ``datasets.tasks.extract_metadata_task``.

The task runs in a Celery worker — its DB goes through
``background_tasks.sync_db`` (sync engine reading ``SM_DATABASE_URL``)
and its bytes come from ``file_storage.build_backend`` (which builds
from ``FileStorageSettings()``, pydantic defaults). Both are independent
of the async test ``app`` fixture, so each test points them at tmp paths
for isolation: ``SM_DATABASE_URL`` via env (still host-level) and the
storage root by monkeypatching ``FileStorageSettings`` to pre-fill the
``fs_root_path`` kwarg.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

GEOJSON_SAMPLE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [10.5, 20.5]},
            "properties": {"name": "A"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-5.0, 0.0]},
            "properties": {"name": "B"},
        },
    ],
}


def _isolate_worker_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    """Configure ``sync_db`` + file_storage backend to point at tmp paths.

    Returns ``(sync_db_file, fs_root)``.
    """
    from background_tasks import sync_db
    from datasets.models import Dataset as _Dataset
    from file_storage import settings as fs_settings
    from file_storage.settings import FileStorageSettings as _RealFileStorageSettings

    db_file = tmp_path / "worker.db"
    fs_root = tmp_path / "fs"
    fs_root.mkdir()

    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite:///{db_file}")

    # The worker (``datasets.tasks._download_to_tempfile``) constructs
    # ``FileStorageSettings()`` with no args — pydantic defaults only, no
    # env reads any more. Swap in a factory that pre-fills the tmp root so
    # the worker sees this test's filesystem backend without a shared DB.
    def _factory(**kwargs: object) -> _RealFileStorageSettings:
        return _RealFileStorageSettings(
            backend="filesystem",
            fs_root_path=str(fs_root),
            **kwargs,
        )

    monkeypatch.setattr(fs_settings, "FileStorageSettings", _factory)

    # Reset the process-global sync engine so the new URL is picked up.
    sync_db._engine = None
    sync_db._session_factory = None

    factory = sync_db.get_sync_session_factory()
    _Dataset.metadata.create_all(factory.kw["bind"])
    return db_file, fs_root


def _teardown_sync_engine() -> None:
    from background_tasks import sync_db

    if sync_db._engine is not None:
        sync_db._engine.dispose()
    sync_db._engine = None
    sync_db._session_factory = None


def test_task_fills_in_bbox_and_feature_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from background_tasks import sync_db
    from datasets.models import Dataset
    from datasets.tasks import extract_metadata_task
    from file_storage.backends.filesystem import FilesystemBackend

    _, fs_root = _isolate_worker_env(tmp_path, monkeypatch)

    payload = json.dumps(GEOJSON_SAMPLE).encode()
    backend = FilesystemBackend(root=fs_root)
    storage_key = "datasets/1/sample.geojson"

    async def _seed_bytes():
        async def stream():
            yield payload

        await backend.put(
            storage_key, stream(), content_type="application/geo+json", size=len(payload)
        )

    asyncio.run(_seed_bytes())

    factory = sync_db.get_sync_session_factory()
    with factory() as session:
        row = Dataset(
            name="Worker Test",
            slug="worker-test",
            kind="vector_geojson",
            original_filename="sample.geojson",
            mime_type="application/geo+json",
            size_bytes=len(payload),
            storage_key=storage_key,
            extraction_status="pending",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        dataset_id = row.id

    try:
        result = extract_metadata_task(dataset_id)
        assert result["status"] == "ok"
        assert result["feature_count"] == 2
        assert result["crs"] == "EPSG:4326"

        with factory() as session:
            row = session.get(Dataset, dataset_id)
            assert row is not None
            assert row.extraction_status == "ok"
            assert row.feature_count == 2
            assert row.crs == "EPSG:4326"
            assert row.bbox_min_x == -5.0
            assert row.bbox_max_x == 10.5
    finally:
        _teardown_sync_engine()


def test_task_on_missing_row_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A dataset deleted before the worker runs should collapse to
    ``not_found``, never crash the task."""
    from datasets.tasks import extract_metadata_task

    _isolate_worker_env(tmp_path, monkeypatch)
    try:
        result = extract_metadata_task(999_999_999)
        assert result["status"] == "not_found"
    finally:
        _teardown_sync_engine()
