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


def test_python_bump_rewrites_optional_dependency_pins(tmp_pkg_dir: Path, writer) -> None:
    p = writer(
        tmp_pkg_dir / "pyproject.toml",
        '[project]\nname = "x"\nversion = "0.0.1"\n'
        "[project.optional-dependencies]\n"
        'tasks = ["simple_module_background_tasks==0.0.1", "celery>=5"]\n',
    )
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert '"simple_module_background_tasks==0.0.2"' in text
    assert '"celery>=5"' in text
    assert bump_python_package(p, "0.0.2", check=True)


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


@pytest.mark.parametrize(
    ("version", "npm_version"),
    [
        ("0.2.0rc1", "0.2.0-rc.1"),
        ("0.2.0a2", "0.2.0-alpha.2"),
        ("0.2.0-beta3", "0.2.0-beta.3"),
        ("0.2.0.rc", "0.2.0-rc.0"),
    ],
)
def test_prerelease_versions_and_pins_use_npm_semver(tmp_path, writer, version, npm_version):
    root = _fake_repo(tmp_path, writer)
    package = writer(root / "packages/ui/package.json", json.dumps(NPM_SAMPLE))
    assert main([version, "--root", str(root)]) == 0
    data = json.loads(package.read_text())
    assert data["version"] == npm_version
    assert data["dependencies"]["@simple-module-py/i18n"] == npm_version
    assert data["devDependencies"]["@simple-module-py/tsconfig"] == npm_version
    assert f'version = "{version}"' in (root / "framework/core/pyproject.toml").read_text()
    assert main([version, "--root", str(root), "--check"]) == 0


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


def test_discover_includes_module_package_json(tmp_path: Path, writer) -> None:
    from scripts.bump_version import discover

    writer(tmp_path / "modules/foo/pyproject.toml", PY_SAMPLE)
    writer(tmp_path / "modules/foo/package.json", '{"name": "@simple-module-py/foo"}')
    writer(tmp_path / "packages/ui/package.json", '{"name": "@simple-module-py/ui"}')
    _, npm = discover(tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in npm] == [
        "modules/foo/package.json",
        "packages/ui/package.json",
    ]


def test_npm_bump_keeps_wildcard_only_for_private_packages(tmp_path: Path, writer) -> None:
    private = tmp_path / "private.json"
    public = tmp_path / "public.json"
    body = '"version": "0.0.1", "peerDependencies": {"@simple-module-py/ui": "*"}'
    writer(private, '{"private": true, ' + body + "}")
    writer(public, "{" + body + "}")
    bump_npm_package(private, "0.0.2")
    bump_npm_package(public, "0.0.2")
    assert json.loads(private.read_text())["peerDependencies"]["@simple-module-py/ui"] == "*"
    assert json.loads(public.read_text())["peerDependencies"]["@simple-module-py/ui"] == "0.0.2"
