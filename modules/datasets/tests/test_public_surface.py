"""Contract tests for the Datasets module's public surface.

Anything asserted here is something downstream modules depend on. Break
it and consuming modules break — treat every failure as an API-version
concern, not a cosmetic one.
"""

from __future__ import annotations

import json
from pathlib import Path

from datasets.service import DatasetService, UploadInput
from file_storage.backends.filesystem import FilesystemBackend
from sqlalchemy.ext.asyncio import AsyncSession

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


def _backend(tmp_path: Path) -> FilesystemBackend:
    root = tmp_path / "store"
    root.mkdir(parents=True, exist_ok=True)
    return FilesystemBackend(root=root)


def _make_temp_geojson(tmp_path: Path, name: str = "sample.geojson") -> tuple[Path, int]:
    path = tmp_path / name
    payload = json.dumps(GEOJSON_SAMPLE).encode()
    path.write_bytes(payload)
    return path, len(payload)


class TestContractsReexports:
    def test_all_public_names_importable(self):
        from datasets.contracts import (  # noqa: F401 — import check
            API_PREFIX,
            KIND_VALUES,
            VIEW_PREFIX,
            DatasetDeleted,
            DatasetFile,
            DatasetKind,
            DatasetOut,
            DatasetUpdate,
            DatasetUploaded,
            IDatasetService,
            detail_url,
            download_url,
            show_url,
        )

    def test_url_helpers(self):
        from datasets.contracts import API_PREFIX, VIEW_PREFIX, detail_url, download_url, show_url

        assert download_url(7) == "/api/datasets/7/download"
        assert detail_url(7) == "/api/datasets/7"
        assert show_url(7) == "/datasets/7"
        assert API_PREFIX == "/api/datasets"
        assert VIEW_PREFIX == "/datasets"

    def test_dep_alias_is_importable(self):
        from datasets.deps import DatasetServiceDep  # noqa: F401


class TestEventShape:
    def test_uploaded_carries_slug_and_kind(self):
        from datasets.contracts import DatasetUploaded

        up = DatasetUploaded(dataset_id=1, name="Borders", slug="borders", kind="vector_geojson")
        assert up.slug == "borders"
        assert up.kind == "vector_geojson"

    def test_deleted_carries_slug(self):
        from datasets.contracts import DatasetDeleted

        down = DatasetDeleted(dataset_id=1, slug="borders")
        assert down.slug == "borders"


class TestLookupsForConsumers:
    async def test_get_by_slug(self, db_session: AsyncSession, tmp_path: Path):
        svc = DatasetService(db_session, _backend(tmp_path))
        path, size = _make_temp_geojson(tmp_path)
        created = await svc.register_upload(
            UploadInput(
                name="World Borders",
                original_filename="sample.geojson",
                temp_path=path,
                size_bytes=size,
                mime_type=None,
            )
        )
        found = await svc.get_by_slug(created.slug)
        assert found is not None
        assert found.id == created.id
        assert await svc.get_by_slug("no-such-slug") is None

    async def test_list_by_kind(self, db_session: AsyncSession, tmp_path: Path):
        svc = DatasetService(db_session, _backend(tmp_path))
        p1, s1 = _make_temp_geojson(tmp_path, "a.geojson")
        p2, s2 = _make_temp_geojson(tmp_path, "b.geojson")
        await svc.register_upload(
            UploadInput(
                name="A",
                original_filename="a.geojson",
                temp_path=p1,
                size_bytes=s1,
                mime_type=None,
            )
        )
        await svc.register_upload(
            UploadInput(
                name="B",
                original_filename="b.geojson",
                temp_path=p2,
                size_bytes=s2,
                mime_type=None,
            )
        )
        vectors = await svc.list_by_kind("vector_geojson")
        assert len(vectors) == 2
        # Ordering is id desc — most recent first.
        assert vectors[0].name == "B"
        assert await svc.list_by_kind("raster_geotiff") == []

        limited = await svc.list_by_kind("vector_geojson", limit=1)
        assert len(limited) == 1


class TestFileHandle:
    async def test_get_file_returns_streamable_handle(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        from datasets.contracts import DatasetFile

        svc = DatasetService(db_session, _backend(tmp_path))
        path, size = _make_temp_geojson(tmp_path)
        created = await svc.register_upload(
            UploadInput(
                name="Opener",
                original_filename="sample.geojson",
                temp_path=path,
                size_bytes=size,
                mime_type=None,
            )
        )
        handle = await svc.get_file(created.id)
        assert isinstance(handle, DatasetFile)
        assert await handle.exists()
        assert handle.metadata.id == created.id
        body = await handle.read()
        assert body.startswith(b"{")
        assert len(body) == size

    async def test_materialize_to_tempfile_gives_local_path(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        svc = DatasetService(db_session, _backend(tmp_path))
        path, size = _make_temp_geojson(tmp_path)
        created = await svc.register_upload(
            UploadInput(
                name="LocalUsage",
                original_filename="sample.geojson",
                temp_path=path,
                size_bytes=size,
                mime_type=None,
            )
        )
        handle = await svc.get_file(created.id)
        assert handle is not None

        local_path = await handle.materialize_to_tempfile()
        try:
            assert local_path.is_file()
            assert local_path.suffix == ".geojson"
            assert local_path.read_bytes().startswith(b"{")
        finally:
            local_path.unlink(missing_ok=True)

    async def test_get_file_missing_id(self, db_session: AsyncSession, tmp_path: Path):
        svc = DatasetService(db_session, _backend(tmp_path))
        assert await svc.get_file(9999) is None
