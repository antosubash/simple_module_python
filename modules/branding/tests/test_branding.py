"""Tests for the Branding module."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from branding.settings import BrandingSettings
from branding.shared_props import branding_payload, branding_shared_props

# ── Unit: settings validation ──────────────────────────────────────────


def test_settings_defaults() -> None:
    s = BrandingSettings()
    assert s.app_name == "SimpleModule"
    assert s.primary_color == ""
    assert s.logo_file_id == ""
    assert s.favicon_file_id == ""


def test_settings_app_name_trimmed_and_required() -> None:
    assert BrandingSettings(app_name="  Acme  ").app_name == "Acme"
    with pytest.raises(ValueError):
        BrandingSettings(app_name="   ")
    with pytest.raises(ValueError):
        BrandingSettings(app_name="x" * 61)


def test_settings_primary_color_validation() -> None:
    assert BrandingSettings(primary_color="#1A7DD1").primary_color == "#1a7dd1"
    assert BrandingSettings(primary_color="").primary_color == ""
    with pytest.raises(ValueError):
        BrandingSettings(primary_color="red")
    with pytest.raises(ValueError):
        BrandingSettings(primary_color="#fff")


# ── Unit: shared-props payload + provider ──────────────────────────────


def test_branding_payload_unset() -> None:
    payload = branding_payload(BrandingSettings())
    assert payload == {
        "appName": "SimpleModule",
        "primaryColor": None,
        "logoUrl": None,
        "faviconUrl": None,
    }


def test_branding_payload_set() -> None:
    s = BrandingSettings(
        app_name="Acme",
        primary_color="#ff0000",
        logo_file_id="abc-123",
        favicon_file_id="def-456",
    )
    payload = branding_payload(s)
    assert payload["appName"] == "Acme"
    assert payload["primaryColor"] == "#ff0000"
    assert payload["logoUrl"] == "/api/file-storage/files/abc-123/download"
    assert payload["faviconUrl"] == "/api/file-storage/files/def-456/download"


def test_provider_returns_empty_when_state_absent() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert branding_shared_props(request) == {}  # type: ignore[arg-type]


def test_provider_emits_branding_block() -> None:
    state = SimpleNamespace(branding=SimpleNamespace(settings=BrandingSettings(app_name="Acme")))
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    out = branding_shared_props(request)  # type: ignore[arg-type]
    assert out["branding"]["appName"] == "Acme"


# ── Integration: API + persistence + hot-swap ──────────────────────────


async def test_get_branding_returns_defaults(authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.get("/api/branding/")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["app_name"] == "SimpleModule"
    assert body["logo_url"] is None


async def test_update_persists_and_hot_swaps(app, authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.put(
        "/api/branding/",
        json={"app_name": "Acme Corp", "primary_color": "#1A7DD1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["app_name"] == "Acme Corp"
    assert body["primary_color"] == "#1a7dd1"

    # Hot-swapped on app.state so the shared-props provider sees it immediately.
    settings = app.state.branding.settings
    assert settings.app_name == "Acme Corp"
    assert branding_payload(settings)["appName"] == "Acme Corp"

    # Persisted: a fresh GET reflects the change.
    again = await authenticated_client.get("/api/branding/")
    assert again.json()["app_name"] == "Acme Corp"


async def test_update_rejects_bad_hex(authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.put("/api/branding/", json={"primary_color": "nope"})
    assert resp.status_code == 422


async def test_logo_upload_rejects_non_image(authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.post(
        "/api/branding/logo",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415


async def test_logo_upload_sets_logo_url(
    app, authenticated_client: httpx.AsyncClient, monkeypatch
) -> None:
    fake_id = uuid.uuid4()

    async def fake_upload(self, upload):
        return SimpleNamespace(id=fake_id)

    monkeypatch.setattr("file_storage.service.FileStorageService.upload", fake_upload, raising=True)

    resp = await authenticated_client.post(
        "/api/branding/logo",
        files={"file": ("logo.png", b"\x89PNG\r\n", "image/png")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["logo_url"] == f"/api/file-storage/files/{fake_id}/download"
    assert app.state.branding.settings.logo_file_id == str(fake_id)

    # Clearing removes it.
    cleared = await authenticated_client.delete("/api/branding/logo")
    assert cleared.status_code == 200
    assert cleared.json()["logo_url"] is None


async def test_manage_view_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get("/branding", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_page_constant_matches_view_literal() -> None:
    # Guards against the inlined render literal drifting from the constant
    # (the literal is required inline for SM003/SM004 static AST pairing).
    import inspect

    from branding import constants
    from branding.endpoints import views

    assert constants._PAGE_MANAGE == "Branding/Manage"
    assert f'"{constants._PAGE_MANAGE}"' in inspect.getsource(views.manage)
