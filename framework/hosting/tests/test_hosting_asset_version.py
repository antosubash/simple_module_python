"""Hosting versions built assets by manifest content, so stale visits reload."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from simple_module_hosting._inertia_setup import setup_inertia
from simple_module_hosting.settings import Settings
from simple_module_inertia import (
    InertiaVersionConflictException,
    inertia_version_conflict_exception_handler,
)
from simple_module_inertia.config import resolved_version
from starlette.requests import Request


def _setup(root: Path, environment: str):
    (root / "templates").mkdir(exist_ok=True)
    app = FastAPI()
    config = setup_inertia(app, Settings(environment=environment), [], root)
    assert config is not None
    return app, config


@pytest.mark.parametrize("layout", ["host", "."])
@pytest.mark.parametrize("environment", ["production", "staging"])
async def test_new_manifest_reloads_visits_from_previous_build(tmp_path, layout, environment):
    manifest = tmp_path / layout / "static" / "dist" / ".vite" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"main.tsx": {"file": "assets/old.js"}}))
    _, old_config = _setup(tmp_path, environment)
    old_version = resolved_version(old_config)
    _, same_config = _setup(tmp_path, environment)
    assert resolved_version(same_config) == old_version

    manifest.write_text(json.dumps({"main.tsx": {"file": "assets/new.js"}}))
    app, new_config = _setup(tmp_path, environment)
    new_version = resolved_version(new_config)
    assert new_version != old_version
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("test", 80),
            "path": "/page",
            "query_string": b"",
            "headers": [(b"x-inertia", b"true"), (b"x-inertia-version", old_version.encode())],
            "session": {},
        }
    )
    with pytest.raises(InertiaVersionConflictException) as exc:
        app.state.inertia_dependency(request)
    stale = await inertia_version_conflict_exception_handler(request, exc.value)
    assert stale.status_code == 409
    assert stale.headers["X-Inertia-Location"] == "http://test/page"
    request.scope["headers"] = [
        (b"x-inertia", b"true"),
        (b"x-inertia-version", new_version.encode()),
    ]
    current = await app.state.inertia_dependency(Request(request.scope)).render("Page")
    assert current.status_code == 200
    assert json.loads(current.body)["version"] == new_version


@pytest.mark.parametrize("environment", ["development", "testing", "production"])
def test_setup_without_built_assets_preserves_fallback(tmp_path, environment):
    _, config = _setup(tmp_path, environment)
    assert resolved_version(config) == "1.0"
    assert config.manifest_json_path == ""
