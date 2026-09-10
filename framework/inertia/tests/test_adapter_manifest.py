"""Production assets come straight from Vite's manifest, keyed as Vite writes it."""

from __future__ import annotations

import json

import pytest
from fastapi.templating import Jinja2Templates
from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.manifest import entry_assets, read_manifest


def _manifest(tmp_path, entries: dict) -> str:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(entries))
    return str(path)


def _cfg(tmp_path, **kw) -> InertiaConfig:
    return InertiaConfig(templates=Jinja2Templates(directory=str(tmp_path)), **kw)


def test_production_resolves_the_entry_by_vites_native_key(tmp_path) -> None:
    manifest = _manifest(
        tmp_path,
        {
            "main.tsx": {
                "file": "assets/main-ABC.js",
                "css": ["assets/main-DEF.css"],
                "isEntry": True,
            },
            "pages/Foo.tsx": {"file": "assets/Foo-XYZ.js"},
        },
    )
    cfg = _cfg(
        tmp_path,
        environment="production",
        manifest_json_path=manifest,
        entrypoint_filename="main.tsx",
        root_directory=".",
        assets_prefix="static/dist",
    )
    files = entry_assets(cfg)
    assert files.js == "/static/dist/assets/main-ABC.js"
    assert files.css == ["/static/dist/assets/main-DEF.css"]


def test_production_falls_back_to_the_upstream_key_shape(tmp_path) -> None:
    manifest = _manifest(tmp_path, {"src/main.js": {"file": "assets/m.js", "isEntry": True}})
    cfg = _cfg(
        tmp_path,
        environment="production",
        manifest_json_path=manifest,
        entrypoint_filename="main.js",
        root_directory="src",
    )
    assert entry_assets(cfg).js == "/assets/m.js"


def test_production_falls_back_to_the_first_is_entry_chunk(tmp_path) -> None:
    manifest = _manifest(tmp_path, {"whatever.tsx": {"file": "assets/w.js", "isEntry": True}})
    cfg = _cfg(
        tmp_path,
        environment="production",
        manifest_json_path=manifest,
        entrypoint_filename="main.tsx",
    )
    assert entry_assets(cfg).js == "/assets/w.js"


def test_production_with_no_entry_raises_naming_the_manifest(tmp_path) -> None:
    manifest = _manifest(tmp_path, {"x.tsx": {"file": "assets/x.js"}})
    cfg = _cfg(tmp_path, environment="production", manifest_json_path=manifest)
    with pytest.raises(LookupError, match=r"manifest\.json"):
        entry_assets(cfg)


def test_production_with_no_manifest_path_raises_clearly(tmp_path) -> None:
    cfg = _cfg(tmp_path, environment="production", manifest_json_path="")
    with pytest.raises(LookupError, match="manifest_json_path"):
        entry_assets(cfg)


def test_development_points_at_the_dev_server_without_a_dot_segment(tmp_path) -> None:
    cfg = _cfg(
        tmp_path,
        dev_url="http://localhost:5050",
        entrypoint_filename="main.tsx",
        root_directory=".",
    )
    assert entry_assets(cfg).js == "http://localhost:5050/main.tsx"
    assert entry_assets(cfg).css == []


def test_development_keeps_a_real_root_directory(tmp_path) -> None:
    cfg = _cfg(
        tmp_path,
        dev_url="http://localhost:5173",
        entrypoint_filename="main.js",
        root_directory="src",
    )
    assert entry_assets(cfg).js == "http://localhost:5173/src/main.js"


def test_read_manifest_is_cached_per_path(tmp_path) -> None:
    path = _manifest(tmp_path, {"a": {"file": "a.js"}})
    assert read_manifest(path) is read_manifest(path)
