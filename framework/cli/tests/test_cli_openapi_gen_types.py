"""``smpy openapi gen-types`` writes per-module API types for the typed client (#504)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from simple_module_cli import openapi_types as ot
from simple_module_cli.cli import app
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parents[3]
LOCAL_TOOL = REPO / "packages" / "ui" / "node_modules" / ".bin" / "openapi-typescript"

SCHEMA = {
    "openapi": "3.1.0",
    "info": {"title": "t", "version": "1"},
    "paths": {
        "/api/widgets/": {
            "get": {
                "tags": ["Widgets"],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/WidgetList"}
                            }
                        }
                    }
                },
            },
            "post": {
                "tags": ["Widgets"],
                "responses": {"201": {"content": {"application/json": {"schema": {}}}}},
            },
        },
        "/api/other/": {
            "get": {
                "tags": ["Other"],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OtherView"}
                            }
                        }
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "WidgetList": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Widget"},
            },
            "Widget": {"type": "object", "properties": {"id": {"type": "string"}}},
            "OtherView": {"type": "object"},
        },
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
    },
}


def _fake_module(tmp_path: Path, package: str, name: str, *, opted_in: bool) -> object:
    """A module object whose package is a real importable directory under tmp_path."""
    pages = tmp_path / package / "pages"
    pages.mkdir(parents=True)
    (tmp_path / package / "__init__.py").write_text("")
    if opted_in:
        (pages / ot.GENERATED_FILENAME).write_text("old\n")
    cls = type("M", (), {"__module__": f"{package}.module", "meta": SimpleNamespace(name=name)})
    return cls()


@pytest.fixture
def importable(tmp_path: Path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


def _writer(output: str):
    """A stand-in for openapi-typescript that records its input and writes ``output``."""
    seen: dict = {}

    def run(cmd, **kwargs):
        src, out = Path(cmd[-3]), Path(cmd[-1])
        seen["schema"] = json.loads(src.read_text())
        seen["cwd"] = kwargs.get("cwd")
        out.write_text(output)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run, seen


def test_filter_and_prune_keep_only_the_module_slice() -> None:
    subset = ot.prune_components(ot.filter_operations(SCHEMA, ["widgets"]))
    assert list(subset["paths"]) == ["/api/widgets/"]
    # Reached transitively through WidgetList; OtherView belongs to another module.
    assert set(subset["components"]["schemas"]) == {"WidgetList", "Widget"}
    assert ot.untyped_operations(subset) == ["POST /api/widgets/"]


def test_targets_default_to_opted_in_modules(importable: Path) -> None:
    mods = [
        _fake_module(importable, "gt_widgets", "Widgets", opted_in=True),
        _fake_module(importable, "gt_other", "Other", opted_in=False),
    ]
    assert [t.package for t in ot.module_targets(mods, importable, [])] == ["gt_widgets"]
    named = ot.module_targets(mods, importable, ["Other"])
    assert [t.name for t in named] == ["Other"]
    with pytest.raises(ot.GenTypesError, match="nope"):
        ot.module_targets(mods, importable, ["nope"])


def test_never_writes_outside_the_project(importable: Path, tmp_path: Path) -> None:
    mods = [_fake_module(importable, "gt_far", "Far", opted_in=True)]
    elsewhere = tmp_path / "project"
    elsewhere.mkdir()
    assert ot.module_targets(mods, elsewhere, []) == []
    with pytest.raises(ot.GenTypesError, match="outside"):
        ot.module_targets(mods, elsewhere, ["far"])


def test_generate_writes_header_and_is_idempotent(importable: Path) -> None:
    mods = [_fake_module(importable, "gt_gen", "Widgets", opted_in=True)]
    (importable / "node_modules" / ".bin").mkdir(parents=True)
    (importable / "node_modules" / ".bin" / "openapi-typescript").write_text("")
    targets = ot.module_targets(mods, importable, [])
    run, seen = _writer("export interface paths {}\n")

    [(target, changed, untyped)] = ot.generate(SCHEMA, targets, importable, runner=run)
    text = target.output.read_text()
    assert changed and untyped == ["POST /api/widgets/"]
    assert text.startswith("// AUTO-GENERATED by `smpy openapi gen-types` from the Widgets")
    assert "--module gt_gen" in text and text.endswith("export interface paths {}\n")
    assert list(seen["schema"]["paths"]) == ["/api/widgets/"]

    [(_, changed_again, _)] = ot.generate(SCHEMA, targets, importable, runner=run)
    assert not changed_again


def test_tool_failure_is_reported(importable: Path) -> None:
    (importable / "node_modules" / ".bin").mkdir(parents=True)
    (importable / "node_modules" / ".bin" / "openapi-typescript").write_text("")
    targets = ot.module_targets(
        [_fake_module(importable, "gt_fail", "W", opted_in=True)], importable, []
    )

    def boom(cmd, **_):
        return subprocess.CompletedProcess(cmd, 1, "", "bad schema")

    with pytest.raises(ot.GenTypesError, match="bad schema"):
        ot.generate(SCHEMA, targets, importable, runner=boom)


def test_tool_command_prefers_local_then_pinned_npx(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ot.shutil, "which", lambda _: "/usr/bin/npx")
    resolved = ot.tool_command(tmp_path)
    assert resolved is not None
    command, cwd = resolved
    assert command == [
        "/usr/bin/npx",
        "--yes",
        f"openapi-typescript@{ot.OPENAPI_TYPESCRIPT_VERSION}",
    ]
    assert cwd is not None and not cwd.is_relative_to(tmp_path)

    local = tmp_path / "packages" / "ui" / "node_modules" / ".bin" / "openapi-typescript"
    local.parent.mkdir(parents=True)
    local.write_text("")
    assert ot.tool_command(tmp_path) == ([str(local)], None)

    local.unlink()
    monkeypatch.setattr(ot.shutil, "which", lambda _: None)
    assert ot.tool_command(tmp_path) is None


def test_pinned_version_matches_the_ui_dev_dependency() -> None:
    ui = json.loads((REPO / "packages" / "ui" / "package.json").read_text())
    assert ui["devDependencies"]["openapi-typescript"] == ot.OPENAPI_TYPESCRIPT_VERSION


def test_real_tool_emits_paths(importable: Path, require_cli_asset) -> None:
    require_cli_asset(LOCAL_TOOL.is_file(), "needs `npm ci` (openapi-typescript)")
    targets = ot.module_targets(
        [_fake_module(importable, "gt_real", "Widgets", opted_in=True)], importable, []
    )
    bin_dir = importable / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "openapi-typescript").symlink_to(LOCAL_TOOL.resolve())
    ot.generate(SCHEMA, targets, importable)
    text = targets[0].output.read_text()
    assert '"/api/widgets/"' in text and "WidgetList" in text and "OtherView" not in text


def test_cli_refuses_a_module_outside_the_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    result = CliRunner().invoke(app, ["openapi", "gen-types", "--module", "feature_flags"])
    assert result.exit_code == 1
    assert "outside" in result.output


def test_cli_without_opted_in_modules_says_so(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    result = CliRunner().invoke(app, ["openapi", "gen-types"])
    assert result.exit_code == 0, result.output
    assert "pass --module" in result.output
