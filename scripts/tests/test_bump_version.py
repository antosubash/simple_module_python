"""Tests for scripts/bump_version.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bump_version import (
    bump_npm_package,
    bump_python_package,
    main,
)

# -------- Python --------

PY_SAMPLE = """\
[project]
name = "simple_module_foo"
version = "0.0.1"
description = "x"
dependencies = [
    "simple_module_core==0.0.1",
    "fastapi>=0.115",
    "simple_module_db==0.0.1",
]
"""


def test_python_bump_updates_version(tmp_pkg_dir: Path, writer) -> None:
    p = writer(tmp_pkg_dir / "pyproject.toml", PY_SAMPLE)
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert 'version = "0.0.2"' in text


def test_python_bump_rewrites_inter_pkg_pins(tmp_pkg_dir: Path, writer) -> None:
    p = writer(tmp_pkg_dir / "pyproject.toml", PY_SAMPLE)
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert '"simple_module_core==0.0.2"' in text
    assert '"simple_module_db==0.0.2"' in text
    assert '"fastapi>=0.115"' in text


def test_python_bump_handles_unpinned_simple_module_dep(tmp_pkg_dir: Path, writer) -> None:
    p = writer(
        tmp_pkg_dir / "pyproject.toml",
        '[project]\nname = "x"\nversion = "0.0.1"\ndependencies = ["simple_module_core"]\n',
    )
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert '"simple_module_core==0.0.2"' in text


# -------- npm --------

NPM_SAMPLE = {
    "name": "@simple-module-py/foo",
    "version": "0.0.1",
    "dependencies": {
        "@simple-module-py/i18n": "0.0.1",
        "react": "^19.0.0",
    },
    "devDependencies": {
        "@simple-module-py/tsconfig": "0.0.1",
    },
    "peerDependencies": {
        "react": "^19.0.0",
    },
}


def test_npm_bump_updates_version_and_inter_pkg(tmp_pkg_dir: Path, writer) -> None:
    p = writer(tmp_pkg_dir / "package.json", json.dumps(NPM_SAMPLE, indent=2) + "\n")
    bump_npm_package(p, "0.0.2")
    data = json.loads(p.read_text())
    assert data["version"] == "0.0.2"
    assert data["dependencies"]["@simple-module-py/i18n"] == "0.0.2"
    assert data["devDependencies"]["@simple-module-py/tsconfig"] == "0.0.2"
    assert data["dependencies"]["react"] == "^19.0.0"
    assert data["peerDependencies"]["react"] == "^19.0.0"


# -------- main() orchestration --------


def _fake_repo(tmp_path: Path, writer) -> Path:
    writer(
        tmp_path / "framework/core/pyproject.toml",
        '[project]\nname = "simple_module_core"\nversion = "0.0.1"\n',
    )
    writer(
        tmp_path / "framework/db/pyproject.toml",
        (
            '[project]\nname = "simple_module_db"\nversion = "0.0.1"\n'
            'dependencies=["simple_module_core==0.0.1"]\n'
        ),
    )
    writer(
        tmp_path / "packages/ui/package.json",
        json.dumps({"name": "@simple-module-py/ui", "version": "0.0.1"}, indent=2) + "\n",
    )
    return tmp_path


def test_main_bumps_all(tmp_path: Path, monkeypatch, writer) -> None:
    _fake_repo(tmp_path, writer)
    monkeypatch.chdir(tmp_path)
    assert main(["0.0.2"]) == 0
    assert 'version = "0.0.2"' in (tmp_path / "framework/core/pyproject.toml").read_text()
    assert 'version = "0.0.2"' in (tmp_path / "framework/db/pyproject.toml").read_text()
    assert '"simple_module_core==0.0.2"' in (tmp_path / "framework/db/pyproject.toml").read_text()
    data = json.loads((tmp_path / "packages/ui/package.json").read_text())
    assert data["version"] == "0.0.2"


def test_main_check_mode_fails_when_out_of_sync(tmp_path: Path, monkeypatch, writer) -> None:
    _fake_repo(tmp_path, writer)
    monkeypatch.chdir(tmp_path)
    assert main(["0.0.2", "--check"]) != 0


def test_main_check_mode_passes_when_in_sync(tmp_path: Path, monkeypatch, writer) -> None:
    _fake_repo(tmp_path, writer)
    monkeypatch.chdir(tmp_path)
    assert main(["0.0.1", "--check"]) == 0


def test_main_rejects_invalid_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["not-a-version"])
