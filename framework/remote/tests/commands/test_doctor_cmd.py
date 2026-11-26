import httpx
from click.testing import CliRunner


def test_doctor_reports_failures(make_cli):
    cli = make_cli(lambda r: httpx.Response(401, json={}))
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 1
    assert "ok    environment" in result.output
    assert "ok    reachable: server answered HTTP 401" in result.output
    assert "FAIL  credentials" in result.output and "fix:" in result.output
    assert "ok    schema" in result.output and "9.9" in result.output
    assert all(req.url.path == "/api/_meta/whoami" for req in cli.requests)


def test_doctor_no_environment(make_cli):
    result = CliRunner().invoke(make_cli(), ["doctor"])
    assert result.exit_code == 1 and "FAIL  environment" in result.output


def test_doctor_all_ok(make_cli):
    cli = make_cli()
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
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
