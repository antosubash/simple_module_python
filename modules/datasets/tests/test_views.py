"""Tests for the Inertia view endpoints (POST / PATCH / DELETE).

These endpoints exist so Inertia's ``router.post/patch/delete`` calls
receive a redirect (which Inertia follows) rather than raw JSON (which
Inertia rejects with ``Inertia response required`` on the client). The
API equivalents under ``/api/datasets/*`` are covered in
``test_datasets.py::TestDatasetsAPI``.
"""

from __future__ import annotations

import httpx


async def _create_via_api(
    authenticated_client: httpx.AsyncClient, name: str = "Seed"
) -> int:
    files = {"file": (f"{name}.geojson", b'{"type":"FeatureCollection","features":[]}', None)}
    resp = await authenticated_client.post("/api/datasets/", data={"name": name}, files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── create ──────────────────────────────────────────────────────────


class TestUploadView:
    async def test_returns_303_redirect(self, authenticated_client: httpx.AsyncClient):
        files = {"file": ("via-view.geojson", b'{"type":"FeatureCollection","features":[]}', None)}
        resp = await authenticated_client.post(
            "/datasets/",
            data={"name": "Via View"},
            files=files,
            follow_redirects=False,
        )
        assert resp.status_code == 303, resp.text
        assert resp.headers["location"] == "/datasets/"

        listing = await authenticated_client.get("/api/datasets/")
        assert any(d["name"] == "Via View" for d in listing.json())

    async def test_rejects_unknown_kind(self, authenticated_client: httpx.AsyncClient):
        files = {"file": ("a.geojson", b"{}", "application/json")}
        resp = await authenticated_client.post(
            "/datasets/",
            data={"name": "x", "kind": "not_a_kind"},
            files=files,
            follow_redirects=False,
        )
        assert resp.status_code == 422


# ── update ──────────────────────────────────────────────────────────


class TestUpdateView:
    async def test_returns_303_redirect(self, authenticated_client: httpx.AsyncClient):
        item_id = await _create_via_api(authenticated_client, name="Before")
        resp = await authenticated_client.patch(
            f"/datasets/{item_id}",
            json={"name": "After", "description": "Notes"},
            follow_redirects=False,
        )
        assert resp.status_code == 303, resp.text
        assert resp.headers["location"] == "/datasets/"

        fresh = await authenticated_client.get(f"/api/datasets/{item_id}")
        assert fresh.json()["name"] == "After"
        assert fresh.json()["description"] == "Notes"

    async def test_missing_id_404(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.patch(
            "/datasets/9999",
            json={"name": "ghost"},
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ── delete ──────────────────────────────────────────────────────────


class TestDeleteView:
    async def test_returns_303_and_removes_row(self, authenticated_client: httpx.AsyncClient):
        item_id = await _create_via_api(authenticated_client, name="Doomed-View")
        resp = await authenticated_client.delete(f"/datasets/{item_id}", follow_redirects=False)
        assert resp.status_code == 303, resp.text
        assert resp.headers["location"] == "/datasets/"

        gone = await authenticated_client.get(f"/api/datasets/{item_id}")
        assert gone.status_code == 404

    async def test_missing_id_404(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.delete("/datasets/9999", follow_redirects=False)
        assert resp.status_code == 404
