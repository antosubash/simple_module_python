"""Shared fixtures and constants for new_module scaffolding tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import new_module
from new_module import scaffold_module

MINIMAL_HOST_PYPROJECT = (
    '[project]\ndependencies = [\n    "products",\n]\n\n'
    "[tool.uv.sources]\nproducts = { workspace = true }\n"
)
MINIMAL_ROOT_PYPROJECT = (
    '[tool.ty.environment]\nextra-paths = [\n    "modules/products",\n]\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["modules/products/tests"]\n'
)


@pytest.fixture
def module_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a temp directory patched as the script's ROOT with modules/ pre-created."""
    monkeypatch.setattr(new_module, "ROOT", tmp_path)
    (tmp_path / "modules").mkdir()
    return tmp_path


@pytest.fixture
def workspace(module_root: Path) -> Path:
    """module_root plus host/ and root pyproject.toml ready for end-to-end runs."""
    (module_root / "host").mkdir()
    (module_root / "host" / "pyproject.toml").write_text(MINIMAL_HOST_PYPROJECT)
    (module_root / "pyproject.toml").write_text(MINIMAL_ROOT_PYPROJECT)
    return module_root


@pytest.fixture
def scaffolded_orders(module_root: Path) -> Path:
    """Run the scaffold once and return the orders source directory."""
    scaffold_module("orders")
    return module_root / "modules" / "orders" / "orders"


# ---------------------------------------------------------------------------
# Fixtures for the release-scripts test suite (check_metadata, check_readmes).
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_pkg_dir(tmp_path: Path) -> Path:
    """A temp directory set up like a simple-module package root."""
    return tmp_path


def _write(path: Path, content: str) -> Path:
    """Write text to a path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def writer():
    return _write
