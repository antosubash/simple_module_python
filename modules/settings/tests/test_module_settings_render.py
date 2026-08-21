"""Settings → Modules must render for a module with a rich settings type.

This screen reflects *every* installed module's pydantic settings, so the value
types are open-ended — but none of the modules in this repo declare anything
the stdlib JSON encoder can't handle, which is why the failure only ever showed
up downstream. A wheel-installed module with ``media_root: Path`` was enough to
500 the page, and only on a client-side visit: the HTML render path has its own
encoder, so reloading the same URL worked and the report read as "sometimes".

The demo module below exists to keep a non-JSON-native settings type in the
suite permanently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings
from simple_module_core.module import ModuleMeta

_OK = 200
_SERVER_ERROR = 500
_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


class _PathCfg(BaseSettings):
    """Mirrors the shape that broke it: a Path with a relative default."""

    media_root: Path = Path("var/demo/media")
    workers: int = 2


class _PathModule:
    meta = ModuleMeta(name="PathDemo")


_PathModule.__module__ = "pathdemo"


@dataclass
class _PathServices:
    settings: _PathCfg


@pytest.fixture
def app_with_path_setting(app: FastAPI) -> FastAPI:
    """Register the demo module against the live app the client talks to."""
    app.state.settings.module_registry.register("pathdemo", _PathCfg)
    app.state.pathdemo = _PathServices(settings=_PathCfg())
    return app


class TestModulesScreenRenders:
    async def test_client_side_visit_does_not_500(
        self,
        app_with_path_setting: FastAPI,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        """The reported bug: reaching the page by clicking the sidebar link."""
        resp = await authenticated_client.get("/admin/settings/", headers=_INERTIA)

        assert resp.status_code != _SERVER_ERROR
        assert resp.status_code == _OK

    async def test_the_path_survives_as_a_string(
        self,
        app_with_path_setting: FastAPI,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        resp = await authenticated_client.get("/admin/settings/", headers=_INERTIA)
        modules = resp.json()["props"]["modules"]

        demo = next(m for m in modules if m["package"] == "pathdemo")
        media_root = next(f for f in demo["fields"] if f["name"] == "media_root")
        assert media_root["value"] == "var/demo/media"

    async def test_full_page_load_still_works(
        self,
        app_with_path_setting: FastAPI,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        """The path that always worked must keep working."""
        resp = await authenticated_client.get("/admin/settings/")

        assert resp.status_code == _OK
        assert resp.headers["content-type"].startswith("text/html")
