import httpx
from click.testing import CliRunner


def logged_in(cli, *, protected=False):
    runner = CliRunner()
    args = ["env", "add", "dev", "--url", "http://localhost:8000"]
    runner.invoke(cli, args + (["--protected"] if protected else []))
    runner.invoke(cli, ["env", "use", "dev"])
    runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
    return runner


def test_api_get_with_query(make_cli):
    cli = make_cli(lambda r: httpx.Response(200, json={"ok": True}))
    runner = logged_in(cli)
    result = runner.invoke(cli, ["api", "get", "/api/things", "--query", "a=1", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert cli.requests[-1].url.query == b"a=1"


def test_api_escape_hatch_rejects_unsafe_path(make_cli):
    cli = make_cli()
    runner = logged_in(cli)
    before = len(cli.requests)
    for bad in ("/health", "https://evil.example/api/x", "/api/../x", "/api//x", "/api/a@b"):
        result = runner.invoke(cli, ["api", "GET", bad])
        assert result.exit_code == 1, bad
    assert len(cli.requests) == before


def test_api_protected_needs_yes(make_cli):
    cli = make_cli(lambda r: httpx.Response(200, json={}))
    runner = logged_in(cli, protected=True)
    before = len(cli.requests)
    result = runner.invoke(cli, ["api", "POST", "/api/x", "--json", "{}"])
    assert result.exit_code == 1 and "--yes" in result.output
    assert len(cli.requests) == before
    assert runner.invoke(cli, ["api", "POST", "/api/x", "--json", "{}", "--yes"]).exit_code == 0


def test_yes_is_not_read_from_environment(make_cli):
    cli = make_cli(lambda r: httpx.Response(200, json={}))
    runner = logged_in(cli, protected=True)
    result = runner.invoke(cli, ["api", "POST", "/api/x", "--json", "{}"], env={"SMDEV_YES": "1"})
    assert result.exit_code == 1


def test_api_bad_method_and_missing_args(make_cli):
    cli = make_cli()
    runner = logged_in(cli)
    assert runner.invoke(cli, ["api", "TRACE", "/api/x"]).exit_code == 1
    assert runner.invoke(cli, ["api"]).exit_code == 1


def test_api_get_rejects_body_flags(make_cli):
    cli = make_cli()
    runner = logged_in(cli)
    before = len(cli.requests)
    for flags in (["--json", "{}"], ["--set", "a=1"]):
        assert runner.invoke(cli, ["api", "GET", "/api/x", *flags]).exit_code == 1
    assert len(cli.requests) == before
