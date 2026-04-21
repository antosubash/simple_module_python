"""Tests for scripts/check_metadata.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_metadata import (
    check_npm_package,
    check_python_package,
    main,
)


def test_python_package_missing_simple_module_keyword(tmp_pkg_dir: Path, writer) -> None:
    pyproject = writer(
        tmp_pkg_dir / "pyproject.toml",
        """
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "A real description"
readme = "README.md"
license = "MIT"
keywords = ["fastapi"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    errors = check_python_package(pyproject)
    assert any("simple-module" in e and "keyword" in e for e in errors)


def test_python_package_placeholder_description_rejected(tmp_pkg_dir: Path, writer) -> None:
    pyproject = writer(
        tmp_pkg_dir / "pyproject.toml",
        """
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "Add your description here"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    errors = check_python_package(pyproject)
    assert any("description" in e.lower() and "placeholder" in e.lower() for e in errors)


def test_python_package_passes_when_valid(tmp_pkg_dir: Path, writer) -> None:
    pyproject = writer(
        tmp_pkg_dir / "pyproject.toml",
        """
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "The foo module — handles foo things"
readme = "README.md"
license = "MIT"
keywords = ["simple-module", "fastapi"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    assert check_python_package(pyproject) == []


def test_npm_package_missing_keyword(tmp_pkg_dir: Path, writer) -> None:
    pkg = writer(
        tmp_pkg_dir / "package.json",
        """{
  "name": "@simple-module-py/foo",
  "version": "0.0.1",
  "description": "Real desc",
  "license": "MIT",
  "keywords": ["react"],
  "repository": "https://github.com/antosubash/simple_module_python",
  "publishConfig": {"access": "public"}
}
""",
    )
    errors = check_npm_package(pkg)
    assert any("simple-module" in e and "keyword" in e for e in errors)


def test_npm_package_private_rejected(tmp_pkg_dir: Path, writer) -> None:
    pkg = writer(
        tmp_pkg_dir / "package.json",
        """{
  "name": "@simple-module-py/foo",
  "version": "0.0.1",
  "description": "Real desc",
  "license": "MIT",
  "keywords": ["simple-module"],
  "private": true,
  "repository": "https://github.com/antosubash/simple_module_python",
  "publishConfig": {"access": "public"}
}
""",
    )
    errors = check_npm_package(pkg)
    assert any("private" in e.lower() for e in errors)


def test_npm_package_publish_config_required(tmp_pkg_dir: Path, writer) -> None:
    pkg = writer(
        tmp_pkg_dir / "package.json",
        """{
  "name": "@simple-module-py/foo",
  "version": "0.0.1",
  "description": "Real desc",
  "license": "MIT",
  "keywords": ["simple-module"],
  "repository": "https://github.com/antosubash/simple_module_python"
}
""",
    )
    errors = check_npm_package(pkg)
    assert any("publishConfig" in e for e in errors)


def test_main_exits_zero_on_clean_repo(tmp_path: Path, monkeypatch, writer) -> None:
    repo = tmp_path
    writer(
        repo / "framework/core/pyproject.toml",
        """
[project]
name = "simple-module-core"
version = "0.0.1"
description = "Core framework"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    writer(
        repo / "packages/ui/package.json",
        """{
  "name": "@simple-module-py/ui",
  "version": "0.0.1",
  "description": "UI",
  "license": "MIT",
  "keywords": ["simple-module"],
  "repository": "https://github.com/antosubash/simple_module_python",
  "publishConfig": {"access": "public"}
}
""",
    )
    monkeypatch.chdir(repo)
    rc = main([])
    assert rc == 0


def test_main_exits_nonzero_on_violation(tmp_path: Path, monkeypatch, writer) -> None:
    repo = tmp_path
    writer(
        repo / "framework/core/pyproject.toml",
        """
[project]
name = "simple-module-core"
version = "0.0.1"
description = "Add your description here"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    monkeypatch.chdir(repo)
    rc = main([])
    assert rc != 0
