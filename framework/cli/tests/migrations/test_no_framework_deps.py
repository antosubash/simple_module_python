"""Guard: the CLI depends only on typer, tomlkit, packaging and PyYAML.

If a future change accidentally pulls in simple_module_core, FastAPI,
SQLModel, or anything else, this test fires immediately.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def _normalize(req: str) -> str:
    """'typer (>=0.12)' -> 'typer'. Strip version specs + extras + spaces."""
    head = req.split(";", 1)[0]
    for sep in ("(", ">=", ">", "<", "==", "[", " "):
        head = head.split(sep, 1)[0]
    return head.strip().lower().replace("_", "-")


def test_simple_module_cli_runtime_deps_are_minimal() -> None:
    # Read the declaration so an editable install's stale metadata cannot hide drift.
    manifest = Path(__file__).parents[2] / "pyproject.toml"
    requires = tomllib.loads(manifest.read_text())["project"]["dependencies"]
    names = {_normalize(r) for r in requires}
    expected = {"typer", "tomlkit", "packaging", "pyyaml"}
    assert names == expected, (
        f"simple_module_cli direct deps drifted; got {sorted(names)}, expected {sorted(expected)}"
    )


def test_vendored_migration_support_matches_core() -> None:
    framework = Path(__file__).resolve().parents[3]
    vendored = framework / "cli/simple_module_cli/migrations/_migration_support.py"
    core = framework / "core/simple_module_core/migrations/support.py"
    assert not vendored.is_symlink()
    assert vendored.read_bytes() == core.read_bytes()
