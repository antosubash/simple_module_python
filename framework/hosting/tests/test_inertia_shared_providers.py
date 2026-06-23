"""Verify InertiaLayoutDataMiddleware merges module-registered shared-prop providers.

Modules contribute layout-wide Inertia shared props (e.g. branding) without the
framework importing the plugin — mirroring the ``principal_serializer`` precedent.
Providers are registered on ``app.state.inertia_shared_providers`` and merged into
the ``shared`` dict for every request.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware
from simple_module_hosting.shared_props import register_inertia_shared_provider
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/shared")
    def shared(request: Request) -> JSONResponse:
        return JSONResponse(request.state.inertia_shared)

    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=MenuRegistry(),
        permission_registry=PermissionRegistry(),
    )
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return app


def test_registered_provider_dict_merged_into_shared() -> None:
    app = _build_app()
    register_inertia_shared_provider(app, lambda _req: {"branding": {"appName": "Acme"}})

    body = TestClient(app).get("/shared").json()

    assert body["branding"] == {"appName": "Acme"}
    # Built-in blocks still present.
    assert "auth" in body
    assert "menus" in body


def test_provider_that_raises_is_skipped_not_fatal(caplog) -> None:
    app = _build_app()

    def boom(_req: Request) -> dict:
        raise RuntimeError("provider blew up")

    register_inertia_shared_provider(app, boom)
    register_inertia_shared_provider(app, lambda _req: {"branding": {"appName": "Acme"}})

    with caplog.at_level(logging.WARNING, logger="simple_module_hosting.middleware"):
        resp = TestClient(app).get("/shared")

    assert resp.status_code == 200
    body = resp.json()
    # The good provider still applied; the failing one was skipped.
    assert body["branding"] == {"appName": "Acme"}
    assert "auth" in body
    assert any("shared-prop" in rec.message.lower() for rec in caplog.records)


def test_no_providers_leaves_shared_unchanged() -> None:
    body = TestClient(_build_app()).get("/shared").json()
    assert "branding" not in body
    assert "auth" in body and "menus" in body


def test_provider_cannot_clobber_framework_keys(caplog) -> None:
    app = _build_app()
    # A misbehaving provider tries to overwrite the framework-owned auth block.
    register_inertia_shared_provider(
        app, lambda _req: {"auth": "HIJACKED", "branding": {"ok": True}}
    )

    with caplog.at_level(logging.WARNING, logger="simple_module_hosting.middleware"):
        body = TestClient(app).get("/shared").json()

    # auth stays the framework's dict; only the non-reserved key is added.
    assert isinstance(body["auth"], dict)
    assert body["branding"] == {"ok": True}
    assert any("reserved shared-prop" in rec.message for rec in caplog.records)
