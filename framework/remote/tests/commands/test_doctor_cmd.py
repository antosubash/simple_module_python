import httpx
from click.testing import CliRunner


def test_doctor_reports_failures(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(401, json={}))
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 1
    assert "ok    environment" in result.output
    assert "ok    reachable (auth required): server answered HTTP 401" in result.output
    assert "FAIL  credentials" in result.output and "fix:" in result.output
    assert "ok    schema" in result.output and "9.9" in result.output
    assert all(req.url.path == "/api/_meta/whoami" for req in cli.requests)


def test_doctor_no_environment(make_cli):
    result = CliRunner().invoke(make_cli(), ["doctor"])
    assert result.exit_code == 1 and "FAIL  environment" in result.output
    assert "fix: smdev env add <name> --url URL" in result.output


def test_doctor_points_at_the_builtin_local_env(make_cli, tmp_path):
    cli = make_cli()
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[env.local]\nurl = "http://localhost:8000"\n')
    cli.context_settings["obj"].defaults_path = defaults
    result = CliRunner().invoke(cli, ["doctor"])
    assert "fix: smdev env use local  (known: local)" in result.output


def test_doctor_credentials_fix_says_where_to_get_a_token(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    out = runner.invoke(cli, ["doctor"]).output
    assert "http://localhost:8000/api-tokens/" in out and "--token-stdin" in out


def test_doctor_ignored_token_variable_points_at_env(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    out = runner.invoke(cli, ["doctor"], env={"SMDEV_TOKEN": "tok"}).output
    assert "pass --env dev or set SMDEV_ENV=dev" in out
    assert "login --token" not in out.split("fix:")[-1]


def test_doctor_all_ok(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli)
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "FAIL" not in result.output and "ok    whoami: ada@example.com" in result.output


def test_schema_status(make_cli):
    result = CliRunner().invoke(make_cli(), ["schema", "status"])
    assert result.exit_code == 0
    assert "bundled" in result.output and "9.9" in result.output
    fingerprint = next(ln for ln in result.output.splitlines() if ln.startswith("fingerprint"))
    assert len(fingerprint.split()[-1]) == 12


def test_doctor_names_token_env_var(make_cli):
    cli = make_cli()
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    env = {"SMDEV_ENV": "dev", "SMDEV_TOKEN": "tok"}
    result = runner.invoke(cli, ["doctor"], env=env)
    assert "token from SMDEV_TOKEN" in result.output


TOKEN_HINT = "smdev --env dev login --token"


def test_login_usage_and_doctor_hints_say_token(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(401, json={}))
    runner = logged_in(cli, login=False)
    doctor = runner.invoke(cli, ["doctor"]).output
    assert f"then {TOKEN_HINT}" in doctor
    fresh = CliRunner().invoke(make_cli(), ["users", "list-users", "--page", "1"], env={})
    assert "login --token`" in fresh.output or "env add" in fresh.output


def test_doctor_unreachable_server_does_not_blame_the_token(make_cli, logged_in):
    def boom(req):
        raise httpx.ConnectError("down")

    runner = logged_in(make_cli(), login=True)
    cli = make_cli(boom)
    out = runner.invoke(cli, ["doctor"]).output
    assert "check the URL, your network and VPN" in out.split("FAIL  whoami")[-1]


def test_doctor_tenant_line_matches_whoami(make_cli, logged_in):
    cli = make_cli()
    out = logged_in(cli).invoke(cli, ["doctor"]).output
    assert "ok    tenant: token tenant t-1" in out


def test_doctor_loose_credentials_file_fix_is_the_chmod(make_cli, fail_keyring, tmp_path):
    cli = make_cli(backend=fail_keyring)
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
    creds = tmp_path / "config" / "smdev" / "credentials.toml"
    creds.chmod(0o644)
    out = runner.invoke(cli, ["doctor"]).output
    assert f"fix: chmod 600 {creds}" in out
