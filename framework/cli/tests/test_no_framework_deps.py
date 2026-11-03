"""Guard: the CLI depends only on typer, tomlkit and packaging.

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
    manifest = Path(__file__).parents[1] / "pyproject.toml"
    requires = tomllib.loads(manifest.read_text())["project"]["dependencies"]
    names = {_normalize(r) for r in requires}
    expected = {"typer", "tomlkit", "packaging"}
    assert names == expected, (
        f"simple_module_cli direct deps drifted; got {sorted(names)}, expected {sorted(expected)}"
    )
