"""Tests for the publish-pypi matrix cross-check in scripts/check_metadata.py.

Guards the failure mode where a module ships, builds a wheel on every release,
and is offered by the CLI — but was never added to the release workflow's
matrix, so installing it from PyPI 404s forever.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_metadata import (
    check_release_matrix,
    discover_python_packages,
    parse_publish_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _release_yml(*packages: str) -> str:
    """A release workflow stub shaped like the real publish-pypi job."""
    entries = "".join(f"          - {p}\n" for p in packages)
    return (
        "name: release\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "  publish-pypi:\n"
        "    needs: build\n"
        "    strategy:\n"
        "      fail-fast: false\n"
        "      matrix:\n"
        "        package:\n"
        f"{entries}"
        "    environment:\n"
        "      name: pypi\n"
        "  publish-npm:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        package: [ui, i18n, tsconfig]\n"
    )


def _pkg(name: str) -> str:
    return f"""
[project]
name = "{name}"
version = "0.0.1"
description = "A real description"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
"""


def test_parse_publish_matrix_reads_package_list(tmp_path: Path, writer) -> None:
    wf = writer(tmp_path / "release.yml", _release_yml("simple_module_core", "simple_module_db"))
    assert parse_publish_matrix(wf) == ["simple_module_core", "simple_module_db"]


def test_parse_publish_matrix_ignores_the_npm_job_matrix(tmp_path: Path, writer) -> None:
    """publish-npm has its own inline `package:` list — it must not leak in."""
    wf = writer(tmp_path / "release.yml", _release_yml("simple_module_core"))
    assert parse_publish_matrix(wf) == ["simple_module_core"]


def test_parse_publish_matrix_raises_when_job_missing(tmp_path: Path, writer) -> None:
    wf = writer(tmp_path / "release.yml", "name: release\njobs:\n  build:\n    runs-on: x\n")
    with pytest.raises(ValueError, match="publish-pypi"):
        parse_publish_matrix(wf)


def test_parse_publish_matrix_raises_when_matrix_missing(tmp_path: Path, writer) -> None:
    wf = writer(
        tmp_path / "release.yml",
        "name: release\njobs:\n  publish-pypi:\n    needs: build\n    runs-on: x\n",
    )
    with pytest.raises(ValueError, match="package"):
        parse_publish_matrix(wf)


def test_flags_package_missing_from_matrix(tmp_path: Path, writer) -> None:
    writer(tmp_path / "modules/site_lock/pyproject.toml", _pkg("simple_module_site_lock"))
    writer(tmp_path / ".github/workflows/release.yml", _release_yml("simple_module_core"))
    errors = check_release_matrix(tmp_path)
    assert any("simple_module_site_lock" in e and "missing from the" in e for e in errors)


def test_flags_stale_matrix_entry(tmp_path: Path, writer) -> None:
    writer(tmp_path / "modules/auth/pyproject.toml", _pkg("simple_module_auth"))
    writer(
        tmp_path / ".github/workflows/release.yml",
        _release_yml("simple_module_auth", "simple_module_gone"),
    )
    errors = check_release_matrix(tmp_path)
    assert any("simple_module_gone" in e and "not a workspace package" in e for e in errors)


def test_clean_when_aligned(tmp_path: Path, writer) -> None:
    writer(tmp_path / "modules/auth/pyproject.toml", _pkg("simple_module_auth"))
    writer(tmp_path / "framework/core/pyproject.toml", _pkg("simple_module_core"))
    writer(
        tmp_path / ".github/workflows/release.yml",
        _release_yml("simple_module_auth", "simple_module_core"),
    )
    assert check_release_matrix(tmp_path) == []


def test_skipped_when_workflow_absent(tmp_path: Path, writer) -> None:
    """main() also runs against partial trees; no workflow means nothing to check."""
    writer(tmp_path / "modules/auth/pyproject.toml", _pkg("simple_module_auth"))
    assert check_release_matrix(tmp_path) == []


def test_real_repo_publishes_every_workspace_package() -> None:
    """The invariant this guard exists for, asserted against the real repo."""
    assert check_release_matrix(REPO_ROOT) == []


def test_real_repo_publishes_site_lock() -> None:
    matrix = parse_publish_matrix(REPO_ROOT / ".github/workflows/release.yml")
    assert "simple_module_site_lock" in matrix
    assert len(matrix) == len(discover_python_packages(REPO_ROOT))
