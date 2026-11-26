import io
import sys

import httpx
from click.testing import CliRunner


def test_login_stdin_line_is_capped(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input="a" * 10000 + "\n")
    assert result.exit_code == 1 and "longer than 4096" in result.output
    assert cli.requests == []


def test_login_prompt_needs_a_terminal(make_cli, logged_in, monkeypatch):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("tok\n"))
    result = runner.invoke(cli, ["login", "--token"])
    assert result.exit_code == 1 and "--token-stdin" in result.output


def test_login_404_blames_the_url_not_the_token(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(404, json={}))
    result = logged_in(cli, login=False).invoke(cli, ["login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 5 and "check the URL" in result.output


def test_whoami_401_suggests_login(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(401, json={}))
    runner = logged_in(cli, login=False)
    runner.invoke(make_cli(), ["login", "--token-stdin"], input="tok\n")
    result = runner.invoke(cli, ["whoami"])
    assert result.exit_code == 4 and "login --token" in result.output


def test_login_selects_a_configured_environment_when_none_is_current(make_cli):
    runner, cli = CliRunner(), make_cli()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    result = runner.invoke(cli, ["--env", "dev", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0, result.output
    assert "current environment: dev" in result.output
    assert runner.invoke(cli, ["whoami"]).exit_code == 0


def test_login_keeps_an_existing_current_environment(make_cli):
    runner, cli = CliRunner(), make_cli()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "add", "other", "--url", "http://127.0.0.1:9000"])
    runner.invoke(cli, ["env", "use", "other"])
    result = runner.invoke(cli, ["--env", "dev", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0 and "current environment" not in result.output
    # whoami still targets the current environment, which has no login of its own
    assert "for 'other'" in runner.invoke(cli, ["whoami"]).output


def test_login_from_a_one_off_url_environment_saves_no_current(make_cli, monkeypatch):
    monkeypatch.setenv("SMDEV_URL", "http://localhost:8000")
    runner, cli = CliRunner(), make_cli()
    result = runner.invoke(cli, ["--env", "ci", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0 and "current environment" not in result.output
    assert "no environment selected" in runner.invoke(cli, ["whoami"]).output


def test_a_config_that_cannot_be_saved_only_warns_after_login(make_cli, monkeypatch):
    from simple_module_remote.commands import auth_cmd
    from simple_module_remote.config.environments import ConfigError

    def refuse(*_args):
        raise ConfigError("read-only config")

    runner, cli = CliRunner(), make_cli()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    monkeypatch.setattr(auth_cmd, "save_config", refuse)
    result = runner.invoke(cli, ["--env", "dev", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0, result.output
    assert "logged in to dev" in result.output
    assert "warning: dev was not made the current environment: read-only config" in result.output
