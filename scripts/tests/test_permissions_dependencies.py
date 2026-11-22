"""The permissions wheel declares imports that workspace installs can hide (#1085)."""

import tomllib
from pathlib import Path

from packaging.requirements import Requirement


def test_permissions_runtime_dependencies():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "modules/permissions/pyproject.toml").read_text())
    deps = {req.name: req.specifier for req in map(Requirement, project["project"]["dependencies"])}
    assert str(deps["fastapi-users-db-sqlalchemy"]) == "<8,>=7"
    assert str(deps["simple_module_auth"]) == f"=={project['project']['version']}"
    assert project["tool"]["uv"]["sources"]["simple_module_auth"] == {"workspace": True}
