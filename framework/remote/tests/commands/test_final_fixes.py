"""Regression tests for the final whole-branch review of the engine."""

import json
import os

import httpx
import pytest
from click.testing import CliRunner

TOKEN_HINT = "smdev --env dev login --token"


def logged_in(cli, *, protected=False, extra=()):
    runner = CliRunner()
    args = ["env", "add", "dev", "--url", "http://localhost:8000", *extra]
    runner.invoke(cli, args + (["--protected"] if protected else []))
    runner.invoke(cli, ["env", "use", "dev"])
    runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
    return runner


def test_invalid_output_format_sends_nothing(make_cli):
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


def test_env_add_keeps_protected_and_tenant_of_existing(make_cli, tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(
        '[env.prod]\nurl = "https://app.example"\nprotected = true\ntenant = "acme"\n'
    )
    cli = make_cli()
    cli_state = cli.context_settings["obj"]
    cli_state.defaults_path = defaults
    runner = CliRunner()
    assert (
        runner.invoke(cli, ["env", "add", "prod", "--url", "https://other.example"]).exit_code == 0
    )
    shown = runner.invoke(cli, ["env", "show", "prod"]).output
    assert "protected: yes" in shown and "tenant:    acme" in shown
    assert (
        runner.invoke(
            cli, ["env", "add", "prod", "--url", "https://other.example", "--no-protected"]
        ).exit_code
        == 0
    )
    assert "protected: no" in runner.invoke(cli, ["env", "show", "prod"]).output
    assert "tenant:    acme" in runner.invoke(cli, ["env", "show", "prod"]).output


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_env_add_into_readonly_config_dir_is_clean(make_cli, tmp_path):
    config = tmp_path / "config" / "smdev"
    config.mkdir(parents=True)
    config.chmod(0o500)
    try:
        result = CliRunner().invoke(make_cli(), ["env", "add", "x", "--url", "https://x.example"])
    finally:
        config.chmod(0o700)
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output and "PermissionError" in result.output
    assert str(config) in result.output


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


def test_api_inherits_confirm_from_matched_operation(make_cli, risk_schema):
    cli = make_cli(lambda r: httpx.Response(200, json={}), schema=risk_schema)
    runner = logged_in(cli, protected=True)
    before = len(cli.requests)
    result = runner.invoke(cli, ["api", "GET", "/api/files/42/purge"])
    assert result.exit_code == 1 and "--yes" in result.output
    assert len(cli.requests) == before
    assert runner.invoke(cli, ["api", "GET", "/api/files/42/purge", "--yes"]).exit_code == 0


def test_api_inherits_safe_from_matched_operation(make_cli, risk_schema):
    cli = make_cli(lambda r: httpx.Response(200, json={}), schema=risk_schema)
    runner = logged_in(cli, protected=True)
    assert runner.invoke(cli, ["api", "POST", "/api/jobs/7/poll", "--json", "{}"]).exit_code == 0
    # An unmatched mutation stays guarded.
    assert runner.invoke(cli, ["api", "POST", "/api/other", "--json", "{}"]).exit_code == 1


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


def test_login_usage_and_doctor_hints_say_token(make_cli):
    cli = make_cli(lambda r: httpx.Response(401, json={}))
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    doctor = runner.invoke(cli, ["doctor"]).output
    assert f"fix: {TOKEN_HINT}" in doctor
    fresh = CliRunner().invoke(make_cli(), ["users", "list-users", "--page", "1"], env={})
    assert "login --token`" in fresh.output or "env add" in fresh.output


def test_fresh_machine_hint_says_login_token(make_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    result = CliRunner().invoke(make_cli(), ["whoami"])
    assert result.exit_code == 1 and "login --token`" in result.output


def test_readonly_credential_dir_is_clean_error(tmp_path, fail_keyring):
    from simple_module_remote.config.credentials import (
        CredentialError,
        CredentialStore,
        StoredCredential,
    )

    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    directory = tmp_path / "config" / "smdev"
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o500)
    store = CredentialStore("smdev", backend=fail_keyring)
    try:
        with pytest.raises(CredentialError) as err:
            store.put("k", StoredCredential("tok-secret", "https://x"))
    finally:
        directory.chmod(0o700)
    assert "PermissionError" in str(err.value) and "tok-secret" not in str(err.value)
