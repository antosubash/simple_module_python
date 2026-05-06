"""Tests for ``simple_module_hosting.manifest`` helpers."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_hosting.manifest import repo_root_from_client_app


def test_repo_root_finds_workspace_root_in_framework_layout(tmp_path: Path) -> None:
    """``host/client_app/`` shape: walk up to the workspace package.json."""
    workspace = tmp_path / "ws"
    (workspace / "host" / "client_app").mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"name": "ws", "workspaces": ["host/client_app", "modules/*"]})
    )
    (workspace / "host" / "package.json").write_text(json.dumps({"name": "ws-host"}))

    assert repo_root_from_client_app(workspace / "host" / "client_app") == workspace.resolve()


def test_repo_root_finds_root_in_flat_scaffold_layout(tmp_path: Path) -> None:
    """Flat scaffold: ``client_app/`` directly under the host root."""
    host = tmp_path / "my-app"
    (host / "client_app").mkdir(parents=True)
    (host / "package.json").write_text(json.dumps({"name": "my-app"}))

    assert repo_root_from_client_app(host / "client_app") == host.resolve()


def test_repo_root_prefers_workspace_package_json_over_nearer_one(tmp_path: Path) -> None:
    """When a non-workspace package.json sits between client_app and the
    workspace root, the workspace one wins so npm install runs at the right cwd."""
    workspace = tmp_path / "ws"
    (workspace / "host" / "client_app").mkdir(parents=True)
    (workspace / "package.json").write_text(
        json.dumps({"name": "ws", "workspaces": ["host/client_app"]})
    )
    (workspace / "host" / "package.json").write_text(json.dumps({"name": "ws-host"}))

    assert repo_root_from_client_app(workspace / "host" / "client_app") == workspace.resolve()


def test_repo_root_falls_back_to_nearest_package_json(tmp_path: Path) -> None:
    """No workspaces field anywhere — settle on the nearest package.json found."""
    root = tmp_path / "root"
    (root / "client_app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "root"}))

    assert repo_root_from_client_app(root / "client_app") == root.resolve()


def test_repo_root_falls_back_to_two_levels_up_if_no_package_json(tmp_path: Path) -> None:
    """No package.json exists yet — preserve the legacy two-up behaviour so
    framework-internal callers still get a path before any npm setup."""
    deep = tmp_path / "outer" / "inner" / "client_app"
    deep.mkdir(parents=True)

    assert repo_root_from_client_app(deep) == (tmp_path / "outer").resolve()
