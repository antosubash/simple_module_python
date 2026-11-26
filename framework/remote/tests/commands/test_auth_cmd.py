import os

import httpx
import pytest
from click.testing import CliRunner

SECRET = "pat-secret-123"
WHO = {
    "id": "u",
    "email": "a@b",
    "auth_kind": "pat",
    "scopes": None,
    "tenant_id": None,
    "roles": [],
}


def test_login_token_stdin_stores_origin_bound(make_cli, keyring_store, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 0, result.output
    assert SECRET not in result.output
    assert cli.requests[0].url.path == "/api/_meta/whoami"
    ((_, stored),) = keyring_store.creds.items()
    assert SECRET in stored and "http://localhost:8000" in stored


def test_login_prompt_token(make_cli, keyring_store, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token"], input=SECRET + "\n")
    assert result.exit_code == 0, result.output
    assert SECRET not in result.output and len(keyring_store.creds) == 1


def test_login_rejects_token_argument(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token", SECRET])
    assert result.exit_code == 1
    assert SECRET not in result.output and SECRET not in result.stderr
    assert cli.requests == []
    extra = runner.invoke(cli, ["login", "extra-positional"])
    assert extra.exit_code == 1
    assert "extra-positional" not in extra.output and "extra-positional" not in extra.stderr
    assert cli.requests == []


def test_login_plain_points_to_token_modes(make_cli, logged_in):
    cli = make_cli()
    result = logged_in(cli, login=False).invoke(cli, ["login"])
    assert result.exit_code == 1 and "--token" in result.output


def test_login_rejected_token_not_stored(make_cli, keyring_store, logged_in):
    cli = make_cli(lambda r: httpx.Response(401, json={"detail": "no"}))
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 4
    assert keyring_store.data == {} and SECRET not in result.output


def test_login_tenant_mismatch_refused(make_cli, keyring_store, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["--tenant", "t-2", "login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 1
    assert "t-1" in result.output and keyring_store.data == {}
    ok = runner.invoke(cli, ["--tenant", "t-1", "login", "--token-stdin"], input=SECRET + "\n")
    assert ok.exit_code == 0
    assert next(iter(keyring_store.creds))[1] == "dev/t-1"


def test_whoami_protected_banner(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, protected=True, login=False)
    runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    result = runner.invoke(cli, ["whoami"])
    assert result.exit_code == 0, result.output
    assert "PROTECTED" in result.output
    assert "ada@example.com" in result.output and "dev" in result.output
    assert SECRET not in result.output
    assert cli.requests[-1].headers["Authorization"] == f"Bearer {SECRET}"


def test_logout_removes_token(make_cli, keyring_store, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert runner.invoke(cli, ["logout"]).exit_code == 0
    assert keyring_store.data == {}
    assert runner.invoke(cli, ["whoami"]).exit_code == 1


def test_token_not_reused_across_envs(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    runner.invoke(cli, ["env", "add", "other", "--url", "http://127.0.0.1:9000"])
    runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert runner.invoke(cli, ["whoami"]).exit_code == 0
    before = len(cli.requests)
    result = runner.invoke(cli, ["--env", "other", "whoami"])
    assert result.exit_code == 1
    assert len(cli.requests) == before


def test_env_default_tenant_checked_on_login(make_cli, keyring_store, logged_in):
    cli = make_cli()
    runner = logged_in(cli, extra=("--tenant", "wrong"), login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 1 and keyring_store.data == {}


def test_root_usage_error_exits_1(make_cli):
    result = CliRunner().invoke(make_cli(), ["--schema", "live", "whoami"])
    assert result.exit_code == 1


def test_login_both_flags_has_specific_message(make_cli):
    cli = make_cli()
    result = CliRunner().invoke(cli, ["login", "--token", "--token-stdin"])
    assert result.exit_code == 1
    assert "choose one of --token and --token-stdin" in result.output


def test_login_unreachable_server_is_connection_failure(make_cli):
    def boom(req):
        raise httpx.ConnectError("down")

    cli = make_cli(boom)
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    result = runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 3, result.output
    assert "cannot reach dev" in result.output and "not accepted" not in result.output


def test_fresh_machine_hint_says_login_token(make_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    result = CliRunner().invoke(make_cli(), ["whoami"])
    assert result.exit_code == 1 and "login --token`" in result.output


def test_login_refuses_a_redirected_identity_check(make_cli, keyring_store, logged_in):
    def handler(req):
        return httpx.Response(302, headers={"Location": "https://elsewhere.example/who"})

    cli = make_cli(handler)
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code != 0 and keyring_store.data == {}
    assert len(cli.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"ok": True},
        {"id": "u", "email": "a@b"},
        {"id": 1},
        [],
        {**WHO, "scopes": "all"},
        {**WHO, "scopes": [1]},
        {**WHO, "tenant_id": 5},
        {**WHO, "roles": "admin"},
        {k: v for k, v in WHO.items() if k != "roles"},
        {k: v for k, v in WHO.items() if k != "scopes"},
        {k: v for k, v in WHO.items() if k != "tenant_id"},
    ],
)
def test_login_refuses_a_reply_that_is_not_an_identity(make_cli, keyring_store, logged_in, body):
    cli = make_cli(lambda r: httpx.Response(200, json=body))
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code != 0 and keyring_store.data == {}


def test_env_token_works_without_a_secure_file_store(make_cli, fail_keyring, monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW")
    cli = make_cli(lambda r: httpx.Response(200, json=WHO), backend=fail_keyring)
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    env = {"SMDEV_ENV": "dev", "SMDEV_TOKEN": "tok"}
    result = runner.invoke(cli, ["whoami"], env=env)
    assert result.exit_code == 0, result.output
    assert cli.requests[-1].headers["Authorization"] == "Bearer tok"
    stored = runner.invoke(cli, ["--env", "dev", "whoami"])
    assert stored.exit_code == 1 and "no secure file credential store" in stored.output


@pytest.mark.parametrize("bad", ["tok en", "tok\x01en", "tök", "tok\x7fen"])
@pytest.mark.parametrize("mode", ["--token-stdin", "--token"])
def test_login_refuses_malformed_token_without_network(make_cli, logged_in, mode, bad):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", mode], input=bad + "\n")
    assert result.exit_code == 1
    assert "not a valid token" in result.output
    assert bad not in result.output
    assert cli.requests == []


def test_env_token_malformed_is_a_clean_error(make_cli, logged_in, monkeypatch):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    monkeypatch.setenv("SMDEV_ENV", "dev")
    monkeypatch.setenv("SMDEV_TOKEN", "bad token")
    result = runner.invoke(cli, ["whoami"])
    assert result.exit_code == 1 and "SMDEV_TOKEN is not a valid token" in result.output
    assert "bad token" not in result.output and cli.requests == []


def test_ci_env_from_url_and_token_variables(make_cli):
    cli = make_cli()
    env = {"SMDEV_ENV": "ci", "SMDEV_URL": "http://localhost:8000", "SMDEV_TOKEN": SECRET}
    result = CliRunner().invoke(cli, ["whoami"], env=env)
    assert result.exit_code == 0, result.output
    assert cli.requests[0].url == "http://localhost:8000/api/_meta/whoami"
    assert cli.requests[0].headers["Authorization"] == f"Bearer {SECRET}"
