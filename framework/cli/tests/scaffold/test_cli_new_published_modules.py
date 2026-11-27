"""Published modules must be selectable with ``smpy new --with`` (#1213)."""

import tomllib

import pytest
from simple_module_cli.cli import app
from typer.testing import CliRunner


@pytest.mark.parametrize(
    ("name", "dependencies"),
    [
        ("oidc", {"auth"}),
        ("audit_log", set()),
        ("keycloak", {"auth"}),
        ("mail", {"settings"}),
        ("sharing", set()),
        ("api_tokens", {"auth"}),
        ("branding", {"settings", "file_storage"}),
    ],
)
def test_new_with_published_module(tmp_path, name, dependencies):
    result = CliRunner().invoke(
        app,
        ["new", "demo", "--yes", "--with", name, "--no-install", "--dest", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    project = tomllib.loads((tmp_path / "host/pyproject.toml").read_text())["project"]
    packages = {dep.split("==")[0] for dep in project["dependencies"]}
    assert {f"simple_module_{key}" for key in {name, *dependencies}} <= packages
