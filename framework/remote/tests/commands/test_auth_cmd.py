import httpx
from click.testing import CliRunner

SECRET = "pat-secret-123"


def setup_env(cli, *extra, protected=False):
    runner = CliRunner()
    args = ["env", "add", "dev", "--url", "http://localhost:8000", *extra]
    if protected:
        args.append("--protected")
    runner.invoke(cli, args)
    runner.invoke(cli, ["env", "use", "dev"])
    return runner


def test_login_token_stdin_stores_origin_bound(make_cli, keyring_store):
    cli = make_cli()
    runner = setup_env(cli)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 0, result.output
    assert SECRET not in result.output
    assert cli.requests[0].url.path == "/api/_meta/whoami"
    ((_, stored),) = keyring_store.data.items()
    assert SECRET in stored and "http://localhost:8000" in stored


def test_login_prompt_token(make_cli, keyring_store):
    cli = make_cli()
    runner = setup_env(cli)
    result = runner.invoke(cli, ["login", "--token"], input=SECRET + "\n")
    assert result.exit_code == 0, result.output
    assert SECRET not in result.output and len(keyring_store.data) == 1


def test_login_rejects_token_argument(make_cli):
    cli = make_cli()
    runner = setup_env(cli)
    result = runner.invoke(cli, ["login", "--token", SECRET])
    assert result.exit_code == 1
    assert SECRET not in result.output and SECRET not in result.stderr
    assert cli.requests == []
    extra = runner.invoke(cli, ["login", "extra-positional"])
    assert extra.exit_code == 1
    assert "extra-positional" not in extra.output and "extra-positional" not in extra.stderr
    assert cli.requests == []


def test_login_plain_points_to_token_modes(make_cli):
    cli = make_cli()
    result = setup_env(cli).invoke(cli, ["login"])
    assert result.exit_code == 1 and "--token" in result.output


def test_login_rejected_token_not_stored(make_cli, keyring_store):
    cli = make_cli(lambda r: httpx.Response(401, json={"detail": "no"}))
    runner = setup_env(cli)
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 4
    assert keyring_store.data == {} and SECRET not in result.output


def test_login_tenant_mismatch_refused(make_cli, keyring_store):
    cli = make_cli()
    runner = setup_env(cli)
    result = runner.invoke(cli, ["--tenant", "t-2", "login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 1
    assert "t-1" in result.output and keyring_store.data == {}
    ok = runner.invoke(cli, ["--tenant", "t-1", "login", "--token-stdin"], input=SECRET + "\n")
    assert ok.exit_code == 0
    assert next(iter(keyring_store.data))[1] == "dev/t-1"


def test_whoami_protected_banner(make_cli):
    cli = make_cli()
    runner = setup_env(cli, protected=True)
    runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    result = runner.invoke(cli, ["whoami"])
    assert result.exit_code == 0, result.output
    assert "PROTECTED" in result.output
    assert "ada@example.com" in result.output and "dev" in result.output
    assert SECRET not in result.output
    assert cli.requests[-1].headers["Authorization"] == f"Bearer {SECRET}"


def test_logout_removes_token(make_cli, keyring_store):
    cli = make_cli()
    runner = setup_env(cli)
    runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert runner.invoke(cli, ["logout"]).exit_code == 0
    assert keyring_store.data == {}
    assert runner.invoke(cli, ["whoami"]).exit_code == 1


def test_token_not_reused_across_envs(make_cli):
    cli = make_cli()
    runner = setup_env(cli)
    runner.invoke(cli, ["env", "add", "other", "--url", "http://127.0.0.1:9000"])
    runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert runner.invoke(cli, ["whoami"]).exit_code == 0
    before = len(cli.requests)
    result = runner.invoke(cli, ["--env", "other", "whoami"])
    assert result.exit_code == 1
    assert len(cli.requests) == before


def test_env_default_tenant_checked_on_login(make_cli, keyring_store):
    cli = make_cli()
    runner = setup_env(cli, "--tenant", "wrong")
    result = runner.invoke(cli, ["login", "--token-stdin"], input=SECRET + "\n")
    assert result.exit_code == 1 and keyring_store.data == {}


def test_root_usage_error_exits_1(make_cli):
    result = CliRunner().invoke(make_cli(), ["--schema", "live", "whoami"])
    assert result.exit_code == 1
