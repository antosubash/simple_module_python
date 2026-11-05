"""Scaffolded areas keep imports and wheel source selection usable."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from simple_module_cli.scaffolding import create_module


@pytest.mark.parametrize("variant", ["workspace", "standalone", "framework_repo"])
def test_scaffolded_modules_import_independently(tmp_path: Path, variant: str):
    dest = create_module(
        tmp_path / "probe",
        name="layout_import_probe",
        standalone=variant == "standalone",
        framework_repo=variant == "framework_repo",
    )
    package = dest / "layout_import_probe"
    assert {p.name for p in package.iterdir()} == {
        "__init__.py",
        "py.typed",
        "module.py",
        "models.py",
        "contracts",
        "core",
        "web",
        "pages",
        "locales",
    }
    for area in ("core", "web", "web/endpoints"):
        tree = ast.parse((package / area / "__init__.py").read_text())
        assert len(tree.body) == 1 and ast.get_docstring(tree)
    for source in sorted(package.rglob("*.py")):
        name = ".".join(source.relative_to(dest).with_suffix("").parts)
        if name.endswith(".__init__"):
            name = name.removesuffix(".__init__")
        result = subprocess.run(
            [sys.executable, "-c", f"import {name}"],
            env={**os.environ, "PYTHONPATH": str(dest)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"
    wheel = tomllib.loads((dest / "pyproject.toml").read_text())["tool"]["hatch"]["build"][
        "targets"
    ]["wheel"]
    assert wheel["packages"] == ["layout_import_probe"]
    assert set(wheel["exclude"]) == {
        "**/*.test.*",
        "**/*.spec.*",
        "**/test-dom.tsx",
        "**/page-tests/**",
    }
    import json

    config = json.loads((dest / "tsconfig.json").read_text())
    assert config["include"] == ["layout_import_probe/**/*.ts", "layout_import_probe/**/*.tsx"]
