import click
import httpx
import pytest
from click.testing import CliRunner
from simple_module_remote import build_cli
from simple_module_remote.generate.tree import TreeError


def names(group: click.Group) -> set[str]:
    return set(group.commands)


def test_generated_groups_and_raw_mirror(make_cli):
    cli = make_cli()
    assert {"users", "file-storage", "feature-flags", "host"} <= names(cli)
    raw = cli.commands["raw"]
    assert {"users", "file-storage", "feature-flags", "host"} <= names(raw)
    assert names(raw.commands["users"]) == names(cli.commands["users"])
    assert "list-users" in names(cli.commands["users"])


def test_session_only_ops_hidden_and_listed(make_cli):
    cli = make_cli()
    assert "session" not in names(cli.commands["users"])
    result = CliRunner().invoke(cli, ["api", "--session-only"])
    assert result.exit_code == 0
    assert "GET /api/session users_session" in result.output
    assert "users_list_users" not in result.output


def test_build_fails_on_collision(mini_path):
    with pytest.raises(TreeError, match="collision"):
        build_cli("smdev", mini_path)


def test_help_lists_groups(make_cli):
    result = CliRunner().invoke(make_cli(), ["--help"])
    assert result.exit_code == 0
    for word in ("users", "env", "login", "doctor", "raw", "api", "schema", "whoami"):
        assert word in result.output


def test_no_env_or_yes_envvar(make_cli, monkeypatch):
    cli = make_cli()
    assert cli.context_settings.get("auto_envvar_prefix") is None
    monkeypatch.setenv("SMDEV_YES", "1")
    for group in (cli.commands["users"],):
        for cmd in group.commands.values():
            for param in cmd.params:
                assert getattr(param, "envvar", None) is None
    for param in cli.params:
        assert getattr(param, "envvar", None) is None


def test_fresh_machine_hint(make_cli):
    result = CliRunner().invoke(make_cli(), ["users", "list-users", "--page", "1"])
    assert result.exit_code == 1
    assert "env use" in result.output and "login" in result.output
    assert make_cli().requests == []


def test_generated_command_runs_with_stored_token(make_cli):

    def handler(req):
        body = {"email": "a@b"} if req.url.path.endswith("whoami") else [{"id": 1}]
        return httpx.Response(200, json=body)

    cli = make_cli(handler)
    runner = CliRunner()
    assert (
        runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"]).exit_code == 0
    )
    assert runner.invoke(cli, ["env", "use", "dev"]).exit_code == 0
    assert runner.invoke(cli, ["login", "--token-stdin"], input="tok\n").exit_code == 0
    result = runner.invoke(cli, ["users", "list-users", "--page", "2", "-o", "json"])
    assert result.exit_code == 0, result.output
    sent = cli.requests[-1]
    assert sent.url.path == "/api/users" and sent.headers["Authorization"] == "Bearer tok"
    assert sent.headers["User-Agent"].startswith("smdev/1.2 simple_module_remote/")
