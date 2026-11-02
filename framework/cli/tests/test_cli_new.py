"""Tests for the `smpy new` / `simple-module new` CLI subcommand."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_cli._env import env_values
from simple_module_cli._local_env import write_local_env
from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_sm_new_generates_pyproject_with_expected_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    pyproject_text = (target / "host" / "pyproject.toml").read_text()
    for required in (
        "simple_module_hosting",
        "simple_module_users",
        "simple_module_dashboard",
        "simple_module_permissions",
    ):
        assert required in pyproject_text, f"missing dep: {required}"


def test_sm_new_generates_package_json_with_npm_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    data = json.loads((target / "host" / "client_app" / "package.json").read_text())
    assert "@simple-module-py/ui" in data.get("dependencies", {})
    assert "@simple-module-py/i18n" in data.get("dependencies", {})
    assert "@simple-module-py/tsconfig" in data.get("devDependencies", {})


def test_sm_new_pins_client_app_simple_module_deps_to_framework_version(tmp_path: Path) -> None:
    from importlib.metadata import version

    expected = version("simple_module_cli")
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    data = json.loads((target / "host" / "client_app" / "package.json").read_text())
    deps = data.get("dependencies", {})
    for pkg in ("@simple-module-py/ui", "@simple-module-py/i18n"):
        assert deps.get(pkg) == expected, (
            f"{pkg} should be pinned to {expected}, got {deps.get(pkg)!r}"
        )


_SECRET_KEYS = (
    "SM_SECRET_KEY",
    "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
    "SM_USERS_VERIFICATION_TOKEN_SECRET",
)


def test_sm_new_writes_generated_secrets_to_gitignored_env(tmp_path: Path) -> None:
    # GH #441: the committed .env.example must not carry real secrets. The
    # users token secrets are needed because UsersSettings refuses its
    # placeholders in production, the mode the compose containers boot in.
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    env = env_values((target / ".env").read_text())
    example_text = (target / ".env.example").read_text()
    example = env_values((target / ".env.example").read_text())
    for key in _SECRET_KEYS:
        assert len(env[key]) >= 20
        assert env[key] not in example_text
        assert key not in example
        assert f"# {key}=" in example_text
    assert ".env" in (target / ".gitignore").read_text().splitlines()
    # Non-secret settings stay in step between the two files.
    assert env["SM_DATABASE_URL"] == example["SM_DATABASE_URL"]


def test_sm_new_keeps_an_existing_env(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\nSM_SECRET_KEY=\n")
    (tmp_path / ".env").write_text("SM_SECRET_KEY=mine\n")
    write_local_env(tmp_path, secret_keys=["SM_SECRET_KEY", "OTHER"])
    env = env_values((tmp_path / ".env").read_text())
    assert env["SM_SECRET_KEY"] == "mine"
    assert len(env["OTHER"]) >= 20


def test_create_app_project_with_selected_kwarg(tmp_path: Path) -> None:
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(
        target,
        name="demo",
        db="sqlite",
        tenancy=False,
        selected=["users", "background_tasks"],
    )

    pyproject = (target / "host" / "pyproject.toml").read_text()
    assert "simple_module_background_tasks" in pyproject
    assert "simple_module_auth" in pyproject  # auto-added (users requires auth)
    assert "simple_module_dashboard" not in pyproject


def test_create_app_project_runs_recipe_for_background_tasks(tmp_path: Path) -> None:
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(
        target,
        name="demo",
        db="sqlite",
        tenancy=False,
        selected=["background_tasks"],
    )

    assert (target / "scripts" / "run_worker.py").is_file()
    assert (target / "docker-compose.yml").is_file()
    assert (target / "docker" / "host.Dockerfile").is_file()
    # worker/beat reuse the app image — no separate worker Dockerfile.
    assert not (target / "docker" / "worker.Dockerfile").exists()
    makefile_text = (target / "Makefile").read_text()
    assert "worker:" in makefile_text


def test_create_app_project_default_selected_keeps_back_compat(tmp_path: Path) -> None:
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False)
    pyproject = (target / "host" / "pyproject.toml").read_text()
    for required in (
        "simple_module_users",
        "simple_module_dashboard",
        "simple_module_permissions",
    ):
        assert required in pyproject


def test_sm_new_with_preset_full_includes_background_tasks(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--preset", "full", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "scripts" / "run_worker.py").is_file()
    assert (target / "docker-compose.yml").is_file()
    pyproject = (target / "host" / "pyproject.toml").read_text()
    assert "simple_module_background_tasks" in pyproject


def test_sm_new_with_explicit_with_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "new",
            "demo",
            "--yes",
            "--preset",
            "minimal",
            "--with",
            "background_tasks",
            "--no-install",
            "--dest",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    pyproject = (target / "host" / "pyproject.toml").read_text()
    assert "simple_module_users" in pyproject
    assert "simple_module_background_tasks" in pyproject
    assert "simple_module_auth" in pyproject


def test_sm_new_unknown_with_module_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--with", "does_not_exist", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "does_not_exist" in result.output
    assert "available" in result.output.lower()


def test_sm_new_yes_with_no_flags_uses_standard_preset(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    pyproject = (target / "host" / "pyproject.toml").read_text()
    for required in (
        "simple_module_users",
        "simple_module_dashboard",
        "simple_module_permissions",
    ):
        assert required in pyproject
    assert "simple_module_background_tasks" not in pyproject


def test_sm_new_interactive_full_preset(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--no-install", "--dest", str(target)],
        input="\n".join(["", "", "3", "", ""]) + "\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "docker-compose.yml").is_file()


def test_sm_new_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "my-app"
    target.mkdir()
    (target / "existing.txt").write_text("x")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "exists" in result.output.lower() or "exists" in (result.stderr or "").lower()


def test_write_local_env_fills_placeholder_on_last_line_without_newline(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\n# SM_SECRET_KEY=")
    write_local_env(tmp_path, secret_keys=["SM_SECRET_KEY"])
    env = env_values((tmp_path / ".env").read_text())
    assert len(env["SM_SECRET_KEY"]) >= 20


def test_write_local_env_keeps_existing_postgres_password_and_url_together(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=kept\n")
    write_local_env(
        tmp_path,
        secret_keys=[],
        overrides={"POSTGRES_PASSWORD": "new", "SM_DATABASE_URL": "postgresql://postgres:new@x/db"},
    )
    assert env_values((tmp_path / ".env").read_text()) == {"POSTGRES_PASSWORD": "kept"}


def test_env_values_ignores_indented_comments_and_strips_key_spacing() -> None:
    text = "  # SM_SECRET_KEY=nope\nA = 1\n# B=2\nC=3\n"
    assert env_values(text) == {"A": " 1", "C": "3"}
