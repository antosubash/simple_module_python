import json

import httpx
import pytest
from click.testing import CliRunner


def test_api_get_with_query(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={"ok": True}))
    runner = logged_in(cli)
    result = runner.invoke(cli, ["api", "get", "/api/things", "--query", "a=1", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert cli.requests[-1].url.query == b"a=1"


def test_api_escape_hatch_rejects_unsafe_path(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli)
    before = len(cli.requests)
    for bad in ("/health", "https://evil.example/api/x", "/api/../x", "/api//x", "/api/a@b"):
        result = runner.invoke(cli, ["api", "GET", bad])
        assert result.exit_code == 1, bad
    assert len(cli.requests) == before


def test_api_protected_needs_yes(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={}))
    runner = logged_in(cli, protected=True)
    before = len(cli.requests)
    result = runner.invoke(cli, ["api", "POST", "/api/x", "--json", "{}"])
    assert result.exit_code == 1 and "--yes" in result.output
    assert len(cli.requests) == before
    assert runner.invoke(cli, ["api", "POST", "/api/x", "--json", "{}", "--yes"]).exit_code == 0


def test_yes_is_not_read_from_environment(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={}))
    runner = logged_in(cli, protected=True)
    result = runner.invoke(cli, ["api", "POST", "/api/x", "--json", "{}"], env={"SMDEV_YES": "1"})
    assert result.exit_code == 1


def test_api_bad_method_and_missing_args(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli)
    assert runner.invoke(cli, ["api", "TRACE", "/api/x"]).exit_code == 1
    assert runner.invoke(cli, ["api"]).exit_code == 1


def test_api_get_rejects_body_flags(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli)
    before = len(cli.requests)
    for flags in (["--json", "{}"], ["--set", "a=1"]):
        assert runner.invoke(cli, ["api", "GET", "/api/x", *flags]).exit_code == 1
    assert len(cli.requests) == before


def test_invalid_output_format_sends_nothing(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json=[]))
    runner = logged_in(cli)
    before = len(cli.requests)
    for args in (
        ["users", "list-users", "--page", "1", "-o", "bogus"],
        ["api", "GET", "/api/x", "-o", "bogus"],
    ):
        result = runner.invoke(cli, args)
        assert result.exit_code == 1, result.output
        assert "bogus" in result.output
    assert len(cli.requests) == before


TOKEN_HINT = "smdev --env dev login --token"


ENV_TOKEN = {"SMDEV_ENV": "dev", "SMDEV_TOKEN": "tok"}


def test_unauthorized_response_prints_login_hint(make_cli):
    cli = make_cli(lambda r: httpx.Response(401, json={"detail": "no"}))
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    for args in (["users", "list-users", "--page", "1"], ["api", "GET", "/api/x"]):
        result = runner.invoke(cli, args, env=ENV_TOKEN)
        assert result.exit_code == 4, result.output
        assert TOKEN_HINT in result.output


def test_api_forbidden_with_tenant_hint_names_tenant(make_cli):
    cli = make_cli(lambda r: httpx.Response(403, json={}))
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    result = runner.invoke(cli, ["--tenant", "t-1", "api", "GET", "/api/x"], env=ENV_TOKEN)
    assert result.exit_code == 4
    assert "smdev --env dev --tenant t-1 login --token" in result.output


@pytest.fixture
def risk_schema(clean_schema):
    data = json.loads(clean_schema.read_text())
    data["paths"]["/api/files/{file_id}/purge"] = {
        "get": {"tags": ["Files"], "operationId": "files_purge", "x-sm-token": True,
                "x-cli-confirm": True,
                "parameters": [{"name": "file_id", "in": "path", "required": True,
                                "schema": {"type": "string"}}]}
    }  # fmt: skip
    data["paths"]["/api/jobs/{job_id}/poll"] = {
        "post": {"tags": ["Jobs"], "operationId": "jobs_poll", "x-sm-token": True,
                 "x-cli-safe": True,
                 "parameters": [{"name": "job_id", "in": "path", "required": True,
                                 "schema": {"type": "string"}}]}
    }  # fmt: skip
    clean_schema.write_text(json.dumps(data))
    return clean_schema


def test_api_inherits_confirm_from_matched_operation(make_cli, risk_schema, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={}), schema=risk_schema)
    runner = logged_in(cli, protected=True)
    before = len(cli.requests)
    result = runner.invoke(cli, ["api", "GET", "/api/files/42/purge"])
    assert result.exit_code == 1 and "--yes" in result.output
    assert len(cli.requests) == before
    assert runner.invoke(cli, ["api", "GET", "/api/files/42/purge", "--yes"]).exit_code == 0


def test_api_inherits_safe_from_matched_operation(make_cli, risk_schema, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={}), schema=risk_schema)
    runner = logged_in(cli, protected=True)
    assert runner.invoke(cli, ["api", "POST", "/api/jobs/7/poll", "--json", "{}"]).exit_code == 0
    # An unmatched mutation stays guarded.
    assert runner.invoke(cli, ["api", "POST", "/api/other", "--json", "{}"]).exit_code == 1


def test_encoded_path_alias_still_needs_confirmation(make_cli, risk_schema, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={}), schema=risk_schema)
    runner = logged_in(cli, protected=True)
    before = len(cli.requests)
    result = runner.invoke(cli, ["api", "GET", "/api/files/42/%70urge"])
    assert result.exit_code == 1 and "--yes" in result.output
    assert len(cli.requests) == before


def test_yes_ignored_even_with_click_auto_envvar(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(200, json={}))
    runner = logged_in(cli, protected=True)
    before = len(cli.requests)
    env = {"SMDEV_API_YES": "1", "SMDEV_USERS_CREATE_USER_YES": "1"}
    api = runner.invoke(
        cli, ["api", "POST", "/api/x", "--json", "{}"], env=env, auto_envvar_prefix="SMDEV"
    )
    gen = runner.invoke(
        cli, ["users", "create-user", "--set", "email=a@b"], env=env, auto_envvar_prefix="SMDEV"
    )
    assert api.exit_code == 1 and gen.exit_code == 1
    assert len(cli.requests) == before


def test_no_active_organisation_is_a_tenant_reason(make_cli, logged_in):
    cli = make_cli(
        lambda r: httpx.Response(403, json={"detail": "No active organisation for this request"})
    )
    runner = logged_in(cli)
    result = runner.invoke(cli, ["api", "GET", "/api/settings/current"])
    assert "the server needs a tenant" in result.output and "login" not in result.output


@pytest.mark.parametrize("flag", ["--body-file"])
def test_missing_body_file_names_file_and_reason(make_cli, logged_in, flag):
    cli = make_cli()
    runner = logged_in(cli)
    result = runner.invoke(cli, ["file-storage", "put-raw", flag, "/nonexistent/part.bin", "--yes"])
    assert "/nonexistent/part.bin" in result.output and "no such file or directory" in result.output
    assert "FileNotFoundError" not in result.output


def test_api_on_a_session_only_route_gives_the_session_hint_whatever_the_wording(
    make_cli, logged_in
):
    cli = make_cli(lambda r: httpx.Response(403, json={"detail": "Permission required: x.y"}))
    runner = logged_in(cli)
    result = runner.invoke(cli, ["api", "GET", "/api/session"])  # a session-only schema route
    assert result.exit_code == 4 and "--session-only" in result.output
    other = runner.invoke(cli, ["api", "GET", "/api/unknown"])
    assert "--session-only" not in other.output  # unmatched paths keep the wording rules
