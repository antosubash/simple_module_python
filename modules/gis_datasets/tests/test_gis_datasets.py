"""Tests for the GisDatasets module."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from gis_datasets.contracts.schemas import DatasetUpdate
from gis_datasets.extractors import extract_metadata, kind_for_filename
from gis_datasets.service import DatasetService, UploadInput, slugify
from gis_datasets.storage import LocalDatasetStorage, safe_filename
from pydantic import ValidationError
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


# ── safe_filename ───────────────────────────────────────────────────


class TestSafeFilename:
    def test_strips_path_components(self):
        assert safe_filename("../../etc/passwd") == "passwd"

    def test_replaces_unsafe_chars(self):
        assert safe_filename("my dataset (v2).geojson") == "my_dataset_v2_.geojson"

    def test_empty_falls_back_to_default(self):
        assert safe_filename("") == "upload.bin"


# ── slugify ──────────────────────────────────────────────────────────


class TestSlugify:
    def test_basic(self):
        assert slugify("My Dataset") == "my-dataset"

    def test_collapses_punctuation(self):
        assert slugify("foo!@#bar") == "foo-bar"

    def test_empty_falls_back(self):
        assert slugify("!!!") == "dataset"


# ── extractors ──────────────────────────────────────────────────────


class TestExtractors:
    def test_kind_for_filename(self):
        assert kind_for_filename("a.geojson") == "vector_geojson"
        assert kind_for_filename("a.shp") == "vector_shapefile"
        assert kind_for_filename("a.tif") == "raster_geotiff"
        assert kind_for_filename("a.csv") == "tabular_csv"
        assert kind_for_filename("a.xyz") == "other"

    def test_geojson_bbox_and_count(self, tmp_path: Path):
        path = tmp_path / "sample.geojson"
        path.write_text(json.dumps(GEOJSON_SAMPLE))
        meta = extract_metadata(path, "vector_geojson")
        assert meta.status == "ok"
        assert meta.feature_count == 2
        assert meta.bbox_min_x == -5.0
        assert meta.bbox_max_x == 10.5
        assert meta.bbox_min_y == 0.0
        assert meta.bbox_max_y == 20.5
        assert meta.crs == "EPSG:4326"

    def test_invalid_geojson_marks_failed(self, tmp_path: Path):
        path = tmp_path / "broken.geojson"
        path.write_text("{not json")
        meta = extract_metadata(path, "vector_geojson")
        assert meta.status == "failed"

    def test_unknown_kind_returns_manual(self, tmp_path: Path):
        path = tmp_path / "x.bin"
        path.write_bytes(b"\x00\x01")
        meta = extract_metadata(path, "other")
        assert meta.status == "manual"


# ── LocalDatasetStorage ─────────────────────────────────────────────


class TestStorage:
    def test_writable_after_ensure_root(self, tmp_path: Path):
        storage = LocalDatasetStorage(tmp_path / "store")
        storage.ensure_root()
        assert storage.is_writable()

    def test_unwritable_when_missing(self, tmp_path: Path):
        storage = LocalDatasetStorage(tmp_path / "missing")
        assert storage.is_writable() is False

    def test_delete_removes_dataset_dir(self, tmp_path: Path):
        storage = LocalDatasetStorage(tmp_path / "store")
        storage.ensure_root()
        key = storage.key_for(7, "data.geojson")
        target = storage.absolute(key)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"hello")
        assert target.exists()
        storage.delete(key)
        assert not target.exists()
        assert not target.parent.exists()


# ── DatasetService ──────────────────────────────────────────────────


def _make_temp_geojson(tmp_path: Path, name: str = "sample.geojson") -> tuple[Path, int]:
    path = tmp_path / name
    payload = json.dumps(GEOJSON_SAMPLE).encode()
    path.write_bytes(payload)
    return path, len(payload)


class TestDatasetService:
    async def test_register_upload_extracts_metadata(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        storage = LocalDatasetStorage(tmp_path / "store")
        storage.ensure_root()
        svc = DatasetService(db_session, storage)
        temp, size = _make_temp_geojson(tmp_path)
        out = await svc.register_upload(
            UploadInput(
                name="My Dataset",
                original_filename="sample.geojson",
                temp_path=temp,
                size_bytes=size,
                mime_type="application/geo+json",
            )
        )
        assert out.id is not None
        assert out.kind == "vector_geojson"
        assert out.feature_count == 2
        assert out.extraction_status == "ok"
        assert out.slug == "my-dataset"
        # The temp file has been moved into final storage.
        assert not temp.exists()
        info = await svc.get_storage_key(out.id)
        assert info is not None
        storage_key, _, _ = info
        assert storage.absolute(storage_key).exists()

    async def test_unique_slug_collision(self, db_session: AsyncSession, tmp_path: Path):
        storage = LocalDatasetStorage(tmp_path / "store")
        storage.ensure_root()
        svc = DatasetService(db_session, storage)
        a_path, a_size = _make_temp_geojson(tmp_path, "a.geojson")
        b_path, b_size = _make_temp_geojson(tmp_path, "b.geojson")
        first = await svc.register_upload(
            UploadInput(
                name="Same Name",
                original_filename="a.geojson",
                temp_path=a_path,
                size_bytes=a_size,
                mime_type=None,
            )
        )
        second = await svc.register_upload(
            UploadInput(
                name="Same Name",
                original_filename="b.geojson",
                temp_path=b_path,
                size_bytes=b_size,
                mime_type=None,
            )
        )
        assert first.slug == "same-name"
        assert second.slug == "same-name-2"

    async def test_delete_removes_file(self, db_session: AsyncSession, tmp_path: Path):
        storage = LocalDatasetStorage(tmp_path / "store")
        storage.ensure_root()
        svc = DatasetService(db_session, storage)
        path, size = _make_temp_geojson(tmp_path)
        out = await svc.register_upload(
            UploadInput(
                name="Doomed",
                original_filename="sample.geojson",
                temp_path=path,
                size_bytes=size,
                mime_type=None,
            )
        )
        info = await svc.get_storage_key(out.id)
        assert info is not None
        stored_path = storage.absolute(info[0])
        assert stored_path.exists()
        deleted = await svc.delete(out.id)
        assert deleted is True
        assert not stored_path.exists()

    async def test_update_validation(self):
        # crs longer than 64 chars should be rejected.
        with pytest.raises(ValidationError):
            DatasetUpdate(crs="x" * 200)


# ── API endpoints ───────────────────────────────────────────────────


class TestDatasetsAPI:
    async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/gis_datasets/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_upload_and_download_geojson(
        self, authenticated_client: httpx.AsyncClient, tmp_path: Path
    ):
        payload = json.dumps(GEOJSON_SAMPLE).encode()
        files = {"file": ("sample.geojson", payload, "application/geo+json")}
        data = {"name": "My GeoJSON"}
        resp = await authenticated_client.post("/api/gis_datasets/", data=data, files=files)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["kind"] == "vector_geojson"
        assert body["feature_count"] == 2
        assert body["extraction_status"] == "ok"

        download = await authenticated_client.get(f"/api/gis_datasets/{body['id']}/download")
        assert download.status_code == 200
        assert download.content == payload

    async def test_upload_unknown_kind_rejected(self, authenticated_client: httpx.AsyncClient):
        files = {"file": ("a.geojson", b"{}", "application/json")}
        resp = await authenticated_client.post(
            "/api/gis_datasets/",
            data={"name": "x", "kind": "not_a_kind"},
            files=files,
        )
        assert resp.status_code == 422

    async def test_delete(self, authenticated_client: httpx.AsyncClient):
        files = {"file": ("doomed.geojson", b'{"type":"FeatureCollection","features":[]}', None)}
        resp = await authenticated_client.post(
            "/api/gis_datasets/", data={"name": "Doomed"}, files=files
        )
        assert resp.status_code == 201
        item_id = resp.json()["id"]
        delete = await authenticated_client.delete(f"/api/gis_datasets/{item_id}")
        assert delete.status_code == 204
        gone = await authenticated_client.get(f"/api/gis_datasets/{item_id}")
        assert gone.status_code == 404

    async def test_patch_metadata(self, authenticated_client: httpx.AsyncClient):
        files = {"file": ("a.geojson", b'{"type":"FeatureCollection","features":[]}', None)}
        create = await authenticated_client.post(
            "/api/gis_datasets/", data={"name": "Original"}, files=files
        )
        item_id = create.json()["id"]
        patch = await authenticated_client.patch(
            f"/api/gis_datasets/{item_id}",
            json={"name": "Renamed", "description": "Notes"},
        )
        assert patch.status_code == 200
        assert patch.json()["name"] == "Renamed"
        assert patch.json()["description"] == "Notes"


# ── Module wiring ───────────────────────────────────────────────────


class TestGisDatasetsModule:
    def test_meta(self):
        from gis_datasets.module import GisDatasetsModule

        mod = GisDatasetsModule()
        assert mod.meta.name == "GisDatasets"
        assert mod.meta.route_prefix == "/api/gis_datasets"
        assert mod.meta.view_prefix == "/gis_datasets"
