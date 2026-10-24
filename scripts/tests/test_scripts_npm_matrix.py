"""npm release matrix must track the packages actually packed (#629)."""

import json
from pathlib import Path

import pytest

from scripts.check_metadata import main


@pytest.mark.parametrize("entries", ["[ui]", "\n          - ui"])
@pytest.mark.parametrize("problem", ["missing", "stale", "aligned", "malformed"])
def test_npm_matrix_completeness(tmp_path, writer, capsys, entries, problem):
    writer(
        tmp_path / "packages/ui/package.json",
        json.dumps(
            {
                "name": "@simple-module-py/ui",
                "description": "UI components",
                "license": "MIT",
                "keywords": ["simple-module"],
                "repository": "repo",
                "publishConfig": {"access": "public"},
            }
        ),
    )
    writer(
        tmp_path / "framework/core/pyproject.toml",
        """[project]
name = "simple_module_core"
description = "Framework core"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]
[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    if problem == "missing":
        entries = "[other]"
    elif problem == "stale":
        entries = "[ui, removed]"
    elif problem == "malformed":
        entries = "null"
    writer(
        tmp_path / ".github/workflows/release.yml",
        f"""jobs:
  publish-pypi:
    strategy:
      matrix:
        package:
          - simple_module_core
  publish-npm:
    strategy:
      matrix:
        package: {entries}
""",
    )
    assert main(["--root", str(tmp_path)]) == (0 if problem == "aligned" else 1)
    if problem != "aligned":
        assert "publish-npm" in capsys.readouterr().err


def test_real_npm_matrix_is_complete():
    assert main(["--root", str(Path(__file__).resolve().parents[2])]) == 0
